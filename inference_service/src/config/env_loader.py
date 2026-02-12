"""
推理服务配置加载模块
使用 dev.env 作为环境配置文件
"""
import os
import logging
from pathlib import Path
from dotenv import dotenv_values

logger = logging.getLogger("Inference_Config")


def load_config():
    """
    加载环境配置
    使用 dev.env 作为配置文件

    Returns:
        配置字典
    """
    project_root = Path(__file__).parent.parent.parent
    env_file = project_root / "dev.env"

    if not env_file.exists():
        logger.warning(f"配置文件不存在: {env_file}")
        return {}

    try:
        config = dotenv_values(env_file)
        logger.info(f"成功加载配置文件: {env_file}")
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败 {env_file}: {e}")
        return {}
