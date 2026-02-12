"""
Backend Service 主应用工厂（重构版）
移除模型加载逻辑，通过HTTP调用推理服务
"""
import sys
import os
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from src.config.env_loader import load_config
from src.config import ConfigManager
from src.utils.logger import setup_logging, get_logger
from src.api.dependencies import init_dependencies
from src.api.routes import system, extract, file


def create_app():
    """
    创建FastAPI应用实例

    Returns:
        FastAPI应用实例
    """
    # 加载环境配置
    config = load_config()
    if config:
        for key, value in config.items():
            if value is not None:
                os.environ[key] = str(value)

    # 配置日志系统
    log_file = setup_logging(
        project_root=project_root,
        log_level=os.getenv('LOG_LEVEL', 'INFO')
    )

    logger = get_logger("Backend_API")

    # 清理超过30天的旧日志文件
    _cleanup_old_logs(project_root / "logs", retention_days=30)

    # 记录配置加载情况
    logger.debug("=" * 60)
    logger.debug("环境变量加载验证")
    logger.debug(f"已加载的配置文件数量: {len(config) if config else 0}")

    # 记录关键环境变量（不显示敏感信息）
    key_env_vars = [
        'REDIS_HOST', 'REDIS_PORT', 'REDIS_DB',
        'MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_DATABASE',
        'INFERENCE_SERVICE_URL',  # 新增：推理服务URL
        'ENV_TYPE'
    ]
    for key in key_env_vars:
        value = os.getenv(key)
        if value:
            logger.debug(f"  {key}: {value}")
        else:
            logger.debug(f"  {key}: 未设置")

    # 创建FastAPI应用
    router_prefix = os.getenv("ROOT_PATH", "/ner_extract_info").strip()
    if not router_prefix:
        router_prefix = None

    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="Backend Service API",
        description="NER后端服务（通过HTTP调用推理服务）",
        version="1.0.0"
    )

    # 配置CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "*",  # 允许所有来源（开发环境）
            "https://szsyzhkjgfyxgs2.qiyukf.com",  # 系统域名
            "http://localhost:13110",
            "http://127.0.0.1:13110",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # 记录推理服务URL
    inference_url = os.getenv('INFERENCE_SERVICE_URL', 'http://localhost:13111')
    logger.info(f"推理服务URL: {inference_url}")

    # 初始化依赖项（传入推理服务客户端，而非模型管理器）
    db_connection = None
    try:
        from src.database.db_connection import DatabaseConnection
        db_connection = DatabaseConnection()
        if db_connection.test_connection():
            logger.info("MySQL数据库连接测试成功")
        else:
            logger.warning("MySQL数据库连接测试失败")
    except Exception as e:
        logger.error(f"MySQL数据库连接初始化失败: {str(e)}")
        db_connection = None

    # 初始化配置管理器
    config_manager = ConfigManager()

    # 初始化依赖项（移除model_manager，使用inference_client）
    init_dependencies(
        config_manager=config_manager,
        project_root=project_root,
        db_connection=db_connection
    )

    # 注册路由
    if router_prefix:
        app.include_router(system.router, prefix=router_prefix)
        app.include_router(extract.router, prefix=router_prefix)
        app.include_router(file.router, prefix=router_prefix)
        logger.info(f"路由已注册，前缀: {router_prefix}")
    else:
        app.include_router(system.router)
        app.include_router(extract.router)
        app.include_router(file.router)
        logger.info("路由已注册，直接访问模式")

    # 打印所有注册的路由（用于调试）
    logger.debug("已注册的路由列表:")
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            methods = ', '.join(route.methods) if route.methods else 'N/A'
            logger.debug(f"  {methods} {route.path}")

    logger.info("Backend Service初始化完成")

    return app


def _cleanup_old_logs(log_dir: Path, retention_days: int = 30) -> None:
    """
    清理超过指定天数的日志文件

    Args:
        log_dir: 日志目录路径
        retention_days: 保留天数，默认30天
    """
    try:
        if not log_dir.exists():
            return

        current_date = datetime.now()
        deleted_count = 0
        deleted_files = []

        # 日志文件命名格式：inference_YYYYMMDD.log
        import re
        log_pattern = re.compile(r'^inference_(\d{8})\.log$')

        for log_file in log_dir.iterdir():
            if not log_file.is_file():
                continue

            # 匹配日志文件名格式
            match = log_pattern.match(log_file.name)
            if not match:
                continue

            # 解析文件中的日期
            try:
                file_date_str = match.group(1)
                file_date = datetime.strptime(file_date_str, '%Y%m%d')

                # 计算日期差
                days_diff = (current_date - file_date).days

                # 删除超过保留天数的文件
                if days_diff > retention_days:
                    log_file.unlink()
                    deleted_count += 1
                    deleted_files.append(log_file.name)
            except (ValueError, OSError) as e:
                # 日期解析失败或文件删除失败，记录但继续处理其他文件
                logger.debug(f"处理日志文件 {log_file.name} 时出错: {str(e)}")
                continue

        # 记录清理结果
        if deleted_count > 0:
            logger = get_logger("Backend_API")
            logger.info(f"日志清理完成: 删除了 {deleted_count} 个超过 {retention_days} 天的日志文件")
            logger.debug(f"已删除的日志文件: {', '.join(deleted_files)}")
    except Exception as e:
        # 清理日志时出错，记录但不影响主程序启动
        logger = get_logger("Backend_API")
        logger.warning(f"清理旧日志文件时出错: {str(e)}")