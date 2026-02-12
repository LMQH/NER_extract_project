"""
实体提取工具模块
提供统一的实体提取和分类功能
"""
import re
from typing import Dict, Any, List, Optional
from ..config.constants import (
    ENTITY_TYPE_PROVINCE, ENTITY_TYPE_CITY, ENTITY_TYPE_DISTRICT,
    ENTITY_TYPE_STREET, ENTITY_TYPE_ROAD, ENTITY_TYPE_UNIT_ADDRESS,
    ENTITY_TYPE_NUMBER_ENG, ENTITY_TYPE_OTHER, PHONE_PATTERN,
    CHINESE_NAME_PATTERN, ADDRESS_KEYWORDS, DEFAULT_ENTITY_MAPPING
)
from .address_parser import AddressParser


class EntityExtractor:
    """实体提取器，用于从NER结果中提取和分类实体"""
    
    @staticmethod
    def parse_entity_list(entities_data: Dict[str, Any], text: str) -> List[Dict[str, Any]]:
        """
        解析实体列表（支持多种格式）
        
        Args:
            entities_data: 实体数据，可能是两种格式
            text: 原始文本
            
        Returns:
            标准化的实体列表，每个实体包含type, span, start, end
        """
        entity_list = []
        
        # 格式1: {"output": [[{...}], [{...}]]}
        if "output" in entities_data:
            output_list = entities_data["output"]
            for item in output_list:
                if isinstance(item, list) and len(item) > 0:
                    entity_info = item[0]  # 取第一个元素
                    entity_type = entity_info.get("type", "")
                    span = entity_info.get("span", "")
                    offset = entity_info.get("offset", [])
                    
                    if offset and len(offset) >= 2:
                        start, end = offset[0], offset[1]
                    else:
                        # 如果没有offset，尝试从文本中查找位置
                        start = text.find(span) if span else -1
                        end = start + len(span) if start >= 0 else -1
                    
                    entity_list.append({
                        "type": entity_type,
                        "span": span,
                        "start": start,
                        "end": end
                    })
        
        # 格式2: {"人物": [{"text": "...", "start": 0, "end": 2}], ...}
        else:
            for entity_type, entities in entities_data.items():
                if isinstance(entities, list):
                    for entity in entities:
                        if isinstance(entity, dict):
                            span = entity.get("text") or entity.get("span", "")
                            start = entity.get("start", -1)
                            end = entity.get("end", -1)
                            
                            if span:
                                entity_list.append({
                                    "type": entity_type,
                                    "span": span,
                                    "start": start,
                                    "end": end
                                })
        
        return entity_list
    
    @staticmethod
    def classify_entities(
        entity_list: List[Dict[str, Any]],
        mapping_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        按实体类型和模式分类实体
        
        Args:
            entity_list: 实体列表
            mapping_config: 映射配置，如果为None则使用默认配置
            
        Returns:
            分类后的实体字典，key为类别名称
        """
        if mapping_config is None:
            mapping_config = DEFAULT_ENTITY_MAPPING
        
        classified = {
            "province": [],
            "city": [],
            "district": [],
            "street": [],
            "address": [],
            "person": []
        }
        
        for entity in entity_list:
            entity_type = entity.get("type", "")
            span = entity.get("span", "")
            
            # 检查省份
            if EntityExtractor._matches_category(
                entity_type, span, mapping_config.get("ProvinceName", {})
            ):
                classified["province"].append(entity)
                continue
            
            # 检查城市
            if EntityExtractor._matches_category(
                entity_type, span, mapping_config.get("CityName", {})
            ):
                classified["city"].append(entity)
                continue
            
            # 检查区县
            if EntityExtractor._matches_category(
                entity_type, span, mapping_config.get("ExpAreaName", {})
            ):
                classified["district"].append(entity)
                continue
            
            # 检查街道
            if EntityExtractor._matches_category(
                entity_type, span, mapping_config.get("StreetName", {})
            ):
                classified["street"].append(entity)
                continue
            
            # 检查详细地址
            if EntityExtractor._matches_category(
                entity_type, span, mapping_config.get("Address", {})
            ):
                classified["address"].append(entity)
                continue
            
            # 检查人物
            if EntityExtractor._matches_category(
                entity_type, span, mapping_config.get("Name", {})
            ):
                classified["person"].append(entity)
        
        return classified
    
    @staticmethod
    def _matches_category(
        entity_type: str,
        span: str,
        category_config: Dict[str, Any]
    ) -> bool:
        """检查实体是否匹配某个类别"""
        entity_types = category_config.get("entity_types", [])
        patterns = category_config.get("patterns", [])
        
        if entity_type not in entity_types:
            return False
        
        if not patterns:
            return True
        
        return any(pattern in span for pattern in patterns)
    
    @staticmethod
    def find_large_location_entity(
        entity_list: List[Dict[str, Any]],
        mapping_config: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        查找大的地理位置实体（包含多个地址层级）
        
        Args:
            entity_list: 实体列表
            mapping_config: 映射配置
            
        Returns:
            大的地理位置实体文本，如果未找到则返回None
        """
        if mapping_config is None:
            mapping_config = DEFAULT_ENTITY_MAPPING
        
        all_location_entities = []
        
        for entity in entity_list:
            entity_type = entity.get("type", "")
            span = entity.get("span", "")
            
            entity_types = mapping_config.get("ProvinceName", {}).get("entity_types", [])
            if entity_type in entity_types:
                all_location_entities.append(span)
                # 检查是否包含多个地址关键词
                address_keywords_count = sum(
                    1 for keyword in ADDRESS_KEYWORDS if keyword in span
                )
                if address_keywords_count >= 3:
                    return span
        
        # 如果只有一个地理位置实体且较长，也尝试解析
        if len(all_location_entities) == 1:
            single_entity = all_location_entities[0]
            if len(single_entity) > 10:
                return single_entity
        
        return None
    
    @staticmethod
    def extract_phone_from_text(text: str) -> str:
        """从文本中提取手机号码"""
        phone_match = re.search(PHONE_PATTERN, text)
        return phone_match.group(0) if phone_match else ""
    
    @staticmethod
    def extract_name_from_entities(
        person_entities: List[Dict[str, Any]],
        text: str,
        address_ranges: List[tuple]
    ) -> str:
        """
        从实体中提取姓名
        
        Args:
            person_entities: 人物实体列表
            text: 原始文本
            address_ranges: 地址范围列表
            
        Returns:
            提取的姓名
        """
        # 首先从人物实体中提取
        if person_entities:
            person_entities.sort(key=lambda x: x.get("start", 0))
            name = person_entities[0].get("span", "")
            # 过滤掉明显不是姓名的内容
            if not any(keyword in name for keyword in ADDRESS_KEYWORDS):
                return name
        
        # 如果还没有找到，从非地址部分查找
        return AddressParser.find_name_in_non_address_text(text, address_ranges)
    
    @staticmethod
    def get_address_ranges(
        entity_list: List[Dict[str, Any]],
        mapping_config: Optional[Dict[str, Any]] = None
    ) -> List[tuple]:
        """
        获取所有地址实体的位置范围
        
        Args:
            entity_list: 实体列表
            mapping_config: 映射配置
            
        Returns:
            地址范围列表，每个元素为(start, end)元组
        """
        if mapping_config is None:
            mapping_config = DEFAULT_ENTITY_MAPPING
        
        address_ranges = []
        
        for entity in entity_list:
            entity_type = entity.get("type", "")
            entity_types = (
                mapping_config.get("ProvinceName", {}).get("entity_types", []) +
                mapping_config.get("CityName", {}).get("entity_types", []) +
                mapping_config.get("ExpAreaName", {}).get("entity_types", []) +
                mapping_config.get("StreetName", {}).get("entity_types", []) +
                mapping_config.get("Address", {}).get("entity_types", [])
            )
            
            if entity_type in entity_types:
                start = entity.get("start", -1)
                end = entity.get("end", -1)
                if start >= 0 and end >= 0:
                    address_ranges.append((start, end))
        
        return address_ranges

