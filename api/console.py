"""Operations console APIs for daily task visibility and document lookup."""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from database import get_db
from services import operations
from tasks.document_processor import (
    batch_process_documents,
    clean_expired_documents,
    clean_headquarters_version_duplicates,
    import_dat_file_task,
)


router = APIRouter()


@router.get("/console/daily", summary="获取每日运行过程")
def console_daily(date: Optional[str] = Query(None, description="北京时间日期，格式 YYYY-MM-DD"), db: Session = Depends(get_db)):
    try:
        return operations.get_daily(db, date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="获取每日运行过程失败")


@router.get("/console/trend", summary="获取每日处理趋势")
def console_trend(days: int = Query(14, ge=1, le=90), db: Session = Depends(get_db)):
    try:
        return operations.get_trend(db, days)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="获取处理趋势失败")


@router.get("/console/documents", summary="查询文档处理状态")
def console_documents(
    date: Optional[str] = Query(None, description="北京时间日期；筛选当日同步、处理或日志触及的文件"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=200),
    db: Session = Depends(get_db),
):
    try:
        return operations.get_documents(
            db,
            day=date,
            page=page,
            page_size=page_size,
            status=status,
            category=category,
            q=q,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="查询文档失败")


class ConsoleActionRequest(BaseModel):
    action: Literal["import", "process_pending", "scan_cleanup", "scan_versions"]
    limit: int = Field(default=20, ge=1, le=5000)
    dat_file_path: Optional[str] = None
    update_existing: bool = False
    dry_run: bool = True

    @model_validator(mode="after")
    def scans_are_previews(self):
        if self.action in ("scan_cleanup", "scan_versions") and self.dry_run is not True:
            raise ValueError("扫描动作只允许预览模式，请将 dry_run 设为 true")
        return self


@router.post("/console/actions", summary="提交每日过程操作")
def console_action(request: ConsoleActionRequest):
    try:
        if request.action == "import":
            task = import_dat_file_task.delay(
                dat_file_path=request.dat_file_path,
                update_existing=request.update_existing,
            )
            message = "DAT导入任务已排队"
        elif request.action == "process_pending":
            task = batch_process_documents.delay(request.limit)
            message = f"批量处理任务已排队，将提交不超过 {request.limit} 个单文件任务；排队不代表已入库"
        elif request.action == "scan_cleanup":
            # Console-triggered scans are always read-only previews.
            task = clean_expired_documents.delay(request.limit, 5, True)
            message = f"过期及重复扫描预览任务已排队，范围上限 {request.limit} 个文档"
        else:
            task = clean_headquarters_version_duplicates.delay(request.limit, True)
            message = f"制度版本扫描预览任务已排队，范围上限 {request.limit} 个文档"

        return {"success": True, "task_id": str(task.id), "message": message}
    except Exception:
        raise HTTPException(status_code=503, detail="任务队列暂不可用，任务未提交")


__all__ = ["ConsoleActionRequest", "router"]
