"""统一文件来源。NAS 只读，不在读失败时偷偷回退到旧 S3 文件。"""
import os
import stat
from pathlib import Path

from config import settings


class FileStorage:
    def nas_path_of(self, file_info):
        """有效 NAS 路径。优先 filerealpath；为空时兼容数据侧把 NAS 绝对路径写入
        tokenkey 的情况（以 / 开头即视为路径），老 S3 key 不以 / 开头、不受影响。"""
        if file_info.filerealpath:
            return file_info.filerealpath
        tokenkey = file_info.tokenkey or ""
        return tokenkey if tokenkey.startswith("/") else None

    def uses_nas(self, file_info):
        return settings.storage_backend == "nas" or (
            settings.storage_backend == "auto" and bool(self.nas_path_of(file_info))
        )

    def resolve_nas_path(self, filerealpath):
        if not filerealpath or not Path(filerealpath).is_absolute():
            raise ValueError("filerealpath 必须是 NAS 文件绝对路径")
        source = Path(filerealpath)
        if ".." in source.parts:
            raise PermissionError("NAS 路径不允许包含 ..")
        root = Path(settings.nas_root).resolve(strict=True)
        if settings.nas_path_prefix:
            prefix = Path(settings.nas_path_prefix)
            if not prefix.is_absolute():
                raise ValueError("NAS_PATH_PREFIX 必须是绝对路径")
            try:
                source = root / source.relative_to(prefix)
            except ValueError as exc:
                raise PermissionError("文件不在 NAS_PATH_PREFIX 范围内") from exc
        resolved = source.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise PermissionError("文件路径或符号链接超出 NAS_ROOT")
        return resolved

    def download_file(self, file_info):
        if not self.uses_nas(file_info):
            if not file_info.tokenkey:
                raise ValueError("S3 文件缺少 tokenkey")
            from services.s3_service import s3_service
            return s3_service.download_file(file_info.tokenkey)
        path = self.resolve_nas_path(self.nas_path_of(file_info))
        # NONBLOCK 避免错误路径指向 FIFO 时阻塞；仅接受普通文件。
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("NAS 路径必须指向普通文件")
            if info.st_size > settings.max_file_size:
                raise ValueError("NAS 文件超过 MAX_FILE_SIZE 限制")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(settings.max_file_size + 1)
        finally:
            os.close(fd)
        if len(data) > settings.max_file_size:
            raise ValueError("NAS 文件超过 MAX_FILE_SIZE 限制")
        if not data:
            raise ValueError("NAS 文件为空")
        return data

    def decrypt_file(self, data, file_info):
        if file_info.asecode and (not self.uses_nas(file_info) or settings.nas_files_encrypted):
            from services.decryption_service import decryption_service
            return decryption_service.decrypt_binary_data(data, file_info.asecode)
        return data


file_storage = FileStorage()
