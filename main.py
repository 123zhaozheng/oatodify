from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import logging
import uvicorn
from database import init_db
from api.routes import router
from api.console import router as console_router
from api.console_config import router as config_router
from config import settings

WEB_DIRECTORY = Path(__file__).resolve().parent / "web"
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 运维必须能在依赖异常时进入配置页；数据接口仍如实报告失败。
    try:
        init_db()
        app.state.database_initialized = True
    except Exception:
        app.state.database_initialized = False
        logger.error("数据库暂不可用，工作台配置页仍可访问；恢复后请运行迁移或重启 API")
    yield
    # 关闭时清理资源

app = FastAPI(
    title="OA文档处理系统",
    description="OA文档下载、解密、分析和知识库集成系统",
    version="2.0.0",
    lifespan=lifespan
)

@app.middleware("http")
async def console_runtime_config(request: Request, call_next):
    # 无登录内网应用：浏览器写请求必须来自同源页面，服务端调用可不带 Origin。
    origin = request.headers.get("origin")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin:
        try:
            same_host = urlsplit(origin).netloc == request.headers.get("host", "")
        except ValueError:
            same_host = False
        if not same_host:
            return JSONResponse(status_code=403, content={"detail": "请从本系统页面提交操作"})
    if request.url.path.startswith("/api/"):
        try:
            from services.runtime_config import refresh_runtime_settings
            refresh_runtime_settings()
        except Exception:
            # 配置可能含秘密；不将异常原文放入日志或页面。
            logger.error("共享运行配置刷新失败")
            return JSONResponse(status_code=503, content={"detail": "运行配置暂不可用，请检查共享配置文件"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    if request.url.path.startswith("/api/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store"
    return response

# 包含路由
app.include_router(router, prefix="/api/v1")
app.include_router(console_router, prefix="/api/v1")
app.include_router(config_router, prefix="/api/v1")
app.mount("/web", StaticFiles(directory=WEB_DIRECTORY, check_dir=False), name="web")

@app.get("/")
async def root():
    return FileResponse(WEB_DIRECTORY / "index.html", media_type="text/html")

@app.get("/health")
async def health_check():
    initialized = getattr(app.state, "database_initialized", False)
    return {"status": "healthy" if initialized else "degraded", "database_initialized": initialized,
            "timestamp": datetime.now(timezone.utc).isoformat()}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
