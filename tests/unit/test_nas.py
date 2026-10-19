from types import SimpleNamespace
import pytest
from config import settings
from services.file_storage import file_storage
from services.dat_importer import DATImporter, DAT_DELIMITER


@pytest.fixture
def nas(tmp_path, monkeypatch):
    root = tmp_path / 'nas'
    root.mkdir()
    monkeypatch.setattr(settings, 'nas_root', str(root))
    monkeypatch.setattr(settings, 'nas_path_prefix', None)
    monkeypatch.setattr(settings, 'storage_backend', 'nas')
    monkeypatch.setattr(settings, 'nas_files_encrypted', False)
    return root


def info(path=None):
    return SimpleNamespace(filerealpath=str(path) if path else None, tokenkey=None, asecode='legacy-key')


def test_read_absolute_chinese_path(nas):
    path = nas / '制度.pdf'
    path.write_bytes(b'plain-document')
    assert file_storage.download_file(info(path)) == b'plain-document'
    assert file_storage.decrypt_file(b'plain-document', info(path)) == b'plain-document'


def test_prefix_mapping(nas, monkeypatch):
    (nas / '2026').mkdir()
    (nas / '2026' / 'a.pdf').write_bytes(b'data')
    monkeypatch.setattr(settings, 'nas_path_prefix', '/oa/files')
    assert file_storage.download_file(info('/oa/files/2026/a.pdf')) == b'data'
    with pytest.raises(PermissionError):
        file_storage.download_file(info('/oa/files-other/2026/a.pdf'))


@pytest.mark.parametrize('path', [None, 'relative.pdf'])
def test_missing_relative(nas, path):
    with pytest.raises(ValueError):
        file_storage.download_file(info(path))


def test_traversal_and_symlink_escape(nas, tmp_path):
    outside = tmp_path / 'outside.txt'
    outside.write_bytes(b'secret')
    (nas / 'escape').symlink_to(outside)
    with pytest.raises(PermissionError):
        file_storage.download_file(info(nas / 'escape'))
    with pytest.raises(PermissionError):
        file_storage.download_file(info(f'{nas}/../outside.txt'))
    with pytest.raises(PermissionError):
        file_storage.download_file(info(outside))


def test_missing_directory_empty_large(nas, monkeypatch):
    with pytest.raises(FileNotFoundError):
        file_storage.download_file(info(nas / 'missing'))
    with pytest.raises(ValueError):
        file_storage.download_file(info(nas))
    empty = nas / 'empty'
    empty.touch()
    with pytest.raises(ValueError):
        file_storage.download_file(info(empty))
    monkeypatch.setattr(settings, 'max_file_size', 3)
    empty.write_bytes(b'1234')
    with pytest.raises(ValueError):
        file_storage.download_file(info(empty))


def test_auto_does_not_fallback_after_nas_failure(nas, monkeypatch):
    from services.s3_service import s3_service
    monkeypatch.setattr(settings, 'storage_backend', 'auto')
    monkeypatch.setattr(s3_service, 'download_file', lambda _: pytest.fail('不得回退'))
    with pytest.raises(FileNotFoundError):
        file_storage.download_file(info(nas / 'not-present'))
    record = info()
    record.tokenkey = 'old'
    monkeypatch.setattr(s3_service, 'download_file', lambda key: key.encode())
    assert file_storage.download_file(record) == b'old'


def test_tokenkey_holds_nas_path(nas, monkeypatch):
    # 数据侧把 NAS 路径写入 tokenkey（filerealpath 为空）时按 NAS 读取。
    path = nas / 'a.pdf'
    path.write_bytes(b'via-tokenkey')
    record = SimpleNamespace(filerealpath=None, tokenkey=str(path), asecode=None)
    monkeypatch.setattr(settings, 'storage_backend', 'auto')
    assert file_storage.nas_path_of(record) == str(path)
    assert file_storage.uses_nas(record) is True
    assert file_storage.download_file(record) == b'via-tokenkey'


def test_tokenkey_s3_key_not_treated_as_nas(monkeypatch):
    # 老 S3 key 不以 / 开头，auto 模式仍走 S3 分支。
    record = SimpleNamespace(filerealpath=None, tokenkey='oa-files/old.pdf', asecode=None)
    monkeypatch.setattr(settings, 'storage_backend', 'auto')
    assert file_storage.nas_path_of(record) is None
    assert file_storage.uses_nas(record) is False


def dat_line(path=None):
    fields = ['ignored', 'file1', 'PUBLIC_STANDARD', '1', '', '制度.pdf', 'pdf', '0', '100', '', 'old-token']
    if path is not None:
        fields.append(path)
    return DAT_DELIMITER.join(fields)


def test_dat_old_new_and_custom_index(monkeypatch):
    importer = DATImporter('unused')
    assert importer.parse_dat_line(dat_line())['filerealpath'] is None
    assert importer.parse_dat_line(dat_line('/oa/制度.pdf'))['filerealpath'] == '/oa/制度.pdf'
    monkeypatch.setattr(settings, 'dat_filerealpath_index', 12)
    assert importer.parse_dat_line(dat_line('extra') + DAT_DELIMITER + '/oa/a.pdf')['filerealpath'] == '/oa/a.pdf'


def test_dat_fills_path_without_reupload(db, make_doc, tmp_path):
    doc = make_doc('file1')
    path = tmp_path / 'a.dat'
    path.write_text(dat_line('/oa/new.pdf') + '\n')
    DATImporter(str(path)).import_to_database(db, update_existing=False)
    db.refresh(doc)
    assert doc.filerealpath == '/oa/new.pdf'
    assert doc.document_id == 'dify-file1'


def test_daily_import_uses_shanghai_business_date(tmp_path, monkeypatch):
    import services.dat_importer as importer
    from datetime import datetime
    class ShanghaiClock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz.key == 'Asia/Shanghai'
            return datetime(2026, 10, 13, 2, 10, tzinfo=tz)
    monkeypatch.setattr(importer, 'datetime', ShanghaiClock)
    folder = tmp_path / '20261012'
    folder.mkdir()
    dat = folder / 'oa.dat'
    dat.write_text('data')
    assert importer.get_latest_dat_file(str(tmp_path)) == str(dat)
