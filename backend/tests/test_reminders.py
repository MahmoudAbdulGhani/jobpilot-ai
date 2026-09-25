from datetime import datetime, timezone

import httpx
import pytest

from app.api.routes.reminders import resolve_time
from app.models import ApplicationRecord, SavedJob
from test_application_tracking import tracking_client, tracking_users, auth_headers
from test_reply_sync import setup, settings, sync, replies


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *a, **k: pytest.fail("No live providers"))


def application(db, owner, job=None):
    if job is None:
        job = SavedJob(owner_id=owner.id, title="Engineer", company="Synthetic")
        db.add(job); db.flush()
    row = ApplicationRecord(owner_id=owner.id, job_id=job.id,
        submission_date=datetime.now(timezone.utc), method="email", status="Applied")
    db.add(row); db.commit()
    return row


def payload(**changes):
    return dict(action="create", revision=0, local_time="2030-01-01T10:00:00", timezone="Asia/Beirut") | changes


def test_lifecycle_owner_duplicate_and_delete(tracking_client, tracking_users, db_session):
    owner, other = tracking_users
    row = application(db_session, owner)
    path = f"/api/applications/{row.id}/reminder"
    h = auth_headers(owner)
    assert tracking_client.get(path, headers=auth_headers(other)).status_code == 404
    assert tracking_client.post(path, json=payload(), headers=auth_headers(other)).status_code == 404
    created = tracking_client.post(path, json=payload(), headers=h).json()
    assert datetime.fromisoformat(created['due_at']).astimezone(timezone.utc) == datetime(2030, 1, 1, 8, tzinfo=timezone.utc)
    assert created['revision'] == 1
    assert tracking_client.post(path, json=payload(), headers=h).json() == created
    assert tracking_client.get('/api/reminders?view=upcoming', headers=auth_headers(other)).json()['items'] == []
    assert tracking_client.post(path, json=payload(action='edit'), headers=h).status_code == 409
    snooze = tracking_client.post(path, json=payload(action='snooze',revision=1,local_time='2030-01-02T10:00'), headers=h).json()
    assert snooze['revision'] == 2 and snooze['status'] == 'active'
    assert tracking_client.post(path, json=payload(action='snooze',revision=2,local_time='2030-01-01T10:00'), headers=h).status_code == 422
    completed = tracking_client.post(path, json=payload(action='complete',revision=2), headers=h).json()
    assert completed['status'] == 'completed'
    assert tracking_client.post(path, json=payload(), headers=h).json()['status'] == 'completed'
    assert len(tracking_client.get('/api/reminders?view=completed',headers=h).json()['items']) == 1
    assert tracking_client.post(path,json=payload(action='cancel',revision=3),headers=h).json()['status']=='cancelled'
    assert tracking_client.delete(f'/api/jobs/{row.job_id}/applications/{row.id}',headers=h).status_code == 204
    assert tracking_client.get(path,headers=h).status_code == 404
    assert tracking_client.get('/api/reminders?view=cancelled',headers=h).json()['items'] == []


@pytest.mark.parametrize('status',['Rejected','Withdrawn','Accepted','Offer'])
def test_terminal_requires_explicit_choice(tracking_client,tracking_users,db_session,status):
    row=application(db_session,tracking_users[0]);row.status=status;db_session.commit()
    path=f'/api/applications/{row.id}/reminder';h=auth_headers(tracking_users[0])
    assert tracking_client.post(path,json=payload(),headers=h).status_code==409
    assert tracking_client.post(path,json=payload(confirm_terminal=True),headers=h).status_code==200


def test_clock_boundaries():
    with pytest.raises(ValueError,match='does not exist'):
        resolve_time(datetime(2026,3,8,2,30),'America/New_York')
    with pytest.raises(ValueError,match='occurs twice'):
        resolve_time(datetime(2026,11,1,1,30),'America/New_York')
    first=resolve_time(datetime(2026,11,1,1,30),'America/New_York',0)
    second=resolve_time(datetime(2026,11,1,1,30),'America/New_York',1)
    assert (second-first).total_seconds()==3600
    assert resolve_time(datetime(2026,1,1,0,15),'Asia/Beirut').isoformat()=='2025-12-31T22:15:00+00:00'
    with pytest.raises(ValueError):resolve_time(datetime.now(),'Invalid/Zone')
    with pytest.raises(ValueError):resolve_time(datetime.now(timezone.utc),'UTC')
    with pytest.raises(ValueError):resolve_time(datetime(1,1,1),'Asia/Beirut')


def test_due_exact_instant_and_legacy_edit_guard(tracking_client,tracking_users,db_session,monkeypatch):
    import app.api.routes.reminders as reminders
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2030,1,1,8,tzinfo=timezone.utc)
    monkeypatch.setattr(reminders,'datetime',Clock)
    row=application(db_session,tracking_users[0]);h=auth_headers(tracking_users[0])
    result=tracking_client.post(f'/api/applications/{row.id}/reminder',json=payload(),headers=h).json()
    assert result['overdue'] is True
    assert len(tracking_client.get('/api/reminders',headers=h).json()['items'])==1
    assert tracking_client.get('/api/reminders?view=upcoming',headers=h).json()['items']==[]
    assert tracking_client.patch(f'/api/jobs/{row.job_id}/applications/{row.id}',
        json={'follow_up_date':'2031-01-01T00:00:00Z'},headers=h).status_code==409


def test_legacy_api_cannot_skip_timezone_or_terminal_warning(tracking_client,tracking_users,db_session):
    owner=tracking_users[0];row=application(db_session,owner);h=auth_headers(owner)
    path=f'/api/jobs/{row.job_id}/applications/{row.id}'
    assert tracking_client.patch(path,json={'follow_up_date':'2030-01-01T00:00:00'},headers=h).status_code==422
    assert tracking_client.patch(path,json={'status':'Accepted'},headers=h).status_code==200
    assert tracking_client.patch(path,json={'follow_up_date':'2030-01-01T00:00:00Z'},headers=h).status_code==409


def test_legacy_due_pagination_and_validation(tracking_client,tracking_users,db_session):
    owner=tracking_users[0];h=auth_headers(owner)
    for _ in range(3):
        row=application(db_session,owner);row.follow_up_date=datetime(2020,1,1,tzinfo=timezone.utc)
    db_session.commit()
    page=tracking_client.get('/api/reminders?limit=2',headers=h).json()
    assert len(page['items'])==2 and all(x['overdue'] for x in page['items'])
    next_page=tracking_client.get('/api/reminders?limit=2&after='+page['next_cursor'],headers=h).json()
    assert len(next_page['items'])==1
    assert not {x['application_id'] for x in page['items']} & {x['application_id'] for x in next_page['items']}
    path=f'/api/applications/{row.id}/reminder'
    assert tracking_client.post(path,json=payload(action='edit',timezone='Not/AZone'),headers=h).status_code==422
    assert tracking_client.get('/api/reminders?limit=101',headers=h).status_code==422


def test_confirmed_and_uncertain_reply_flags(tracking_client,db_session,settings,setup):
    data=setup;row=application(db_session,data.owner,data.job)
    path=f'/api/applications/{row.id}/reminder';h=auth_headers(data.owner)
    tracking_client.post(path,json=payload(),headers=h)
    # First bounded sync contains only a same-thread uncertain message.
    data.reader.thread_messages=['original','reply-2']
    sync(db_session,data,settings)
    assert tracking_client.get(path,headers=h).json()['reply_received'] is False
    uncertain=replies(db_session,data)[0]
    from app.services.reply_service import correct
    correct(db_session,data.owner.id,uncertain.id,data.job.id)
    result=tracking_client.get(path,headers=h).json()
    assert result['reply_received'] and result['status']=='active' and result['revision']==1
    correct(db_session,data.owner.id,uncertain.id,None)
    assert tracking_client.get(path,headers=h).json()['reply_received'] is False
    uncertain.job_id=data.job.id;uncertain.match_kind='reply_headers';db_session.commit()
    assert tracking_client.get(path,headers=h).json()['reply_received'] is True
