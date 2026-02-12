"""
系统相关路由
"""
import logging
from fastapi import APIRouter
from datetime import datetime

from ..schemas import HealthResponse, ModelsResponse
from ...models.model_manager import get_model_manager
from ...utils.logger import get_logger

router = APIRouter()
logger = get_logger("Inference_API")


@router.get("/health", tags=["系统"])
async def health_check():
    """
    健康检查接口
    """
    try:
        model_manager = get_model_manager()
        # 检查模型管理器是否可用
        models = model_manager.list_models()

        return HealthResponse(
            status="healthy",
            message="推理服务运行正常",
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}")
        return HealthResponse(
            status="unhealthy",
            message=f"服务异常: {str(e)}",
            timestamp=datetime.now().isoformat()
        )


@router.get("/models", tags=["系统"])
async def list_models():
    """
    获取支持的模型列表
    """
    try:
        model_manager = get_model_manager()
        models = model_manager.list_models()

        return ModelsResponse(
            status="success",
            models=models,
            count=len(models)
        )
    except Exception as e:
        logger.error(f"获取模型列表失败: {str(e)}")
        raise
