"""
实体映射配置加载模块
从JSON文件加载标签到字段的映射关系
"""
import os
import json
import logging
from typing import Dict, Any, Optional, Set, List
from pathlib import Path

logger = logging.getLogger("NER_API")


class EntityMappingLoader:
    """实体映射配置加载器"""
    
    _instance = None
    _mapping_config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EntityMappingLoader, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._mapping_config is None:
            self._load_config()
    
    def _load_config(self):
        """加载映射配置"""
        # 默认映射配置（向后兼容）
        default_mapping = {
            "ProvinceName": {
                "entity_types": ["PB"],
                "is_single_value": True
            },
            "CityName": {
                "entity_types": ["PC"],
                "is_single_value": True
            },
            "ExpAreaName": {
                "entity_types": ["PD"],
                "is_single_value": True
            },
            "StreetName": {
                "entity_types": ["PE", "PF", "PH", "PS"],
                "is_single_value": False
            },
            "AreasInfo": {
                "entity_types": ["BS", "BL", "RD", "Brand", "CategorySuffix", "SS", "SA", "UD", "UE", "YA"],
                "is_single_value": False
            },
            "Address": {
                "entity_types": ["PG", "UA", "UB", "UC", "Entity", "NumEng"],
                "is_single_value": False
            },
            "others": {
                "entity_types": ["Yewu", "Desc", "BD"],
                "is_single_value": False,
                "default_for_unmapped": True
            }
        }
        
        default_special_types = {
            "phone_extraction": {
                "entity_types": ["ZZ"]
            },
            "name_extraction": {
                "entity_types": ["ZZ"]
            }
        }
        
        default_address_range_types = [
            "PB", "PC", "PD",
            "PF", "PG", "PH", "PS",
            "BS", "BL", "RD", "Brand", "CategorySuffix", "SS", "SA", "UD", "UE", "YA",
            "UA", "UB", "UC", "Entity", "NumEng"
        ]
        
        # 尝试从JSON文件加载配置
        config_file = self._get_config_file_path()
        
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                # 验证并提取映射配置
                if "mappings" in config_data:
                    mapping_config = {}
                    for field_name, field_config in config_data["mappings"].items():
                        if "entity_types" in field_config:
                            mapping_config[field_name] = {
                                "entity_types": field_config["entity_types"],
                                "is_single_value": field_config.get("is_single_value", False),
                                "default_for_unmapped": field_config.get("default_for_unmapped", False)
                            }
                    
                    # 如果配置有效，使用它；否则使用默认配置
                    if mapping_config:
                        self._mapping_config = {
                            "mappings": mapping_config,
                            "special_types": config_data.get("special_types", default_special_types),
                            "address_range_types": config_data.get("address_range_types", {}).get("entity_types", default_address_range_types)
                        }
                        logger.info(f"成功加载实体映射配置: {config_file}")
                    else:
                        logger.warning(f"配置文件格式无效，使用默认配置: {config_file}")
                        self._mapping_config = {
                            "mappings": default_mapping,
                            "special_types": default_special_types,
                            "address_range_types": default_address_range_types
                        }
                else:
                    logger.warning(f"配置文件缺少'mappings'字段，使用默认配置: {config_file}")
                    self._mapping_config = {
                        "mappings": default_mapping,
                        "special_types": default_special_types,
                        "address_range_types": default_address_range_types
                    }
            except json.JSONDecodeError as e:
                logger.error(f"配置文件JSON格式错误: {config_file}, 错误: {str(e)}, 使用默认配置")
                self._mapping_config = {
                    "mappings": default_mapping,
                    "special_types": default_special_types,
                    "address_range_types": default_address_range_types
                }
            except Exception as e:
                logger.error(f"加载配置文件失败: {config_file}, 错误: {str(e)}, 使用默认配置")
                self._mapping_config = {
                    "mappings": default_mapping,
                    "special_types": default_special_types,
                    "address_range_types": default_address_range_types
                }
        else:
            # 配置文件不存在，使用默认配置
            if config_file:
                logger.info(f"配置文件不存在: {config_file}, 使用默认配置")
            self._mapping_config = {
                "mappings": default_mapping,
                "special_types": default_special_types,
                "address_range_types": default_address_range_types
            }
    
    def _get_config_file_path(self) -> Optional[str]:
        """获取配置文件路径"""
        # 优先使用环境变量指定的路径
        config_path = os.getenv('ENTITY_MAPPING_CONFIG', None)
        if config_path and os.path.exists(config_path):
            return config_path
        
        # 尝试从项目根目录查找
        current_dir = Path(__file__).parent.parent.parent
        config_file = current_dir / "entity_mapping.json"
        if config_file.exists():
            return str(config_file)
        
        return None
    
    def get_field_for_entity_type(self, entity_type: str) -> Optional[str]:
        """
        根据实体类型获取对应的字段名
        
        Args:
            entity_type: 实体类型（如 "PB", "PC", "PF" 等）
            
        Returns:
            字段名（如 "ProvinceName", "CityName" 等），如果未找到则返回None
        """
        if not self._mapping_config:
            return None
        
        for field_name, field_config in self._mapping_config["mappings"].items():
            if entity_type in field_config.get("entity_types", []):
                return field_name
        
        # 检查是否是未映射类型，如果是，返回others字段（如果others配置了default_for_unmapped）
        others_config = self._mapping_config["mappings"].get("others", {})
        if others_config.get("default_for_unmapped", False):
            return "others"
        
        return None
    
    def get_entity_types_for_field(self, field_name: str) -> List[str]:
        """
        获取指定字段对应的所有实体类型
        
        Args:
            field_name: 字段名（如 "ProvinceName", "AreasInfo" 等）
            
        Returns:
            实体类型列表
        """
        if not self._mapping_config:
            return []
        
        field_config = self._mapping_config["mappings"].get(field_name, {})
        return field_config.get("entity_types", [])
    
    def is_single_value_field(self, field_name: str) -> bool:
        """
        判断字段是否为单值字段
        
        Args:
            field_name: 字段名
            
        Returns:
            如果是单值字段返回True，否则返回False
        """
        if not self._mapping_config:
            return False
        
        field_config = self._mapping_config["mappings"].get(field_name, {})
        return field_config.get("is_single_value", False)
    
    def get_address_range_types(self) -> List[str]:
        """
        获取用于确定地址范围的实体类型列表
        
        Returns:
            实体类型列表
        """
        if not self._mapping_config:
            return []
        
        return self._mapping_config.get("address_range_types", [])
    
    def get_phone_extraction_types(self) -> List[str]:
        """
        获取用于提取电话号码的实体类型列表
        
        Returns:
            实体类型列表
        """
        if not self._mapping_config:
            return []
        
        special_types = self._mapping_config.get("special_types", {})
        phone_config = special_types.get("phone_extraction", {})
        return phone_config.get("entity_types", ["ZZ"])
    
    def get_name_extraction_types(self) -> List[str]:
        """
        获取用于提取姓名的实体类型列表
        
        Returns:
            实体类型列表
        """
        if not self._mapping_config:
            return []
        
        special_types = self._mapping_config.get("special_types", {})
        name_config = special_types.get("name_extraction", {})
        return name_config.get("entity_types", ["ZZ"])
    
    def reload_config(self):
        """重新加载配置"""
        self._mapping_config = None
        self._load_config()
        logger.info("实体映射配置已重新加载")


# 全局单例实例
_mapping_loader = None

def get_mapping_loader() -> EntityMappingLoader:
    """获取映射配置加载器单例"""
    global _mapping_loader
    if _mapping_loader is None:
        _mapping_loader = EntityMappingLoader()
    return _mapping_loader

