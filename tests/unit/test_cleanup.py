import hashlib
import json
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from config import settings
from models import BusinessCategory, CleanupCandidate, ProcessingStatus
from services.version_manager import VersionManager
from services.cleanup_service import cleanup_service
from services.dify_service import DifyService


@pytest.fixture
def manager(monkeypatch):
    manager = VersionManager()
    monkeypatch.setattr(manager, 'today', lambda: date(2026, 10, 12))
    return manager


def content(doc, text='一份完整制度正文'):
    doc.parsed_content = text
    doc.content_sha256 = hashlib.sha256(text.encode()).hexdigest()
    return doc


def approve(db, candidate):
    candidate.status = 'approved'
    candidate.reviewed_at = datetime.now()
    candidate.reviewed_by = 'tester'
    db.commit()


def test_expiration_last_day_inclusive(manager, make_doc):
    doc = make_doc('a', ai_analysis_result=json.dumps({'ai_metadata': {'expiration_date': '2026-10-12'}}))
    assert manager.check_document_expiration_by_metadata(doc)[0] is False
    doc.ai_analysis_result = json.dumps({'ai_metadata': {'expiration_date': '2026年10月11日'}})
    assert manager.check_document_expiration_by_metadata(doc)[0] is True
    doc.ai_analysis_result = json.dumps({'ai_metadata': {'expiration_date': '2026-10'}})
    assert manager.check_document_expiration_by_metadata(doc) == (False, None)


def test_expiration_requires_actual_quote_and_confidence(manager, make_doc, monkeypatch):
    doc = make_doc('a')
    text = '本文件有效期至2026年10月11日，届时全文失效。'
    result = dict(decision='expired', expiration_date='2026-10-11', evidence_quote=text,
                  confidence=99, whole_document=True)
    monkeypatch.setattr(manager, 'ask_json', lambda _: dict(result))
    assert manager.analyze_expiration(doc, text)['verified'] is True
    for key, value in [('confidence', 10), ('confidence', '99'), ('confidence', True),
                       ('whole_document', 'true'), ('evidence_quote', '虚构引用2026-10-11'),
                       ('expiration_date', '2025-10-11'), ('decision', 'unknown')]:
        altered = dict(result, **{key: value})
        monkeypatch.setattr(manager, 'ask_json', lambda _, r=altered: r)
        assert manager.analyze_expiration(doc, text)['verified'] is False


def test_context_keeps_last_clause(manager):
    assert manager.context('开头' + 'x' * 10000 + '废止条款', 1000).endswith('废止条款')


def test_rotation_covers_history_and_headquarters(db, make_doc, manager, monkeypatch):
    docs = [make_doc(str(i), business_category=BusinessCategory.HEADQUARTERS_ISSUE) for i in range(3)]
    for doc in docs:
        content(doc)
    db.commit()
    monkeypatch.setattr(manager, 'analyze_expiration', lambda *_: {'verified': False})
    for _ in range(3):
        assert manager.process_document_expiration_check(db, limit=1)['processed'] == 1
    assert all(doc.expiration_checked_at for doc in docs)


def test_duplicate_scope_and_same_name_different_content(db, make_doc, manager):
    a = content(make_doc('a', imagefilename='同名.pdf'))
    b = content(make_doc('b', imagefilename='同名.docx'))
    c = content(make_doc('c', imagefilename='同名.pdf'), '不同内容')
    d = content(make_doc('d', business_category=BusinessCategory.RETAIL_ANNOUNCEMENT))
    e = content(make_doc('e', dify_dataset_id='other-kb'))
    db.commit()
    stats = manager.process_duplicate_document_cleanup(db, limit=10, dry_run=True)
    rows = db.query(CleanupCandidate).all()
    assert len(rows) == 1 and rows[0].file_id == b.imagefileid
    assert rows[0].replacement_file_id == a.imagefileid
    assert stats['deleted'] == 0
    assert all(doc.document_id for doc in (a, b, c, d, e))


def test_proposal_idempotent_and_rejection_persists(db, make_doc, manager):
    a = content(make_doc('a'))
    b = content(make_doc('b'))
    db.commit()
    manager.process_duplicate_document_cleanup(db, dry_run=True)
    row = db.query(CleanupCandidate).one()
    row.status = 'rejected'
    db.commit()
    manager.process_duplicate_document_cleanup(db, dry_run=True)
    assert db.query(CleanupCandidate).count() == 1
    assert row.status == 'rejected'


def candidate_pair(db, make_doc):
    keep = content(make_doc('keep'))
    old = content(make_doc('old'))
    candidate = cleanup_service.propose(db, old, 'duplicate', {'content_sha256': old.content_sha256}, keep)
    db.commit()
    return old, keep, candidate


def test_approval_required_and_remote_failure_keeps_document(db, make_doc, monkeypatch):
    old, keep, candidate = candidate_pair(db, make_doc)
    service = Mock()
    monkeypatch.setattr(cleanup_service, 'service_for_file', lambda *_: service)
    assert cleanup_service.execute(db, candidate.id)['success'] is False
    service.delete_document_from_knowledge_base.assert_not_called()
    approve(db, candidate)
    service.get_document_detail.return_value = {'success': True, 'document': {
        'id': keep.document_id, 'indexing_status': 'completed', 'enabled': True, 'archived': False}}
    service.delete_document_from_knowledge_base.return_value = {'success': False, 'error': 'network timeout'}
    assert cleanup_service.execute(db, candidate.id)['success'] is False
    assert old.document_id == 'dify-old' and old.processing_status == ProcessingStatus.COMPLETED
    assert candidate.status == 'failed' and candidate.attempts == 1
    service.delete_document_from_knowledge_base.return_value = {'success': True}
    assert cleanup_service.execute(db, candidate.id)['success'] is True
    assert old.document_id is None and candidate.document_id == 'dify-old'
    assert candidate.status == 'deleted' and candidate.attempts == 2
    assert cleanup_service.execute(db, candidate.id)['already_deleted'] is True
    assert service.delete_document_from_knowledge_base.call_count == 2


@pytest.mark.parametrize('state', [
    {'indexing_status': 'indexing', 'enabled': True, 'archived': False},
    {'indexing_status': 'error', 'enabled': True, 'archived': False},
    {'indexing_status': 'completed', 'enabled': False, 'archived': False},
    {'indexing_status': 'completed', 'enabled': True, 'archived': True},
    {'indexing_status': 'completed'},
])
def test_unusable_replacement_never_deletes(db, make_doc, monkeypatch, state):
    old, keep, candidate = candidate_pair(db, make_doc)
    approve(db, candidate)
    service = Mock()
    service.get_document_detail.return_value = {'success': True, 'document': dict(id=keep.document_id, **state)}
    monkeypatch.setattr(cleanup_service, 'service_for_file', lambda *_: service)
    assert cleanup_service.execute(db, candidate.id)['success'] is False
    service.delete_document_from_knowledge_base.assert_not_called()
    assert old.document_id


def test_stale_snapshot_and_changed_content(db, make_doc, monkeypatch):
    old, keep, candidate = candidate_pair(db, make_doc)
    approve(db, candidate)
    old.document_id = 'new-document-id'
    db.commit()
    assert cleanup_service.execute(db, candidate.id)['success'] is False
    assert candidate.status == 'stale'


def test_changed_content_blocks_delete(db, make_doc, monkeypatch):
    old, keep, candidate = candidate_pair(db, make_doc)
    approve(db, candidate)
    old.parsed_content = 'changed-body'
    db.commit()
    assert cleanup_service.execute(db, candidate.id)['success'] is False
    assert old.document_id == 'dify-old'


def test_unbound_old_records_blocked(db, make_doc):
    old = make_doc('old', dify_dataset_id=None)
    with pytest.raises(ValueError):
        cleanup_service.propose(db, old, 'expiration', {})


def test_model_cannot_choose_id_outside_group(db, make_doc, manager, monkeypatch):
    a = make_doc('a')
    b = make_doc('b')
    response = dict(latest_document_id='a', old_document_ids=['external-file-id'],
                    confidence=99, effective_date='2026-01-01',
                    replacement_evidence=[{'old_document_id': 'external-file-id', 'quote': '明确全文废止的引用'}])
    monkeypatch.setattr(manager, 'ask_json', lambda _: response)
    assert manager.compare_versions_by_ai([(a, 'body'), (b, 'body')]) is None
    response['old_document_ids'] = ['a']
    assert manager.compare_versions_by_ai([(a, 'body'), (b, 'body')]) is None


def test_404_success_only_when_correct_dataset_exists(monkeypatch):
    service = DifyService()
    service.api_key = 'test-key'
    service.dataset_id = 'kb-test'
    missing = SimpleNamespace(status_code=404, text='missing')
    service.session = Mock()
    service.session.delete.return_value = missing
    service.session.get.side_effect = [missing]
    assert not service.delete_document_from_knowledge_base('doc')['success']
    dataset = SimpleNamespace(status_code=200, json=lambda: {'id': 'kb-test'})
    service.session.get.side_effect = [dataset, missing]
    assert service.delete_document_from_knowledge_base('doc')['success']


def test_auto_cleanup_and_dry_run_guard(db, make_doc, manager, monkeypatch):
    keep = content(make_doc('keep'))
    old = content(make_doc('old'))
    db.commit()
    monkeypatch.setattr(settings, 'cleanup_auto_delete', True)
    service = Mock()
    service.get_document_detail.return_value = {'success': True, 'document': {
        'id': keep.document_id, 'indexing_status': 'completed', 'enabled': True, 'archived': False}}
    service.delete_document_from_knowledge_base.return_value = {'success': True}
    monkeypatch.setattr(cleanup_service, 'service_for_file', lambda *_: service)
    manager.process_duplicate_document_cleanup(db, dry_run=True)
    service.delete_document_from_knowledge_base.assert_not_called()
    assert old.document_id
    stats = manager.process_duplicate_document_cleanup(db, dry_run=False)
    assert stats['deleted'] == 1 and old.document_id is None


def test_version_replacement_with_evidence_requires_review(db, make_doc, manager, monkeypatch):
    old = content(make_doc('old', business_category=BusinessCategory.HEADQUARTERS_ISSUE,
                            imagefilename='《信贷办法》.pdf'), '原制度全文')
    quote = '自2026年1月1日起，本办法全面替代《信贷办法》原版本。'
    new = content(make_doc('new', business_category=BusinessCategory.HEADQUARTERS_ISSUE,
                            imagefilename='关于修订《信贷办法》的通知.pdf'), quote)
    db.commit()
    monkeypatch.setattr(settings, 'cleanup_auto_delete', True)
    monkeypatch.setattr(manager, 'ask_json', lambda _: dict(latest_document_id='new', old_document_ids=['old'],
        confidence=99, effective_date='2026-01-01', reasoning='全面替代',
        replacement_evidence=[{'old_document_id': 'old', 'quote': quote}]))
    result = manager.process_headquarters_version_deduplication(db, dry_run=False)
    candidate = db.query(CleanupCandidate).one()
    assert result['candidates'] == 1 and result['deleted'] == 0
    assert candidate.status == 'pending' and candidate.replacement_file_id == 'new'
    assert old.document_id
