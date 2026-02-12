"""
日志工具模块
"""
import logging
import sys
from pathlib import Path
from datetime import datetime


def get_logger(name: str = __name__) -> logging.Logger:
    """
    获取日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        日志记录器实例
    """
    return logging.getLogger(name)


def setup_logging(project_root: Path, log_level: str = "INFO"):
    """
    配置日志系统

    Args:
        project_root: 项目根目录
        log_level: 日志级别
    """
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"inference_{datetime.now().strftime('%Y%m%d')}.log"

    # 从日志级别字符串转换为logging常量
    level = getattr(logging, log_level.upper(), logging.INFO)

    # 配置日志格式
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(log_format, date_format)

    # 创建文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers = []
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return log_file
