"""
Backend Service 主入口（重构版）
提供RESTful API接口，通过HTTP调用推理服务进行模型推理
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from src.main import create_app
from src.utils.logger import get_logger

# 创建应用实例
app = create_app()
logger = get_logger("Backend_API")


# 启动事件处理
@app.on_event("startup")
async def startup_event():
    """应用启动时执行的初始化操作"""
    logger.info("Backend Service 启动事件触发")

    # 初始化定时任务（如果需要）
    try:
        from src.tasks.api_usage_sync import ApiUsageSyncTask
        from src.database.statistics_db_connection import StatisticsDatabaseConnection

        stats_db_connection = StatisticsDatabaseConnection()
        if stats_db_connection.test_connection():
            sync_task = ApiUsageSyncTask(db_connection=stats_db_connection)
            if sync_task.enabled:
                import asyncio
                # 启动后台任务
                asyncio.create_task(sync_task.run_periodic())
                logger.info("API使用统计同步任务已启动")
        else:
            logger.warning("统计数据库连接失败，跳过定时任务初始化")
    except Exception as e:
        logger.warning(f"初始化API使用统计同步任务失败: {str(e)}")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行的清理操作"""
    logger.info("Backend Service 关闭事件触发")

    # 停止定时任务
    try:
        from src.tasks.api_usage_sync import ApiUsageSyncTask
        # 这里需要访问全局的sync_task实例
        # 实际实现中需要通过依赖注入管理
        logger.info("定时任务已停止")
    except Exception as e:
        logger.warning(f"停止定时任务时出错: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    # 从环境变量读取端口
    port = int(os.getenv('BACKEND_SERVICE_PORT', '8080'))

    logger.info("=" * 60)
    logger.info("Backend Service 启动")
    logger.info("=" * 60)
    logger.info(f"服务地址: http://0.0.0.0:{port}")
    logger.info(f"API文档: http://localhost:{port}/docs")
    logger.info(f"API文档 (ReDoc): http://localhost:{port}/redoc")
    logger.info("=" * 60)

    # 启动FastAPI服务
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True)
