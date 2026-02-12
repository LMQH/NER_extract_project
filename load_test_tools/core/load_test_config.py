#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
负责配置文件的加载、验证和合并
"""

import os
import json
from typing import Dict, Any, Optional


def load_config(config_path: str) -> Dict:
    """
    加载配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        配置字典，如果文件不存在或读取失败则返回空字典
    """
    if not os.path.exists(config_path):
        return {}

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"警告: 无法读取配置文件 {config_path}: {str(e)}")
        return {}


def validate_config(config: Dict) -> bool:
    """
    验证配置完整性

    Args:
        config: 配置字典

    Returns:
        验证是否通过

    Raises:
        ValueError: 当配置验证失败时
    """
    # 必需参数检查
    if 'url' not in config:
        raise ValueError("配置文件缺少必需参数: url")

    # 互斥参数检查
    if config.get('total') and config.get('duration'):
        raise ValueError("total 和 duration 不能同时设置")

    return True


def merge_config(
    file_config: Dict,
    cli_config: Dict,
    defaults: Dict
) -> Dict:
    """
    合并配置：默认值 -> 配置文件 -> 命令行参数

    Args:
        file_config: 从配置文件读取的配置
        cli_config: 命令行参数配置
        defaults: 默认配置

    Returns:
        合并后的配置
    """
    merged = defaults.copy()
    merged.update(file_config)
    merged.update(cli_config)
    return merged


def get_default_config() -> Dict:
    """
    获取默认配置

    Returns:
        默认配置字典
    """
    return {
        'concurrent': 10,
        'timeout': 5,
        't1': 1.0,
        't2': 3.0,
        'content': "广东省深圳市龙岗区坂田街道长坑路西2巷2号202 黄大大 18273778575",
        'output_dir': 'test/load_test/reports',
        'json': False,
        'batch_mode': {
            'cooldown': 5
        }
    }


def get_base_config(config_path: Optional[str] = None) -> Dict:
    """
    从配置文件获取基础配置（用于BASE_CONFIG）
    
    从配置文件中提取以下字段作为基础配置：
    - url: API接口地址
    - timeout: 请求超时时间
    - t1: 快速请求阈值
    - t2: 慢速请求阈值
    - content: 请求内容
    
    Args:
        config_path: 配置文件路径，如果为None则使用默认路径
        
    Returns:
        基础配置字典，包含url、timeout、t1、t2、content
    """
    if config_path is None:
        # 获取配置文件默认路径（相对于当前文件）
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(os.path.dirname(current_dir), 'load_test_config.json')
    
    # 加载配置文件
    config = load_config(config_path)
    
    # 如果配置文件不存在或为空，使用默认值
    defaults = get_default_config()
    
    # 提取基础配置字段
    base_config = {
        'url': config.get('url', ''),
        'timeout': config.get('timeout', defaults['timeout']),
        't1': config.get('t1', defaults['t1']),
        't2': config.get('t2', defaults['t2']),
        'content': config.get('content', defaults['content']),
    }
    
    # 验证url是否设置
    if not base_config['url']:
        raise ValueError("配置文件缺少必需参数: url")
    
    return base_config


def get_output_config(config_path: Optional[str] = None) -> Dict:
    """
    从配置文件获取输出相关配置
    
    Args:
        config_path: 配置文件路径，如果为None则使用默认路径
        
    Returns:
        输出配置字典，包含output_dir、json、cooldown
    """
    if config_path is None:
        # 获取配置文件默认路径（相对于当前文件）
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(os.path.dirname(current_dir), 'load_test_config.json')
    
    # 加载配置文件
    config = load_config(config_path)
    defaults = get_default_config()
    
    # 提取输出配置
    output_config = {
        'output_dir': config.get('output_dir', defaults['output_dir']),
        'json': config.get('json', defaults['json']),
        'cooldown': config.get('batch_mode', {}).get('cooldown', defaults['batch_mode']['cooldown']),
    }
    
    return output_config
