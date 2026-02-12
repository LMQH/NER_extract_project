"""
模型基类
"""
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseModel(ABC):
    """模型基类"""

    def __init__(self, model_path: str):
        """
        初始化模型

        Args:
            model_path: 模型路径
        """
        self.model_path = model_path
        self.model = None

    @abstractmethod
    def extract_entities(self, text: str) -> Dict[str, Any]:
        """
        从文本中抽取实体

        Args:
            text: 输入文本

        Returns:
            抽取结果字典，包含:
            - text: 原始文本
            - entities: 抽取的实体
            - error: 错误信息（如果有）
        """
        pass

    def load(self):
        """加载模型"""
        pass

    def unload(self):
        """卸载模型，释放内存"""
        if self.model:
            del self.model
            self.model = None
