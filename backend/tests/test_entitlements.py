import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import AccountPlan, AIUsage, PlanAudit, UsageReservation, User
from app.schemas.plans import PlanLimits
from app.services import ai_usage, entitlements as service, account_data, interview_service, interview_voice, profile_suggestion_service, job_fit_service, application_pack_service
from app.services.ai_provider import ProviderFailure
from app.services.application_pack_service import PackError
from test_email_applications import settings as mailbox_settings
from test_interviews import settings as interview_settings, sources, begin, advance

PASSWORD='synthetic-admin-password'


def test_plan_configuration_fails_closed():
    from pydantic import ValidationError
    from app.core.config import Settings
    synthetic = dict(_env_file=None, POSTGRES_USER='synthetic', POSTGRES_PASSWORD='synthetic')
    for invalid in [{'total': -1}, {'pack': 10001}, {'paid_access': True}, {'fit': '20'}]:
        with pytest.raises(ValidationError):
            PlanLimits(**invalid)
    with pytest.raises(ValidationError):
        Settings(**synthetic, JOBPILOT_PLAN_LIMITS={'free': {}})
    configured = Settings(**synthetic, JOBPILOT_PLAN_ADMIN_EMAILS=' ADMIN@example.com ')
    assert configured.JOBPILOT_PLAN_ADMIN_EMAILS == ['admin@example.com']
    assert configured.JOBPILOT_PROPOSED_MONTHLY_PRICE_USD == 8


@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',lambda *a,**k:pytest.fail('No live providers'))


@pytest.fixture
def settings(interview_settings):
    return interview_settings.model_copy(update={'JOBPILOT_VOICE_ENABLED':True,'JOBPILOT_VOICE_TEST_PROVIDER':True})


@pytest.fixture
def data(db_session,settings):
    data=sources(db_session,settings)
    data.owner.password_hash=hash_password(PASSWORD);db_session.commit()
    return data


def configured(settings,**limits):
    return settings.model_copy(update={'JOBPILOT_PLAN_LIMITS':{**settings.JOBPILOT_PLAN_LIMITS,'free':PlanLimits(**limits)}})


def charge(db,owner,settings,feature='profile'):
    token=ai_usage.reserve(db,owner,settings,feature=feature);db.commit()
    ai_usage.release(db,owner,token);db.commit()
    return token


def grant(db,data,settings,**changes):
    args=dict(email=data.owner.email,password=PASSWORD,owner=data.other.id,action='grant',hours=24,reason='evaluation',request_key=uuid.uuid4())
    args.update(changes)
    return service.administer(db,settings.model_copy(update={'JOBPILOT_PLAN_ADMIN_EMAILS':[data.owner.email]}),**args)


def test_shared_ledger_units_and_feature_bypass(db_session,data,settings):
    settings=configured(settings,total=6,profile=1,speech=0)
    for feature in ['profile','fit','pack','interview','transcription']:charge(db_session,data.owner.id,settings,feature)
    usage=service.snapshot(db_session,data.owner.id,settings)
    assert usage['total']=={'allowance':6,'consumed':5,'remaining':1}
    assert usage['features']['profile']['state']=='exhausted'
    assert usage['features']['speech']['state']=='not_in_plan'
    assert db_session.get(AIUsage,data.owner.id).requests==5
    for feature,code in [('profile',429),('speech',403),('paid',422),(None,422)]:
        with pytest.raises(ai_usage.AIUsageError) as error:ai_usage.reserve(db_session,data.owner.id,settings,feature=feature)
        assert error.value.status_code==code
        db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(UsageReservation).where(UsageReservation.owner_id==data.owner.id))==5


def test_utc_boundaries_and_no_result_deletion_refund(db_session,data,settings,monkeypatch):
    settings=configured(settings,total=1)
    before=datetime(2028,2,29,23,59,59,tzinfo=timezone.utc)
    monkeypatch.setattr(service,'now',lambda:before)
    charge(db_session,data.owner.id,settings)
    with pytest.raises(ai_usage.AIUsageError):charge(db_session,data.owner.id,settings)
    db_session.rollback()
    after=before+timedelta(seconds=1);monkeypatch.setattr(service,'now',lambda:after)
    snapshot=service.snapshot(db_session,data.owner.id,settings)
    assert snapshot['total']['remaining']==1 and snapshot['reset_at']==datetime(2028,4,1,tzinfo=timezone.utc)
    charge(db_session,data.owner.id,settings)
    assert db_session.get(AIUsage,data.owner.id).requests==2
    # Different local offsets identifying the same instant use the same bucket.
    assert service.period(after.astimezone(timezone(timedelta(hours=3))))==service.period(after)
    assert service.period(datetime(2028,12,31,tzinfo=timezone.utc))[1].year==2029


def test_beta_expiry_revocation_auth_and_idempotency(db_session,data,settings,monkeypatch):
    start=datetime(2028,1,1,tzinfo=timezone.utc);monkeypatch.setattr(service,'now',lambda:start)
    key=uuid.uuid4();audit=grant(db_session,data,settings,request_key=key)
    assert grant(db_session,data,settings,request_key=key).id==audit.id
    assert service.snapshot(db_session,data.other.id,settings)['plan']=='invited_beta'
    charge(db_session,data.other.id,settings,'fit')
    monkeypatch.setattr(service,'now',lambda:start+timedelta(hours=24))
    assert service.snapshot(db_session,data.other.id,settings)['plan']=='free'
    assert service.snapshot(db_session,data.other.id,settings)['total']['consumed']==1
    grant(db_session,data,settings,hours=1)
    grant(db_session,data,settings,action='revoke',hours=0)
    assert service.snapshot(db_session,data.other.id,settings)['plan']=='free'
    assert db_session.scalar(select(func.count()).select_from(PlanAudit).where(PlanAudit.owner_id==data.other.id))==3
    with pytest.raises(service.EntitlementError):grant(db_session,data,settings,hours=2161)
    db_session.rollback()
    with pytest.raises(service.EntitlementError):grant(db_session,data,settings,password='wrong')
    db_session.rollback()
    with pytest.raises(service.EntitlementError):service.administer(db_session,settings,email=data.owner.email,password=PASSWORD,owner=data.other.id,action='grant',hours=1,reason='support',request_key=uuid.uuid4())
    db_session.rollback()
    with pytest.raises(service.EntitlementError):grant(db_session,data,settings,action='paid')


def test_continuity_does_not_expire_and_paid_assignment_rejected(db_session,data,settings,monkeypatch):
    db_session.add(AccountPlan(owner_id=data.other.id,base_plan='legacy'));db_session.commit()
    before=service.snapshot(db_session,data.other.id,settings)
    assert before['plan']=='legacy' and before['total']['allowance']==60
    grant(db_session,data,settings,hours=1)
    monkeypatch.setattr(service,'now',lambda:datetime.now(timezone.utc)+timedelta(days=91))
    assert service.snapshot(db_session,data.other.id,settings)['plan']=='legacy'
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.get(AccountPlan,data.other.id).base_plan='paid';db_session.flush()


def test_owner_scoped_usage_api_and_unmetered_data(client,db_session,data,settings):
    settings=configured(settings,total=1)
    charge(db_session,data.owner.id,settings)
    client.app.dependency_overrides[get_db]=lambda:db_session
    client.app.dependency_overrides[get_settings]=lambda:settings
    headers=lambda user:{'Authorization':'Bearer '+create_access_token(user.id)}
    try:
        assert client.get('/api/account/usage').status_code==401
        own=client.get('/api/account/usage?owner_id='+str(data.other.id),headers=headers(data.owner))
        assert own.status_code==200 and own.json()['total']['remaining']==0
        assert own.headers['cache-control']=='no-store'
        assert client.get('/api/account/usage',headers=headers(data.other)).json()['total']['consumed']==0
        assert client.post('/api/account/usage',headers=headers(data.owner),json={'plan':'paid','remaining':999999}).status_code==405
        assert client.get('/api/jobs/'+str(data.job.id),headers=headers(data.owner)).status_code==200
        assert client.get('/api/profile',headers=headers(data.owner)).status_code==200
        # Approved exports remain accessible even with zero shared allowance.
        path=f'/api/jobs/{data.job.id}/application-packs/{data.pack.id}/versions/1/download?document=cv&format=docx'
        assert client.get(path,headers=headers(data.owner)).status_code==200
    finally:client.app.dependency_overrides.clear()


def test_failure_and_unknown_outcomes_remain_reserved(db_session,data,settings,monkeypatch):
    settings=configured(settings,total=1)
    class Broken:
        name='synthetic';model='synthetic'
        def suggest(self,source):raise ProviderFailure('Synthetic failure')
    monkeypatch.setattr(profile_suggestion_service,'provider_for',lambda s:Broken())
    row=profile_suggestion_service.generate(db_session,owner_id=data.owner.id,resume=data.resume,settings=settings)
    assert row.status=='failed'
    db_session.delete(row);db_session.commit()
    assert service.snapshot(db_session,data.owner.id,settings)['total']['remaining']==0
    with pytest.raises(profile_suggestion_service.SuggestionError):profile_suggestion_service.generate(db_session,owner_id=data.owner.id,resume=data.resume,settings=settings)
    db_session.rollback()
    # A committed reservation abandoned before release also consumes a unit.
    token=ai_usage.reserve(db_session,data.other.id,settings,feature='fit');db_session.commit()
    assert db_session.get(UsageReservation,token).released_at is None
    assert service.snapshot(db_session,data.other.id,settings)['total']['remaining']==0


@pytest.mark.parametrize('feature',['profile','fit','pack','interview','transcription','speech'])
def test_all_actual_dispatch_paths_enforce_feature_entitlement(db_session,data,settings,feature):
    from app.schemas.application_packs import PackGenerate
    from test_interview_voice import wav
    if feature in {'interview','transcription','speech'}:
        row,_=begin(db_session,data,settings)
        if feature!='interview':row,_=advance(db_session,data,row,settings)
    settings=configured(settings,**{feature:0})
    with pytest.raises((profile_suggestion_service.SuggestionError,job_fit_service.JobFitError,PackError)) as error:
        if feature=='profile':profile_suggestion_service.generate(db_session,owner_id=data.owner.id,resume=data.resume,settings=settings)
        elif feature=='fit':job_fit_service.generate(db_session,owner_id=data.owner.id,job=data.job,key=str(uuid.uuid4()),settings=settings)
        elif feature=='pack':application_pack_service.generate(db_session,owner_id=data.owner.id,job_id=data.job.id,body=PackGenerate(resume_id=data.resume.id,idempotency_key=str(uuid.uuid4())),settings=settings)
        elif feature=='interview':advance(db_session,data,row,settings)
        else:interview_voice.run(db_session,data.owner.id,row.id,uuid.uuid4(),1,True,'transcribe' if feature=='transcription' else 'speak',settings,wav())
    assert error.value.status_code==403


def test_concurrent_last_unit_and_ledger_survives_result_deletion(test_engine,settings):
    settings=configured(settings,total=1)
    with Session(test_engine) as db:
        user=User(email=f'entitlement-{uuid.uuid4()}@example.com',password_hash=hash_password(PASSWORD));db.add(user);db.commit();owner=user.id
    barrier=Barrier(2)
    def attempt():
        with Session(test_engine) as db:
            barrier.wait(timeout=10)
            try:charge(db,owner,settings);return 'reserved'
            except ai_usage.AIUsageError as e:return e.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a,b=pool.submit(attempt),pool.submit(attempt);results=[a.result(timeout=10),b.result(timeout=10)]
        assert results.count('reserved')==1 and any(x in {409,429} for x in results)
        with Session(test_engine) as db:
            assert service.snapshot(db,owner,settings)['total']['consumed']==1
            assert db.get(AIUsage,owner).requests==1
    finally:
        with Session(test_engine) as db:db.execute(delete(User).where(User.id==owner));db.commit()


def test_export_deletion_and_inactive_write_barriers(db_session,data,settings):
    grant(db_session,data,settings);charge(db_session,data.other.id,settings)
    assert len(db_session.execute(account_data.export_query('usage_reservations',data.other.id)).all())==1
    assert not db_session.execute(account_data.export_query('usage_reservations',data.owner.id)).all()
    exported=db_session.execute(account_data.export_query('plan_audits',data.other.id)).mappings().one()
    assert 'actor_id' not in exported and 'request_hash' not in exported
    other=data.other.id;data.other.is_active=False;db_session.commit()
    with pytest.raises(ai_usage.AIUsageError):charge(db_session,other,settings)
    db_session.rollback()
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(UsageReservation(id=uuid.uuid4(),owner_id=other,feature='fit',period_start=service.period(service.now())[0],created_at=service.now()));db_session.flush()
    db_session.delete(data.other);db_session.commit()
    for model in [AccountPlan,UsageReservation,PlanAudit]:assert db_session.scalar(select(func.count()).select_from(model).where(model.owner_id==other))==0


def test_admin_cli_password_not_echoed_and_no_paid_command(db_session,data,settings,monkeypatch,capsys):
    import contextlib
    from app.cli import main
    admin_settings=settings.model_copy(update={'JOBPILOT_PLAN_ADMIN_EMAILS':[data.owner.email]})
    @contextlib.contextmanager
    def factory():yield db_session
    monkeypatch.setattr('app.cli.SessionLocal',factory)
    monkeypatch.setattr('app.core.config.get_settings',lambda:admin_settings)
    monkeypatch.setattr('getpass.getpass',lambda _:PASSWORD)
    args=['beta-grant','--admin-email',data.owner.email,'--user-id',str(data.other.id),'--request-key',str(uuid.uuid4()),'--reason','invited_beta','--hours','24']
    assert main(args)==0
    output=capsys.readouterr().out
    assert PASSWORD not in output and 'No payment' in output
    with pytest.raises(SystemExit):main(['paid-grant'])


def test_admin_deletion_preserves_target_grant_and_anonymizes_actor(db_session,data,settings):
    audit=grant(db_session,data,settings);audit_id=audit.id;target=data.other.id
    db_session.delete(data.owner);db_session.commit()
    assert db_session.get(PlanAudit,audit_id).actor_id is None
    assert service.snapshot(db_session,target,settings)['plan']=='invited_beta'


def test_guarded_exhaustion_refuses_existing_accounts(client,db_session,data,settings,monkeypatch):
    from app.api.routes import e2e
    client.app.dependency_overrides[get_db]=lambda:db_session
    monkeypatch.setattr(e2e,'get_settings',lambda:settings)
    headers={'Authorization':'Bearer '+create_access_token(data.owner.id)}
    try:
        assert client.post('/api/e2e/exhaust-usage',headers=headers).status_code==404
        assert service.snapshot(db_session,data.owner.id,settings)['total']['consumed']==0
    finally:client.app.dependency_overrides.clear()


def test_guarded_exhaustion_synthetic_fixture(db_session,settings,monkeypatch):
    from app.api.routes import e2e
    monkeypatch.setattr(e2e,'get_settings',lambda:settings)
    row=e2e.bootstrap_user(e2e.BootstrapRequest(email=f'e2e-usage-{uuid.uuid4()}@jobpilot-test.com',password=PASSWORD),db_session)
    user=db_session.get(User,row.user_id)
    db_session.autoflush=False  # Production SessionLocal configuration.
    try:
        assert e2e.exhaust_usage(user,db_session)['provider_requests_sent']==0
        assert service.snapshot(db_session,user.id,settings)['total']['remaining']==0
    finally:e2e._usage_fixture_users.discard(user.id)


def test_exhausted_quota_does_not_block_private_export_or_deletion(db_session,data,settings,monkeypatch):
    settings=configured(settings,total=1)
    charge(db_session,data.owner.id,settings)
    monkeypatch.setattr(account_data.resume_store,'read_bytes',lambda _:b'x')
    exported=account_data.create_export(db_session,data.owner.id,PASSWORD,settings)
    assert exported['id']
    receipt=account_data.request_deletion(db_session,data.owner.id,PASSWORD,'DELETE MY ACCOUNT')
    assert receipt['id'] and not db_session.get(User,data.owner.id).is_active


# ── Administrator entitlement bypass tests ──────────────────────────


def test_is_plan_admin_case_insensitive(db_session, data, settings):
    """Admin email match is case-insensitive."""
    email = data.owner.email  # e.g. "owner@example.com"
    admin_settings = settings.model_copy(update={"JOBPILOT_PLAN_ADMIN_EMAILS": [email.upper()]})
    assert service.is_plan_admin(db_session, data.owner.id, admin_settings)


def test_is_plan_admin_empty_list(db_session, data, settings):
    """Empty admin list means nobody is admin."""
    assert not service.is_plan_admin(db_session, data.owner.id, settings)


def test_is_plan_admin_not_listed(db_session, data, settings):
    """Email not in the list is not admin."""
    admin_settings = settings.model_copy(update={"JOBPILOT_PLAN_ADMIN_EMAILS": ["other@example.com"]})
    assert not service.is_plan_admin(db_session, data.owner.id, admin_settings)


def test_admin_bypasses_total_quota(db_session, data, settings):
    """Admin can reserve beyond the normal total limit."""
    settings = configured(settings, total=1)
    admin_settings = settings.model_copy(update={"JOBPILOT_PLAN_ADMIN_EMAILS": [data.owner.email]})
    charge(db_session, data.owner.id, settings)
    # Non-admin would get 429
    with pytest.raises(ai_usage.AIUsageError) as error:
        ai_usage.reserve(db_session, data.owner.id, settings, feature="profile")
    assert error.value.status_code == 429
    db_session.rollback()
    # Admin succeeds
    token = ai_usage.reserve(db_session, data.owner.id, admin_settings, feature="profile")
    ai_usage.release(db_session, data.owner.id, token)
    db_session.commit()


def test_admin_bypasses_per_feature_quota(db_session, data, settings):
    """Admin can reserve beyond per-feature allowance."""
    settings = configured(settings, total=10, profile=1)
    admin_settings = settings.model_copy(update={"JOBPILOT_PLAN_ADMIN_EMAILS": [data.owner.email]})
    charge(db_session, data.owner.id, settings, "profile")
    # Non-admin would get 429 on profile
    with pytest.raises(ai_usage.AIUsageError) as error:
        ai_usage.reserve(db_session, data.owner.id, settings, feature="profile")
    assert error.value.status_code == 429
    db_session.rollback()
    # Admin succeeds
    token = ai_usage.reserve(db_session, data.owner.id, admin_settings, feature="profile")
    ai_usage.release(db_session, data.owner.id, token)
    db_session.commit()


def test_admin_bypasses_disabled_feature(db_session, data, settings):
    """Admin can use a feature set to 0 allowance."""
    settings = configured(settings, total=10, speech=0)
    admin_settings = settings.model_copy(update={"JOBPILOT_PLAN_ADMIN_EMAILS": [data.owner.email]})
    # Non-admin gets 403
    with pytest.raises(ai_usage.AIUsageError) as error:
        ai_usage.reserve(db_session, data.owner.id, settings, feature="speech")
    assert error.value.status_code == 403
    db_session.rollback()
    # Admin succeeds
    token = ai_usage.reserve(db_session, data.owner.id, admin_settings, feature="speech")
    ai_usage.release(db_session, data.owner.id, token)
    db_session.commit()


@pytest.mark.parametrize("feature", ["profile", "fit", "pack", "interview", "transcription", "speech", "qa"])
def test_admin_bypasses_every_metered_feature(db_session, data, settings, feature):
    """Admin bypass works for all 7 metered features via the reserve() path."""
    settings = configured(settings, total=1, **{feature: 0})
    admin_settings = settings.model_copy(update={"JOBPILOT_PLAN_ADMIN_EMAILS": [data.owner.email]})
    # Non-admin gets 403 or 429
    with pytest.raises(ai_usage.AIUsageError) as error:
        ai_usage.reserve(db_session, data.owner.id, settings, feature=feature)
    assert error.value.status_code in (403, 429)
    db_session.rollback()
    # Admin succeeds
    token = ai_usage.reserve(db_session, data.owner.id, admin_settings, feature=feature)
    ai_usage.release(db_session, data.owner.id, token)
    db_session.commit()


def test_admin_snapshot_reports_admin_flag(db_session, data, settings):
    """Snapshot includes admin=True and unlimited remaining for admins."""
    settings = configured(settings, total=1)
    admin_settings = settings.model_copy(update={"JOBPILOT_PLAN_ADMIN_EMAILS": [data.owner.email]})
    snap = service.snapshot(db_session, data.owner.id, admin_settings)
    assert snap["admin"] is True
    assert snap["total"]["remaining"] == 999999
    for feature, info in snap["features"].items():
        if info["state"] != "unavailable":
            assert info["state"] == "admin"
            assert info["remaining"] == 999999


def test_non_admin_snapshot_reports_admin_false(db_session, data, settings):
    """Non-admin snapshot has admin=False and normal remaining."""
    settings = configured(settings, total=5)
    snap = service.snapshot(db_session, data.owner.id, settings)
    assert snap["admin"] is False
    assert snap["total"]["remaining"] == 5


def test_owner_email_not_automatic_admin(db_session, data, settings):
    """Owner is not admin unless their email is explicitly listed."""
    assert not service.is_plan_admin(db_session, data.owner.id, settings)
    snap = service.snapshot(db_session, data.owner.id, settings)
    assert snap["admin"] is False


def test_admin_beta_grant_still_works(db_session, data, settings):
    """Admin bypass for quotas does not break beta-grant/revoke."""
    key = uuid.uuid4()
    admin_settings = settings.model_copy(update={"JOBPILOT_PLAN_ADMIN_EMAILS": [data.owner.email]})
    audit = grant(db_session, data, admin_settings, request_key=key)
    assert audit.id
    assert service.snapshot(db_session, data.other.id, admin_settings)["plan"] == "invited_beta"
    # Revoke also works
    grant(db_session, data, admin_settings, action="revoke", hours=0, request_key=uuid.uuid4())
