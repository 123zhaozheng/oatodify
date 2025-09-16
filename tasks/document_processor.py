from celery import Celery
from celery.signals import worker_ready
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from database import get_db_session
from models import OAFileInfo, ProcessingLog, ProcessingStatus
from services.s3_service import s3_service
from services.decryption_service import decryption_service
from services.document_parser import document_parser
from services.ai_analyzer import ai_analyzer
from services.dify_service import dify_service
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

@app.task(bind=True, max_retries=3, default_retry_delay=300)
def process_document(self, file_id: str):
    """
    处理单个文档的完整流程
    
    Args:
        file_id: 文件ID
    """
    start_time = datetime.now()
    db = None
    
    try:
        logger.info(f"开始处理文档: {file_id}")
        
        # 获取数据库会话
        db = get_db_session()
        file_info = db.query(OAFileInfo).filter(OAFileInfo.imagefileid == file_id).first()
        
        if not file_info:
            logger.error(f"文件信息不存在: {file_id}")
            return {'success': False, 'error': '文件信息不存在'}
        
        # 检查是否为正文文档
        if not file_info.is_zw:
            logger.info(f"跳过非正文文档: {file_id}")
            update_file_status(file_id, ProcessingStatus.SKIPPED, "非正文文档")
            return {'success': False, 'error': '非正文文档'}
        
        update_file_status(file_id, ProcessingStatus.DOWNLOADING, "开始下载")
        
        # 步骤1: 从S3下载文档
        step_start = datetime.now()
        try:
            file_data = s3_service.download_file(file_info.imagefileid, file_info.tokenkey)
            step_duration = (datetime.now() - step_start).seconds
            log_processing_step(file_id, "download", "success", 
                              f"下载成功，大小: {len(file_data)} 字节", step_duration)
        except Exception as e:
            step_duration = (datetime.now() - step_start).seconds
            error_msg = f"下载失败: {str(e)}"
            log_processing_step(file_id, "download", "failed", error_msg, step_duration)
            update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
            file_info.error_count += 1
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
            file_info.error_count += 1
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
            
            # 如果是ZIP文件，先提取
            if file_info.is_zip or file_info.imagefilename.lower().endswith('.zip'):
                extracted_files = decryption_service.extract_zip_files(decrypted_data)
                # 选择最大的文档文件进行处理
                if extracted_files:
                    largest_file = max(extracted_files.items(), key=lambda x: len(x[1]))
                    parse_result = document_parser.parse_document(largest_file[1], largest_file[0])
                    # 更新为提取出的文件内容和名称，用于Dify上传
                    final_file_content = largest_file[1]
                    final_filename = largest_file[0]
                    logger.info(f"ZIP文件处理：选择最大文件 {final_filename} ({len(final_file_content)} 字节) 用于知识库上传")
                else:
                    raise Exception("ZIP文件中没有找到可处理的文档")
            else:
                parse_result = document_parser.parse_document(decrypted_data, file_info.imagefilename)
            
            step_duration = (datetime.now() - step_start).seconds
            
            if not parse_result['success']:
                error_msg = f"解析失败: {parse_result['error']}"
                log_processing_step(file_id, "parse", "failed", error_msg, step_duration)
                update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
                file_info.error_count += 1
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
            file_info.error_count += 1
            file_info.last_error = error_msg
            db.commit()
            raise
        
        update_file_status(file_id, ProcessingStatus.ANALYZING, "AI分析中")
        
        # 步骤4: AI分析
        step_start = datetime.now()
        try:
            analysis_result = ai_analyzer.analyze_document_content(
                content, file_info.imagefilename, metadata
            )
            
            step_duration = (datetime.now() - step_start).seconds
            log_processing_step(file_id, "analyze", "success", 
                              f"分析完成，适合知识库: {analysis_result['suitable_for_kb']}", 
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
                'analysis_method': 'failed'
            }
            file_info.ai_analysis_result = json.dumps(analysis_result, ensure_ascii=False)
            file_info.ai_confidence_score = 0
            file_info.should_add_to_kb = False
        
        # 步骤5: 决定下一步处理
        if analysis_result['suitable_for_kb'] and analysis_result['confidence_score'] >= 80:
            # 高置信度，直接加入知识库
            step_start = datetime.now()
            try:
                # 使用文件上传方式，支持DOC转DOCX和父子分段策略
                # 对于ZIP文件使用提取出的文档内容，否则使用原始文件
                dify_result = dify_service.add_document_to_knowledge_base_by_file(
                    final_file_content, final_filename, {
                        **metadata,
                        'analysis_result': analysis_result,
                        'file_id': file_id
                    }
                )
                
                step_duration = (datetime.now() - step_start).seconds
                
                if dify_result['success']:
                    file_info.document_id = dify_result.get('document_id')
                    update_file_status(file_id, ProcessingStatus.COMPLETED, "已成功加入知识库")
                    log_processing_step(file_id, "add_to_kb", "success", 
                                      f"成功加入知识库: {dify_result.get('document_id')}", 
                                      step_duration)
                else:
                    error_msg = f"加入知识库失败: {dify_result['error']}"
                    update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
                    log_processing_step(file_id, "add_to_kb", "failed", error_msg, step_duration)
                    file_info.error_count += 1
                    file_info.last_error = error_msg
                
            except NotImplementedError as e:
                # DOC格式暂不支持，标记为跳过而不是失败
                step_duration = (datetime.now() - step_start).seconds
                skip_msg = f"DOC格式暂不支持: {str(e)}"
                log_processing_step(file_id, "skip_doc", "success", skip_msg, step_duration)
                update_file_status(file_id, ProcessingStatus.SKIPPED, skip_msg)
                logger.warning(f"跳过DOC文件: {file_id} - {final_filename}")
                
            except Exception as e:
                step_duration = (datetime.now() - step_start).seconds
                error_msg = f"加入知识库异常: {str(e)}"
                log_processing_step(file_id, "add_to_kb", "failed", error_msg, step_duration)
                update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
                file_info.error_count += 1
                file_info.last_error = error_msg
        
        elif analysis_result['suitable_for_kb'] and analysis_result['confidence_score'] >= 40:
            # 中等置信度，需要人工审核
            update_file_status(file_id, ProcessingStatus.AWAITING_APPROVAL, "等待人工审核")
            log_processing_step(file_id, "review", "pending", 
                              f"置信度{analysis_result['confidence_score']}%，需要人工审核")
        
        else:
            # 低置信度，跳过
            update_file_status(file_id, ProcessingStatus.SKIPPED, 
                             f"置信度过低({analysis_result['confidence_score']}%)，已跳过")
            log_processing_step(file_id, "skip", "success", "置信度过低，自动跳过")
        
        db.commit()
        
        total_duration = (datetime.now() - start_time).seconds
        logger.info(f"文档处理完成: {file_id}, 耗时: {total_duration}秒")
        
        return {
            'success': True,
            'file_id': file_id,
            'status': file_info.processing_status.value,
            'duration': total_duration,
            'analysis_result': analysis_result
        }
        
    except Exception as e:
        logger.error(f"处理文档时发生未知错误: {e}")
        import traceback
        traceback.print_exc()
        
        if db and file_info:
            file_info.error_count += 1
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

@app.task
def batch_process_documents(limit: int = 10):
    """
    批量处理待处理的文档
    
    Args:
        limit: 每次处理的文档数量限制
    """
    try:
        db = get_db_session()
        
        # 查询待处理的正文文档
        pending_files = db.query(OAFileInfo).filter(
            OAFileInfo.is_zw == True,
            OAFileInfo.processing_status == ProcessingStatus.PENDING
        ).limit(limit).all()
        
        logger.info(f"找到 {len(pending_files)} 个待处理文档")
        
        results = []
        for file_info in pending_files:
            try:
                # 异步处理每个文档
                task = process_document.delay(file_info.imagefileid)
                results.append({
                    'file_id': file_info.imagefileid,
                    'task_id': task.id,
                    'filename': file_info.imagefilename
                })
                logger.info(f"已提交处理任务: {file_info.imagefileid}")
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
    人工审核文档
    
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
                
                # 重新从S3下载文档内容进行知识库上传
                try:
                    file_data = s3_service.download_file(file_info.imagefileid, file_info.tokenkey)
                    logger.info(f"重新下载文件成功，准备加入知识库: {file_info.imagefilename}")
                except Exception as e:
                    error_msg = f"重新下载文件失败: {str(e)}"
                    logger.error(error_msg)
                    update_file_status(file_id, ProcessingStatus.FAILED, error_msg)
                    log_processing_step(file_id, "manual_approve", "failed", error_msg)
                    return {'success': False, 'error': error_msg}
                
                # 使用文件上传方式，支持DOC转DOCX和父子分段策略
                dify_result = dify_service.add_document_to_knowledge_base_by_file(
                    file_data, file_info.imagefilename, {
                        'analysis_result': analysis_result,
                        'file_id': file_id,
                        'manual_approved': True,
                        'reviewer_comment': reviewer_comment
                    }
                )
                
                if dify_result['success']:
                    file_info.document_id = dify_result.get('document_id')
                    update_file_status(file_id, ProcessingStatus.COMPLETED, 
                                     f"人工审核通过并加入知识库: {reviewer_comment}")
                    log_processing_step(file_id, "manual_approve", "success", 
                                      f"审核通过: {reviewer_comment}")
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

# 定期任务：每小时检查待处理文档
from celery.schedules import crontab

app.conf.beat_schedule = {
    'batch-process-documents': {
        'task': 'batch_process_documents',
        'schedule': crontab(minute=0),  # 每小时执行一次
        'args': (20,)  # 每次处理20个文档
    },
}

if __name__ == '__main__':
    app.start()
