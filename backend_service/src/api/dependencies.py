"""
API 依赖项（重构版）
使用推理服务客户端替换模型管理器
"""
from fastapi import Depends
from src.client.inference_client import InferenceClient
from src.processor_mgeo import AddressCompleter
from src.config import ConfigManager
from src.database import DatabaseConnection
from pathlib import Path

# 这些将在 app.py 中初始化
_inference_client: InferenceClient = None
_config_manager: ConfigManager = None
_db_connection: DatabaseConnection = None
_address_completer: AddressCompleter = None
_project_root: Path = None


def init_dependencies(
    config_manager: ConfigManager,
    project_root: Path,
    db_connection: DatabaseConnection = None
):
    """
    初始化依赖项（重构版）

    Args:
        config_manager: 配置管理器
        project_root: 项目根目录
        db_connection: 数据库连接（可选）
    """
    global _inference_client, _config_manager, _project_root
    global _db_connection, _address_completer

    _config_manager = config_manager
    _project_root = project_root

    # 初始化推理服务客户端（替换原模型管理器）
    try:
        _inference_client = InferenceClient()
        import logging
        logger = logging.getLogger("Backend_API")
        logger.info("推理服务客户端初始化成功")
    except Exception as e:
        import logging
        logger = logging.getLogger("Backend_API")
        logger.error(f"推理服务客户端初始化失败: {str(e)}")
        _inference_client = None

    # 初始化数据库连接和地址补全器（保持不变）
    try:
        if db_connection is None:
            _db_connection = DatabaseConnection()
        else:
            _db_connection = db_connection

        if _db_connection:
            _address_completer = AddressCompleter(_db_connection)
        else:
            _address_completer = None
    except Exception as e:
        import logging
        logger = logging.getLogger("Backend_API")
        logger.warning(f"数据库连接初始化失败，地址补全功能将不可用: {str(e)}")
        _db_connection = None
        _address_completer = None


def get_inference_client() -> InferenceClient:
    """获取推理服务客户端"""
    if _inference_client is None:
        raise RuntimeError("推理服务客户端未初始化")
    return _inference_client


def get_config_manager() -> ConfigManager:
    """获取配置管理器"""
    return _config_manager


def get_project_root() -> Path:
    """获取项目根目录"""
    return _project_root


def get_db_connection() -> DatabaseConnection:
    """获取数据库连接"""
    return _db_connection


def get_address_completer() -> AddressCompleter:
    """获取地址补全器"""
    return _address_completer

