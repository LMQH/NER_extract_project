"""
模型管理器（推理服务简化版）
支持模型的动态加载和缓存
"""
import os
from pathlib import Path
from typing import Optional
from .mgeo_model import MGeoModel
from ..config.constants import SUPPORTED_MODELS, MODEL_TYPES
from ..utils.logger import get_logger

logger = get_logger(__name__)


# 全局模型管理器单例
_model_manager = None


def get_model_manager():
    """
    获取全局模型管理器单例

    Returns:
        ModelManager实例
    """
    global _model_manager
    if _model_manager is None:
        base_path = Path(__file__).parent.parent.parent
        _model_manager = ModelManager(base_path=str(base_path))
    return _model_manager


class ModelManager:
    """模型管理器，支持模型缓存和动态切换"""

    # 支持的模型映射（从常量文件导入）
    SUPPORTED_MODELS = SUPPORTED_MODELS

    # 模型类型映射（从常量文件导入）
    MODEL_TYPES = MODEL_TYPES

    def __init__(self, base_path: str = None):
        """
        初始化模型管理器

        Args:
            base_path: 项目根目录路径，如果为None则自动检测
        """
        if base_path:
            self.base_path = Path(base_path)
        else:
            # 自动检测项目根目录（假设在src目录下）
            self.base_path = Path(__file__).parent.parent

        self.models = {}
        self.current_model_name: Optional[str] = None

    def get_model_path(self, model_name: str) -> Path:
        """
        获取模型路径

        Args:
            model_name: 模型名称

        Returns:
            模型路径
        """
        if model_name not in self.SUPPORTED_MODELS:
            raise ValueError(
                f"不支持的模型: {model_name}。"
                f"支持的模型: {list(self.SUPPORTED_MODELS.keys())}"
            )

        model_relative_path = self.SUPPORTED_MODELS[model_name]
        model_path = self.base_path / model_relative_path

        if not model_path.exists():
            raise FileNotFoundError(
                f"模型路径不存在: {model_path}。"
                f"请确保模型已下载到指定目录。"
            )

        return model_path

    def load_model(self, model_name: str, force_reload: bool = False):
        """
        加载模型（支持缓存）

        Args:
            model_name: 模型名称
            force_reload: 是否强制重新加载（即使已缓存）

        Returns:
            模型实例
        """
        # 检查模型是否已加载
        if model_name in self.models and not force_reload:
            logger.debug(f"使用缓存模型: {model_name}")
            self.current_model_name = model_name
            return self.models[model_name]

        # 加载新模型
        logger.info(f"加载模型: {model_name}")

        try:
            # 获取模型路径
            model_path = self.get_model_path(model_name)
            model_path_str = str(model_path.absolute())

            # 根据模型类型选择不同的模型类
            model_type = self.MODEL_TYPES.get(model_name)

            if model_type == 'mgeo':
                model = MGeoModel(model_path_str)
            else:
                raise ValueError(f"不支持的模型类型: {model_name}")

            # 加载模型
            model.load()

            self.models[model_name] = model
            self.current_model_name = model_name
            logger.info(f"模型加载成功: {model_name}")
            return model

        except Exception as e:
            raise Exception(f"模型加载失败: {model_name}, {str(e)}")

    def get_model(self, model_name: str = None):
        """
        获取模型实例

        Args:
            model_name: 模型名称，如果为None则返回当前模型

        Returns:
            模型实例
        """
        if model_name is None:
            if self.current_model_name is None:
                raise ValueError("没有指定模型，且当前没有已加载的模型")
            model_name = self.current_model_name

        if model_name not in self.models:
            return self.load_model(model_name)

        return self.models[model_name]

    def list_models(self) -> list:
        """获取支持的模型列表"""
        return list(self.SUPPORTED_MODELS.keys())

    def unload_model(self, model_name: str):
        """
        卸载模型（释放内存）

        Args:
            model_name: 模型名称
        """
        if model_name in self.models:
            self.models[model_name].unload()
            del self.models[model_name]
            if self.current_model_name == model_name:
                self.current_model_name = None
            logger.debug(f"模型已卸载: {model_name}")

    def unload_all(self):
        """卸载所有模型"""
        model_names = list(self.models.keys())
        for model_name in model_names:
            self.unload_model(model_name)
