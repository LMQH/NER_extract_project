"""
自定义异常类
提供统一的异常处理
"""


class NERDemoException(Exception):
    """NER Demo基础异常类"""
    pass


class ModelLoadError(NERDemoException):
    """模型加载错误"""
    pass


class ConfigLoadError(NERDemoException):
    """配置加载错误"""
    pass


class FileReadError(NERDemoException):
    """文件读取错误"""
    pass


class EntityExtractionError(NERDemoException):
    """实体抽取错误"""
    pass


class AddressParseError(NERDemoException):
    """地址解析错误"""
    pass

