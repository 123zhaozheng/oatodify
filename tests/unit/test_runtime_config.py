import json
import os
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.console_config import router
from config import settings
from database import get_db
from models import Base, DocumentCategoryMapping, KnowledgeBase, OAFileInfo, BusinessCategory, ProcessingStatus
from services.runtime_config import refresh_runtime_settings
from services.runtime_config import VersionConflict, patch_runtime_config


@pytest.fixture
def runtime_app(tmp_path, monkeypatch):
    config_path = tmp_path / "shared" / "runtime.json"
    monkeypatch.setenv("RUNTIME_CONFIG_PATH", str(config_path))
    refresh_runtime_settings()

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client, session_factory, config_path
    engine.dispose()


def test_config_get_masks_secret_values_and_describes_fields(runtime_app, monkeypatch):
    client, _, _ = runtime_app
    monkeypatch.setattr(settings, "database_url", "postgresql://user:very-secret@db/oa")
    monkeypatch.setattr(settings, "openai_api_key", "api-secret")

    response = client.get("/api/v1/console/config")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 0
    assert data["values"]["database_url"] == ""
    assert data["values"]["openai_api_key"] == ""
    assert all(data["values"][key] == "" for key in data["secrets"])
    assert data["secrets"]["database_url"] is True
    assert data["secrets"]["openai_api_key"] is True
    assert all(field["label"] and field["group"] and field["help"] for field in data["fields"])
    assert next(field for field in data["fields"] if field["key"] == "database_url")["apply"] == "restart"


def test_patch_strict_validation_secret_retention_clear_and_file_mode(runtime_app):
    client, _, config_path = runtime_app
    first = client.get("/api/v1/console/config").json()
    saved = client.patch("/api/v1/console/config", json={
        "version": first["version"],
        "values": {"nas_root": "/mnt/new", "dify_api_key": "dify-secret", "database_url": "postgresql://u:p@db/new"},
    })
    assert saved.status_code == 200
    result = saved.json()
    assert result["version"] == 1
    assert "database_url" in result["restart_required"]
    data = client.get("/api/v1/console/config").json()
    assert data["values"]["dify_api_key"] == ""
    assert data["secrets"]["dify_api_key"] is True
    assert data["values"]["nas_root"] == "/mnt/new"
    stored = json.loads(config_path.read_text(encoding="utf-8"))
    assert stored["values"]["dify_api_key"] == "dify-secret"
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600

    # A blank secret leaves the original in place; clearing is explicit.
    retained = client.patch("/api/v1/console/config", json={
        "version": data["version"], "values": {"dify_api_key": ""},
    })
    assert retained.status_code == 200
    assert json.loads(config_path.read_text(encoding="utf-8"))["values"]["dify_api_key"] == "dify-secret"
    cleared_version = retained.json()["version"]
    cleared = client.patch("/api/v1/console/config", json={
        "version": cleared_version, "values": {}, "clear_secrets": ["dify_api_key"],
    })
    assert cleared.status_code == 200
    assert json.loads(config_path.read_text(encoding="utf-8"))["values"]["dify_api_key"] == ""

    version = cleared.json()["version"]
    for body in (
        {"version": version, "values": {"cleanup_min_confidence": True}},
        {"version": version, "values": {"not_a_setting": "x"}},
        {"version": version, "values": {"cleanup_min_confidence": 101}},
    ):
        invalid = client.patch("/api/v1/console/config", json=body)
        assert invalid.status_code == 422


def test_config_version_conflict_and_secret_error_does_not_echo_input(runtime_app):
    client, _, _ = runtime_app
    stale = client.get("/api/v1/console/config").json()["version"]
    assert client.patch("/api/v1/console/config", json={
        "version": stale, "values": {"nas_root": "/mnt/one"},
    }).status_code == 200
    conflict = client.patch("/api/v1/console/config", json={
        "version": stale, "values": {"openai_api_key": "do-not-echo-secret"},
    })
    assert conflict.status_code == 409
    assert "do-not-echo-secret" not in conflict.text


def test_read_limit_and_independent_filter_limit_with_absolute_paths(runtime_app):
    client, _, _ = runtime_app
    initial = client.get("/api/v1/console/config").json()
    assert initial["values"]["max_file_size"] == 100 * 1024 * 1024
    assert "filter_enable_duplicate_filter" not in {field["key"] for field in initial["fields"]}
    assert hasattr(settings, "filter_enable_duplicate_filter")
    assert "读取保护" in next(field for field in initial["fields"] if field["key"] == "max_file_size")["help"]
    assert "筛选" in next(field for field in initial["fields"] if field["key"] == "filter_max_file_size_mb")["help"]

    valid = client.patch("/api/v1/console/config", json={
        "version": initial["version"],
        "values": {
            "max_file_size": 2 * 1024 * 1024,
            "filter_max_file_size_mb": 1,
            "nas_root": "/mnt/oa-data",
            "nas_path_prefix": "/OA",
            "dat_import_directory": "/data/dat-import",
        },
    })
    assert valid.status_code == 200
    assert settings.max_file_size == 2 * 1024 * 1024
    assert settings.filter_max_file_size_mb == 1

    version = valid.json()["version"]
    for values in (
        {"max_file_size": True},
        {"max_file_size": "2097152"},
        {"max_file_size": 0},
        {"max_file_size": 1_000_000_000_001},
        {"nas_root": "mnt/oa-data"},
        {"nas_path_prefix": "OA"},
        {"dat_import_directory": "data/dat-import"},
        {"filter_max_file_size_mb": 0},
    ):
        invalid = client.patch("/api/v1/console/config", json={"version": version, "values": values})
        assert invalid.status_code == 422

    retired = client.patch("/api/v1/console/config", json={
        "version": version, "values": {"filter_enable_duplicate_filter": False},
    })
    assert retired.status_code == 422


def test_endpoint_metadata_displays_safe_summary_without_replacing_uri_secret(runtime_app):
    client, _, config_path = runtime_app
    first = client.get("/api/v1/console/config").json()
    secret_url = "https://user:private-pass@dify.example/v1?token=query-secret#fragment-secret"
    saved = client.patch("/api/v1/console/config", json={
        "version": first["version"], "values": {"dify_base_url": secret_url},
    })
    assert saved.status_code == 200

    fetched = client.get("/api/v1/console/config").json()
    field = next(item for item in fetched["fields"] if item["key"] == "dify_base_url")
    assert field["display_value"] == "https://dify.example/v1"
    assert "仅展示无凭证部分" in field["help"]
    assert fetched["values"]["dify_base_url"] == ""
    assert "private-pass" not in json.dumps(fetched, ensure_ascii=False)
    assert "query-secret" not in json.dumps(fetched, ensure_ascii=False)
    assert json.loads(config_path.read_text(encoding="utf-8"))["values"]["dify_base_url"] == secret_url

    # If the summary is accidentally submitted as an input value, preserve the
    # original URI instead of replacing its hidden credentials/query string.
    echoed = client.patch("/api/v1/console/config", json={
        "version": fetched["version"], "values": {"dify_base_url": field["display_value"]},
    })
    assert echoed.status_code == 200
    assert json.loads(config_path.read_text(encoding="utf-8"))["values"]["dify_base_url"] == secret_url

    invalid = client.patch("/api/v1/console/config", json={
        "version": echoed.json()["version"], "values": {"dify_base_url": "ftp://dify.example/api"},
    })
    assert invalid.status_code == 422
    invalid_host = client.patch("/api/v1/console/config", json={
        "version": echoed.json()["version"], "values": {"dify_base_url": "https:///missing-host"},
    })
    assert invalid_host.status_code == 422


def test_concurrent_config_writes_are_serialized_by_version(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_CONFIG_PATH", str(tmp_path / "shared" / "runtime.json"))

    def write(key, value):
        try:
            return patch_runtime_config(0, {key: value})["version"]
        except VersionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: write(*item), [
            ("nas_root", "/mnt/a"), ("dat_import_directory", "/mnt/b"),
        ]))
    assert sorted(map(str, results)) == ["1", "conflict"]


def test_startup_runtime_file_overrides_environment_without_default_path(tmp_path):
    config_path = tmp_path / "runtime.json"
    config_path.write_text(json.dumps({
        "version": 4,
        "values": {"database_url": "postgresql://saved-user:saved-pass@db/saved",
                   "nas_root": "/mnt/saved"},
        "updated_at": "2026-10-12T00:00:00Z",
    }), encoding="utf-8")
    env = os.environ.copy()
    env["RUNTIME_CONFIG_PATH"] = str(config_path)
    env["DATABASE_URL"] = "postgresql://env-user:env-pass@db/env"
    result = subprocess.run(
        [sys.executable, "-c", "from config import settings; print(settings.database_url); print(settings.nas_root)"],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        env=env, text=True, capture_output=True, check=True,
    )
    assert result.stdout.splitlines() == ["postgresql://saved-user:saved-pass@db/saved", "/mnt/saved"]


def test_shared_revision_refreshes_process_cache_only_once(runtime_app, monkeypatch):
    from services.file_filter import file_filter

    calls = []
    original = file_filter._load_keywords_from_config
    monkeypatch.setattr(file_filter, "_load_keywords_from_config", lambda: (calls.append(1), original())[1])
    client, _, _ = runtime_app
    current = client.get("/api/v1/console/config").json()
    result = client.patch("/api/v1/console/config", json={
        "version": current["version"], "values": {"filter_keywords_common": "draft,archive"},
    })
    assert result.status_code == 200
    assert len(calls) == 1
    refresh_runtime_settings()
    assert len(calls) == 1


def test_refresh_applies_hot_fields_but_never_switches_database_in_process(runtime_app, monkeypatch):
    client, _, _ = runtime_app
    old_database = settings.database_url
    current = client.get("/api/v1/console/config").json()
    response = client.patch("/api/v1/console/config", json={
        "version": current["version"],
        "values": {"dat_import_directory": "/mnt/dat-new", "database_url": "postgresql://u:p@other/oa"},
    })
    assert response.status_code == 200
    assert settings.dat_import_directory == "/mnt/dat-new"
    assert settings.database_url == old_database
    assert "database_url" in response.json()["restart_required"]


def test_knowledge_base_secrets_dataset_binding_and_category_mappings(runtime_app):
    client, session_factory, _ = runtime_app
    created = client.post("/api/v1/console/knowledge-bases", json={
        "name": "总行制度", "dify_dataset_id": "dataset-1",
        "base_url": "https://user:password@dify.example/v1?token=secret",
        "api_key": "kb-api-secret",
    })
    assert created.status_code == 200
    row = created.json()
    assert row["api_key_configured"] is True
    assert row["base_url"] == "https://dify.example/v1"
    assert "password" not in created.text and "secret" not in created.text

    bad_url = client.post("/api/v1/console/knowledge-bases", json={
        "name": "错误地址", "dify_dataset_id": "dataset-bad", "base_url": "ftp://dify.example/v1",
    })
    assert bad_url.status_code == 422
    empty_url = client.post("/api/v1/console/knowledge-bases", json={
        "name": "空地址", "dify_dataset_id": "dataset-empty", "base_url": "",
    })
    assert empty_url.status_code == 422

    session = session_factory()
    doc = OAFileInfo(
        imagefileid="linked", imagefilename="linked.pdf",
        business_category=BusinessCategory.PUBLIC_STANDARD, is_zw=True,
        processing_status=ProcessingStatus.COMPLETED, document_id="doc-1",
        dify_dataset_id="dataset-1", knowledge_base_id=row["id"],
    )
    session.add(doc)
    session.commit()
    session.close()
    blocked = client.patch(f"/api/v1/console/knowledge-bases/{row['id']}", json={
        "dify_dataset_id": "dataset-2",
    })
    assert blocked.status_code == 409

    mappings = client.put("/api/v1/console/category-mappings", json={"items": [{
        "business_category": "PUBLIC_STANDARD", "knowledge_base_id": row["id"],
        "min_confidence_score": 73, "auto_approve_threshold": 91,
        "ai_prompt_template": "请只依据原文分析 {filename}", "is_active": True,
    }]})
    assert mappings.status_code == 200
    got = client.get("/api/v1/console/category-mappings")
    assert got.json()["items"][0]["min_confidence_score"] == 73
    assert len(got.json()["items"]) == 1

    invalid = client.put("/api/v1/console/category-mappings", json={"items": [{
        "business_category": "PUBLIC_STANDARD", "knowledge_base_id": row["id"],
        "min_confidence_score": True, "auto_approve_threshold": 91,
        "ai_prompt_template": "x", "is_active": True,
    }]})
    assert invalid.status_code == 422


def test_restart_connections_cannot_be_invalid_or_cleared(runtime_app):
    client, _, _ = runtime_app
    meta = client.get('/api/v1/console/config').json()
    for field in meta['fields']:
        if field['key'] in {'database_url', 'redis_url', 'document_parse_api_url'}:
            assert field['clearable'] is False
    for values in ({'database_url': 'not-a-database'}, {'redis_url': 'http://queue'}, {'nas_root': ''}):
        assert client.patch('/api/v1/console/config', json={'version': meta['version'], 'values': values}).status_code == 422
    for key in ['database_url', 'redis_url']:
        assert client.patch('/api/v1/console/config', json={
            'version': meta['version'], 'values': {}, 'clear_secrets': [key]
        }).status_code == 422


def test_mapping_update_preserves_unedited_schema_priority_and_id(runtime_app):
    client, session_factory, _ = runtime_app
    db = session_factory()
    kb = KnowledgeBase(name='Schema库', dify_dataset_id='schema-dataset')
    db.add(kb)
    db.commit()
    row = DocumentCategoryMapping(knowledge_base_id=kb.id, business_category=BusinessCategory.PUBLIC_STANDARD,
        min_confidence_score=70, auto_approve_threshold=90, ai_prompt_template='',
        ai_output_schema='{"custom":"kept"}', processing_priority=8, is_active=True)
    db.add(row)
    db.commit()
    original_id = row.id
    items = client.get('/api/v1/console/category-mappings').json()['items']
    items[0]['auto_approve_threshold'] = 92
    assert client.put('/api/v1/console/category-mappings', json={'items': items}).status_code == 200
    db.expire_all()
    actual = db.query(DocumentCategoryMapping).one()
    assert actual.id == original_id and actual.ai_output_schema == '{"custom":"kept"}' and actual.processing_priority == 8
    items[0]['auto_approve_threshold'] = 60
    assert client.put('/api/v1/console/category-mappings', json={'items': items}).status_code == 422
    db.close()


def test_knowledge_base_inherits_default_endpoint_with_null(runtime_app):
    client, _, _ = runtime_app
    response = client.post('/api/v1/console/knowledge-bases', json={
        'name': '默认连接库', 'dify_dataset_id': 'inherit-dataset', 'base_url': None
    })
    assert response.status_code == 200
    assert response.json()['base_url'] is None
    assert client.patch('/api/v1/console/knowledge-bases/' + str(response.json()['id']), json={
        'name': '改名后的库', 'base_url': None
    }).status_code == 200
