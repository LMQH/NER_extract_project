"""
地址解析工具模块
提供统一的中文地址解析功能
"""
import re
from typing import Dict, List, Tuple
from ..config.constants import (
    ADDRESS_KEYWORDS, DIRECT_CITIES, PROVINCE_PATTERN,
    CITY_PATTERN, DISTRICT_PATTERN, STREET_PATTERN
)


class AddressParser:
    """地址解析器，用于解析中文地址字符串"""
    
    @staticmethod
    def parse_chinese_address(address_text: str) -> Dict[str, str]:
        """
        使用正则表达式和规则解析中文地址字符串
        
        将完整的地址字符串（如"广东省深圳市龙岗区坂田街道长坑路西2巷2号202"）
        分解为省、市、区、街道、详细地址等部分
        
        Args:
            address_text: 完整的地址字符串
        
        Returns:
            包含省、市、区、街道、详细地址的字典:
            {
                "province": "广东省",
                "city": "深圳市",
                "district": "龙岗区",
                "street": "坂田街道",
                "address": "长坑路西2巷2号202"
            }
        """
        result = {
            "province": "",
            "city": "",
            "district": "",
            "street": "",
            "address": ""
        }
        
        if not address_text:
            return result
        
        remaining_text = address_text.strip()
        
        # 处理直辖市（北京、上海、天津、重庆）
        for full_name, short_name in DIRECT_CITIES.items():
            if remaining_text.startswith(full_name):
                result["province"] = full_name
                remaining_text = remaining_text[len(full_name):].strip()
                break
            elif remaining_text.startswith(short_name + "市"):
                result["province"] = short_name + "市"
                remaining_text = remaining_text[len(short_name + "市"):].strip()
                break
        
        # 1. 匹配省份（如果还没有匹配到）
        if not result["province"]:
            province_match = re.match(PROVINCE_PATTERN, remaining_text)
            if province_match:
                result["province"] = province_match.group(1)
                remaining_text = remaining_text[len(result["province"]):].strip()
        
        # 2. 匹配城市
        city_match = re.match(CITY_PATTERN, remaining_text)
        if city_match:
            result["city"] = city_match.group(1)
            remaining_text = remaining_text[len(result["city"]):].strip()
        
        # 3. 匹配区县
        district_match = re.match(DISTRICT_PATTERN, remaining_text)
        if district_match:
            result["district"] = district_match.group(1)
            remaining_text = remaining_text[len(result["district"]):].strip()
        
        # 4. 匹配街道
        street_match = re.match(STREET_PATTERN, remaining_text)
        if street_match:
            result["street"] = street_match.group(1)
            remaining_text = remaining_text[len(result["street"]):].strip()
        
        # 5. 剩余部分作为详细地址
        if remaining_text:
            result["address"] = remaining_text.strip()
        
        return result
    
    @staticmethod
    def extract_phone_and_name(text: str) -> Dict[str, str]:
        """
        从文本中提取电话号码和姓名
        
        Args:
            text: 输入文本
            
        Returns:
            包含phone和name的字典
        """
        from ..config.constants import PHONE_PATTERN, FIXED_PHONE_PATTERN, CHINESE_NAME_PATTERN
        
        result = {"phone": "", "name": ""}
        
        # 提取电话号码
        phone_match = re.search(PHONE_PATTERN, text)
        if phone_match:
            result["phone"] = phone_match.group(0)
        else:
            fixed_phone_match = re.search(FIXED_PHONE_PATTERN, text)
            if fixed_phone_match:
                result["phone"] = fixed_phone_match.group(0)
        
        # 提取姓名（2-4个汉字）
        name_match = re.search(CHINESE_NAME_PATTERN, text)
        if name_match:
            potential_name = name_match.group(0)
            # 确保不是地址关键词
            if not any(keyword in potential_name for keyword in ADDRESS_KEYWORDS):
                result["name"] = potential_name
        
        return result
    
    @staticmethod
    def merge_address_ranges(ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """
        合并重叠的地址范围
        
        Args:
            ranges: 地址范围列表，每个元素为(start, end)元组
            
        Returns:
            合并后的地址范围列表
        """
        if not ranges:
            return []
        
        ranges.sort()
        merged = [ranges[0]]
        
        for start, end in ranges[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        
        return merged
    
    @staticmethod
    def find_name_in_non_address_text(
        text: str,
        address_ranges: List[Tuple[int, int]]
    ) -> str:
        """
        在非地址部分的文本中查找姓名
        
        Args:
            text: 完整文本
            address_ranges: 地址范围列表
            
        Returns:
            找到的姓名，如果未找到则返回空字符串
        """
        from ..config.constants import CHINESE_NAME_PATTERN, ADDRESS_KEYWORDS
        
        merged_ranges = AddressParser.merge_address_ranges(address_ranges)
        
        for start, end in merged_ranges:
            before_text = text[:start]
            after_text = text[end:]
            
            for text_part in [before_text, after_text]:
                name_match = re.search(CHINESE_NAME_PATTERN, text_part)
                if name_match:
                    potential_name = name_match.group(0)
                    if not any(keyword in potential_name for keyword in ADDRESS_KEYWORDS):
                        return potential_name
        
        return ""

