import os
import magic
import hashlib
import mimetypes
from typing import Dict, List, Optional, Tuple, Union
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class FileTypeDetector:
    """文件类型检测器"""
    
    # 支持的文档格式及其MIME类型
    SUPPORTED_FORMATS = {
        'pdf': [
            'application/pdf'
        ],
        'docx': [
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        ],
        'doc': [
            'application/msword'
        ],
        'txt': [
            'text/plain',
            'text/plain; charset=utf-8',
            'text/plain; charset=ascii'
        ],
        'html': [
            'text/html',
            'application/xhtml+xml'
        ],
        'xml': [
            'application/xml',
            'text/xml'
        ],
        'rtf': [
            'application/rtf',
            'text/rtf'
        ],
        'csv': [
            'text/csv',
            'application/csv'
        ],
        'json': [
            'application/json',
            'text/json'
        ]
    }
    
    @classmethod
    def detect_file_type(cls, file_data: bytes, filename: str = "") -> Dict:
        """
        检测文件类型
        
        Args:
            file_data: 文件二进制数据
            filename: 文件名（可选）
            
        Returns:
            Dict: 包含文件类型信息的字典
        """
        result = {
            'file_type': 'unknown',
            'mime_type': 'application/octet-stream',
            'confidence': 0,
            'is_supported': False,
            'detection_method': 'unknown'
        }
        
        try:
            # 方法1: 通过文件扩展名检测
            if filename:
                ext_result = cls._detect_by_extension(filename)
                if ext_result['confidence'] > result['confidence']:
                    result.update(ext_result)
            
            # 方法2: 通过文件头魔数检测
            magic_result = cls._detect_by_magic(file_data)
            if magic_result['confidence'] > result['confidence']:
                result.update(magic_result)
            
            # 方法3: 通过MIME类型检测
            mime_result = cls._detect_by_mime(file_data)
            if mime_result['confidence'] > result['confidence']:
                result.update(mime_result)
            
            # 检查是否为支持的格式
            result['is_supported'] = result['file_type'] in cls.SUPPORTED_FORMATS
            
            return result
            
        except Exception as e:
            logger.error(f"文件类型检测失败: {e}")
            return result
    
    @classmethod
    def _detect_by_extension(cls, filename: str) -> Dict:
        """通过文件扩展名检测"""
        try:
            file_ext = Path(filename).suffix.lower().lstrip('.')
            
            # 检查是否为已知格式
            for file_type, mime_types in cls.SUPPORTED_FORMATS.items():
                if file_ext == file_type:
                    return {
                        'file_type': file_type,
                        'mime_type': mime_types[0],
                        'confidence': 70,  # 扩展名检测置信度中等
                        'detection_method': 'extension'
                    }
            
            # 使用mimetypes库推测
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type:
                for file_type, mime_types in cls.SUPPORTED_FORMATS.items():
                    if mime_type in mime_types:
                        return {
                            'file_type': file_type,
                            'mime_type': mime_type,
                            'confidence': 60,
                            'detection_method': 'extension_mime'
                        }
            
            return {
                'file_type': file_ext if file_ext else 'unknown',
                'mime_type': mime_type or 'application/octet-stream',
                'confidence': 30,
                'detection_method': 'extension_guess'
            }
            
        except Exception as e:
            logger.error(f"扩展名检测失败: {e}")
            return {
                'file_type': 'unknown',
                'mime_type': 'application/octet-stream',
                'confidence': 0,
                'detection_method': 'extension_error'
            }
    
    @classmethod
    def _detect_by_magic(cls, file_data: bytes) -> Dict:
        """通过文件头魔数检测"""
        try:
            # 检查常见的文件头标识
            magic_signatures = {
                b'\x25\x50\x44\x46': 'pdf',  # PDF文件头 %PDF
                b'\x50\x4B\x03\x04': 'docx',  # ZIP/DOCX文件头 PK
                b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1': 'doc',  # DOC文件头
                b'\xEF\xBB\xBF': 'txt',  # UTF-8 BOM
                b'\xFF\xFE': 'txt',  # UTF-16 LE BOM
                b'\xFE\xFF': 'txt',  # UTF-16 BE BOM
                b'<!DOCTYPE html': 'html',
                b'<html': 'html',
                b'<?xml': 'xml',
                b'{\\"': 'json',
                b'{': 'json'
            }
            
            # 检查文件头
            file_head = file_data[:50] if len(file_data) >= 50 else file_data
            
            for signature, file_type in magic_signatures.items():
                if file_head.startswith(signature):
                    mime_type = cls.SUPPORTED_FORMATS.get(file_type, ['application/octet-stream'])[0]
                    return {
                        'file_type': file_type,
                        'mime_type': mime_type,
                        'confidence': 90,  # 魔数检测置信度高
                        'detection_method': 'magic_signature'
                    }
            
            # 尝试使用python-magic库
            try:
                mime_type = magic.from_buffer(file_data, mime=True)
                
                for file_type, mime_types in cls.SUPPORTED_FORMATS.items():
                    if mime_type in mime_types:
                        return {
                            'file_type': file_type,
                            'mime_type': mime_type,
                            'confidence': 85,
                            'detection_method': 'magic_library'
                        }
                
                return {
                    'file_type': 'unknown',
                    'mime_type': mime_type,
                    'confidence': 50,
                    'detection_method': 'magic_library_unknown'
                }
                
            except Exception:
                # python-magic可能未安装或不可用
                pass
            
            return {
                'file_type': 'unknown',
                'mime_type': 'application/octet-stream',
                'confidence': 0,
                'detection_method': 'magic_failed'
            }
            
        except Exception as e:
            logger.error(f"魔数检测失败: {e}")
            return {
                'file_type': 'unknown',
                'mime_type': 'application/octet-stream',
                'confidence': 0,
                'detection_method': 'magic_error'
            }
    
    @classmethod
    def _detect_by_mime(cls, file_data: bytes) -> Dict:
        """通过MIME类型检测"""
        try:
            # 尝试检测文本编码
            if cls._is_text_file(file_data):
                return {
                    'file_type': 'txt',
                    'mime_type': 'text/plain',
                    'confidence': 60,
                    'detection_method': 'mime_text'
                }
            
            return {
                'file_type': 'unknown',
                'mime_type': 'application/octet-stream',
                'confidence': 0,
                'detection_method': 'mime_binary'
            }
            
        except Exception as e:
            logger.error(f"MIME检测失败: {e}")
            return {
                'file_type': 'unknown',
                'mime_type': 'application/octet-stream',
                'confidence': 0,
                'detection_method': 'mime_error'
            }
    
    @classmethod
    def _is_text_file(cls, file_data: bytes, sample_size: int = 1024) -> bool:
        """判断是否为文本文件"""
        try:
            # 取样本数据
            sample = file_data[:sample_size]
            
            # 尝试UTF-8解码
            try:
                sample.decode('utf-8')
                return True
            except UnicodeDecodeError:
                pass
            
            # 检查是否包含大量可打印字符
            printable_chars = sum(1 for byte in sample if 32 <= byte <= 126 or byte in [9, 10, 13])
            ratio = printable_chars / len(sample) if sample else 0
            
            return ratio > 0.7  # 如果70%以上是可打印字符，认为是文本文件
            
        except Exception:
            return False

class FileValidator:
    """文件验证器"""
    
    @staticmethod
    def validate_file(file_data: bytes, filename: str, max_size: int = None) -> Dict:
        """
        验证文件
        
        Args:
            file_data: 文件二进制数据
            filename: 文件名
            max_size: 最大文件大小（字节）
            
        Returns:
            Dict: 验证结果
        """
        result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'file_info': {}
        }
        
        try:
            # 检查文件大小
            file_size = len(file_data)
            result['file_info']['size'] = file_size
            
            if file_size == 0:
                result['is_valid'] = False
                result['errors'].append("文件为空")
                return result
            
            if max_size and file_size > max_size:
                result['is_valid'] = False
                result['errors'].append(f"文件大小超过限制 ({format_file_size(file_size)} > {format_file_size(max_size)})")
            
            # 检查文件名
            if not filename or filename.strip() == "":
                result['warnings'].append("文件名为空")
            else:
                # 检查文件名是否包含非法字符
                illegal_chars = ['<', '>', ':', '"', '|', '?', '*']
                for char in illegal_chars:
                    if char in filename:
                        result['warnings'].append(f"文件名包含非法字符: {char}")
                        break
                
                # 检查文件名长度
                if len(filename) > 255:
                    result['warnings'].append("文件名过长")
            
            # 检测文件类型
            file_type_info = FileTypeDetector.detect_file_type(file_data, filename)
            result['file_info'].update(file_type_info)
            
            if not file_type_info['is_supported']:
                result['warnings'].append(f"不支持的文件类型: {file_type_info['file_type']}")
            
            # 检查文件完整性
            integrity_check = FileValidator._check_file_integrity(file_data, file_type_info['file_type'])
            if not integrity_check['is_valid']:
                result['errors'].extend(integrity_check['errors'])
            result['warnings'].extend(integrity_check['warnings'])
            
            return result
            
        except Exception as e:
            logger.error(f"文件验证失败: {e}")
            result['is_valid'] = False
            result['errors'].append(f"验证过程出错: {str(e)}")
            return result
    
    @staticmethod
    def _check_file_integrity(file_data: bytes, file_type: str) -> Dict:
        """检查文件完整性"""
        result = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        try:
            if file_type == 'pdf':
                # PDF完整性检查
                if not file_data.startswith(b'%PDF'):
                    result['errors'].append("PDF文件头损坏")
                    result['is_valid'] = False
                
                if b'%%EOF' not in file_data:
                    result['warnings'].append("PDF文件可能不完整（缺少EOF标记）")
            
            elif file_type == 'docx':
                # DOCX是ZIP格式，检查ZIP头
                if not file_data.startswith(b'PK'):
                    result['errors'].append("DOCX文件头损坏")
                    result['is_valid'] = False
            
            elif file_type == 'doc':
                # DOC文件头检查
                doc_header = b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'
                if not file_data.startswith(doc_header):
                    result['errors'].append("DOC文件头损坏")
                    result['is_valid'] = False
            
            elif file_type == 'txt':
                # 文本文件编码检查
                try:
                    file_data.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        file_data.decode('gbk')
                    except UnicodeDecodeError:
                        result['warnings'].append("文本文件编码可能有问题")
            
            return result
            
        except Exception as e:
            logger.error(f"完整性检查失败: {e}")
            result['warnings'].append(f"完整性检查出错: {str(e)}")
            return result

class FileHasher:
    """文件哈希计算器"""
    
    @staticmethod
    def calculate_hash(file_data: bytes, algorithm: str = 'sha256') -> str:
        """
        计算文件哈希值
        
        Args:
            file_data: 文件二进制数据
            algorithm: 哈希算法 (md5, sha1, sha256, sha512)
            
        Returns:
            str: 哈希值的十六进制字符串
        """
        try:
            hash_algorithms = {
                'md5': hashlib.md5,
                'sha1': hashlib.sha1,
                'sha256': hashlib.sha256,
                'sha512': hashlib.sha512
            }
            
            if algorithm not in hash_algorithms:
                raise ValueError(f"不支持的哈希算法: {algorithm}")
            
            hasher = hash_algorithms[algorithm]()
            hasher.update(file_data)
            return hasher.hexdigest()
            
        except Exception as e:
            logger.error(f"计算哈希失败: {e}")
            raise
    
    @staticmethod
    def calculate_multiple_hashes(file_data: bytes, algorithms: List[str] = None) -> Dict[str, str]:
        """
        计算多种哈希值
        
        Args:
            file_data: 文件二进制数据
            algorithms: 哈希算法列表
            
        Returns:
            Dict[str, str]: 算法名 -> 哈希值的映射
        """
        if algorithms is None:
            algorithms = ['md5', 'sha256']
        
        results = {}
        for algorithm in algorithms:
            try:
                results[algorithm] = FileHasher.calculate_hash(file_data, algorithm)
            except Exception as e:
                logger.error(f"计算{algorithm}哈希失败: {e}")
                results[algorithm] = None
        
        return results

def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小
    
    Args:
        size_bytes: 文件大小（字节）
        
    Returns:
        str: 格式化后的文件大小字符串
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    
    i = int(math.floor(math.log(size_bytes, 1024)))
    i = min(i, len(size_names) - 1)  # 防止超出范围
    
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    
    return f"{s} {size_names[i]}"

def is_safe_filename(filename: str) -> bool:
    """
    检查文件名是否安全
    
    Args:
        filename: 文件名
        
    Returns:
        bool: 是否安全
    """
    if not filename or filename.strip() == "":
        return False
    
    # 检查非法字符
    illegal_chars = ['<', '>', ':', '"', '|', '?', '*', '/', '\\']
    for char in illegal_chars:
        if char in filename:
            return False
    
    # 检查保留名称（Windows）
    reserved_names = [
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    ]
    
    name_without_ext = os.path.splitext(filename)[0].upper()
    if name_without_ext in reserved_names:
        return False
    
    # 检查长度
    if len(filename) > 255:
        return False
    
    return True

def sanitize_filename(filename: str) -> str:
    """
    清理文件名，使其安全
    
    Args:
        filename: 原始文件名
        
    Returns:
        str: 清理后的文件名
    """
    if not filename:
        return "unnamed_file"
    
    # 替换非法字符
    illegal_chars = ['<', '>', ':', '"', '|', '?', '*', '/', '\\']
    sanitized = filename
    
    for char in illegal_chars:
        sanitized = sanitized.replace(char, '_')
    
    # 移除开头和结尾的空格和点
    sanitized = sanitized.strip(' .')
    
    # 确保不为空
    if not sanitized:
        sanitized = "unnamed_file"
    
    # 限制长度
    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        max_name_length = 255 - len(ext)
        sanitized = name[:max_name_length] + ext
    
    return sanitized

def extract_text_preview(content: str, max_length: int = 200) -> str:
    """
    提取文本预览
    
    Args:
        content: 完整文本内容
        max_length: 最大预览长度
        
    Returns:
        str: 预览文本
    """
    if not content:
        return ""
    
    # 清理文本
    cleaned = content.strip()
    
    # 移除多余的空白字符
    import re
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # 截取预览
    if len(cleaned) <= max_length:
        return cleaned
    
    # 尝试在句号处截断
    truncated = cleaned[:max_length]
    last_period = truncated.rfind('。')
    if last_period > max_length * 0.7:  # 如果句号位置合理
        return truncated[:last_period + 1]
    
    # 否则在空格处截断
    last_space = truncated.rfind(' ')
    if last_space > max_length * 0.7:
        return truncated[:last_space] + "..."
    
    # 直接截断
    return truncated + "..."

def get_file_extension(filename: str) -> str:
    """
    获取文件扩展名
    
    Args:
        filename: 文件名
        
    Returns:
        str: 扩展名（小写，不包含点）
    """
    if not filename:
        return ""
    
    ext = Path(filename).suffix.lower().lstrip('.')
    return ext

def is_archive_file(filename: str) -> bool:
    """
    判断是否为压缩文件
    
    Args:
        filename: 文件名
        
    Returns:
        bool: 是否为压缩文件
    """
    archive_extensions = ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz']
    ext = get_file_extension(filename)
    return ext in archive_extensions

def get_content_type(filename: str) -> str:
    """
    根据文件名获取Content-Type
    
    Args:
        filename: 文件名
        
    Returns:
        str: Content-Type
    """
    content_types = {
        'pdf': 'application/pdf',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'doc': 'application/msword',
        'txt': 'text/plain',
        'html': 'text/html',
        'xml': 'application/xml',
        'json': 'application/json',
        'csv': 'text/csv'
    }
    
    ext = get_file_extension(filename)
    return content_types.get(ext, 'application/octet-stream')
