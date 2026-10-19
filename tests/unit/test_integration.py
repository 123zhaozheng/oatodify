from unittest.mock import Mock
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI
from fastapi.testclient import TestClient
from config import settings
from models import ProcessingStatus
from schema_migration import migrate_schema
from services.file_storage import file_storage
from services.version_manager import VersionManager
from services.cleanup_service import cleanup_service
from backfill_bindings import backfill
from services.dify_service import dify_service


def test_existing_database_additive_migration_twice():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE oa_file_info (id INTEGER PRIMARY KEY, imagefileid VARCHAR(100))'))
        conn.execute(text("INSERT INTO oa_file_info VALUES (1, 'keep-existing')"))
    migrate_schema(engine)
    migrate_schema(engine)
    columns = {c['name'] for c in inspect(engine).get_columns('oa_file_info')}
    assert {'filerealpath', 'parsed_content', 'dify_dataset_id', 'expiration_checked_at'} <= columns
    assert inspect(engine).has_table('cleanup_candidates')
    with engine.connect() as conn:
        assert conn.execute(text('SELECT imagefileid FROM oa_file_info')).scalar() == 'keep-existing'


@pytest.fixture
def client(db):
    from api.routes import router
    from database import get_db
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client


def test_default_preview_routes_forward_true(client, monkeypatch):
    from api import routes
    versions, expiration = Mock(), Mock()
    versions.delay.return_value.id = 'task-version'
    expiration.delay.return_value.id = 'task-expiration'
    monkeypatch.setattr(routes, 'clean_headquarters_version_duplicates', versions)
    monkeypatch.setattr(routes, 'clean_expired_documents', expiration)
    assert client.post('/api/v1/maintenance/clean-version-duplicates').json()['dry_run'] is True
    assert client.post('/api/v1/maintenance/clean-expired-documents').json()['dry_run'] is True
    versions.delay.assert_called_once_with(50, True)
    expiration.delay.assert_called_once_with(50, 5, True)


def test_chinese_file_download_from_nas(client, make_doc, tmp_path, monkeypatch):
    path = tmp_path / '银行制度.pdf'
    path.write_bytes(b'pdf-content')
    make_doc('a', filerealpath=str(path), imagefilename='银行制度.pdf', imagefiletype='pdf', tokenkey=None)
    monkeypatch.setattr(settings, 'storage_backend', 'nas')
    monkeypatch.setattr(settings, 'nas_root', str(tmp_path))
    monkeypatch.setattr(settings, 'nas_path_prefix', None)
    response = client.get('/api/v1/oafile/download/a')
    assert response.status_code == 200 and response.content == b'pdf-content'
    assert '%E9%93%B6' in response.headers['content-disposition']


def test_review_execute_api_separation(client, db, make_doc, monkeypatch):
    from api import routes
    row = make_doc('a')
    candidate = cleanup_service.propose(db, row, 'expiration', {'expiration_date': '2020-01-01'})
    db.commit()
    path = f'/api/v1/maintenance/cleanup-candidates/{candidate.id}'
    assert client.post(path + '/execute').status_code == 409
    assert client.post(path + '/review', json={'approved': True, 'reviewer': '  '}).status_code == 422
    assert client.post(path + '/review', json={'approved': True, 'reviewer': '张三'}).status_code == 200
    task = Mock()
    task.delay.return_value.id = 'execution-task'
    monkeypatch.setattr(routes, 'execute_cleanup_candidate', task)
    assert client.post(path + '/execute').json()['task_id'] == 'execution-task'
    task.delay.assert_called_once_with(candidate.id)
    result = client.get('/api/v1/maintenance/cleanup-candidates?status=approved').json()
    assert result['total'] == 1 and result['items'][0]['reviewed_by'] == '张三'


def test_main_processing_uses_nas_and_pins_dataset(db, make_doc, tmp_path, monkeypatch):
    import tasks.document_processor as worker
    path = tmp_path / 'a.pdf'
    path.write_bytes(b'plain-file')
    row = make_doc('a', filerealpath=str(path), tokenkey=None, asecode='legacy',
                   processing_status=ProcessingStatus.PENDING, document_id=None, dify_dataset_id=None)
    monkeypatch.setattr(settings, 'storage_backend', 'nas')
    monkeypatch.setattr(settings, 'nas_root', str(tmp_path))
    monkeypatch.setattr(settings, 'nas_path_prefix', None)
    monkeypatch.setattr(settings, 'nas_files_encrypted', False)
    monkeypatch.setattr(worker, 'get_db_session', sessionmaker(bind=db.get_bind()))
    monkeypatch.setattr(worker, 'log_processing_step', lambda *_: None)
    parser = Mock()
    parser.parse_document.return_value = {'success': True, 'content': '完整正文用于入库和清理', 'metadata': {}}
    monkeypatch.setattr(worker, 'api_document_parser', parser)
    analyzer = Mock()
    analyzer.analyze_document_content.return_value = ({'suitable_for_kb': True, 'confidence_score': 99}, None)
    monkeypatch.setattr(worker, 'ai_analyzer', analyzer)
    service = Mock(dataset_id='actual-dataset')
    service.add_document_to_knowledge_base_by_text.return_value = {'success': True, 'document_id': 'uploaded-id'}
    monkeypatch.setattr(worker, 'dify_service', service)
    result = worker.process_document.run('a')
    db.expire_all()
    assert result['status'] == 'COMPLETED'
    assert row.dify_dataset_id == 'actual-dataset' and row.document_id == 'uploaded-id'
    assert row.parsed_content == '完整正文用于入库和清理' and len(row.content_sha256) == 64
    parser.parse_document.assert_called_once_with(b'plain-file', 'a.pdf')
    worker.process_document.run('a')
    assert service.add_document_to_knowledge_base_by_text.call_count == 1


def test_approval_processing_uses_same_nas(db, make_doc, tmp_path, monkeypatch):
    import tasks.document_processor as worker
    path = tmp_path / 'a.pdf'
    path.write_bytes(b'plain-file')
    row = make_doc('a', filerealpath=str(path), tokenkey=None, asecode='legacy',
                   processing_status=ProcessingStatus.AWAITING_APPROVAL, document_id=None)
    monkeypatch.setattr(settings, 'storage_backend', 'nas')
    monkeypatch.setattr(settings, 'nas_root', str(tmp_path))
    monkeypatch.setattr(settings, 'nas_path_prefix', None)
    monkeypatch.setattr(worker, 'get_db_session', sessionmaker(bind=db.get_bind()))
    monkeypatch.setattr(worker, 'log_processing_step', lambda *_: None)
    parser = Mock()
    parser.parse_document.return_value = {'success': True, 'content': '审批入库正文', 'metadata': {}}
    monkeypatch.setattr(worker, 'api_document_parser', parser)
    monkeypatch.setattr(worker.ai_analyzer, 'get_target_knowledge_base', lambda *_: None)
    service = Mock(dataset_id='actual-dataset')
    service.add_document_to_knowledge_base_by_text.return_value = {'success': True, 'document_id': 'approved-id'}
    monkeypatch.setattr(worker, 'dify_service', service)
    assert worker.approve_document.run('a', True)['success'] is True
    db.expire_all()
    assert row.document_id == 'approved-id' and row.parsed_content == '审批入库正文'
    assert row.dify_dataset_id == 'actual-dataset'
    assert worker.approve_document.run('a', True)['success'] is False
    assert service.add_document_to_knowledge_base_by_text.call_count == 1


def test_backfill_verifies_id_before_binding(db, make_doc, monkeypatch):
    row = make_doc('a', dify_dataset_id=None)
    monkeypatch.setattr(dify_service, 'dataset_id', 'kb-test')
    monkeypatch.setattr(dify_service, 'get_document_detail', lambda _: {'success': True, 'document': {'id': 'wrong'}})
    assert backfill(db, dataset_id='kb-test')['unresolved'] == 1
    assert row.dify_dataset_id is None
    monkeypatch.setattr(dify_service, 'get_document_detail', lambda _: {'success': True, 'document': {'id': row.document_id}})
    assert backfill(db, dataset_id='kb-test')['bound'] == 1
    assert row.dify_dataset_id == 'kb-test'


def test_batch_nas_without_token_does_not_delete_same_name(db, make_doc, tmp_path, monkeypatch):
    import tasks.document_processor as worker
    from services.file_filter import file_filter
    old = make_doc('old', imagefilename='正式制度.pdf')
    new = make_doc('new', imagefilename='正式制度.pdf', processing_status=ProcessingStatus.PENDING,
                   document_id=None, dify_dataset_id=None, filerealpath=str(tmp_path / 'new.pdf'),
                   tokenkey=None, filesize=1000)
    monkeypatch.setattr(settings, 'storage_backend', 'nas')
    monkeypatch.setattr(worker, 'get_db_session', sessionmaker(bind=db.get_bind()))
    task = Mock()
    task.delay.return_value.id = 'queued-new'
    monkeypatch.setattr(worker, 'process_document', task)
    result = worker.batch_process_documents.run(20)
    db.expire_all()
    assert result['success']
    task.delay.assert_called_once_with('new')
    assert old.document_id == 'dify-old' and old.processing_status == ProcessingStatus.COMPLETED
    assert new.processing_status == ProcessingStatus.PENDING


def test_cache_future_expiry_becomes_expired_without_new_llm_call(db, make_doc, monkeypatch):
    from datetime import date
    manager = VersionManager()
    row = make_doc('a')
    row.parsed_content = '本文件有效期截至2026年10月12日，次日全文失效。'
    manager.full_content(row)
    monkeypatch.setattr(manager, 'today', lambda: date(2026, 10, 12))
    ask = Mock(return_value={'decision': 'active', 'expiration_date': '2026-10-12',
                            'evidence_quote': row.parsed_content, 'confidence': 99, 'whole_document': True})
    monkeypatch.setattr(manager, 'ask_json', ask)
    assert not manager.expiration_analysis(row, row.parsed_content)['verified']
    monkeypatch.setattr(manager, 'today', lambda: date(2026, 10, 13))
    assert manager.expiration_analysis(row, row.parsed_content)['verified']
    assert ask.call_count == 1


def test_unknown_analysis_cache_and_content_invalidation(db, make_doc, monkeypatch):
    manager = VersionManager()
    row = make_doc('a', parsed_content='长期制度正文，无明确失效日期')
    manager.full_content(row)
    ask = Mock(return_value={'decision': 'unknown', 'whole_document': False})
    monkeypatch.setattr(manager, 'ask_json', ask)
    assert not manager.expiration_analysis(row, row.parsed_content)['verified']
    assert not manager.expiration_analysis(row, row.parsed_content)['verified']
    assert ask.call_count == 1
    row.parsed_content = '变更后的正文'
    manager.full_content(row)
    manager.expiration_analysis(row, row.parsed_content)
    assert ask.call_count == 2
