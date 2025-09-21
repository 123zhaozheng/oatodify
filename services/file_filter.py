import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from models import OAFileInfo, ProcessingStatus, BusinessCategory
from utils.file_utils import  format_file_size
from database import get_db_session
from config import settings

logger = logging.getLogger(__name__)


class FileFilter:
    """文件筛选器 - 处理文件类型检测、关键字筛选和重复文件检测"""

    def __init__(self):
        """初始化筛选器"""
        # 从配置文件加载关键字
        self._load_keywords_from_config()

        # 可配置的筛选参数（从配置文件加载）
        self.config = {
            'enable_keyword_filter': settings.filter_enable_keyword_filter,
            'enable_duplicate_filter': settings.filter_enable_duplicate_filter,
            'case_sensitive_keywords': settings.filter_case_sensitive_keywords,
            'max_file_size_mb': settings.filter_max_file_size_mb,
            'min_file_size_bytes': settings.filter_min_file_size_bytes,
        }

    def _load_keywords_from_config(self):
        """从配置文件加载关键字"""
        # 共用关键字（所有业务分类都会检查）
        self.common_keywords = [kw.strip() for kw in settings.filter_keywords_common.split(',') if kw.strip()]

        # 按业务分类的关键字
        self.business_category_keywords = {
            BusinessCategory.HEADQUARTERS_ISSUE: [kw.strip() for kw in getattr(settings, 'filter_keywords_headquarters_issue', '').split(',') if kw.strip()],
            BusinessCategory.RETAIL_ANNOUNCEMENT: [kw.strip() for kw in getattr(settings, 'filter_keywords_retail_announcement', '').split(',') if kw.strip()],
            BusinessCategory.PUBLICATION_RELEASE: [kw.strip() for kw in getattr(settings, 'filter_keywords_publication_release', '').split(',') if kw.strip()],
            BusinessCategory.BRANCH_ISSUE: [kw.strip() for kw in getattr(settings, 'filter_keywords_branch_issue', '').split(',') if kw.strip()],
            BusinessCategory.BRANCH_RECEIVE: [kw.strip() for kw in getattr(settings, 'filter_keywords_branch_receive', '').split(',') if kw.strip()],
            BusinessCategory.PUBLIC_STANDARD: [kw.strip() for kw in getattr(settings, 'filter_keywords_public_standard', '').split(',') if kw.strip()],
            BusinessCategory.HEADQUARTERS_RECEIVE: [kw.strip() for kw in getattr(settings, 'filter_keywords_headquarters_receive', '').split(',') if kw.strip()],
            BusinessCategory.CORPORATE_ANNOUNCEMENT: [kw.strip() for kw in getattr(settings, 'filter_keywords_corporate_announcement', '').split(',') if kw.strip()],
        }

        # 保留原有的文件类型关键字作为备用
        self.file_type_keywords = {
            'pdf': [kw.strip() for kw in settings.filter_keywords_pdf.split(',') if kw.strip()],
            'docx': [kw.strip() for kw in settings.filter_keywords_docx.split(',') if kw.strip()],
            'doc': [kw.strip() for kw in settings.filter_keywords_docx.split(',') if kw.strip()],
            'txt': [kw.strip() for kw in settings.filter_keywords_txt.split(',') if kw.strip()],
            'other': [kw.strip() for kw in settings.filter_keywords_other.split(',') if kw.strip()]
        }

        total_business_keywords = sum(len(v) for v in self.business_category_keywords.values())
        logger.info(f"已加载关键字配置 - 共用: {len(self.common_keywords)}个, "
                   f"业务分类: {total_business_keywords}个, "
                   f"文件类型: {sum(len(v) for v in self.file_type_keywords.values())}个")



    def should_process_file(self, file_info: OAFileInfo, file_data: bytes = None) -> Dict:
        """
        判断文件是否应该被处理

        Args:
            file_info: 文件信息对象
            file_data: 文件二进制数据（可选，用于类型检测）

        Returns:
            Dict: 筛选结果 {
                'should_process': bool,
                'skip_reason': str,
                'filters_applied': List[str],
                'file_type_info': Dict,
                'duplicate_info': Dict or None
            }
        """
        result = {
            'should_process': True,
            'skip_reason': '',
            'filters_applied': [],
            'file_type_info': {},
            'duplicate_info': None
        }

        try:
            logger.info(f"开始筛选文件: {file_info.imagefilename} (ID: {file_info.imagefileid})")

            # 1. 基础验证
            basic_check = self._basic_validation(file_info)
            if not basic_check['is_valid']:
                result['should_process'] = False
                result['skip_reason'] = basic_check['reason']
                result['filters_applied'].append('basic_validation')
                return result

            # 2. 文件类型检测和筛选
            # if file_data:
            #     type_check = self._check_file_type(file_info, file_data)
            #     result['file_type_info'] = type_check
            #     result['filters_applied'].append('file_type_detection')

            #     if not type_check.get('is_processable', True):
            #         result['should_process'] = False
            #         result['skip_reason'] = f"文件类型不支持: {type_check.get('file_type', 'unknown')}"
            #         return result

            # 3. 关键字筛选（根据业务分类使用不同关键字）
            if self.config['enable_keyword_filter']:
                keyword_check = self._check_keywords(file_info.imagefilename, file_info.business_category)
                result['filters_applied'].append('keyword_filter')

                if keyword_check['should_skip']:
                    result['should_process'] = False
                    result['skip_reason'] = f"文件名包含跳过关键字: {keyword_check['matched_keywords']} (业务分类: {file_info.business_category.value if file_info.business_category else 'unknown'})"
                    return result

            # 4. 重复文件检测
            if self.config['enable_duplicate_filter']:
                duplicate_check = self._check_duplicate(file_info)
                result['duplicate_info'] = duplicate_check
                result['filters_applied'].append('duplicate_filter')

                if duplicate_check['is_duplicate']:
                    result['should_process'] = False
                    result['skip_reason'] = f"文件重复: {duplicate_check['reason']}"
                    return result

            # 5. 文件大小检查
            size_check = self._check_file_size(file_info)
            result['filters_applied'].append('size_filter')

            if not size_check['is_valid']:
                result['should_process'] = False
                result['skip_reason'] = size_check['reason']
                return result

            logger.info(f"文件筛选通过: {file_info.imagefilename}")
            return result

        except Exception as e:
            logger.error(f"文件筛选过程出错: {e}")
            result['should_process'] = False
            result['skip_reason'] = f"筛选过程出错: {str(e)}"
            result['filters_applied'].append('error')
            return result

    def _basic_validation(self, file_info: OAFileInfo) -> Dict:
        """基础验证"""
        try:
            # 检查是否为正文文档
            if not file_info.is_zw:
                return {
                    'is_valid': False,
                    'reason': '非正文文档，跳过处理'
                }

            # 检查文件名
            if not file_info.imagefilename or file_info.imagefilename.strip() == "":
                return {
                    'is_valid': False,
                    'reason': '文件名为空或无效'
                }

            # 检查必要的下载信息
            if not file_info.tokenkey:
                return {
                    'is_valid': False,
                    'reason': '缺少下载tokenkey'
                }

            return {'is_valid': True}

        except Exception as e:
            logger.error(f"基础验证失败: {e}")
            return {
                'is_valid': False,
                'reason': f'基础验证出错: {str(e)}'
            }

    def _check_file_type(self, file_info: OAFileInfo, file_data: bytes) -> Dict:
        """检查文件类型"""
        try:
            # 使用已有的文件类型检测器
            type_result = FileTypeDetector.detect_file_type(file_data, file_info.imagefilename)

            # 更新文件信息中的类型信息
            detected_type = type_result['file_type']

            # 检查是否为支持的文档类型
            supported_types = ['pdf', 'docx', 'doc', 'txt', 'html', 'xml', 'rtf']
            is_processable = detected_type in supported_types or type_result['is_supported']

            result = {
                'file_type': detected_type,
                'mime_type': type_result['mime_type'],
                'confidence': type_result['confidence'],
                'detection_method': type_result['detection_method'],
                'is_supported': type_result['is_supported'],
                'is_processable': is_processable
            }

            # 记录检测结果
            logger.info(f"文件类型检测: {file_info.imagefilename} -> {detected_type} "
                       f"(置信度: {type_result['confidence']}%, 方法: {type_result['detection_method']})")

            return result

        except Exception as e:
            logger.error(f"文件类型检测失败: {e}")
            return {
                'file_type': 'unknown',
                'mime_type': 'application/octet-stream',
                'confidence': 0,
                'detection_method': 'error',
                'is_supported': False,
                'is_processable': False,
                'error': str(e)
            }

    def _check_keywords(self, filename: str, business_category: BusinessCategory = None) -> Dict:
        """检查文件名关键字（根据业务分类）"""
        try:
            if not filename:
                return {'should_skip': False, 'matched_keywords': [], 'checked_keywords_types': []}

            # 根据配置决定是否大小写敏感
            check_filename = filename if self.config['case_sensitive_keywords'] else filename.lower()

            matched_keywords = []
            checked_types = []

            # 1. 检查共用关键字（所有业务分类都检查）
            for keyword in self.common_keywords:
                check_keyword = keyword if self.config['case_sensitive_keywords'] else keyword.lower()
                if check_keyword in check_filename:
                    matched_keywords.append(f"{keyword}(共用)")
            checked_types.append('共用')

            # 2. 检查特定业务分类的关键字
            if business_category and business_category in self.business_category_keywords:
                specific_keywords = self.business_category_keywords[business_category]
                for keyword in specific_keywords:
                    check_keyword = keyword if self.config['case_sensitive_keywords'] else keyword.lower()
                    if check_keyword in check_filename:
                        matched_keywords.append(f"{keyword}({business_category.value})")
                checked_types.append(business_category.value)

            should_skip = len(matched_keywords) > 0

            if should_skip:
                logger.info(f"文件名关键字筛选: {filename} 匹配关键字 {matched_keywords}，跳过处理")

            return {
                'should_skip': should_skip,
                'matched_keywords': matched_keywords,
                'checked_keywords_types': checked_types,
                'business_category': business_category.value if business_category else 'unknown'
            }

        except Exception as e:
            logger.error(f"关键字检查失败: {e}")
            return {
                'should_skip': False,
                'matched_keywords': [],
                'checked_keywords_types': [],
                'error': str(e)
            }

    def _check_duplicate(self, file_info: OAFileInfo) -> Dict:
        """检查重复文件"""
        try:
            db = get_db_session()

            # 查找同名文件，排除当前文件
            duplicate_query = db.query(OAFileInfo).filter(
                and_(
                    OAFileInfo.imagefilename == file_info.imagefilename,
                    OAFileInfo.imagefileid != file_info.imagefileid
                )
            )

            duplicates = duplicate_query.all()

            if not duplicates:
                db.close()
                return {
                    'is_duplicate': False,
                    'reason': '',
                    'duplicate_files': []
                }

            # 检查是否存在已完成或正在处理的同名同大小文件
            for duplicate in duplicates:
                # 检查处理状态 - 包含所有正在处理和已完成的状态
                if duplicate.processing_status in [
                    ProcessingStatus.DOWNLOADING,
                    ProcessingStatus.DECRYPTING,
                    ProcessingStatus.PARSING,
                    ProcessingStatus.ANALYZING,
                    ProcessingStatus.AWAITING_APPROVAL,
                    ProcessingStatus.COMPLETED,
                    ProcessingStatus.SKIPPED
                ]:
                    # 检查文件大小是否相同
                    if duplicate.filesize and file_info.filesize and duplicate.filesize == file_info.filesize:
                        db.close()
                        logger.info(f"发现重复文件: {file_info.imagefilename} "
                                   f"(大小: {format_file_size(file_info.filesize)}) "
                                   f"状态: {duplicate.processing_status.value}")
                        return {
                            'is_duplicate': True,
                            'reason': f'同名同大小文件已存在 (状态: {duplicate.processing_status.value})',
                            'duplicate_files': [{
                                'id': duplicate.imagefileid,
                                'filename': duplicate.imagefilename,
                                'size': duplicate.filesize,
                                'status': duplicate.processing_status.value,
                                'created_at': duplicate.created_at.isoformat() if duplicate.created_at else None
                            }]
                        }

            db.close()

            # 存在同名文件但大小不同或状态不同，不算重复
            return {
                'is_duplicate': False,
                'reason': '存在同名文件但大小或状态不同',
                'duplicate_files': [{
                    'id': dup.imagefileid,
                    'filename': dup.imagefilename,
                    'size': dup.filesize,
                    'status': dup.processing_status.value
                } for dup in duplicates]
            }

        except Exception as e:
            logger.error(f"重复文件检查失败: {e}")
            if 'db' in locals():
                db.close()
            return {
                'is_duplicate': False,
                'reason': f'重复检查出错: {str(e)}',
                'duplicate_files': [],
                'error': str(e)
            }

    def _check_file_size(self, file_info: OAFileInfo) -> Dict:
        """检查文件大小"""
        try:
            if not file_info.filesize:
                return {
                    'is_valid': True,  # 如果没有大小信息，暂时允许通过
                    'reason': '文件大小信息缺失'
                }

            file_size = file_info.filesize

            # 检查最小大小
            if file_size < self.config['min_file_size_bytes']:
                return {
                    'is_valid': False,
                    'reason': f'文件太小 ({format_file_size(file_size)} < {format_file_size(self.config["min_file_size_bytes"])})'
                }

            # 检查最大大小
            max_size_bytes = self.config['max_file_size_mb'] * 1024 * 1024
            if file_size > max_size_bytes:
                return {
                    'is_valid': False,
                    'reason': f'文件太大 ({format_file_size(file_size)} > {format_file_size(max_size_bytes)})'
                }

            return {'is_valid': True}

        except Exception as e:
            logger.error(f"文件大小检查失败: {e}")
            return {
                'is_valid': True,  # 出错时允许通过，避免误判
                'reason': f'大小检查出错: {str(e)}'
            }

    def _guess_file_type_from_extension(self, filename: str) -> str:
        """根据文件扩展名推断文件类型"""
        if not filename:
            return 'other'

        # 提取文件扩展名
        import os
        _, ext = os.path.splitext(filename.lower())
        ext = ext.lstrip('.')

        # 映射文件扩展名到类型
        extension_mapping = {
            'pdf': 'pdf',
            'doc': 'doc',
            'docx': 'docx',
            'txt': 'txt',
            'text': 'txt',
            'log': 'txt',
            'html': 'other',
            'htm': 'other',
            'xml': 'other',
            'rtf': 'other',
            'xls': 'other',
            'xlsx': 'other',
            'ppt': 'other',
            'pptx': 'other',
        }

        return extension_mapping.get(ext, 'other')

    def get_keywords_summary(self) -> Dict:
        """获取关键字配置摘要"""
        return {
            'common_keywords': self.common_keywords,
            'business_category_keywords': {k.value: v for k, v in self.business_category_keywords.items()},
            'file_type_keywords': self.file_type_keywords,
            'total_common': len(self.common_keywords),
            'total_by_business_category': {k.value: len(v) for k, v in self.business_category_keywords.items()},
            'total_by_file_type': {k: len(v) for k, v in self.file_type_keywords.items()}
        }

    def update_config(self, config_updates: Dict):
        """更新配置"""
        self.config.update(config_updates)
        logger.info(f"已更新筛选器配置: {config_updates}")

    def get_filter_stats(self, limit: int = 100) -> Dict:
        """获取筛选统计信息"""
        try:
            db = get_db_session()

            # 统计各种状态的文件数量
            total_files = db.query(OAFileInfo).filter(OAFileInfo.is_zw == True).count()
            pending_files = db.query(OAFileInfo).filter(
                and_(OAFileInfo.is_zw == True, OAFileInfo.processing_status == ProcessingStatus.PENDING)
            ).count()
            completed_files = db.query(OAFileInfo).filter(
                and_(OAFileInfo.is_zw == True, OAFileInfo.processing_status == ProcessingStatus.COMPLETED)
            ).count()
            failed_files = db.query(OAFileInfo).filter(
                and_(OAFileInfo.is_zw == True, OAFileInfo.processing_status == ProcessingStatus.FAILED)
            ).count()
            skipped_files = db.query(OAFileInfo).filter(
                and_(OAFileInfo.is_zw == True, OAFileInfo.processing_status == ProcessingStatus.SKIPPED)
            ).count()

            # 获取最近的待处理文件示例
            recent_pending = db.query(OAFileInfo).filter(
                and_(OAFileInfo.is_zw == True, OAFileInfo.processing_status == ProcessingStatus.PENDING)
            ).order_by(OAFileInfo.created_at.desc()).limit(limit).all()

            db.close()

            return {
                'total_files': total_files,
                'pending_files': pending_files,
                'completed_files': completed_files,
                'failed_files': failed_files,
                'skipped_files': skipped_files,
                'processing_rate': round((completed_files / total_files * 100), 2) if total_files > 0 else 0,
                'recent_pending_files': [{
                    'id': f.imagefileid,
                    'filename': f.imagefilename,
                    'size': f.filesize,
                    'business_category': f.business_category.value if f.business_category else 'unknown',
                    'created_at': f.created_at.isoformat() if f.created_at else None
                } for f in recent_pending],
                'current_config': self.config,
                'keywords_summary': self.get_keywords_summary()
            }

        except Exception as e:
            logger.error(f"获取筛选统计失败: {e}")
            return {
                'error': str(e),
                'current_config': self.config,
                'keywords_summary': self.get_keywords_summary()
            }


# 创建全局筛选器实例
file_filter = FileFilter()