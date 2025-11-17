from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, case
from typing import List, Optional
from datetime import datetime, timedelta
import json
import io

from database import get_db
from models import OAFileInfo, ProcessingLog, ProcessingStatus, BusinessCategory
from tasks.document_processor import (
    process_document,
    batch_process_documents,
    approve_document,
    clean_headquarters_version_duplicates,
    clean_expired_documents,
    import_dat_file_task
)
from services.system_monitor import (
    get_system_snapshot,
    get_s3_overview,
    run_s3_full_diagnostics,
    get_dify_overview,
    get_recent_activity as monitor_recent_activity,
    get_recent_errors as monitor_recent_errors,
    get_queue_statistics as monitor_queue_statistics,
)
from services.s3_service import s3_service
from config import settings

router = APIRouter()

@router.get("/files/", summary="获取文件列表")
async def get_files(
    status: Optional[ProcessingStatus] = Query(None, description="按状态筛选"),
    category: Optional[BusinessCategory] = Query(None, description="按业务分类筛选"),
    is_zw: Optional[bool] = Query(True, description="是否只显示正文"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db)
):
    """获取文件列表，支持分页和筛选"""
    try:
        query = db.query(OAFileInfo)
        
        # 应用筛选条件
        if is_zw is not None:
            query = query.filter(OAFileInfo.is_zw == is_zw)
        if status:
            query = query.filter(OAFileInfo.processing_status == status)
        if category:
            query = query.filter(OAFileInfo.business_category == category)
        
        # 计算总数
        total = query.count()
        
        # 应用分页
        files = query.order_by(OAFileInfo.created_at.desc()).offset((page - 1) * size).limit(size).all()
        
        # 格式化返回数据
        items = []
        for file_info in files:
            item = {
                "id": file_info.id,
                "imagefileid": file_info.imagefileid,
                "filename": file_info.imagefilename,
                "file_type": file_info.imagefiletype,
                "business_category": file_info.business_category.value if file_info.business_category else None,
                "filesize": file_info.filesize,
                "processing_status": file_info.processing_status.value,
                "processing_message": file_info.processing_message,
                "ai_confidence_score": file_info.ai_confidence_score,
                "should_add_to_kb": file_info.should_add_to_kb,
                "created_at": file_info.created_at.isoformat() if file_info.created_at else None,
                "processing_started_at": file_info.processing_started_at.isoformat() if file_info.processing_started_at else None,
                "processing_completed_at": file_info.processing_completed_at.isoformat() if file_info.processing_completed_at else None,
                "error_count": file_info.error_count,
                "last_error": file_info.last_error
            }
            
            # 解析AI分析结果
            if file_info.ai_analysis_result:
                try:
                    item["ai_analysis"] = json.loads(file_info.ai_analysis_result)
                except:
                    item["ai_analysis"] = None
            else:
                item["ai_analysis"] = None
                
            items.append(item)
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "pages": (total + size - 1) // size
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {str(e)}")

@router.get("/files/{file_id}", summary="获取文件详情")
async def get_file_detail(file_id: str, db: Session = Depends(get_db)):
    """获取单个文件的详细信息"""
    try:
        file_info = db.query(OAFileInfo).filter(OAFileInfo.imagefileid == file_id).first()
        
        if not file_info:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 获取处理日志
        logs = db.query(ProcessingLog).filter(ProcessingLog.file_id == file_id).order_by(ProcessingLog.created_at.desc()).all()
        
        detail = {
            "id": file_info.id,
            "imagefileid": file_info.imagefileid,
            "filename": file_info.imagefilename,
            "file_type": file_info.imagefiletype,
            "business_category": file_info.business_category.value if file_info.business_category else None,
            "is_zw": file_info.is_zw,
            "is_zip": file_info.is_zip,
            "filesize": file_info.filesize,
            "processing_status": file_info.processing_status.value,
            "processing_message": file_info.processing_message,
            "ai_confidence_score": file_info.ai_confidence_score,
            "should_add_to_kb": file_info.should_add_to_kb,
            "document_id": file_info.document_id,
            "created_at": file_info.created_at.isoformat() if file_info.created_at else None,
            "processing_started_at": file_info.processing_started_at.isoformat() if file_info.processing_started_at else None,
            "processing_completed_at": file_info.processing_completed_at.isoformat() if file_info.processing_completed_at else None,
            "error_count": file_info.error_count,
            "last_error": file_info.last_error,
            "processing_logs": [
                {
                    "step": log.step,
                    "status": log.status,
                    "message": log.message,
                    "duration_seconds": log.duration_seconds,
                    "created_at": log.created_at.isoformat()
                }
                for log in logs
            ]
        }
        
        # 解析AI分析结果
        if file_info.ai_analysis_result:
            try:
                detail["ai_analysis"] = json.loads(file_info.ai_analysis_result)
            except:
                detail["ai_analysis"] = None
        else:
            detail["ai_analysis"] = None
            
        return detail
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件详情失败: {str(e)}")

@router.post("/files/{file_id}/process", summary="手动处理文档")
async def process_file(file_id: str, db: Session = Depends(get_db)):
    """手动触发文档处理"""
    try:
        file_info = db.query(OAFileInfo).filter(OAFileInfo.imagefileid == file_id).first()
        
        if not file_info:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        if not file_info.is_zw:
            raise HTTPException(status_code=400, detail="只能处理正文文档")
        
        if file_info.processing_status in [ProcessingStatus.DOWNLOADING, ProcessingStatus.DECRYPTING, 
                                         ProcessingStatus.PARSING, ProcessingStatus.ANALYZING]:
            raise HTTPException(status_code=400, detail="文档正在处理中，请勿重复提交")
        
        # 重置状态
        file_info.processing_status = ProcessingStatus.PENDING
        file_info.processing_message = "手动触发处理"
        file_info.processing_started_at = None
        file_info.processing_completed_at = None
        db.commit()
        
        # 提交处理任务
        task = process_document.delay(file_id)
        
        return {
            "success": True,
            "message": "处理任务已提交",
            "task_id": task.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提交处理任务失败: {str(e)}")

@router.post("/files/batch-process", summary="批量处理文档")
async def batch_process(limit: int = Query(10, ge=1, le=50, description="处理数量限制")):
    """批量处理待处理的文档"""
    try:
        task = batch_process_documents.delay(limit)
        
        return {
            "success": True,
            "message": f"批量处理任务已提交，限制数量: {limit}",
            "task_id": task.id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量处理任务提交失败: {str(e)}")

class ApprovalRequest(BaseModel):
    approved: bool
    comment: str = ""

@router.post("/files/{file_id}/approve", summary="人工审核文档")
async def approve_file(
    file_id: str,
    request: ApprovalRequest,
    db: Session = Depends(get_db)
):
    """人工审核文档"""
    try:
        # 添加调试日志
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"收到审核请求: file_id={file_id}, approved={request.approved}, comment={request.comment}")
        
        # URL解码处理
        import urllib.parse
        decoded_file_id = urllib.parse.unquote(file_id)
        logger.info(f"解码后的file_id: {decoded_file_id}")
        
        # 尝试用原始file_id查询
        file_info = db.query(OAFileInfo).filter(OAFileInfo.imagefileid == file_id).first()
        
        # 如果没找到，尝试用解码后的file_id查询
        if not file_info:
            file_info = db.query(OAFileInfo).filter(OAFileInfo.imagefileid == decoded_file_id).first()
            logger.info(f"使用解码后的file_id查询结果: {'找到' if file_info else '未找到'}")
        
        # 如果还没找到，尝试用文件名查询
        if not file_info:
            file_info = db.query(OAFileInfo).filter(OAFileInfo.imagefilename == decoded_file_id).first()
            logger.info(f"使用文件名查询结果: {'找到' if file_info else '未找到'}")
            if file_info:
                logger.info(f"通过文件名找到文档，真实imagefileid: {file_info.imagefileid}")
        
        if not file_info:
            raise HTTPException(status_code=404, detail=f"文件不存在，尝试的标识符: {file_id}, 解码后: {decoded_file_id}")
        
        if file_info.processing_status != ProcessingStatus.AWAITING_APPROVAL:
            raise HTTPException(status_code=400, detail=f"文档状态不正确，当前状态: {file_info.processing_status}, 无法审核")
        
        # 使用真实的imagefileid提交审核任务
        actual_file_id = file_info.imagefileid
        task = approve_document.delay(actual_file_id, request.approved, request.comment)
        
        return {
            "success": True,
            "message": "审核任务已提交",
            "task_id": task.id,
            "approved": request.approved,
            "actual_file_id": actual_file_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提交审核任务失败: {str(e)}")

@router.get("/statistics/dashboard", summary="获取仪表板统计数据")
async def get_dashboard_statistics(db: Session = Depends(get_db)):
    """获取仪表板统计数据"""
    try:
        # 基础统计
        total_files = db.query(OAFileInfo).filter(OAFileInfo.is_zw == True).count()
        
        # 按状态统计
        status_stats = db.query(
            OAFileInfo.processing_status,
            func.count(OAFileInfo.id).label('count')
        ).filter(OAFileInfo.is_zw == True).group_by(OAFileInfo.processing_status).all()
        
        status_distribution = {status.value: 0 for status in ProcessingStatus}
        for status, count in status_stats:
            status_distribution[status.value] = count
        
        # 按业务分类统计
        category_stats = db.query(
            OAFileInfo.business_category,
            func.count(OAFileInfo.id).label('count')
        ).filter(OAFileInfo.is_zw == True).group_by(OAFileInfo.business_category).all()
        
        category_distribution = {category.value: 0 for category in BusinessCategory}
        for category, count in category_stats:
            if category:
                category_distribution[category.value] = count
        
        # 今日处理统计
        today = datetime.now().date()
        today_stats = db.query(
            func.count(OAFileInfo.id).label('total'),
            func.coalesce(func.sum(case((OAFileInfo.processing_status == ProcessingStatus.COMPLETED, 1), else_=0)), 0).label('completed'),
            func.coalesce(func.sum(case((OAFileInfo.processing_status == ProcessingStatus.FAILED, 1), else_=0)), 0).label('failed')
        ).filter(
            and_(
                OAFileInfo.is_zw == True,
                func.date(OAFileInfo.processing_started_at) == today
            )
        ).first()
        
        # 错误统计
        error_files = db.query(OAFileInfo).filter(
            and_(
                OAFileInfo.is_zw == True,
                OAFileInfo.error_count > 0
            )
        ).count()
        
        # 待审核统计
        pending_approval = db.query(OAFileInfo).filter(
            and_(
                OAFileInfo.is_zw == True,
                OAFileInfo.processing_status == ProcessingStatus.AWAITING_APPROVAL
            )
        ).count()
        
        return {
            "total_files": total_files,
            "status_distribution": status_distribution,
            "category_distribution": category_distribution,
            "today_processed": today_stats.total or 0,
            "today_completed": today_stats.completed or 0,
            "today_failed": today_stats.failed or 0,
            "error_files": error_files,
            "pending_approval": pending_approval,
            "success_rate": round((today_stats.completed or 0) / max(today_stats.total or 1, 1) * 100, 2) if (today_stats.total or 0) > 0 else 0
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计数据失败: {str(e)}")

@router.get("/statistics/trend", summary="获取趋势数据")
async def get_trend_statistics(
    days: int = Query(7, ge=1, le=30, description="天数"),
    db: Session = Depends(get_db)
):
    """获取最近几天的处理趋势数据"""
    try:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days-1)
        
        # 按日期统计
        daily_stats = db.query(
            func.date(OAFileInfo.processing_started_at).label('date'),
            func.count(OAFileInfo.id).label('total'),
            func.coalesce(func.sum(case((OAFileInfo.processing_status == ProcessingStatus.COMPLETED, 1), else_=0)), 0).label('completed'),
            func.coalesce(func.sum(case((OAFileInfo.processing_status == ProcessingStatus.FAILED, 1), else_=0)), 0).label('failed')
        ).filter(
            and_(
                OAFileInfo.is_zw == True,
                func.date(OAFileInfo.processing_started_at) >= start_date,
                func.date(OAFileInfo.processing_started_at) <= end_date
            )
        ).group_by(func.date(OAFileInfo.processing_started_at)).all()
        
        # 构建完整的日期序列
        trend_data = []
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.isoformat()
            
            # 查找当日数据
            day_data = next((item for item in daily_stats if item.date == current_date), None)
            
            trend_data.append({
                "date": date_str,
                "total": day_data.total if day_data else 0,
                "completed": day_data.completed if day_data else 0,
                "failed": day_data.failed if day_data else 0
            })
            
            current_date += timedelta(days=1)
        
        return {
            "trend_data": trend_data,
            "period": f"{start_date} 至 {end_date}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取趋势数据失败: {str(e)}")

@router.get("/logs/{file_id}", summary="获取文件处理日志")
async def get_file_logs(file_id: str, db: Session = Depends(get_db)):
    """获取指定文件的处理日志"""
    try:
        logs = db.query(ProcessingLog).filter(
            ProcessingLog.file_id == file_id
        ).order_by(ProcessingLog.created_at.asc()).all()
        
        return {
            "file_id": file_id,
            "logs": [
                {
                    "id": log.id,
                    "step": log.step,
                    "status": log.status,
                    "message": log.message,
                    "duration_seconds": log.duration_seconds,
                    "created_at": log.created_at.isoformat()
                }
                for log in logs
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取处理日志失败: {str(e)}")
@router.get("/system/status", summary="获取系统状态概览")
async def get_system_status():
    try:
        return get_system_snapshot()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取系统状态失败: {str(e)}")


@router.get("/system/s3", summary="获取S3配置与状态")
async def get_system_s3_status():
    try:
        return get_s3_overview(include_stats=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取S3状态失败: {str(e)}")


@router.post("/system/s3/test", summary="执行S3诊断")
async def run_system_s3_test():
    try:
        return run_s3_full_diagnostics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"执行S3诊断失败: {str(e)}")


@router.get("/system/dify", summary="获取Dify集成状态")
async def get_system_dify_status():
    try:
        return get_dify_overview()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取Dify状态失败: {str(e)}")


@router.post("/system/dify/test", summary="测试Dify连接")
async def test_system_dify_connection():
    try:
        overview = get_dify_overview()
        return overview.get("connection", overview)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"测试Dify连接失败: {str(e)}")


@router.get("/system/activity", summary="获取最近活动日志")
async def get_system_activity(limit: int = Query(10, ge=1, le=50)):
    try:
        items = monitor_recent_activity(limit=limit)
        return {"items": items, "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取活动日志失败: {str(e)}")


@router.get("/system/errors", summary="获取最近错误")
async def get_system_errors(limit: int = Query(5, ge=1, le=50)):
    try:
        items = monitor_recent_errors(limit=limit)
        return {"items": items, "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取错误信息失败: {str(e)}")


@router.get("/system/queue", summary="获取任务队列统计")
async def get_system_queue():
    try:
        return monitor_queue_statistics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取队列统计失败: {str(e)}")

@router.get("/files/{imagefileid}/attachments", summary="获取文档附件信息")
async def get_file_attachments(imagefileid: str, db: Session = Depends(get_db)):
    """获取指定正文文档的所有附件信息及下载链接"""
    try:
        # 查询正文文档
        main_file = db.query(OAFileInfo).filter(
            and_(
                OAFileInfo.imagefileid == imagefileid,
                OAFileInfo.is_zw == True
            )
        ).first()
        
        if not main_file:
            raise HTTPException(status_code=404, detail="正文文档不存在")
        
        # 解析附件ID列表
        attachment_ids = []
        if main_file.fj_imagefileid:
            try:
                attachment_ids = json.loads(main_file.fj_imagefileid)
                if not isinstance(attachment_ids, list):
                    attachment_ids = [attachment_ids] if attachment_ids else []
            except json.JSONDecodeError:
                # 如果不是JSON格式，尝试按逗号分割
                attachment_ids = [id.strip() for id in main_file.fj_imagefileid.split(',') if id.strip()]
        
        if not attachment_ids:
            return {
                "main_file": {
                    "imagefileid": main_file.imagefileid,
                    "filename": main_file.imagefilename
                },
                "attachments": [],
                "message": "该文档没有附件"
            }
        
        # 查询附件信息
        attachments = db.query(OAFileInfo).filter(
            and_(
                OAFileInfo.imagefileid.in_(attachment_ids),
                OAFileInfo.is_zw == False
            )
        ).all()
        
        # 按文件名去重（保留最新的）
        unique_attachments = {}
        for attachment in attachments:
            filename = attachment.imagefilename
            if filename not in unique_attachments or attachment.created_at > unique_attachments[filename].created_at:
                unique_attachments[filename] = attachment
        
        # 构建返回数据
        attachment_list = []
        base_url = getattr(settings, 'base_url', 'http://localhost:8000')  # 从设置获取基础URL
        
        for attachment in unique_attachments.values():
            download_url = f"{base_url}/oafile/download/{attachment.imagefileid}"
            
            attachment_info = {
                "imagefileid": attachment.imagefileid,
                "imagefilename": attachment.imagefilename,
                "downloadurl": download_url
            }
            attachment_list.append(attachment_info)
        
        return {
            "main_file": {
                "imagefileid": main_file.imagefileid,
                "filename": main_file.imagefilename
            },
            "attachments": attachment_list,
            "total_attachments": len(attachment_list),
            "deduplication_info": {
                "total_found": len(attachments),
                "after_dedup": len(attachment_list),
                "removed_duplicates": len(attachments) - len(attachment_list)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取附件信息失败: {str(e)}")

@router.get("/oafile/download/{imagefileid}", summary="下载文件")
async def download_file(imagefileid: str, db: Session = Depends(get_db)):
    """下载指定文件"""
    try:
        # 查询文件信息
        file_info = db.query(OAFileInfo).filter(OAFileInfo.imagefileid == imagefileid).first()

        if not file_info:
            raise HTTPException(status_code=404, detail="文件不存在")

        if not file_info.tokenkey:
            raise HTTPException(status_code=400, detail="文件下载凭证不存在")

        # 从S3下载文件
        try:
            file_data = s3_service.download_file(file_info.tokenkey)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="文件在存储中不存在")
        except PermissionError:
            raise HTTPException(status_code=403, detail="文件访问权限不足")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"下载文件失败: {str(e)}")

        # 确定文件的MIME类型
        content_type = "application/octet-stream"
        if file_info.imagefiletype:
            ext = file_info.imagefiletype.lower()
            if ext == "pdf":
                content_type = "application/pdf"
            elif ext in ["doc", "docx"]:
                content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if ext == "docx" else "application/msword"
            elif ext == "txt":
                content_type = "text/plain"
            elif ext in ["jpg", "jpeg"]:
                content_type = "image/jpeg"
            elif ext == "png":
                content_type = "image/png"

        # 创建文件流
        file_stream = io.BytesIO(file_data)

        # 返回流式响应
        return StreamingResponse(
            io.BytesIO(file_data),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{file_info.imagefilename}",
                "Content-Length": str(len(file_data))
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载文件时发生错误: {str(e)}")

@router.post("/maintenance/clean-version-duplicates", summary="手动清理总行发文版本重复")
async def manual_clean_version_duplicates(
    limit: int = Query(50, ge=1, le=200, description="每次处理的文档数量限制")
):
    """
    手动触发总行发文版本去重任务

    - 检测文档名中的修订关键词
    - 使用AI判断最新版本
    - 删除旧版本文档
    """
    try:
        # 提交异步任务
        task = clean_headquarters_version_duplicates.delay(limit)

        return {
            "success": True,
            "message": f"总行发文版本去重任务已提交，限制处理: {limit} 个文档",
            "task_id": task.id,
            "description": "任务将检测修订文档并清理旧版本，请查看日志了解详细进度"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提交版本去重任务失败: {str(e)}")

@router.post("/maintenance/clean-expired-documents", summary="手动清理过期文档")
async def manual_clean_expired_documents(
    limit: int = Query(50, ge=1, le=200, description="每次处理的文档数量限制")
):
    """
    手动触发过期文档清理任务

    - 检查ai_metadata中的expiration_date
    - 对于没有元数据的文档，使用AI判断
    - 删除过期文档
    """
    try:
        # 提交异步任务
        task = clean_expired_documents.delay(limit)

        return {
            "success": True,
            "message": f"过期文档清理任务已提交，限制处理: {limit} 个文档",
            "task_id": task.id,
            "description": "任务将检查文档有效期并清理过期文档，请查看日志了解详细进度"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提交过期文档清理任务失败: {str(e)}")

class MaintenanceTaskStatus(BaseModel):
    """维护任务状态查询请求"""
    task_id: str

@router.get("/maintenance/task-status/{task_id}", summary="查询维护任务状态")
async def get_maintenance_task_status(task_id: str):
    """
    查询维护任务的执行状态

    - task_id: 任务ID（从提交任务时返回）
    """
    try:
        from celery.result import AsyncResult
        from celery_app import app as celery_app

        # 获取任务结果
        task_result = AsyncResult(task_id, app=celery_app)

        response = {
            "task_id": task_id,
            "state": task_result.state,
            "ready": task_result.ready(),
            "successful": task_result.successful() if task_result.ready() else None
        }

        # 如果任务完成，返回结果
        if task_result.ready():
            if task_result.successful():
                response["result"] = task_result.result
            else:
                response["error"] = str(task_result.info)
        else:
            # 任务进行中
            response["info"] = task_result.info if task_result.info else "任务正在执行中..."

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询任务状态失败: {str(e)}")

class DATImportRequest(BaseModel):
    """DAT文件导入请求"""
    dat_file_path: Optional[str] = None
    update_existing: Optional[bool] = None

@router.post("/data/import-dat", summary="手动导入DAT文件")
async def manual_import_dat_file(request: DATImportRequest = None):
    """
    手动触发DAT文件导入任务

    - dat_file_path: DAT文件路径（可选，不指定则自动选择最新文件）
    - update_existing: 是否更新已存在的记录（可选，不指定则使用配置文件设置）
    """
    try:
        # 如果没有提供请求体，创建空的请求对象
        if request is None:
            request = DATImportRequest()

        # 提交异步任务
        task = import_dat_file_task.delay(
            dat_file_path=request.dat_file_path,
            update_existing=request.update_existing
        )

        return {
            "success": True,
            "message": "DAT文件导入任务已提交",
            "task_id": task.id,
            "description": "任务将自动导入最新的DAT文件数据，请通过task_id查询任务状态"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提交DAT导入任务失败: {str(e)}")

@router.get("/data/import-status", summary="查询最近的导入记录")
async def get_import_status(db: Session = Depends(get_db)):
    """
    查询最近的数据导入记录统计
    """
    try:
        # 统计最近导入的数据
        recent_imports = db.query(
            func.date(OAFileInfo.last_sync_at).label('sync_date'),
            OAFileInfo.sync_source,
            func.count(OAFileInfo.id).label('count')
        ).filter(
            OAFileInfo.sync_source == 'dat_import'
        ).group_by(
            func.date(OAFileInfo.last_sync_at),
            OAFileInfo.sync_source
        ).order_by(
            func.date(OAFileInfo.last_sync_at).desc()
        ).limit(10).all()

        import_history = []
        for sync_date, sync_source, count in recent_imports:
            import_history.append({
                "date": sync_date.isoformat() if sync_date else None,
                "source": sync_source,
                "count": count
            })

        # 统计总的导入记录数
        total_imported = db.query(OAFileInfo).filter(
            OAFileInfo.sync_source == 'dat_import'
        ).count()

        return {
            "total_imported": total_imported,
            "recent_imports": import_history
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询导入状态失败: {str(e)}")
