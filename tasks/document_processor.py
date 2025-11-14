from celery import Celery
from celery.signals import worker_ready
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from database import get_db_session
from models import OAFileInfo, ProcessingLog, ProcessingStatus, BusinessCategory
from services.s3_service import s3_service
from services.decryption_service import decryption_service
from services.api_document_parser import api_document_parser
from services.ai_analyzer import ai_analyzer
from services.dify_service import dify_service, multi_kb_manager
from services.file_filter import file_filter
from services.version_manager import version_manager
from config import settings
import json

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建Celery应用
app = Celery('document_processor')
app.conf.update(
    broker_url=settings.redis_url,
    result_backend=settings.redis_url,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    enable_utc=True,
    task_routes={
        'tasks.document_processor.process_document': {'queue': 'document_processing'},
        'tasks.document_processor.batch_process_documents': {'queue': 'batch_processing'},
        'tasks.document_processor.approve_document': {'queue': 'document_processing'},
    },
    task_default_queue='document_processing'
)

def log_processing_step(file_id: str, step: str, status: str, message: str, duration: int = None):
    """记录处理步骤日志"""
    try:
        db = get_db_session()
        log_entry = ProcessingLog(
            file_id=file_id,
            step=step,
            status=status,
            message=message,
            duration_seconds=duration
        )
        db.add(log_entry)
        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"记录处理日志失败: {e}")

def update_file_status(file_id: str, status: ProcessingStatus, message: str = None):
    """更新文件处理状态"""
    try:
        db = get_db_session()
        file_info = db.query(OAFileInfo).filter(OAFileInfo.imagefileid == file_id).first()
        if file_info:
            file_info.processing_status = status
            if message:
                file_info.processing_message = message

            if status == ProcessingStatus.PENDING:
                file_info.processing_started_at = datetime.now()
            elif status in [ProcessingStatus.COMPLETED, ProcessingStatus.FAILED, ProcessingStatus.SKIPPED]:
                file_info.processing_completed_at = datetime.now()

            db.commit()
        db.close()
    except Exception as e:
        logger.error(f"更新文件状态失败: {e}")

def can_process_file(file_id: str) -> bool:
    """检查文件是否可以被处理（防止重复处理已跳过的文档）"""
    try:
        db = get_db_session()
        file_info = db.query(OAFileInfo).filter(OAFileInfo.imagefileid == file_id).first()
        db.close()

        if not file_info:
            logger.warning(f"文件不存在: {file_id}")
            return False

        # 只有 PENDING 状态的文档才能被处理
        if file_info.processing_status != ProcessingStatus.PENDING:
            logger.info(f"文件 {file_id} 状态为 {file_info.processing_status.value}，跳过处理")
            return False

        return True
    except Exception as e:
        logger.error(f"检查文件处理状态失败: {e}")
        return False

@app.task(bind=True, max_retries=3, default_retry_delay=300)
def process_document(self, file_id: str):
    """
    处理单个文档的完整流程 - 支持多知识库和分类映射
    
    Args:
        file_id: 文件ID
    """
    start_time = datetime.now()
    db = None
    
    try:
        logger.info(f"开始处理文档: {file_id}")

        # 检查文件是否可以被处理（防止重复处理已跳过的文档）
        if not can_process_file(file_id):
            logger.info(f"文档 {file_id} 无法处理，可能已被跳过或正在处理中")
            return {'success': False, 'error': '文档无法处理，状态不正确'}

        # 获取数据库会话
        db = get_db_session()
        file_info = db.query(OAFileInfo).filter(OAFileInfo.imagefileid == file_id).first()

        if not file_info:
            logger.error(f"文件信息不存在: {file_id}")
            return {'success': False, 'error': '文件信息不存在'}
        
        # 步骤0: 文件筛选检查
        # logger.info(f"开始文件筛选检查: {file_id}")
        # filter_result = file_filter.should_process_file(file_info)

        # if not filter_result['should_process']:
        #     logger.info(f"文件筛选未通过: {file_id} - {filter_result['skip_reason']}")
        #     update_file_status(file_id, ProcessingStatus.SKIPPED, f"筛选未通过: {filter_result['skip_reason']}")
        #     log_processing_step(file_id, "filter_check", "skipped",
        #                       f"筛选未通过: {filter_result['skip_reason']} (应用筛选器: {', '.join(filter_result['filters_applied'])})")
        #     return {
        #         'success': False,
        #         'error': filter_result['skip_reason'],
        #         'filter_result': filter_result
        #     }

        # logger.info(f"文件筛选通过: {file_id} (应用筛选器: {', '.join(filter_result['filters_applied'])})")
        # log_processing_step(file_id, "filter_check", "success",
        #                   f"筛选通过 (应用筛选器: {', '.join(filter_result['filters_applied'])})")
        
        update_file_status(file_id, ProcessingStatus.DOWNLOADING, "开始下载")
        
        # 步骤1: 从S3下载文档
        step_start = datetime.now()
        try:
            file_data = s3_service.download_file(file_info.tokenkey)
            step_duration = (datetime.now() - step_start).seconds
            log_processing_step(file_id, "download", "success",
                              f"下载成功，大小: {len(file_data)} 字节", step_duration)

        except Exception as e:
            step_duration = (datetime.now() - step_start).seconds
            error_msg = f"下载失败: {str(e)}"
            log_processing_step(file_id, "download", "failed", error_msg, step_duration)
            update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
            file_info.error_count = (file_info.error_count or 0) + 1
            file_info.last_error = error_msg
            db.commit()
            raise
        
        update_file_status(file_id, ProcessingStatus.DECRYPTING, "开始解密")
        
        # 步骤2: 解密文档
        step_start = datetime.now()
        try:
            if file_info.asecode:
                decrypted_data = decryption_service.decrypt_binary_data(file_data, file_info.asecode)
            else:
                decrypted_data = file_data  # 如果没有解密密码，直接使用原数据
            
            step_duration = (datetime.now() - step_start).seconds
            log_processing_step(file_id, "decrypt", "success", 
                              f"解密成功，大小: {len(decrypted_data)} 字节", step_duration)
        except Exception as e:
            step_duration = (datetime.now() - step_start).seconds
            error_msg = f"解密失败: {str(e)}"
            log_processing_step(file_id, "decrypt", "failed", error_msg, step_duration)
            update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
            file_info.error_count = (file_info.error_count or 0) + 1
            file_info.last_error = error_msg
            db.commit()
            raise
        
        update_file_status(file_id, ProcessingStatus.PARSING, "开始解析")
        
        # 步骤3: 解析文档内容
        step_start = datetime.now()
        try:
            # 用于存储最终处理的文件内容和名称（用于后续Dify上传）
            final_file_content = decrypted_data
            final_filename = file_info.imagefilename
            
            # 如果是ZIP文件，先提取唯一文件的二进制内容
            if file_info.is_zip :
                extracted_content = decryption_service.extract_zip_files(decrypted_data)
                parse_result = api_document_parser.parse_document(extracted_content, file_info.imagefilename)
                # 更新为提取出的文件内容和最终文件名（来自数据库字段）
                final_file_content = extracted_content
                final_filename = file_info.imagefilename
                logger.info(f"ZIP文件处理：使用单一文件 {final_filename} ({len(final_file_content)} 字节) 用于知识库上传")
            else:
                parse_result = api_document_parser.parse_document(decrypted_data, file_info.imagefilename)
            
            step_duration = (datetime.now() - step_start).seconds
            
            if not parse_result['success']:
                error_msg = f"解析失败: {parse_result['error']}"
                log_processing_step(file_id, "parse", "failed", error_msg, step_duration)
                update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
                file_info.error_count = (file_info.error_count or 0) + 1
                file_info.last_error = error_msg
                db.commit()
                return {'success': False, 'error': error_msg}
            
            content = parse_result['content']
            metadata = parse_result['metadata']
            
            log_processing_step(file_id, "parse", "success", 
                              f"解析成功，内容长度: {len(content)} 字符", step_duration)
        except Exception as e:
            step_duration = (datetime.now() - step_start).seconds
            error_msg = f"解析失败: {str(e)}"
            log_processing_step(file_id, "parse", "failed", error_msg, step_duration)
            update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
            file_info.error_count = (file_info.error_count or 0) + 1
            file_info.last_error = error_msg
            db.commit()
            raise
        
        update_file_status(file_id, ProcessingStatus.ANALYZING, "AI分析中")
        
        # 步骤4: 增强版AI分析 - 支持分类映射和多知识库
        step_start = datetime.now()
        target_knowledge_base = None
        try:
            # 构建文件信息字典(从数据库字段)
            file_info_dict = {
                'imagefileid': file_info.imagefileid,
                'business_category': file_info.business_category,
                'imagefilename': file_info.imagefilename,
                'imagefiletype': file_info.imagefiletype,
                'is_zw': file_info.is_zw,
                'filesize': file_info.filesize
            }
            
            # 使用新的AI分析器，返回分析结果和目标知识库
            analysis_result, target_knowledge_base = ai_analyzer.analyze_document_content(
                content, file_info.imagefilename, file_info_dict, metadata
            )
            
            step_duration = (datetime.now() - step_start).seconds
            
            kb_info = target_knowledge_base.name if target_knowledge_base else "未找到目标知识库"
            log_processing_step(file_id, "analyze", "success", 
                              f"分析完成 [分类: {file_info.business_category.value}]，适合知识库: {analysis_result['suitable_for_kb']}, 目标知识库: {kb_info}", 
                              step_duration)
            
            # 保存分析结果
            file_info.ai_analysis_result = json.dumps(analysis_result, ensure_ascii=False)
            file_info.ai_confidence_score = analysis_result['confidence_score']
            file_info.should_add_to_kb = analysis_result['suitable_for_kb']
            
        except Exception as e:
            step_duration = (datetime.now() - step_start).seconds
            error_msg = f"AI分析失败: {str(e)}"
            log_processing_step(file_id, "analyze", "failed", error_msg, step_duration)
            # AI分析失败不算致命错误，继续后续处理
            analysis_result = {
                'suitable_for_kb': False,
                'confidence_score': 0,
                'reasons': [f"AI分析失败: {str(e)}"],
                'analysis_method': 'failed',
                'category': file_info.business_category.value if file_info.business_category else 'unknown'
            }
            file_info.ai_analysis_result = json.dumps(analysis_result, ensure_ascii=False)
            file_info.ai_confidence_score = 0
            file_info.should_add_to_kb = False
        
        # 步骤5: 决定下一步处理 - 使用分类特定的阈值
        processor_config = analysis_result.get('processor_config', {})
        auto_approve_threshold = processor_config.get('auto_approve_threshold', 80)
        min_confidence = processor_config.get('min_confidence_score', 40)
        
        if analysis_result['suitable_for_kb'] and analysis_result['confidence_score'] >= auto_approve_threshold:
            # 高置信度，直接加入知识库
            step_start = datetime.now()
            try:
                # 查询对应的知识库并创建Dify服务对象
                if target_knowledge_base:
                    dify_service_instance = multi_kb_manager.get_service_for_knowledge_base(target_knowledge_base)
                    logger.info(f"使用专用知识库服务: {target_knowledge_base.name}")
                else:
                    dify_service_instance = dify_service  # 使用默认服务
                    logger.warning("使用默认知识库服务")
                
                # 使用文本内容直接传入Dify，使用父子分段策略
                dify_result = dify_service_instance.add_document_to_knowledge_base_by_text(
                    content, final_filename, {
                        **metadata,
                        'analysis_result': analysis_result,
                        'file_id': file_id,
                        'business_category': file_info.business_category.value if file_info.business_category else 'unknown'
                    }
                )
                
                step_duration = (datetime.now() - step_start).seconds
                
                if dify_result['success']:
                    file_info.document_id = dify_result.get('document_id')
                    kb_name = dify_result.get('knowledge_base_name', 'unknown')
                    update_file_status(file_id, ProcessingStatus.COMPLETED, f"已成功加入知识库: {kb_name}")
                    log_processing_step(file_id, "add_to_kb", "success", 
                                      f"成功加入知识库 [{kb_name}]: {dify_result.get('document_id')}", 
                                      step_duration)
                else:
                    error_msg = f"加入知识库失败: {dify_result['error']}"
                    update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
                    log_processing_step(file_id, "add_to_kb", "failed", error_msg, step_duration)
                    file_info.error_count = (file_info.error_count or 0) + 1
                    file_info.last_error = error_msg
                
            except Exception as e:
                step_duration = (datetime.now() - step_start).seconds
                error_msg = f"加入知识库异常: {str(e)}"
                log_processing_step(file_id, "add_to_kb", "failed", error_msg, step_duration)
                update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
                file_info.error_count = (file_info.error_count or 0) + 1
                file_info.last_error = error_msg
        
        elif analysis_result['suitable_for_kb'] and analysis_result['confidence_score'] >= min_confidence:
            # 中等置信度，需要人工审核
            kb_info = target_knowledge_base.name if target_knowledge_base else "默认知识库"
            update_file_status(file_id, ProcessingStatus.AWAITING_APPROVAL, f"等待人工审核 (目标知识库: {kb_info})")
            log_processing_step(file_id, "review", "pending", 
                              f"置信度{analysis_result['confidence_score']}%，需要人工审核 (目标知识库: {kb_info})")
        
        else:
            # 低置信度，跳过
            update_file_status(file_id, ProcessingStatus.SKIPPED, 
                             f"置信度过低({analysis_result['confidence_score']}%)，已跳过")
            log_processing_step(file_id, "skip", "success", "置信度过低，自动跳过")
        
        db.commit()
        
        total_duration = (datetime.now() - start_time).seconds
        logger.info(f"文档处理完成: {file_id}, 耗时: {total_duration}秒, 目标知识库: {target_knowledge_base.name if target_knowledge_base else 'None'}")
        
        return {
            'success': True,
            'file_id': file_id,
            'status': file_info.processing_status.value,
            'duration': total_duration,
            'analysis_result': analysis_result,
            'target_knowledge_base': {
                'id': target_knowledge_base.id if target_knowledge_base else None,
                'name': target_knowledge_base.name if target_knowledge_base else None
            }
        }
        
    except Exception as e:
        logger.error(f"处理文档时发生未知错误: {e}")
        import traceback
        traceback.print_exc()
        
        if db and file_info:
            file_info.error_count = (file_info.error_count or 0) + 1
            file_info.last_error = str(e)
            update_file_status(file_id, ProcessingStatus.FAILED, f"未知错误: {str(e)}")
            db.commit()
        
        # 重试机制
        if self.request.retries < self.max_retries:
            logger.info(f"准备重试处理文档: {file_id}, 重试次数: {self.request.retries + 1}")
            raise self.retry(countdown=300, exc=e)
        
        return {'success': False, 'error': str(e)}
    
    finally:
        if db:
            db.close()

@app.task(name='batch_process_documents')
def batch_process_documents(limit: int = 10):
    """
    批量处理待处理的文档
    
    Args:
        limit: 每次处理的文档数量限制
    """
    try:
        db = get_db_session()
        
        # 查询待处理的正文文档，排除已跳过的文档
        pending_files = db.query(OAFileInfo).filter(
            OAFileInfo.is_zw == True,
            OAFileInfo.processing_status == ProcessingStatus.PENDING
        ).limit(limit * 2).all()  # 获取更多文件用于预筛选

        # 预筛选文件，只处理通过筛选的文件
        filtered_files = []
        skipped_count = 0

        for file_info in pending_files:
            if len(filtered_files) >= limit:
                break

            # 进行基础筛选（不包含文件数据的筛选）
            filter_result = file_filter.should_process_file(file_info)

            if filter_result['should_process']:
                filtered_files.append(file_info)
            else:
                # 直接标记为跳过
                try:
                    update_file_status(file_info.imagefileid, ProcessingStatus.SKIPPED,
                                     f"批量处理筛选未通过: {filter_result['skip_reason']}")
                    log_processing_step(file_info.imagefileid, "batch_filter", "skipped",
                                      f"批量筛选: {filter_result['skip_reason']}")
                    skipped_count += 1
                    logger.info(f"批量处理跳过文件: {file_info.imagefilename} - {filter_result['skip_reason']}")
                except Exception as e:
                    logger.error(f"更新跳过状态失败 {file_info.imagefileid}: {e}")

        logger.info(f"批量处理预筛选完成: 原始 {len(pending_files)} 个，筛选后 {len(filtered_files)} 个，跳过 {skipped_count} 个")
        pending_files = filtered_files
        
        logger.info(f"找到 {len(pending_files)} 个待处理文档")
        
        results = []
        for file_info in pending_files:
            try:
                # 异步处理每个文档
                task = process_document.delay(file_info.imagefileid)
                results.append({
                    'file_id': file_info.imagefileid,
                    'task_id': task.id,
                    'filename': file_info.imagefilename,
                    'business_category': file_info.business_category.value if file_info.business_category else 'unknown'
                })
                logger.info(f"已提交处理任务: {file_info.imagefileid} [分类: {file_info.business_category.value if file_info.business_category else 'unknown'}]")
            except Exception as e:
                logger.error(f"提交处理任务失败 {file_info.imagefileid}: {e}")
                results.append({
                    'file_id': file_info.imagefileid,
                    'error': str(e)
                })
        
        db.close()
        
        return {
            'success': True,
            'processed_count': len(results),
            'results': results
        }
        
    except Exception as e:
        logger.error(f"批量处理文档失败: {e}")
        return {
            'success': False,
            'error': str(e)
        }

@app.task
def approve_document(file_id: str, approved: bool, reviewer_comment: str = ""):
    """
    人工审核文档 - 支持多知识库

    Args:
        file_id: 文件ID
        approved: 是否通过审核
        reviewer_comment: 审核意见
    """
    try:
        db = get_db_session()
        file_info = db.query(OAFileInfo).filter(OAFileInfo.imagefileid == file_id).first()

        if not file_info:
            return {'success': False, 'error': '文件信息不存在'}

        if file_info.processing_status != ProcessingStatus.AWAITING_APPROVAL:
            return {'success': False, 'error': '文档状态不正确，无法审核'}

        if approved:
            # 审核通过，加入知识库
            try:
                # 重新解析分析结果
                analysis_result = json.loads(file_info.ai_analysis_result or '{}')

                # 重新从S3下载文档内容并解析
                try:
                    file_data = s3_service.download_file(file_info.tokenkey)
                    logger.info(f"重新下载文件成功，准备解析并加入知识库: {file_info.imagefilename}")

                    # 解密文档
                    if file_info.asecode:
                        decrypted_data = decryption_service.decrypt_binary_data(file_data, file_info.asecode)
                    else:
                        decrypted_data = file_data

                    # 解析文档内容（与自动流程保持一致：ZIP需先解压取唯一文件内容）
                    if file_info.is_zip:
                        extracted_content = decryption_service.extract_zip_files(decrypted_data)
                        parse_result = api_document_parser.parse_document(extracted_content, file_info.imagefilename)
                    else:
                        parse_result = api_document_parser.parse_document(decrypted_data, file_info.imagefilename)

                    if not parse_result['success']:
                        error_msg = f"重新解析文档失败: {parse_result['error']}"
                        logger.error(error_msg)
                        update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
                        log_processing_step(file_id, "manual_approve", "failed", error_msg)
                        return {'success': False, 'error': error_msg}

                    content = parse_result['content']

                except Exception as e:
                    error_msg = f"重新处理文件失败: {str(e)}"
                    logger.error(error_msg)
                    update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
                    log_processing_step(file_id, "manual_approve", "failed", error_msg)
                    return {'success': False, 'error': error_msg}

                # 根据业务分类查询对应的知识库并创建Dify服务对象
                target_kb = ai_analyzer.get_target_knowledge_base(file_info.business_category, db)
                if target_kb:
                    dify_service_instance = multi_kb_manager.get_service_for_knowledge_base(target_kb)
                    logger.info(f"使用目标知识库服务: {target_kb.name}")
                else:
                    dify_service_instance = dify_service  # 使用默认服务
                    logger.warning("使用默认知识库服务进行人工审核")

                # 使用文本内容传入方式，支持父子分段策略
                dify_result = dify_service_instance.add_document_to_knowledge_base_by_text(
                    content, file_info.imagefilename, {
                        'analysis_result': analysis_result,
                        'file_id': file_id,
                        'manual_approved': True,
                        'reviewer_comment': reviewer_comment,
                        'business_category': file_info.business_category.value if file_info.business_category else 'unknown'
                    }
                )

                if dify_result['success']:
                    file_info.document_id = dify_result.get('document_id')
                    kb_name = dify_result.get('knowledge_base_name', target_kb.name if target_kb else 'unknown')
                    update_file_status(file_id, ProcessingStatus.COMPLETED,
                                     f"人工审核通过并加入知识库 [{kb_name}]: {reviewer_comment}")
                    log_processing_step(file_id, "manual_approve", "success",
                                      f"审核通过，加入知识库 [{kb_name}]: {reviewer_comment}")
                else:
                    error_msg = f"加入知识库失败: {dify_result['error']}"
                    update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
                    log_processing_step(file_id, "manual_approve", "failed", error_msg)

            except Exception as e:
                error_msg = f"审核通过后处理失败: {str(e)}"
                update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
                log_processing_step(file_id, "manual_approve", "failed", error_msg)
        else:
            # 审核不通过，跳过
            update_file_status(file_id, ProcessingStatus.SKIPPED,
                             f"人工审核未通过: {reviewer_comment}")
            log_processing_step(file_id, "manual_reject", "success",
                              f"审核未通过: {reviewer_comment}")

        db.commit()
        db.close()

        return {'success': True, 'approved': approved}

    except Exception as e:
        logger.error(f"人工审核失败: {e}")
        return {'success': False, 'error': str(e)}

@app.task(name='clean_headquarters_version_duplicates')
def clean_headquarters_version_duplicates(limit: int = 50):
    """
    清理总行发文的版本重复文档

    Args:
        limit: 每次处理的文档数量限制
    """
    try:
        db = get_db_session()
        logger.info(f"开始清理总行发文版本重复，限制处理: {limit} 个文档")

        stats = version_manager.process_headquarters_version_deduplication(db, limit)

        db.close()

        logger.info(f"总行发文版本去重完成 - 统计: {stats}")
        return stats

    except Exception as e:
        logger.error(f"清理总行发文版本重复失败: {e}")
        return {
            'success': False,
            'error': str(e)
        }

@app.task(name='clean_expired_documents')
def clean_expired_documents(limit: int = 50):
    """
    清理过期文档（除总行发文外）

    Args:
        limit: 每次处理的文档数量限制
    """
    try:
        db = get_db_session()
        logger.info(f"开始清理过期文档，限制处理: {limit} 个文档")

        stats = version_manager.process_document_expiration_check(db, limit)

        db.close()

        logger.info(f"过期文档清理完成 - 统计: {stats}")
        return stats

    except Exception as e:
        logger.error(f"清理过期文档失败: {e}")
        return {
            'success': False,
            'error': str(e)
        }

# 定期任务：每小时检查待处理文档
from celery.schedules import crontab

app.conf.beat_schedule = {
    'batch-process-documents': {
        'task': 'batch_process_documents',
        'schedule': crontab(minute='*/5'),  # 每5分钟执行一次
        'args': (20,)  # 每次处理20个文档
    },
    'clean-headquarters-version-duplicates': {
        'task': 'clean_headquarters_version_duplicates',
        'schedule': crontab(hour='2', minute='0'),  # 每天凌晨2点执行
        'args': (50,)  # 每次处理50个文档
    },
    'clean-expired-documents': {
        'task': 'clean_expired_documents',
        'schedule': crontab(hour='3', minute='0', day_of_week='0'),  # 每周日凌晨3点执行（每7天一次）
        'args': (50,)  # 每次处理50个文档
    },
}

if __name__ == '__main__':
    app.start()
