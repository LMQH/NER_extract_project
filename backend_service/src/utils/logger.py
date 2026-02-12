"""
日志配置模块
提供统一的日志管理接口,支持不同日志级别的配置
"""
import logging
import os
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


class LoggerManager:
    """日志管理器"""
    
    _instance = None
    _loggers = {}
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化日志管理器"""
        if self._initialized:
            return
        
        self._initialized = True
        
        # 从环境变量读取日志级别,默认为INFO
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        self.level = getattr(logging, log_level, logging.INFO)
        
        # 日志格式
        self.format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        self.date_format = '%Y-%m-%d %H:%M:%S'
        
        # 初始化根日志记录器
        self._setup_root_logger()
    
    def _setup_root_logger(self):
        """配置根日志记录器"""
        # 获取根日志记录器
        root_logger = logging.getLogger()
        root_logger.setLevel(self.level)
        
        # 清除已有的处理器
        root_logger.handlers.clear()
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.level)
        
        # 创建格式化器
        formatter = logging.Formatter(self.format_str, self.date_format)
        console_handler.setFormatter(formatter)
        
        # 添加处理器
        root_logger.addHandler(console_handler)
        
        # 设置第三方库的日志级别,避免过于冗余
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        获取日志记录器
        
        Args:
            name: 日志记录器名称(通常使用模块名,如__name__)
            
        Returns:
            日志记录器实例
        """
        if name not in self._loggers:
            logger = logging.getLogger(name)
            logger.setLevel(self.level)
            self._loggers[name] = logger
        return self._loggers[name]


# 创建全局日志管理器实例
_logger_manager = LoggerManager()


def get_logger(name: str) -> logging.Logger:
    """
    获取日志记录器的便捷函数
    
    Args:
        name: 日志记录器名称(通常使用模块名,如__name__)
        
    Returns:
        日志记录器实例
    """
    return _logger_manager.get_logger(name)


def set_log_level(level: str):
    """
    动态设置日志级别
    
    Args:
        level: 日志级别字符串(DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    global _logger_manager
    log_level = getattr(logging, level.upper(), logging.INFO)
    _logger_manager.level = log_level
    
    # 更新根日志记录器级别
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # 更新所有处理器级别
    for handler in root_logger.handlers:
        handler.setLevel(log_level)
    
    # 更新所有已创建的日志记录器级别
    for logger in _logger_manager._loggers.values():
        logger.setLevel(log_level)


def setup_logging(project_root: Path, log_level: str = "INFO"):
    """
    配置日志系统，支持文件和控制台输出

    Args:
        project_root: 项目根目录
        log_level: 日志级别

    Returns:
        日志文件路径
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

    # 设置第三方库的日志级别,避免过于冗余
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return log_file
