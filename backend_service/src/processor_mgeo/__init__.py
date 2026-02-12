"""
MGeo处理器模块
包含地址数据匹配、候选结果处理、数据校验等功能
"""
from .address_completer import AddressCompleter
from .input_validator import InputValidator
from .converters import (
    convert_mgeo_tagging_to_output_format,
    convert_mgeo_to_output_format,
    parse_chinese_address,
    reorder_data_fields
)

__all__ = [
    'AddressCompleter',
    'InputValidator',
    'convert_mgeo_tagging_to_output_format',
    'convert_mgeo_to_output_format',
    'parse_chinese_address',
    'reorder_data_fields'
]
