"""
格式转换工具函数
用于将不同模型的返回结果转换为统一格式
保留映射和预处理相关功能
"""
import logging
from typing import Dict, Any, Optional, List
from src.config.constants import (
    DEFAULT_EBUSINESS_ID, DEFAULT_SUCCESS_CODE, DEFAULT_ERROR_CODE,
    DEFAULT_SUCCESS_REASON, DEFAULT_ERROR_REASON, DEFAULT_ENTITY_MAPPING,
    ENTITY_TYPE_PROVINCE, ENTITY_TYPE_CITY, ENTITY_TYPE_DISTRICT,
    ENTITY_TYPE_STREET, ENTITY_TYPE_ROAD, ENTITY_TYPE_UNIT_ADDRESS,
    ENTITY_TYPE_NUMBER_ENG, ENTITY_TYPE_OTHER, PHONE_PATTERN, CHINESE_NAME_PATTERN
)
from src.config.entity_mapping_loader import get_mapping_loader
from src.utils.address_parser import AddressParser
from src.utils.entity_extractor import EntityExtractor

logger = logging.getLogger("NER_API")


def _preprocess_remove_special_administrative_region(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    预处理函数：删除特别行政区数据
    
    在模型数据映射阶段前，删除output中type为"PD"且span为"特别行政区"的条目。
    
    Args:
        entities: 实体列表，每个实体包含type、span等字段
    
    Returns:
        过滤后的实体列表
    """
    if not entities:
        return entities
    
    filtered_entities = []
    removed_count = 0
    
    for entity in entities:
        entity_type = entity.get("type", "")
        span = entity.get("span", "")
        
        # 检查是否为type="PD"且span="特别行政区"的条目
        if entity_type == "PD" and span == "特别行政区":
            removed_count += 1
            logger.debug(f"预处理删除特别行政区: type={entity_type}, span={span}")
        else:
            filtered_entities.append(entity)
    
    if removed_count > 0:
        logger.info(f"预处理完成: 删除了{removed_count}条特别行政区数据（type=PD, span=特别行政区）")
    
    return filtered_entities


def _postprocess_fix_special_administrative_region(data: Dict[str, Any], original_text: str = "") -> Dict[str, Any]:
    """
    后处理函数：修复特别行政区相关的数据格式问题
    
    问题场景：
    - 模型将"香港特别行政区"拆分为"香港"（PB）和"特别行政区"（PD）
    - 预处理删除了"特别行政区"（PD），导致ProvinceName只保留了"香港"
    - 需要在后处理阶段补全ProvinceName为"香港特别行政区"
    
    修复策略：
    1. 检查ProvinceName是否为"香港"或"澳门"
    2. 检查原始文本是否包含 ProvinceName + "特别行政区"
    3. 如果满足条件，将ProvinceName补全为"香港特别行政区"或"澳门特别行政区"
    4. 只修改ProvinceName，不修改其他字段
    
    Args:
        data: 数据字典，包含ProvinceName、CityName、ExpAreaName等字段
        original_text: 原始输入文本，用于检查是否包含"特别行政区"
    
    Returns:
        修复后的数据字典
    """
    if not data:
        return data
    
    province_name = data.get("ProvinceName", "").strip()
    original_text = original_text.strip() if original_text else ""
    
    # 定义特别行政区省份名映射
    special_region_provinces = {
        "香港": "香港特别行政区",
        "澳门": "澳门特别行政区"
    }
    
    # 检查是否需要修复
    if province_name in special_region_provinces and original_text:
        # 检查原始文本是否包含 ProvinceName + "特别行政区"
        expected_full_name = special_region_provinces[province_name]
        if expected_full_name in original_text:
            # 补全ProvinceName
            data["ProvinceName"] = expected_full_name
            logger.info(f"后处理完成: 将ProvinceName从'{province_name}'补全为'{expected_full_name}'")
    
    return data


# 将 mgeo_geographic_elements_tagging_chinese_base 模型的返回结果转换为规定格式
def convert_mgeo_tagging_to_output_format(mgeo_result: Dict[str, Any], original_text: str = "") -> Dict[str, Any]:
    """
    将 mgeo_geographic_elements_tagging_chinese_base 模型的返回结果转换为规定格式
    
    新模型的实体类型映射：
    - prov -> ProvinceName (省)
    - city -> CityName (市)
    - district -> ExpAreaName (区/县)
    - town -> StreetName (街道/镇)
    - road -> Address (路)
    - road_number -> Address (路号)
    - poi -> Address (POI)
    - house_number -> Address (门牌号)
    - other -> 其他信息（用于提取电话和姓名）
    
    Args:
        mgeo_result: mgeo_geographic_elements_tagging_chinese_base 模型的返回结果
        original_text: 原始输入文本（用于提取电话和姓名）
    
    Returns:
        规定格式的结果
    """
    # 检查是否是已包装的格式（包含 EBusinessID 和 Data）
    if "EBusinessID" in mgeo_result and "Data" in mgeo_result:
        # 从 Data 中提取 entities 和 text
        data = mgeo_result.get("Data", {})
        entities_data = data.get("entities", {})
        text = data.get("text", original_text)
        ebusiness_id = mgeo_result.get("EBusinessID", "2223333")
        success = mgeo_result.get("Success", True)
        reason = mgeo_result.get("Reason", "解析成功")
        result_code = mgeo_result.get("ResultCode", "100")
    else:
        # 直接格式，从根级别提取
        entities_data = mgeo_result.get("entities", {})
        text = mgeo_result.get("text", original_text)
        ebusiness_id = "2223333"
        success = True
        reason = "解析成功"
        result_code = "100"
    
    # 初始化结果
    result = _create_default_result(ebusiness_id, success, reason, result_code)
    
    # 检查是否有错误
    if "error" in mgeo_result or not success:
        result["Success"] = False
        result["Reason"] = mgeo_result.get("error", reason if not success else DEFAULT_ERROR_REASON)
        result["ResultCode"] = DEFAULT_ERROR_CODE
        return result
    
    # 获取实体列表
    entities = entities_data.get("output", [])
    
    if not entities:
        return result
    
    # 预处理：删除特别行政区数据（在模型数据映射阶段前）
    entities = _preprocess_remove_special_administrative_region(entities)
    
    if not entities:
        return result
    
    # 按实体类型分类
    province = ""
    city = ""
    district = ""
    street = ""
    address_entities = []
    other_entities = []
    
    # 按 start 位置排序，确保顺序正确
    sorted_entities = sorted(entities, key=lambda x: x.get("start", 0))
    
    for entity in sorted_entities:
        entity_type = entity.get("type", "")
        span = entity.get("span", "")
        
        # 新模型的实体类型映射
        if entity_type == "prov":
            province = span
        elif entity_type == "city":
            city = span
        elif entity_type == "district":
            district = span
        elif entity_type == "town":
            street = span
        elif entity_type in ["road", "road_number", "poi", "house_number"]:
            # 这些类型都归入详细地址
            address_entities.append(entity)
        elif entity_type == "other":
            other_entities.append(span)
    
    # 填充地址信息
    result["Data"]["ProvinceName"] = province
    result["Data"]["CityName"] = city
    result["Data"]["ExpAreaName"] = district
    result["Data"]["StreetName"] = street
    
    # 按位置顺序组合详细地址
    if address_entities:
        address_entities_sorted = sorted(address_entities, key=lambda x: x.get("start", 0))
        address_parts = [entity.get("span", "") for entity in address_entities_sorted]
        result["Data"]["Address"] = "".join(address_parts)
    
    # 从原始文本中提取电话和姓名
    _extract_phone_and_name_from_mgeo(
        result, other_entities, sorted_entities, original_text or text
    )
    
    # 后处理：修复特别行政区相关的数据格式问题（通用方案）
    result["Data"] = _postprocess_fix_special_administrative_region(result["Data"], original_text or text)
    
    # 重新排序Data字段
    result["Data"] = reorder_data_fields(result["Data"])
    
    return result


def _smart_assign_entity(
    entity: Dict[str, Any],
    street_entities: List[Dict[str, Any]],
    areas_info_entities: List[Dict[str, Any]]
) -> str:
    """
    Entity标签智能分配函数
    
    根据当前StreetName和AreasInfo的状态，动态决定Entity应该放入哪个字段。
    
    分配规则：
    - 如果StreetName为空 → 返回 'street'（放入StreetName）
    - 如果StreetName不为空且AreasInfo为空 → 返回 'areas_info'（放入AreasInfo）
    - 如果两者都不为空 → 返回 'address'（放入Address）
    
    Args:
        entity: Entity实体对象（用于兼容，当前未使用）
        street_entities: 当前已收集的StreetName相关实体列表
        areas_info_entities: 当前已收集的AreasInfo相关实体列表
    
    Returns:
        目标列表标识字符串：'street'、'areas_info' 或 'address'
    """
    # 计算当前street_entities组合后的StreetName值（按位置排序后拼接）
    if street_entities:
        street_entities_sorted = sorted(street_entities, key=lambda x: x.get("start", 0))
        street_name = "".join([entity.get("span", "") for entity in street_entities_sorted])
    else:
        street_name = ""
    
    # 计算当前areas_info_entities组合后的AreasInfo值（按位置排序后拼接）
    if areas_info_entities:
        areas_info_entities_sorted = sorted(areas_info_entities, key=lambda x: x.get("start", 0))
        areas_info = "".join([entity.get("span", "") for entity in areas_info_entities_sorted])
    else:
        areas_info = ""
    
    # 根据判断规则返回目标列表标识
    if not street_name:
        # StreetName为空，放入StreetName
        return 'street'
    elif not areas_info:
        # StreetName不为空且AreasInfo为空，放入AreasInfo
        return 'areas_info'
    else:
        # 两者都不为空，放入Address
        return 'address'


def convert_mgeo_to_output_format(mgeo_result: Dict[str, Any], original_text: str = "") -> Dict[str, Any]:
    """
    将 mgeo 模型的返回结果转换为规定格式
    
    实体类型映射关系从 entity_mapping.json 配置文件加载，如果配置文件不存在则使用默认映射。
    
    Args:
        mgeo_result: mgeo 模型的返回结果
        original_text: 原始输入文本（用于提取电话和姓名）
    
    Returns:
        qwen-flash 格式的结果
    """
    # 检查是否是已包装的格式（包含 EBusinessID 和 Data）
    if "EBusinessID" in mgeo_result and "Data" in mgeo_result:
        # 从 Data 中提取 entities 和 text
        data = mgeo_result.get("Data", {})
        entities_data = data.get("entities", {})
        text = data.get("text", original_text)
        ebusiness_id = mgeo_result.get("EBusinessID", "2223333")
        success = mgeo_result.get("Success", True)
        reason = mgeo_result.get("Reason", "解析成功")
        result_code = mgeo_result.get("ResultCode", "100")
    else:
        # 直接格式，从根级别提取
        entities_data = mgeo_result.get("entities", {})
        text = mgeo_result.get("text", original_text)
        ebusiness_id = "2223333"
        success = True
        reason = "解析成功"
        result_code = "100"
    
    # 初始化结果
    result = _create_default_result(ebusiness_id, success, reason, result_code)
    
    # 检查是否有错误
    if "error" in mgeo_result or not success:
        result["Success"] = False
        result["Reason"] = mgeo_result.get("error", reason if not success else DEFAULT_ERROR_REASON)
        result["ResultCode"] = DEFAULT_ERROR_CODE
        return result
    
    # 获取实体列表
    entities = entities_data.get("output", [])
    
    if not entities:
        return result
    
    # 预处理：删除特别行政区数据（在模型数据映射阶段前）
    entities = _preprocess_remove_special_administrative_region(entities)
    
    if not entities:
        return result
    
    # 获取映射配置加载器
    mapping_loader = get_mapping_loader()
    
    # 按实体类型分类
    province = ""
    city = ""
    district = ""
    street_entities = []
    areas_info_entities = []
    address_entities = []
    others_entities = []
    other_entities = []  # 用于存储 ZZ，用于提取电话和姓名
    
    # 从配置中获取各字段对应的实体类型
    street_types = mapping_loader.get_entity_types_for_field("StreetName")
    areas_info_types = mapping_loader.get_entity_types_for_field("AreasInfo")
    address_types = mapping_loader.get_entity_types_for_field("Address")
    others_types = mapping_loader.get_entity_types_for_field("others")
    phone_extraction_types = mapping_loader.get_phone_extraction_types()
    
    # 按 start 位置排序，确保顺序正确
    sorted_entities = sorted(entities, key=lambda x: x.get("start", 0))
    
    for entity in sorted_entities:
        entity_type = entity.get("type", "")
        span = entity.get("span", "")
        
        if entity_type == ENTITY_TYPE_PROVINCE:
            province = span
        elif entity_type == ENTITY_TYPE_CITY:
            city = span
        elif entity_type == ENTITY_TYPE_DISTRICT:
            district = span
        elif entity_type in street_types:
            street_entities.append(entity)
        elif entity_type in areas_info_types:
            areas_info_entities.append(entity)
        elif entity_type == "Entity":
            # Entity类型使用智能分配逻辑
            target_list = _smart_assign_entity(entity, street_entities, areas_info_entities)
            if target_list == 'street':
                street_entities.append(entity)
            elif target_list == 'areas_info':
                areas_info_entities.append(entity)
            else:
                address_entities.append(entity)
        elif entity_type in address_types:
            address_entities.append(entity)
        elif entity_type in others_types:
            others_entities.append(entity)
        elif entity_type in phone_extraction_types:
            # ZZ: 未知，用于提取电话和姓名
            other_entities.append(span)
        else:
            # 其他未映射的类型也归入 others
            others_entities.append(entity)
    
    # 填充地址信息
    result["Data"]["ProvinceName"] = province
    result["Data"]["CityName"] = city
    result["Data"]["ExpAreaName"] = district
    
    # 组合 StreetName（按位置顺序）
    if street_entities:
        street_entities_sorted = sorted(street_entities, key=lambda x: x.get("start", 0))
        street_parts = [entity.get("span", "") for entity in street_entities_sorted]
        result["Data"]["StreetName"] = "".join(street_parts)
    
    # 组合 AreasInfo（按位置顺序）
    if areas_info_entities:
        areas_info_entities_sorted = sorted(areas_info_entities, key=lambda x: x.get("start", 0))
        areas_info_parts = [entity.get("span", "") for entity in areas_info_entities_sorted]
        result["Data"]["AreasInfo"] = "".join(areas_info_parts)
    
    # 组合 Address（按位置顺序）
    if address_entities:
        address_entities_sorted = sorted(address_entities, key=lambda x: x.get("start", 0))
        address_parts = [entity.get("span", "") for entity in address_entities_sorted]
        result["Data"]["Address"] = "".join(address_parts)
    
    # 组合 others（按位置顺序）
    if others_entities:
        others_entities_sorted = sorted(others_entities, key=lambda x: x.get("start", 0))
        others_parts = [entity.get("span", "") for entity in others_entities_sorted]
        result["Data"]["others"] = "".join(others_parts)
    
    # 从原始文本中提取电话和姓名
    _extract_phone_and_name_from_mgeo(
        result, other_entities, sorted_entities, original_text or text
    )
    
    # 后处理：修复特别行政区相关的数据格式问题（通用方案）
    result["Data"] = _postprocess_fix_special_administrative_region(result["Data"], original_text or text)
    
    # 重新排序Data字段
    result["Data"] = reorder_data_fields(result["Data"])
    
    return result


def parse_chinese_address(address_text: str) -> Dict[str, str]:
    """
    使用正则表达式和规则解析中文地址字符串
    
    将完整的地址字符串（如"广东省深圳市龙岗区坂田街道长坑路西2巷2号202"）
    分解为省、市、区、街道、详细地址等部分
    
    Args:
        address_text: 完整的地址字符串
    
    Returns:
        包含省、市、区、街道、详细地址的字典
    """
    return AddressParser.parse_chinese_address(address_text)


def reorder_data_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    重新排序Data字典的字段，确保顺序为：
    ProvinceName, CityName, ExpAreaName, StreetName, AreasInfo, Address, others, Mobile, Name
    
    Args:
        data: 原始的Data字典
    
    Returns:
        重新排序后的Data字典
    """
    return {
        "ProvinceName": data.get("ProvinceName", ""),
        "CityName": data.get("CityName", ""),
        "ExpAreaName": data.get("ExpAreaName", ""),
        "StreetName": data.get("StreetName", ""),
        "AreasInfo": data.get("AreasInfo", ""),
        "Address": data.get("Address", ""),
        "others": data.get("others", ""),
        "Mobile": data.get("Mobile", ""),
        "Name": data.get("Name", "")
    }


def _create_default_result(
    ebusiness_id: str = DEFAULT_EBUSINESS_ID,
    success: bool = True,
    reason: str = DEFAULT_SUCCESS_REASON,
    result_code: str = DEFAULT_SUCCESS_CODE
) -> Dict[str, Any]:
    """创建默认格式的结果字典"""
    return {
        "EBusinessID": ebusiness_id,
        "Data": {
            "ProvinceName": "",
            "CityName": "",
            "ExpAreaName": "",
            "StreetName": "",
            "AreasInfo": "",
            "Address": "",
            "others": "",
            "Mobile": "",
            "Name": ""
        },
        "Success": success,
        "Reason": reason,
        "ResultCode": result_code
    }


def _extract_phone_and_name_from_mgeo(
    result: Dict[str, Any],
    other_entities: List[str],
    sorted_entities: List[Dict[str, Any]],
    text: str
) -> None:
    """从MGeo模型的other_entities中提取电话和姓名"""
    import re
    from src.config.constants import PHONE_PATTERN, CHINESE_NAME_PATTERN, ADDRESS_KEYWORDS
    
    # 首先尝试从 other_entities 中识别
    for entity_text in other_entities:
        if re.match(PHONE_PATTERN, entity_text):
            result["Data"]["Mobile"] = entity_text
        elif re.match(CHINESE_NAME_PATTERN, entity_text):
            result["Data"]["Name"] = entity_text
    
    # 如果从 other_entities 中没有找到，尝试从原始文本中提取
    if not result["Data"]["Mobile"]:
        phone = EntityExtractor.extract_phone_from_text(text)
        if phone:
            result["Data"]["Mobile"] = phone
    
    if not result["Data"]["Name"]:
        # 获取映射配置加载器
        mapping_loader = get_mapping_loader()
        
        # 找到所有地址实体的位置范围（包括所有地址相关类型）
        address_ranges = []
        address_range_types = mapping_loader.get_address_range_types()
        
        for entity in sorted_entities:
            entity_type = entity.get("type", "")
            # 检查是否是地址相关类型（包括省市区、街道、区域信息、详细地址等）
            if entity_type in address_range_types or entity_type in [
                ENTITY_TYPE_PROVINCE, ENTITY_TYPE_CITY, ENTITY_TYPE_DISTRICT
            ]:
                start = entity.get("start", 0)
                end = entity.get("end", 0)
                address_ranges.append((start, end))
        
        # 在非地址部分查找姓名
        name = AddressParser.find_name_in_non_address_text(text, address_ranges)
        if name:
            result["Data"]["Name"] = name

