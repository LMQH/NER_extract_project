"""
自定义异常类
"""


class ModelLoadError(Exception):
    """模型加载失败异常"""
    pass


class ModelNotFoundError(Exception):
    """模型不存在异常"""
    pass


class InferenceError(Exception):
    """推理失败异常"""
    pass
