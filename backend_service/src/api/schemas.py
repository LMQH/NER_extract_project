"""
API 请求和响应的 Pydantic 模型定义
"""
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    message: str
    timestamp: str


class ModelsResponse(BaseModel):
    """模型列表响应"""
    status: str
    models: List[str]
    count: int


class ExtractRequest(BaseModel):
    """实体抽取请求"""
    Content: str = Field(..., description="待处理的文本，格式：地址信息 人名 电话")


class ExtractResponse(BaseModel):
    """实体抽取响应"""
    EBusinessID: str = Field(..., description="业务ID")
    Data: Dict[str, Any] = Field(..., description="提取的实体数据")
    Success: bool = Field(..., description="是否成功")
    Reason: str = Field(..., description="原因说明")
    ResultCode: str = Field(..., description="结果代码")
    Warning: List[str] = Field(default_factory=list, description="警告信息列表，当存在无法确定的候选值或匹配失败时会有警告提示")


class UploadResponse(BaseModel):
    """文件上传响应"""
    status: str
    data: Optional[Dict[str, Any]] = None
    timestamp: str


class MultipleUploadResponse(BaseModel):
    """多文件上传响应"""
    status: str
    data: Optional[Dict[str, Any]] = None
    timestamp: str

