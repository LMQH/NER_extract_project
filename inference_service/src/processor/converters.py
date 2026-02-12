"""
推理结果格式转换器
"""
from typing import Dict, Any
from ..utils.logger import get_logger
from .numpy_converter import convert_numpy_types

logger = get_logger(__name__)


def format_inference_result(
    text: str,
    entities: Dict[str, Any],
    model_name: str,
    inference_time: float
) -> Dict[str, Any]:
    """
    格式化推理结果为标准响应格式

    Args:
        text: 原始文本
        entities: 模型返回的实体
        model_name: 使用的模型名称
        inference_time: 推理耗时（秒）

    Returns:
        格式化后的结果字典
    """
    # 转换numpy类型
    entities = convert_numpy_types(entities)

    # 检查是否有错误
    if "error" in entities:
        return {
            "text": text,
            "entities": entities,
            "inference_time": inference_time,
            "model_name": model_name,
            "success": False,
            "error": entities.get("error")
        }

    return {
        "text": text,
        "entities": entities,
        "inference_time": inference_time,
        "model_name": model_name,
        "success": True,
        "error": None
    }
