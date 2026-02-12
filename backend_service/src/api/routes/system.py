"""
系统相关路由
包括健康检查、模型列表等
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from src.api.schemas import HealthResponse, ModelsResponse
from src.api.dependencies import get_inference_client

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
async def list_models(inference_client=Depends(get_inference_client)):
    """获取支持的模型列表"""
    try:
        result = inference_client.list_models()
        # 推理服务返回格式: {"models": [...], "count": ...} 或 {"status": "success", "models": [...]}
        if isinstance(result, dict):
            models = result.get("models", result.get("data", []))
            if isinstance(models, list):
                return {
                    "status": "success",
                    "models": models,
                    "count": len(models)
                }
            else:
                return {
                    "status": "success",
                    "models": [models] if models else [],
                    "count": 1 if models else 0
                }
        else:
            return {
                "status": "success",
                "models": [],
                "count": 0
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {str(e)}")
