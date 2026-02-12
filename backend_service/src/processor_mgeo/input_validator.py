"""
输入数据校验器
用于校验和清洗输入数据，确保数据格式统一、安全可靠
"""
import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("NER_API")


class InputValidator:
    """输入数据校验器"""
    
    # 需要校验的地址字段
    ADDRESS_FIELDS = ['ProvinceName', 'CityName', 'ExpAreaName', 'StreetName', 'AreasInfo', 'Address']
    
    # 字段最大长度限制（字符数）
    MAX_FIELD_LENGTH = 50
    
    # 危险字符模式（用于防止SQL注入等攻击）
    DANGEROUS_PATTERNS = ['--', 'DROP', 'DELETE', 'INSERT', 'UPDATE', 'SELECT', 
                          'UNION', 'EXEC', 'EXECUTE', 'SCRIPT', '<SCRIPT', 'JAVASCRIPT:', '/**/', '/*', '*/','<script>']
    
    # 需要去除的标点符号
    PUNCTUATION_PATTERN = r'[，。、；：""\'\'（）【】《》〈〉『』「」]'
    
    @staticmethod
    def validate_and_clean(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        校验并清洗输入数据
        
        Args:
            data: 输入数据字典，包含地址相关字段
            
        Returns:
            清洗后的数据字典
        """
        if not isinstance(data, dict):
            logger.warning(f"输入数据不是字典类型: {type(data)}")
            return {}
        
        cleaned = {}
        
        # 处理地址相关字段
        for field in InputValidator.ADDRESS_FIELDS:
            value = data.get(field, '')
            cleaned_value = InputValidator._clean_field_value(value, field)
            cleaned[field] = cleaned_value
        
        # 保留其他字段（如Name, Mobile等），但进行基本清洗
        for key, value in data.items():
            if key not in InputValidator.ADDRESS_FIELDS:
                if isinstance(value, str):
                    # 对其他字符串字段进行基本清洗（去除首尾空格）
                    cleaned[key] = value.strip() if value else value
                else:
                    cleaned[key] = value
        
        return cleaned
    
    @staticmethod
    def _clean_field_value(value: Any, field_name: str) -> str:
        """
        清洗单个字段值
        
        Args:
            value: 字段值，可能是字符串、字典或其他类型
            field_name: 字段名称（用于日志）
            
        Returns:
            清洗后的字符串值
        """
        # 1. 类型统一：如果是字典，提取region_name
        if isinstance(value, dict):
            value = value.get('region_name', '')
        
        # 2. 转换为字符串
        if not isinstance(value, str):
            value = str(value) if value is not None else ''
        
        # 3. 去除首尾空格
        value = value.strip()
        
        # 4. 如果为空，直接返回
        if not value:
            return ''
        
        # 5. 去除无意义字符
        # 去除所有空格（地址字段通常不需要空格）
        value = re.sub(r'\s+', '', value)
        
        # 去除标点符号
        value = re.sub(InputValidator.PUNCTUATION_PATTERN, '', value)
        
        # 6. 长度限制
        if len(value) > InputValidator.MAX_FIELD_LENGTH:
            logger.warning(f"字段 {field_name} 长度异常: {len(value)}，已截断至{InputValidator.MAX_FIELD_LENGTH}字符")
            value = value[:InputValidator.MAX_FIELD_LENGTH]
        
        # 7. 敏感词过滤（防止SQL注入等）
        if InputValidator._contains_dangerous_pattern(value):
            logger.error(f"字段 {field_name} 包含危险字符: {value}，已清空")
            return ''
        
        return value
    
    @staticmethod
    def _contains_dangerous_pattern(value: str) -> bool:
        """
        检测危险字符模式
        
        Args:
            value: 待检测的字符串
            
        Returns:
            如果包含危险模式返回True，否则返回False
        """
        if not value:
            return False
        
        value_upper = value.upper()
        for pattern in InputValidator.DANGEROUS_PATTERNS:
            if pattern in value_upper:
                return True
        
        return False
    
    @staticmethod
    def validate_extract_response(response: Dict[str, Any]) -> Dict[str, Any]:
        """
        校验并清洗ExtractResponse格式的响应数据
        
        Args:
            response: ExtractResponse格式的响应字典，包含Data字段
            
        Returns:
            清洗后的响应字典
        """
        if not isinstance(response, dict):
            logger.warning(f"响应数据不是字典类型: {type(response)}")
            return response
        
        # 创建响应副本
        validated_response = response.copy()
        
        # 如果包含Data字段，对Data字段进行校验和清洗
        if 'Data' in validated_response and isinstance(validated_response['Data'], dict):
            validated_response['Data'] = InputValidator.validate_and_clean(validated_response['Data'])
        
        return validated_response

