"""
推理服务API数据模型
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(..., description="服务状态")
    message: str = Field(..., description="响应消息")
    timestamp: str = Field(..., description="时间戳")


class ModelsResponse(BaseModel):
    """模型列表响应"""
    status: str = Field(..., description="服务状态")
    models: List[str] = Field(..., description="支持的模型列表")
    count: int = Field(..., description="模型数量")


class InferenceRequest(BaseModel):
    """推理请求模型"""
    Content: str = Field(..., description="待处理的文本")
    model_name: str = Field(
        default="mgeo_geographic_composition_analysis_chinese_base",
        description="模型名称"
    )


class InferenceResponse(BaseModel):
    """推理响应模型"""
    text: str = Field(..., description="原始文本")
    entities: Dict[str, Any] = Field(..., description="抽取的实体")
    inference_time: float = Field(..., description="推理耗时(秒)")
    model_name: str = Field(..., description="使用的模型名称")
    success: bool = Field(default=True, description="推理是否成功")
    error: Optional[str] = Field(default=None, description="错误信息")
