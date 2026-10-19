from fastapi.testclient import TestClient
from models import KnowledgeBase, ProcessingLog
from database import get_db
from main import app


def test_static_console_is_same_origin_and_needs_no_login(db, monkeypatch, tmp_path):
    monkeypatch.setenv('RUNTIME_CONFIG_PATH', str(tmp_path / 'runtime.json'))
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get('/')
        assert response.status_code == 200
        assert 'text/html' in response.headers['content-type']
        assert 'no-store' in response.headers['cache-control']
        assert 'OA 文档中台' in response.text
        assert client.get('/web/styles.css').status_code == 200
        assert client.get('/web/app.js').status_code == 200
        assert client.get('/api/v1/console/daily').status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_cross_origin_write_blocked_without_adding_login(db, monkeypatch, tmp_path):
    monkeypatch.setenv('RUNTIME_CONFIG_PATH', str(tmp_path / 'runtime.json'))
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.patch('/api/v1/console/config', json={}, headers={'Origin': 'https://unrelated.example'})
        assert response.status_code == 403
        metadata = client.get('/api/v1/console/config').json()
        response = client.patch('/api/v1/console/config', json={
            'version': metadata['version'], 'values': {}, 'operator': '页面操作'
        }, headers={'Origin': 'http://testserver'})
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_file_details_have_plain_text_and_pinned_kb(db, make_doc, monkeypatch):
    from api.routes import router
    from fastapi import FastAPI
    body = '<script>window.leak=true</script>银行制度正文'
    kb = KnowledgeBase(name='原入库库', dify_dataset_id='old-dataset')
    db.add(kb)
    db.commit()
    document = make_doc('detail', parsed_content=body, dify_dataset_id='old-dataset')
    db.add(ProcessingLog(file_id=document.imagefileid, step='parse', status='success', message='解析完成'))
    db.commit()
    test_app = FastAPI()
    test_app.include_router(router, prefix='/api/v1')
    test_app.dependency_overrides[get_db] = lambda: db
    result = TestClient(test_app).get('/api/v1/files/detail').json()
    assert result['parsed_content'] == body
    assert result['content_length'] == len(body)
    assert result['target_knowledge_base']['name'] == '原入库库'
    assert result['target_knowledge_base']['dataset_id'] == 'old-dataset'
    assert result['processing_logs'][0]['created_at'].endswith('+08:00')


def test_already_uploaded_document_cannot_be_requeued(db, make_doc):
    from api.routes import router
    from fastapi import FastAPI
    row = make_doc('existing')
    test_app = FastAPI()
    test_app.include_router(router, prefix='/api/v1')
    test_app.dependency_overrides[get_db] = lambda: db
    response = TestClient(test_app).post('/api/v1/files/existing/process')
    assert response.status_code == 409
    db.refresh(row)
    assert row.document_id == 'dify-existing'


def test_console_config_remains_available_when_database_startup_fails(monkeypatch, tmp_path):
    import main
    monkeypatch.setenv('RUNTIME_CONFIG_PATH', str(tmp_path / 'runtime.json'))
    def unavailable():
        raise RuntimeError('simulated database unavailable')
    monkeypatch.setattr(main, 'init_db', unavailable)
    with TestClient(main.app) as client:
        assert client.get('/').status_code == 200
        assert client.get('/api/v1/console/config').status_code == 200
        health = client.get('/health').json()
        assert health['status'] == 'degraded' and health['database_initialized'] is False
