import re
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from openai import OpenAI

from models import OAFileInfo, ProcessingStatus, BusinessCategory
from services.s3_service import s3_service
from services.decryption_service import decryption_service
from services.api_document_parser import api_document_parser
from services.dify_service import dify_service, multi_kb_manager
from config import settings

logger = logging.getLogger(__name__)


class VersionManager:
    """文档版本管理和有效期管理服务"""

    def __init__(self):
        self.client = None
        self.model_name = settings.openai_model_name
        self._init_client()

    def _init_client(self):
        """初始化OpenAI客户端"""
        try:
            api_key = settings.openai_api_key
            if not api_key:
                logger.error("未配置OPENAI_API_KEY")
                return

            # 构建客户端参数
            client_kwargs = {"api_key": api_key}

            # 如果配置了自定义base_url，则使用自定义URL
            if settings.openai_base_url:
                client_kwargs["base_url"] = settings.openai_base_url
                logger.info(f"使用自定义OpenAI URL: {settings.openai_base_url}")

            self.client = OpenAI(**client_kwargs)
            logger.info(f"OpenAI客户端初始化成功，模型: {self.model_name}")

        except Exception as e:
            logger.error(f"OpenAI客户端初始化失败: {e}")

    def extract_title_from_brackets(self, filename: str) -> Optional[str]:
        """
        从文档名中提取《》中间的内容

        Args:
            filename: 文件名

        Returns:
            提取的标题，如果没有找到返回None
        """
        pattern = r'《(.+?)》'
        match = re.search(pattern, filename)
        if match:
            return match.group(1)
        return None

    def check_revision_keywords(self, filename: str) -> bool:
        """
        检查文档名是否包含修订等相关字眼

        Args:
            filename: 文件名

        Returns:
            是否包含修订关键词
        """
        revision_keywords = ['修订', '修改', '更新', '调整', '变更', '修正', '补充', '完善', '废止', '废除']
        filename_lower = filename.lower()

        for keyword in revision_keywords:
            if keyword in filename:
                logger.info(f"文档名包含修订关键词: {keyword}")
                return True

        return False

    def find_similar_documents(self, db: Session, title: str, business_category: BusinessCategory) -> List[OAFileInfo]:
        """
        根据标题模糊查询相似文档

        Args:
            db: 数据库会话
            title: 提取的标题
            business_category: 业务分类

        Returns:
            相似文档列表
        """
        # 使用LIKE进行模糊查询
        similar_docs = db.query(OAFileInfo).filter(
            OAFileInfo.business_category == business_category,
            OAFileInfo.imagefilename.like(f'%{title}%'),
            OAFileInfo.processing_status == ProcessingStatus.COMPLETED,
            OAFileInfo.document_id.isnot(None)  # 只查询已成功加入知识库的文档
        ).all()

        logger.info(f"找到 {len(similar_docs)} 个标题包含 '{title}' 的文档")
        return similar_docs

    def download_and_extract_document_preview(self, file_info: OAFileInfo, preview_length: int = 400) -> Optional[str]:
        """
        下载并提取文档的前N个字符

        Args:
            file_info: 文件信息
            preview_length: 预览长度，默认400字符

        Returns:
            文档预览内容，失败返回None
        """
        try:
            # 下载文件
            file_data = s3_service.download_file(file_info.tokenkey)
            logger.info(f"下载文件成功: {file_info.imagefilename}, 大小: {len(file_data)} 字节")

            # 解密文件
            if file_info.asecode:
                decrypted_data = decryption_service.decrypt_binary_data(file_data, file_info.asecode)
            else:
                decrypted_data = file_data

            logger.info(f"解密完成: {file_info.imagefilename}")

            # 如果是ZIP文件，先解压
            if file_info.is_zip:
                extracted_content = decryption_service.extract_zip_files(decrypted_data)
                parse_result = api_document_parser.parse_document(extracted_content, file_info.imagefilename)
            else:
                parse_result = api_document_parser.parse_document(decrypted_data, file_info.imagefilename)

            if not parse_result['success']:
                logger.error(f"解析文档失败: {parse_result['error']}")
                return None

            content = parse_result['content']

            # 提取前preview_length个字符
            preview = content[:preview_length] if len(content) > preview_length else content

            logger.info(f"成功提取文档预览: {file_info.imagefilename}, 预览长度: {len(preview)} 字符")
            return preview

        except Exception as e:
            logger.error(f"下载和提取文档预览失败 {file_info.imagefilename}: {e}")
            return None

    def compare_versions_by_ai(self, documents_with_previews: List[Tuple[OAFileInfo, str]]) -> Optional[str]:
        """
        通过AI判断哪个文档是最新版本

        Args:
            documents_with_previews: 包含文档信息和预览内容的列表

        Returns:
            最新版本文档的imagefileid，失败返回None
        """
        if not self.client:
            logger.error("OpenAI客户端未初始化")
            return None

        if not documents_with_previews or len(documents_with_previews) < 2:
            logger.warning("文档数量不足，无需比较")
            return None

        try:
            # 构建提示词
            doc_info_list = []
            for idx, (file_info, preview) in enumerate(documents_with_previews):
                doc_info_list.append(f"""
文档 {idx + 1}:
- 文件ID: {file_info.imagefileid}
- 文件名: {file_info.imagefilename}
- 内容预览（前400字）:
{preview}
""")

            prompt = f"""
你是一个专业的文档版本分析专家。现在有 {len(documents_with_previews)} 个相似的文档，需要你判断哪个是最新版本。

{chr(10).join(doc_info_list)}

请仔细分析每个文档的内容预览，特别关注：
1. 文档开头的发文号（例如：昆农商发【2025】xxx号）
2. 文档中提到的版本号、修订日期等信息
3. 文档名中的修订标识

请返回JSON格式的结果，包含以下字段：
{{
    "latest_document_id": "最新版本文档的文件ID",
    "reasoning": "判断理由",
    "version_comparison": "版本对比说明",
    "old_document_ids": ["旧版本文档的文件ID列表"]
}}
"""

            messages = [
                {
                    "role": "system",
                    "content": "你是一个专业的文档版本分析专家，擅长通过文档内容判断版本新旧。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            logger.info(f"AI版本比较请求 - 文档数量: {len(documents_with_previews)}")

            # 调用AI
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=1000
            )

            content_result = response.choices[0].message.content or "{}"
            result = json.loads(content_result)

            latest_doc_id = result.get("latest_document_id")
            reasoning = result.get("reasoning", "")
            old_doc_ids = result.get("old_document_ids", [])

            logger.info(f"AI版本比较完成 - 最新版本: {latest_doc_id}")
            logger.info(f"判断理由: {reasoning}")
            logger.info(f"旧版本文档: {old_doc_ids}")

            return {
                'latest_document_id': latest_doc_id,
                'reasoning': reasoning,
                'old_document_ids': old_doc_ids,
                'version_comparison': result.get('version_comparison', '')
            }

        except Exception as e:
            logger.error(f"AI版本比较失败: {e}")
            return None

    def delete_document_from_dify(self, file_info: OAFileInfo, db: Session) -> bool:
        """
        从Dify知识库中删除文档

        Args:
            file_info: 文件信息
            db: 数据库会话

        Returns:
            是否删除成功
        """
        if not file_info.document_id:
            logger.warning(f"文档 {file_info.imagefileid} 没有document_id，无法删除")
            return False

        try:
            # 根据业务分类获取对应的知识库
            from services.ai_analyzer import ai_analyzer
            target_kb = ai_analyzer.get_target_knowledge_base(file_info.business_category, db)

            if target_kb:
                dify_service_instance = multi_kb_manager.get_service_for_knowledge_base(target_kb)
                logger.info(f"使用专用知识库服务删除文档: {target_kb.name}")
            else:
                dify_service_instance = dify_service
                logger.warning("使用默认知识库服务删除文档")

            # 调用删除接口
            result = dify_service_instance.delete_document_from_knowledge_base(file_info.document_id)

            if result['success']:
                logger.info(f"成功从知识库删除文档: {file_info.imagefilename} (document_id: {file_info.document_id})")

                # 更新数据库记录
                file_info.processing_status = ProcessingStatus.SKIPPED
                file_info.processing_message = f"旧版本文档已删除 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                file_info.document_id = None
                db.commit()

                return True
            else:
                logger.error(f"删除文档失败: {result['error']}")
                return False

        except Exception as e:
            logger.error(f"删除文档时发生异常: {e}")
            return False

    def process_headquarters_version_deduplication(self, db: Session, limit: int = 50) -> Dict:
        """
        处理总行发文的版本去重

        Args:
            db: 数据库会话
            limit: 每次处理的文档数量限制

        Returns:
            处理结果统计
        """
        stats = {
            'processed': 0,
            'duplicates_found': 0,
            'deleted': 0,
            'errors': 0,
            'details': []
        }

        try:
            # 查询所有已完成的总行发文
            headquarters_docs = db.query(OAFileInfo).filter(
                OAFileInfo.business_category == BusinessCategory.HEADQUARTERS_ISSUE,
                OAFileInfo.processing_status == ProcessingStatus.COMPLETED,
                OAFileInfo.document_id.isnot(None)
            ).limit(limit).all()

            logger.info(f"找到 {len(headquarters_docs)} 个总行发文待处理")

            for file_info in headquarters_docs:
                stats['processed'] += 1

                try:
                    # 检查文档名是否包含修订关键词
                    if not self.check_revision_keywords(file_info.imagefilename):
                        logger.debug(f"文档不含修订关键词，跳过: {file_info.imagefilename}")
                        continue

                    # 提取标题
                    title = self.extract_title_from_brackets(file_info.imagefilename)
                    if not title:
                        logger.warning(f"无法从文档名提取标题: {file_info.imagefilename}")
                        continue

                    logger.info(f"提取标题: {title}")

                    # 查找相似文档
                    similar_docs = self.find_similar_documents(db, title, BusinessCategory.HEADQUARTERS_ISSUE)

                    if len(similar_docs) <= 1:
                        logger.info(f"没有找到重复文档，跳过: {title}")
                        continue

                    stats['duplicates_found'] += 1
                    logger.info(f"找到 {len(similar_docs)} 个相似文档")

                    # 下载并提取文档预览
                    documents_with_previews = []
                    for doc in similar_docs:
                        preview = self.download_and_extract_document_preview(doc, preview_length=400)
                        if preview:
                            documents_with_previews.append((doc, preview))

                    if len(documents_with_previews) < 2:
                        logger.warning(f"可下载的文档不足2个，跳过版本比较")
                        continue

                    # 使用AI判断最新版本
                    comparison_result = self.compare_versions_by_ai(documents_with_previews)

                    if not comparison_result:
                        logger.error("AI版本比较失败")
                        stats['errors'] += 1
                        continue

                    latest_doc_id = comparison_result['latest_document_id']
                    old_doc_ids = comparison_result['old_document_ids']

                    # 删除旧版本文档
                    deleted_count = 0
                    for old_id in old_doc_ids:
                        old_file = db.query(OAFileInfo).filter(
                            OAFileInfo.imagefileid == old_id
                        ).first()

                        if old_file and self.delete_document_from_dify(old_file, db):
                            deleted_count += 1
                            stats['deleted'] += 1

                    stats['details'].append({
                        'title': title,
                        'latest_document': latest_doc_id,
                        'deleted_count': deleted_count,
                        'reasoning': comparison_result['reasoning']
                    })

                except Exception as e:
                    logger.error(f"处理文档时发生错误 {file_info.imagefilename}: {e}")
                    stats['errors'] += 1
                    continue

            return stats

        except Exception as e:
            logger.error(f"处理总行发文版本去重失败: {e}")
            stats['errors'] += 1
            return stats

    def check_document_expiration_by_metadata(self, file_info: OAFileInfo) -> Tuple[bool, Optional[str]]:
        """
        通过ai_metadata检查文档是否过期

        Args:
            file_info: 文件信息

        Returns:
            (是否过期, 过期日期)
        """
        try:
            if not file_info.ai_analysis_result:
                return False, None

            analysis_result = json.loads(file_info.ai_analysis_result)
            ai_metadata = analysis_result.get('ai_metadata', {})

            expiration_date_str = ai_metadata.get('expiration_date')

            if not expiration_date_str:
                logger.debug(f"文档 {file_info.imagefilename} 没有有效期信息")
                return False, None

            # 检查是否为永久有效
            if expiration_date_str in ['永久', '无', 'permanent', 'none', 'never', '长期']:
                logger.info(f"文档 {file_info.imagefilename} 永久有效")
                return False, expiration_date_str

            # 尝试解析日期
            try:
                # 支持多种日期格式
                date_formats = ['%Y-%m-%d', '%Y/%m/%d', '%Y年%m月%d日']
                expiration_date = None

                for fmt in date_formats:
                    try:
                        expiration_date = datetime.strptime(expiration_date_str, fmt)
                        break
                    except ValueError:
                        continue

                if not expiration_date:
                    logger.warning(f"无法解析有效期日期: {expiration_date_str}")
                    return False, expiration_date_str

                # 比较日期
                now = datetime.now()
                is_expired = expiration_date < now

                if is_expired:
                    logger.info(f"文档 {file_info.imagefilename} 已过期，有效期: {expiration_date_str}")
                else:
                    logger.debug(f"文档 {file_info.imagefilename} 未过期，有效期: {expiration_date_str}")

                return is_expired, expiration_date_str

            except Exception as e:
                logger.error(f"解析日期失败 {expiration_date_str}: {e}")
                return False, expiration_date_str

        except Exception as e:
            logger.error(f"检查文档有效期失败 {file_info.imagefilename}: {e}")
            return False, None

    def check_document_expiration_by_ai(self, file_info: OAFileInfo, preview_content: str) -> Tuple[bool, str]:
        """
        通过AI判断文档是否过期

        Args:
            file_info: 文件信息
            preview_content: 文档预览内容

        Returns:
            (是否过期, 判断理由)
        """
        if not self.client:
            logger.error("OpenAI客户端未初始化")
            return False, "AI客户端未初始化"

        try:
            today = datetime.now().strftime('%Y-%m-%d')

            prompt = f"""
今天的日期是: {today}

请分析以下文档是否已经过期。重点关注：
1. 文档标题中的日期信息
2. 文档内容中提到的时间区间、有效期
3. 文档中的生效日期和失效日期

文档信息：
- 文件名: {file_info.imagefilename}
- 内容预览:
{preview_content}

请返回JSON格式的结果：
{{
    "is_expired": true/false,
    "reasoning": "判断理由",
    "expiration_date": "过期日期（如果能找到）",
    "confidence": 0-100
}}
"""

            messages = [
                {
                    "role": "system",
                    "content": "你是一个专业的文档有效期分析专家，擅长判断文档是否过期。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            logger.info(f"AI有效期检查请求 - 文档: {file_info.imagefilename}")

            # 调用AI
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=500
            )

            content_result = response.choices[0].message.content or "{}"
            result = json.loads(content_result)

            is_expired = result.get("is_expired", False)
            reasoning = result.get("reasoning", "")

            logger.info(f"AI有效期检查完成 - 文档: {file_info.imagefilename}, 是否过期: {is_expired}")
            logger.info(f"判断理由: {reasoning}")

            return is_expired, reasoning

        except Exception as e:
            logger.error(f"AI有效期检查失败: {e}")
            return False, f"检查失败: {str(e)}"

    def process_document_expiration_check(self, db: Session, limit: int = 50) -> Dict:
        """
        处理文档有效期检查（排除总行发文）

        Args:
            db: 数据库会话
            limit: 每次处理的文档数量限制

        Returns:
            处理结果统计
        """
        stats = {
            'processed': 0,
            'expired_by_metadata': 0,
            'expired_by_ai': 0,
            'deleted': 0,
            'errors': 0,
            'details': []
        }

        try:
            # 查询所有已完成的非总行发文
            documents = db.query(OAFileInfo).filter(
                OAFileInfo.business_category != BusinessCategory.HEADQUARTERS_ISSUE,
                OAFileInfo.processing_status == ProcessingStatus.COMPLETED,
                OAFileInfo.document_id.isnot(None)
            ).limit(limit).all()

            logger.info(f"找到 {len(documents)} 个非总行发文待检查有效期")

            for file_info in documents:
                stats['processed'] += 1

                try:
                    # 先检查ai_metadata中的有效期
                    is_expired, expiration_info = self.check_document_expiration_by_metadata(file_info)

                    if is_expired:
                        stats['expired_by_metadata'] += 1

                        # 删除过期文档
                        if self.delete_document_from_dify(file_info, db):
                            stats['deleted'] += 1
                            stats['details'].append({
                                'filename': file_info.imagefilename,
                                'expiration_date': expiration_info,
                                'check_method': 'metadata'
                            })

                        continue

                    # 如果ai_metadata为空或没有有效期信息，使用AI判断
                    if not file_info.ai_analysis_result or not expiration_info:
                        logger.info(f"文档 {file_info.imagefilename} 没有有效期元数据，使用AI判断")

                        # 下载并提取文档预览
                        preview = self.download_and_extract_document_preview(file_info, preview_length=600)

                        if not preview:
                            logger.warning(f"无法获取文档预览，跳过: {file_info.imagefilename}")
                            stats['errors'] += 1
                            continue

                        # 使用AI判断是否过期
                        is_expired_ai, reasoning = self.check_document_expiration_by_ai(file_info, preview)

                        if is_expired_ai:
                            stats['expired_by_ai'] += 1

                            # 删除过期文档
                            if self.delete_document_from_dify(file_info, db):
                                stats['deleted'] += 1
                                stats['details'].append({
                                    'filename': file_info.imagefilename,
                                    'reasoning': reasoning,
                                    'check_method': 'ai'
                                })

                except Exception as e:
                    logger.error(f"处理文档有效期检查时发生错误 {file_info.imagefilename}: {e}")
                    stats['errors'] += 1
                    continue

            return stats

        except Exception as e:
            logger.error(f"处理文档有效期检查失败: {e}")
            stats['errors'] += 1
            return stats


# 创建全局实例
version_manager = VersionManager()
