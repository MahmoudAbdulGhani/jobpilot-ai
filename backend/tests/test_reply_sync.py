import uuid
from copy import deepcopy
from datetime import timedelta
from email import policy
from email.parser import BytesParser

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token
from app.models import ApplicationRecord, MailboxReply, ReplySync, SavedJob
from app.services import email_application_service as email_service, mailbox_service, reply_service as service
from app.services.mailbox_provider import MailboxError, TestMailboxProvider as SyntheticOAuth
from app.services.reply_provider import GmailReplies, SyncError, replies_for
from test_email_applications import seed, payload, settings  # Reuse isolated synthetic pack/mailbox fixtures.


class OAuth(SyntheticOAuth):
    name = 'google'


class Reader:
    def __init__(self, attempt):
        self.calls=[];self.fail=None;self.pages={};self.found={'messages':[{'id':'original','threadId':'thread'}]}
        original=BytesParser(policy=policy.default).parsebytes(attempt.raw_message)
        original_headers={n:str(original.get(n,'')) for n in ('Message-ID','From','To','Subject','Date')}
        self.root=str(original['Message-ID'])
        self.messages={'original':{'id':'original','threadId':'thread','labelIds':['SENT'],
            'internalDate':str(int(attempt.created_at.timestamp()*1000)),
            'payload':{'headers':[{'name':k,'value':v} for k,v in original_headers.items()]}}}
        self.received=str(int((attempt.dispatch_at or attempt.created_at).timestamp()*1000)+1000)
        self.add('reply-1',refs=self.root);self.add('reply-2')
        self.thread_messages=['original','reply-1','reply-2']
    def add(self,id,refs='',thread='thread'):
        self.messages[id]={'id':id,'threadId':thread,'labelIds':['INBOX'],'internalDate':self.received,
            'snippet':'Thanks &lt;script&gt;unsafe()&lt;/script&gt;',
            'payload':{'headers':[{'name':k,'value':v} for k,v in {'Message-ID':f'<{id}@example.com>',
                'From':'Recruiter <recruiter@example.com>','Subject':'Re: My application','References':refs}.items()]}}
    def message(self,id):
        self.calls.append(('message',id))
        if self.fail==id:raise SyncError('provider_unavailable')
        return deepcopy(self.messages[id])
    def checkpoint(self):self.calls.append(('checkpoint',));return '100'
    def thread(self,id):
        self.calls.append(('thread',id))
        return {'id':id,'historyId':'5','messages':[{'id':i,'threadId':self.messages[i]['threadId']} for i in self.thread_messages]}
    def history(self,start,page):
        self.calls.append(('history',start,page))
        if self.fail=='history':raise SyncError('history_expired')
        if self.fail=='page':raise SyncError('page_expired')
        if self.fail=='rate':raise SyncError('rate_limited',120)
        if self.fail=='revoked':raise SyncError('credential_revoked')
        return deepcopy(self.pages.get(page,{'historyId':'110','history':[]}))
    def find_sent(self,rfc):self.calls.append(('find_sent',rfc));return deepcopy(self.found)


@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',lambda *a,**k:pytest.fail('Live Google access forbidden'))


@pytest.fixture()
def setup(db_session,settings,monkeypatch):
    data=seed(db_session,settings);oauth=OAuth(settings)
    monkeypatch.setattr(email_service,'provider_for',lambda s:oauth)
    monkeypatch.setattr(email_service.pack_export,'render_document',lambda *args:b'%PDF-synthetic')
    attempt=email_service.create_review(db_session,data.owner.id,data.job.id,payload(data),settings)
    digest=attempt.snapshot_hash
    attempt.status='sent';attempt.provider_message_id='original';attempt.provider_thread_id='thread'
    attempt.approved_hash=digest;attempt.approved_at=mailbox_service.now();attempt.dispatch_at=mailbox_service.now()
    data.connection.capabilities=['send','read_replies'];db_session.commit()
    reader=Reader(attempt)
    monkeypatch.setattr(service,'provider_for',lambda s:oauth)
    monkeypatch.setattr(service,'replies_for',lambda *a:reader)
    data.attempt=attempt;data.reader=reader;data.oauth=oauth
    return data


def sync(db,data,settings):return service.batch(db,data.owner.id,data.job.id,data.attempt.id,settings)


def replies(db,data):return db.scalars(select(MailboxReply).where(MailboxReply.owner_id==data.owner.id)).all()


def test_exact_headers_uncertain_thread_and_no_status_interpretation(db_session,settings,setup):
    data=setup
    data.reader.add('unrelated',refs=data.reader.root,thread='other-thread');data.reader.thread_messages.append('unrelated')
    result=sync(db_session,data,settings)
    assert result.status=='up_to_date_for_thread' and result.progress['history']=='100'  # Current checkpoint, not old thread ID 5.
    rows={r.message_id:r for r in replies(db_session,data)}
    assert rows['reply-1'].match_kind=='reply_headers' and rows['reply-1'].job_id==data.job.id
    assert rows['reply-2'].match_kind=='uncertain_thread' and rows['reply-2'].job_id is None
    assert ('message','unrelated') not in data.reader.calls
    assert not db_session.scalar(select(ApplicationRecord).where(ApplicationRecord.job_id==data.job.id))
    assert '<script>' in rows['reply-1'].preview  # Stored text, rendered escaped by React.


def test_duplicates_correction_and_dismissal_survive_resync(db_session,settings,setup):
    data=setup;sync(db_session,data,settings)
    rows=replies(db_session,data)
    other_job=SavedJob(owner_id=data.owner.id,title='Another role',company='Example');db_session.add(other_job);db_session.commit()
    service.correct(db_session,data.owner.id,rows[0].id,other_job.id)
    service.correct(db_session,data.owner.id,rows[1].id,None)
    state=db_session.get(ReplySync,data.attempt.id);state.progress={};db_session.commit()
    before=list(data.reader.calls)
    sync(db_session,data,settings)
    assert not any(call[0]=='message' and call[1]!='original' for call in data.reader.calls[len(before):])
    assert len(replies(db_session,data))==2
    assert db_session.get(MailboxReply,rows[0].id).job_id==other_job.id
    dismissed=db_session.get(MailboxReply,rows[1].id)
    assert dismissed.match_kind=='dismissed' and dismissed.preview=='' and dismissed.sender==''


@pytest.mark.parametrize('mode',['missing_consent','disconnected','revoked_refresh','missing_refreshed_scope'])
def test_permission_rechecks_without_read_requirement_for_sending(db_session,settings,setup,mode):
    data=setup
    if mode=='missing_consent':data.connection.capabilities=['send']
    if mode=='disconnected':data.connection.status='disconnected'
    if mode=='revoked_refresh':
        def fail(token):raise MailboxError('reconnect_required',409)
        data.oauth.refresh=fail
    if mode=='missing_refreshed_scope':
        original=data.oauth.refresh
        data.oauth.refresh=lambda t:original(t).model_copy(update={'scope':'openid email https://www.googleapis.com/auth/gmail.send'})
    db_session.commit()
    if mode in ('missing_consent','disconnected'):
        with pytest.raises(service.PackError):sync(db_session,data,settings)
    else:assert sync(db_session,data,settings).status in ('reconnect_required','reading_permission_required')
    assert not data.reader.calls
    if mode=='missing_refreshed_scope':assert data.connection.capabilities==['send'] and data.connection.status=='connected'


def history_page(ids,token=None):
    return {'historyId':'150','nextPageToken':token,'history':[{'messagesAdded':[{'message':{'id':i,'threadId':'thread'}} for i in ids]}]}


def test_bounded_pagination_preserves_cursor_until_entire_window_processed(db_session,settings,setup):
    data=setup;sync(db_session,data,settings)
    for i in range(8):data.reader.add(f'new-{i}',refs=data.reader.root)
    data.reader.pages={None:history_page([f'new-{i}' for i in range(7)],'page-two'),'page-two':history_page(['new-7'])}
    state=sync(db_session,data,settings)
    assert state.status=='more_pending' and len(state.progress['queue'])==2 and state.progress['history']=='100'
    sync(db_session,data,settings)
    assert state.progress['page']=='page-two' and state.progress['history']=='100'
    sync(db_session,data,settings)
    assert state.progress['history']=='150' and not state.progress['page'] and len(replies(db_session,data))==10


def test_interrupted_batch_commits_only_completed_messages_and_resumes(db_session,settings,setup):
    data=setup;data.reader.fail='reply-2'
    state=sync(db_session,data,settings)
    assert state.status=='provider_unavailable' and state.progress['queue']==['reply-2']
    assert len(replies(db_session,data))==1
    data.reader.fail=None
    sync(db_session,data,settings)
    assert len(replies(db_session,data))==2 and state.progress['history']=='100'


@pytest.mark.parametrize('failure',['history','page','rate','revoked'])
def test_cursor_rate_and_revocation_errors_are_bounded(db_session,settings,setup,failure):
    data=setup;sync(db_session,data,settings);data.reader.fail=failure
    state=sync(db_session,data,settings)
    if failure=='history':
        assert state.status=='history_expired' and not state.progress.get('history')
        data.reader.fail=None;sync(db_session,data,settings)
        assert len(replies(db_session,data))==2
    if failure=='page':assert state.status=='page_expired' and state.progress['history']=='100'
    if failure=='rate':
        assert state.retry_after>mailbox_service.now()
        calls=list(data.reader.calls);sync(db_session,data,settings);assert calls==data.reader.calls
    if failure=='revoked':assert data.connection.status=='reconnect_required' and not data.connection.credentials


@pytest.mark.parametrize('mismatch',['none','multiple','message_id','sender','subject','date','not_sent'])
def test_unknown_reconciliation_requires_unique_exact_original(db_session,settings,setup,mismatch):
    data=setup;data.attempt.status='unknown';data.attempt.provider_message_id=None;data.attempt.provider_thread_id=None;db_session.commit()
    original=data.reader.messages['original']
    if mismatch=='multiple':data.reader.found['messages']*=2
    names={'message_id':'Message-ID','sender':'From','subject':'Subject','date':'Date'}
    if mismatch in names:
        for h in original['payload']['headers']:
            if h['name']==names[mismatch]:h['value']='different'
    if mismatch=='not_sent':original['labelIds']=['INBOX']
    result=sync(db_session,data,settings)
    if mismatch=='none':
        assert result.status=='send_reconciled_sync_again' and data.attempt.status=='sent'
        assert data.attempt.provider_message_id=='original'
        application=db_session.get(ApplicationRecord,data.attempt.application_id)
        assert application.status=='Applied' and application.cv_snapshot==data.attempt.snapshot['cv']
    else:
        assert result.status=='send_remains_unknown' and data.attempt.status=='unknown'
        assert not db_session.scalar(select(ApplicationRecord).where(ApplicationRecord.job_id==data.job.id))
    assert not replies(db_session,data)  # Reconciliation is separate from the next reply batch.


def test_owner_isolation_all_endpoints(client,db_session,settings,setup):
    data=setup;sync(db_session,data,settings);reply=replies(db_session,data)[0]
    client.app.dependency_overrides[get_db]=lambda:db_session
    client.app.dependency_overrides[get_settings]=lambda:settings
    other={'Authorization':'Bearer '+create_access_token(data.other.id)}
    owner={'Authorization':'Bearer '+create_access_token(data.owner.id)}
    other_job=SavedJob(owner_id=data.other.id,title='Private',company='Private');db_session.add(other_job);db_session.commit()
    try:
        assert client.get(f'/api/jobs/{data.job.id}/replies',headers=other).status_code==404
        assert client.post(f'/api/jobs/{data.job.id}/email-applications/{data.attempt.id}/replies/sync',headers=other,json={'confirm':True}).status_code==404
        assert client.patch(f'/api/replies/{reply.id}/association',headers=other,json={'confirm':True,'job_id':str(other_job.id)}).status_code==404
        assert client.patch(f'/api/replies/{reply.id}/association',headers=owner,json={'confirm':True,'job_id':str(other_job.id)}).status_code==404
        assert client.post(f'/api/jobs/{data.job.id}/email-applications/{data.attempt.id}/replies/sync',headers=owner,json={'confirm':False}).status_code==422
        listing=client.get(f'/api/jobs/{data.job.id}/replies',headers=owner)
        assert listing.status_code==200 and listing.headers['cache-control']=='no-store'
        assert 'progress' not in listing.text and 'refresh_token' not in listing.text
    finally:client.app.dependency_overrides.clear()


def test_gmail_wire_limits_no_attachment_body_or_unrestricted_search():
    calls=[]
    def handler(r):
        calls.append(r)
        assert r.method=='GET' and 'attachments' not in str(r.url)
        assert r.url.params.get('fields') and 'body' not in r.url.params['fields'] and 'raw' not in r.url.params['fields']
        return httpx.Response(200,json={'id':'message','historyId':'100'})
    p=GmailReplies('private',httpx.MockTransport(handler))
    p.checkpoint();p.message('message');p.thread('thread');p.history('100','opaque-page');p.find_sent(f'<{uuid.uuid4()}@jobpilot.invalid>')
    assert calls[3].url.params['maxResults']=='10' and calls[4].url.params['maxResults']=='2'
    assert calls[4].url.params['q'].startswith('in:sent rfc822msgid:')
    with pytest.raises(SyncError):p.find_sent('guessed subject')
    with pytest.raises(SyncError):p.message('../arbitrary-url')
    for _ in range(3):p.message('message')
    with pytest.raises(SyncError):p.message('message')
    assert len(calls)==8


@pytest.mark.parametrize('code,expected',[(401,'credential_revoked'),(403,'reading_permission_required'),(429,'rate_limited'),(500,'provider_unavailable'),(404,'history_expired')])
def test_provider_error_sanitization_no_retry(code,expected):
    calls=[]
    def handler(r):calls.append(r);return httpx.Response(code,json={'error':{'message':'private body'}})
    with pytest.raises(SyncError) as error:GmailReplies('private-token',httpx.MockTransport(handler)).history('100',None)
    assert error.value.code==expected and len(calls)==1 and 'private' not in str(error.value)


def test_guarded_reader_cannot_run_in_normal_mode(settings,setup):
    settings.JOBPILOT_MAILBOX_TEST_PROVIDER=True;settings.E2E_TEST_MODE=False
    with pytest.raises(MailboxError):replies_for(settings,'test',setup.attempt)


def test_disconnect_stops_sync_without_erasing_previously_reviewed_replies(db_session,settings,setup):
    data=setup;sync(db_session,data,settings);calls=list(data.reader.calls)
    mailbox_service.disconnect(db_session,data.owner.id,data.connection.id,settings,data.oauth)
    with pytest.raises(service.PackError):sync(db_session,data,settings)
    assert calls==data.reader.calls and len(replies(db_session,data))==2


def test_unrelated_history_ids_are_not_fetched_or_retained(db_session,settings,setup):
    data=setup;sync(db_session,data,settings)
    data.reader.pages[None]={'historyId':'200','history':[{'messagesAdded':[{'message':{'id':'private-unrelated','threadId':'unrelated'}}]}]}
    state=sync(db_session,data,settings)
    assert state.progress['history']=='200'
    assert 'private-unrelated' not in str(state.progress) and ('message','private-unrelated') not in data.reader.calls
    assert len(replies(db_session,data))==2


def test_malformed_page_cannot_advance_checkpoint(db_session,settings,setup):
    data=setup;sync(db_session,data,settings)
    data.reader.add('new',refs=data.reader.root)
    data.reader.pages[None]=history_page(['new'],'x'*2049)
    state=sync(db_session,data,settings)
    assert state.status=='invalid_provider_response' and state.progress['history']=='100'
    assert not state.progress['queue'] and ('message','new') not in data.reader.calls


def test_large_thread_limit_fails_closed_without_checkpoint(db_session,settings,setup):
    data=setup;data.reader.thread_messages=['reply-1']*201
    state=sync(db_session,data,settings)
    assert state.status=='response_limit' and not state.progress.get('history') and not replies(db_session,data)


def test_reconciliation_preserves_existing_application_edits(db_session,settings,setup):
    data=setup
    application=ApplicationRecord(owner_id=data.owner.id,job_id=data.job.id,status='Withdrawn',method='other',
        submission_date=mailbox_service.now(),notes='User-authored private note')
    db_session.add(application);data.attempt.status='unknown';db_session.commit()
    sync(db_session,data,settings)
    assert data.attempt.status=='sent' and data.attempt.application_id==application.id
    db_session.refresh(application)
    assert application.status=='Withdrawn' and application.method=='other' and application.notes=='User-authored private note'
