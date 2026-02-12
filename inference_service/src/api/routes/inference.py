"""
推理相关路由
"""
import time
import logging
from fastapi import APIRouter, HTTPException
from datetime import datetime

from ..schemas import InferenceRequest, InferenceResponse
from ...models.model_manager import get_model_manager
from ...processor.converters import format_inference_result
from ...utils.logger import get_logger

router = APIRouter()
logger = get_logger("Inference_API")


@router.post("/extract", tags=["推理"])
async def extract_entities(request: InferenceRequest):
    """
    实体推理接口

    请求格式:
    {
        "Content": "广东省深圳市龙岗区坂田街道...",
        "model_name": "mgeo_geographic_composition_analysis_chinese_base"
    }

    响应格式:
    {
        "text": "原始文本",
        "entities": {...},
        "inference_time": 0.1234,
        "model_name": "mgeo...",
        "success": true,
        "error": null
    }
    """
    try:
        # 验证输入
        if not request.Content or not request.Content.strip():
            raise HTTPException(status_code=400, detail="Content字段不能为空")

        model_name = request.model_name or 'mgeo_geographic_composition_analysis_chinese_base'

        # 获取模型管理器
        model_manager = get_model_manager()

        # 加载模型
        try:
            model = model_manager.load_model(model_name)
        except Exception as e:
            logger.error(f"模型加载失败: {str(e)}")
            return InferenceResponse(
                text=request.Content,
                entities={},
                inference_time=0.0,
                model_name=model_name,
                success=False,
                error=f"模型加载失败: {str(e)}"
            )

        # 执行推理
        inference_start_time = time.time()
        try:
            result = model.extract_entities(request.Content)
            inference_end_time = time.time()
            inference_time = inference_end_time - inference_start_time

            logger.info(f"推理成功 | 耗时: {inference_time:.4f}秒")

            # 格式化结果
            formatted_result = format_inference_result(
                text=request.Content,
                entities=result.get("entities", {}),
                model_name=model_name,
                inference_time=inference_time
            )

            return formatted_result

        except Exception as e:
            inference_end_time = time.time()
            inference_time = inference_end_time - inference_start_time

            logger.error(f"推理失败 | 耗时: {inference_time:.4f}秒 | 错误: {str(e)}")

            return InferenceResponse(
                text=request.Content,
                entities={},
                inference_time=inference_time,
                model_name=model_name,
                success=False,
                error=str(e)
            )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")
