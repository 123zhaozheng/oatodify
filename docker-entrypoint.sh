#!/bin/bash
# =============================================================================
# OA文档处理系统 Docker 启动脚本
# 支持多种运行模式：FastAPI、Streamlit、Celery Worker、Celery Beat
# =============================================================================

set -e

# 检查数据库连接
check_database() {
    echo "正在检查数据库连接..."
    python -c "
import sys
try:
    from database import init_db
    init_db()
    print('✅ 数据库连接成功')
except Exception as e:
    print(f'❌ 数据库连接失败: {e}')
    sys.exit(1)
    "
}

# 检查 Redis 连接
check_redis() {
    echo "正在检查 Redis 连接..."
    python -c "
import sys
import redis
from config import settings
try:
    r = redis.from_url(settings.redis_url)
    r.ping()
    print('✅ Redis 连接成功')
except Exception as e:
    print(f'❌ Redis 连接失败: {e}')
    sys.exit(1)
    "
}

# 等待依赖服务启动
wait_for_services() {
    echo "🔍 检查依赖服务状态..."
    
    # 检查数据库
    until check_database; do
        echo "⏳ 等待数据库启动..."
        sleep 5
    done
    
    # 检查 Redis
    until check_redis; do
        echo "⏳ 等待 Redis 启动..."
        sleep 5
    done
    
    echo "✅ 所有依赖服务已就绪"
}

# 启动 FastAPI 服务
start_fastapi() {
    echo "🚀 启动 FastAPI 服务..."
    exec uvicorn main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers 1 \
        --access-log
}

# 启动 Streamlit 前端
start_streamlit() {
    echo "🚀 启动 Streamlit 前端..."
    exec streamlit run app.py \
        --server.address 0.0.0.0 \
        --server.port 8501 \
        --server.headless true \
        --server.enableCORS false \
        --server.enableXsrfProtection false
}

# 启动 Celery Worker
start_celery_worker() {
    echo "🚀 启动 Celery Worker..."
    exec celery -A tasks.document_processor worker \
        --loglevel=info \
        --concurrency=2 \
        --max-tasks-per-child=1000 \
        --queues=document_processing,batch_processing
}

# 启动 Celery Beat (定时任务调度器)
start_celery_beat() {
    echo "🚀 启动 Celery Beat..."
    exec celery -A tasks.document_processor beat \
        --loglevel=info \
        --schedule=/tmp/celerybeat-schedule
}

# 启动 Celery Flower (监控界面)
start_celery_flower() {
    echo "🚀 启动 Celery Flower..."
    exec celery -A tasks.document_processor flower \
        --address=0.0.0.0 \
        --port=5555
}

# # 运行数据库迁移
# run_migrations() {
#     echo "📊 运行数据库迁移..."
#     python -c "
# from database import init_db
# print('初始化数据库...')
# init_db()
# print('✅ 数据库初始化完成')
#     "
# }

# 显示帮助信息
show_help() {
    echo "OA文档处理系统 Docker 启动脚本"
    echo ""
    echo "用法: $0 [COMMAND]"
    echo ""
    echo "可用命令:"
    echo "  fastapi        启动 FastAPI 后端服务 (默认端口: 8000)"
    echo "  streamlit      启动 Streamlit 前端界面 (默认端口: 8501)"
    echo "  celery-worker  启动 Celery 后台任务处理器"
    echo "  celery-beat    启动 Celery 定时任务调度器"
    echo "  celery-flower  启动 Celery 监控界面 (端口: 5555)"
    echo "  migrate        仅运行数据库迁移"
    echo "  help           显示此帮助信息"
    echo ""
    echo "环境变量:"
    echo "  SKIP_HEALTH_CHECK  设置为 'true' 跳过依赖服务健康检查"
    echo ""
    echo "示例:"
    echo "  docker run -p 8000:8000 --env-file .env oa-processor fastapi"
    echo "  docker run -p 8501:8501 --env-file .env oa-processor streamlit"
}

# 主逻辑
main() {
    local command=${1:-fastapi}
    
    echo "================================================"
    echo "🏗️  OA文档处理系统 Docker 容器启动"
    echo "📅 启动时间: $(date)"
    echo "🔧 运行模式: $command"
    echo "================================================"
    
    # 检查环境变量
    if [[ -z "${DATABASE_URL:-}" ]]; then
        echo "❌ 错误: 未设置 DATABASE_URL 环境变量"
        exit 1
    fi
    
    if [[ -z "${REDIS_URL:-}" ]]; then
        echo "❌ 错误: 未设置 REDIS_URL 环境变量"
        exit 1
    fi
    
    # 根据命令执行相应操作
    case "$command" in
        "fastapi")
            if [[ "${SKIP_HEALTH_CHECK:-false}" != "true" ]]; then
                wait_for_services
            fi
            # run_migrations
            start_fastapi
            ;;
        "streamlit")
            if [[ "${SKIP_HEALTH_CHECK:-false}" != "true" ]]; then
                wait_for_services
            fi
            start_streamlit
            ;;
        "celery-worker")
            if [[ "${SKIP_HEALTH_CHECK:-false}" != "true" ]]; then
                wait_for_services
            fi
            start_celery_worker
            ;;
        "celery-beat")
            if [[ "${SKIP_HEALTH_CHECK:-false}" != "true" ]]; then
                wait_for_services
            fi
            start_celery_beat
            ;;
        "celery-flower")
            if [[ "${SKIP_HEALTH_CHECK:-false}" != "true" ]]; then
                check_redis
            fi
            start_celery_flower
            ;;
        "migrate")
            wait_for_services
            run_migrations
            echo "✅ 数据库迁移完成"
            ;;
        "help"|"--help"|"-h")
            show_help
            exit 0
            ;;
        *)
            echo "❌ 错误: 未知命令 '$command'"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 信号处理
cleanup() {
    echo ""
    echo "🛑 收到停止信号，正在优雅关闭..."
    exit 0
}

trap cleanup SIGTERM SIGINT

# 执行主函数
main "$@"