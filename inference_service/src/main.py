"""
Inference Service 主应用工厂
"""
import os
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from .config.env_loader import load_config
from .utils.logger import setup_logging, get_logger
from .api.routes import inference, system


def create_app() -> FastAPI:
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

    logger = get_logger("Inference_API")
    logger.info("正在初始化Inference Service...")
    logger.info(f"日志文件: {log_file}")

    # 创建FastAPI应用
    app = FastAPI(
        title="Inference Service API",
        description="NER模型推理服务",
        version="1.0.0"
    )

    # 配置CORS - 从环境变量读取配置
    cors_origins_str = os.getenv('CORS_ALLOW_ORIGINS', '*')
    backend_url = os.getenv('BACKEND_SERVICE_URL', 'http://localhost:8080')
    
    # 解析CORS允许的来源
    if cors_origins_str == '*':
        # 支持所有来源访问
        allow_origins = ["*"]
        allow_credentials = False
    else:
        # 支持指定来源列表（用逗号分隔）
        allow_origins = [origin.strip() for origin in cors_origins_str.split(',')]
        # 如果包含backend_url，确保也在列表中
        if backend_url not in allow_origins:
            allow_origins.append(backend_url)
        allow_credentials = True
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    logger.info(f"CORS允许的来源: {allow_origins}")
    logger.info(f"CORS允许凭证: {allow_credentials}")

    # 注册路由
    app.include_router(inference.router, prefix="/inference")
    app.include_router(system.router, prefix="/inference")

    logger.info("路由注册完成:")
    logger.info("  - POST /inference/extract")
    logger.info("  - GET  /inference/health")
    logger.info("  - GET  /inference/models")

    logger.info("Inference Service初始化完成")

    return app
