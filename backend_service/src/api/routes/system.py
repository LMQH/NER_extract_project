"""
系统相关路由
包括健康检查、模型列表等
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from src.api.schemas import HealthResponse, ModelsResponse
from src.api.dependencies import get_model_manager

router = APIRouter()


@router.get("/api/health", response_model=HealthResponse, tags=["系统"])
async def health_check():
    """健康检查接口"""
    return {
        "status": "ok",
        "message": "NER API服务运行正常",
        "timestamp": datetime.now().isoformat()
    }


@router.get("/api/models", response_model=ModelsResponse, tags=["模型"])
async def list_models(model_manager=Depends(get_model_manager)):
    """获取支持的模型列表"""
    try:
        models = model_manager.list_models()
        return {
            "status": "success",
            "models": models,
            "count": len(models)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {str(e)}")
