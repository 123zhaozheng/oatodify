from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, case
from typing import List, Optional
from datetime import datetime, timedelta
import json

from database import get_db
from models import OAFileInfo, ProcessingLog, ProcessingStatus, BusinessCategory
from tasks.document_processor import process_document, batch_process_documents, approve_document
from services.system_monitor import (
    get_system_snapshot,
    get_s3_overview,
    run_s3_full_diagnostics,
    get_dify_overview,
    get_recent_activity as monitor_recent_activity,
    get_recent_errors as monitor_recent_errors,
    get_queue_statistics as monitor_queue_statistics,
)

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

@router.post("/files/{file_id}/approve", summary="人工审核文档")
async def approve_file(
    file_id: str,
    approved: bool,
    comment: str = "",
    db: Session = Depends(get_db)
):
    """人工审核文档"""
    try:
        file_info = db.query(OAFileInfo).filter(OAFileInfo.imagefileid == file_id).first()
        
        if not file_info:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        if file_info.processing_status != ProcessingStatus.AWAITING_APPROVAL:
            raise HTTPException(status_code=400, detail="文档状态不正确，无法审核")
        
        # 提交审核任务
        task = approve_document.delay(file_id, approved, comment)
        
        return {
            "success": True,
            "message": "审核任务已提交",
            "task_id": task.id,
            "approved": approved
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
