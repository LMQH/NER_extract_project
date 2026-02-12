"""
第一阶段：地址数据匹配模块
执行四个匹配任务，收集所有候选结果
"""
import logging
import re
from typing import Dict, Any, List, Optional, Union
from .matcher import RegionMatcher

logger = logging.getLogger("NER_API")


class Stage1Matcher:
    """第一阶段匹配器：执行四个匹配任务"""
    
    def __init__(self, matcher: RegionMatcher, region_type_map: Dict[str, int]):
        """
        初始化第一阶段匹配器
        
        Args:
            matcher: 区域匹配器实例
            region_type_map: 区域类型映射字典
        """
        self.matcher = matcher
        self.region_type_map = region_type_map
    
    def _extract_region_name_from_field(self, field_value: Any) -> str:
        """
        从字段值中提取区域名称
        
        Args:
            field_value: 字段值，可能是字符串或字典
        
        Returns:
            区域名称字符串
        """
        if not field_value:
            return ''
        
        if isinstance(field_value, dict):
            return field_value.get('region_name', '').strip()
        elif isinstance(field_value, str):
            return field_value.strip()
        else:
            return str(field_value).strip()
    
    def _process_match_result(
        self,
        result: Union[Dict[str, Any], List[Dict[str, Any]], None],
        candidates: List[Dict[str, Any]],
        step_name: str,
        field_name: str,
        field_value: str,
        region_type: int
    ) -> None:
        """
        统一处理匹配结果
        
        Args:
            result: 匹配结果（可能是dict、list或None）
            candidates: 候选列表（会被修改）
            step_name: 步骤名称（用于日志）
            field_name: 字段名（用于日志）
            field_value: 字段值（用于日志）
            region_type: 区域类型（用于日志）
        """
        if isinstance(result, dict):
            candidates.append(result)
            logger.debug(f"{step_name}成功: 在region_type={region_type}中通过{field_name}='{field_value}'找到唯一结果")
        elif isinstance(result, list):
            candidates.extend(result)
            logger.debug(f"{step_name}匹配到候选列表: 在region_type={region_type}中通过{field_name}='{field_value}'找到{len(result)}个候选记录")
        else:
            logger.debug(f"{step_name}未匹配: 在region_type={region_type}中通过{field_name}='{field_value}'未找到任何结果")
    
    def remove_matched_region_from_string(
        self,
        original_string: str,
        match_result: Union[Dict[str, Any], List[Dict[str, Any]]]
    ) -> str:
        """
        从字符串中移除匹配到的region_name子串
        
        如果匹配结果是候选列表，清除第一个匹配的region_name
        
        Args:
            original_string: 原始字符串（AreasInfo或Address）
            match_result: 匹配结果（单个字典或字典列表）
        
        Returns:
            清除后的字符串
        """
        if not original_string or not original_string.strip():
            return original_string
        
        # 获取要清除的region_name
        region_name_to_remove = None
        
        if isinstance(match_result, dict):
            # 单个匹配结果
            region_name_to_remove = match_result.get('region_name', '').strip()
        elif isinstance(match_result, list) and len(match_result) > 0:
            # 候选列表，取第一个
            region_name_to_remove = match_result[0].get('region_name', '').strip()
        
        if not region_name_to_remove:
            return original_string
        
        # 从字符串中移除region_name
        # 处理边界情况：region_name可能在开头、中间或结尾
        result_string = original_string
        
        # 移除region_name（支持在任意位置）
        if region_name_to_remove in result_string:
            # 先尝试移除完整的region_name
            result_string = result_string.replace(region_name_to_remove, '', 1)  # 只替换第一个匹配
            
            # 清理可能产生的多余空格
            # 如果region_name在开头或结尾，移除后可能有空格
            result_string = result_string.strip()
            
            # 如果region_name在中间，移除后可能有连续空格，需要清理
            result_string = re.sub(r'\s+', ' ', result_string)  # 将多个连续空格替换为单个空格
            
            logger.debug(f"从字符串中清除region_name: 原字符串='{original_string}', region_name='{region_name_to_remove}', 清除后='{result_string}'")
        
        return result_string
    
    def task1_match_street_name(
        self, 
        street_name_str: str,
        areas_info_str: str,
        address_str: str,
        data: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        任务1：region_type=1004匹配（街道/镇级别）
        依次使用StreetName、AreasInfo（若前者失败）、Address（若前两者都失败）进行匹配
        
        Args:
            street_name_str: StreetName字段值
            areas_info_str: AreasInfo字段值
            address_str: Address字段值
        
        Returns:
            候选列表（单个结果也放入列表）
        """
        region_type = self.region_type_map.get('StreetName')  # 1004
        candidates = []
        
        logger.debug(f"任务1开始: region_type=1004, StreetName='{street_name_str}', AreasInfo='{areas_info_str}', Address='{address_str}'")
        
        # 步骤1：使用StreetName匹配
        if street_name_str:
            logger.debug(f"任务1步骤1开始: 使用StreetName='{street_name_str}'在region_type=1004中匹配")
            result = self.matcher.match_region_by_field(region_type, street_name_str, 'StreetName')
            self._process_match_result(result, candidates, "任务1步骤1", 'StreetName', street_name_str, region_type)
        else:
            logger.debug(f"任务1步骤1跳过: StreetName字段为空，跳过StreetName匹配")
        
        # 步骤2：如果上一步未成功，使用AreasInfo匹配
        if not candidates and areas_info_str:
            logger.debug(f"任务1步骤2开始: 使用AreasInfo='{areas_info_str}'在region_type=1004中匹配")
            result = self.matcher.match_region_by_field(region_type, areas_info_str, 'AreasInfo')
            self._process_match_result(result, candidates, "任务1步骤2", 'AreasInfo', areas_info_str, region_type)
            # 清除AreasInfo中匹配到的region_name
            if data is not None and (isinstance(result, dict) or (isinstance(result, list) and result)):
                cleared_areas_info = self.remove_matched_region_from_string(areas_info_str, result)
                data['AreasInfo'] = cleared_areas_info
                logger.debug(f"任务1步骤2清除AreasInfo: '{areas_info_str}' -> '{cleared_areas_info}'")
        elif not areas_info_str:
            logger.debug(f"任务1步骤2跳过: AreasInfo字段为空，跳过AreasInfo匹配")
        
        # 步骤3：如果上一步未成功，使用Address匹配
        if not candidates and address_str:
            logger.debug(f"任务1步骤3开始: 使用Address='{address_str}'在region_type=1004中匹配")
            result = self.matcher.match_region_by_field(region_type, address_str, 'Address')
            self._process_match_result(result, candidates, "任务1步骤3", 'Address', address_str, region_type)
            # 清除Address中匹配到的region_name
            if data is not None and (isinstance(result, dict) or (isinstance(result, list) and result)):
                cleared_address = self.remove_matched_region_from_string(address_str, result)
                data['Address'] = cleared_address
                logger.debug(f"任务1步骤3清除Address: '{address_str}' -> '{cleared_address}'")
        elif not address_str:
            logger.debug(f"任务1步骤3跳过: Address字段为空，跳过Address匹配")
        
        return candidates
    
    def task2_match_exp_area_name(
        self,
        street_name_str: str,
        areas_info_str: str,
        address_str: str,
        exp_area_name_str: str,
        data: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        任务2：region_type=1003匹配（区/县级别）
        依次使用StreetName、AreasInfo（若前者失败）、Address（若前两者都失败）进行匹配，
        然后无论上一步是否成功都使用ExpAreaName在1003中匹配（收集所有结果）
        
        Args:
            street_name_str: StreetName字段值
            areas_info_str: AreasInfo字段值
            address_str: Address字段值
            exp_area_name_str: ExpAreaName字段值
        
        Returns:
            候选列表（合并所有匹配结果）
        """
        region_type = self.region_type_map.get('ExpAreaName')  # 1003
        candidates = []
        
        # 步骤1：使用StreetName在1003中匹配
        if street_name_str:
            logger.debug(f"任务2步骤1开始: 使用StreetName='{street_name_str}'在region_type=1003中匹配")
            result = self.matcher.match_region_by_field(region_type, street_name_str, 'StreetName(1003)')
            self._process_match_result(result, candidates, "任务2步骤1", 'StreetName', street_name_str, region_type)
        else:
            logger.debug(f"任务2步骤1跳过: StreetName字段为空，跳过StreetName匹配")
        
        # 步骤2：如果上一步未成功，使用AreasInfo在1003中匹配
        if not candidates and areas_info_str:
            logger.debug(f"任务2步骤2开始: 使用AreasInfo='{areas_info_str}'在region_type=1003中匹配")
            result = self.matcher.match_region_by_field(region_type, areas_info_str, 'AreasInfo(1003)')
            self._process_match_result(result, candidates, "任务2步骤2", 'AreasInfo', areas_info_str, region_type)
            # 清除AreasInfo中匹配到的region_name
            if data is not None and (isinstance(result, dict) or (isinstance(result, list) and result)):
                cleared_areas_info = self.remove_matched_region_from_string(areas_info_str, result)
                data['AreasInfo'] = cleared_areas_info
                logger.debug(f"任务2步骤2清除AreasInfo: '{areas_info_str}' -> '{cleared_areas_info}'")
        elif not areas_info_str:
            logger.debug(f"任务2步骤2跳过: AreasInfo字段为空，跳过AreasInfo匹配")
        
        # 步骤3：如果上一步未成功，使用Address在1003中匹配
        if not candidates and address_str:
            logger.debug(f"任务2步骤3开始: 使用Address='{address_str}'在region_type=1003中匹配")
            result = self.matcher.match_region_by_field(region_type, address_str, 'Address(1003)')
            self._process_match_result(result, candidates, "任务2步骤3", 'Address', address_str, region_type)
            # 清除Address中匹配到的region_name
            if data is not None and (isinstance(result, dict) or (isinstance(result, list) and result)):
                cleared_address = self.remove_matched_region_from_string(address_str, result)
                data['Address'] = cleared_address
                logger.debug(f"任务2步骤3清除Address: '{address_str}' -> '{cleared_address}'")
        elif not address_str:
            logger.debug(f"任务2步骤3跳过: Address字段为空，跳过Address匹配")
        
        # 步骤4：无论上一步是否成功，都使用ExpAreaName在1003中匹配
        if exp_area_name_str:
            logger.debug(f"任务2步骤4开始: 使用ExpAreaName='{exp_area_name_str}'在region_type=1003中匹配")
            result = self.matcher.match_region_by_field(region_type, exp_area_name_str, 'ExpAreaName')
            self._process_match_result(result, candidates, "任务2步骤4", 'ExpAreaName', exp_area_name_str, region_type)
        else:
            logger.debug(f"任务2步骤4跳过: ExpAreaName字段为空，跳过ExpAreaName匹配")
        
        # 去重：基于id去重
        seen_ids = set()
        unique_candidates = []
        for candidate in candidates:
            candidate_id = candidate.get('id')
            if candidate_id and candidate_id not in seen_ids:
                seen_ids.add(candidate_id)
                unique_candidates.append(candidate)
        
        return unique_candidates
    
    def task3_match_city_name(
        self,
        exp_area_name_str: str,
        city_name_str: str
    ) -> List[Dict[str, Any]]:
        """
        任务3：region_type=1002匹配（市级别）
        使用ExpAreaName匹配，而后是CityName进行匹配
        
        Args:
            exp_area_name_str: ExpAreaName字段值
            city_name_str: CityName字段值
        
        Returns:
            候选列表
        """
        region_type = self.region_type_map.get('CityName')  # 1002
        candidates = []
        
        # 步骤1：使用ExpAreaName在1002中匹配
        if exp_area_name_str:
            logger.debug(f"任务3步骤1开始: 使用ExpAreaName='{exp_area_name_str}'在region_type=1002中匹配")
            result = self.matcher.match_region_by_field(region_type, exp_area_name_str, 'ExpAreaName(1002)')
            self._process_match_result(result, candidates, "任务3步骤1", 'ExpAreaName', exp_area_name_str, region_type)
        else:
            logger.debug(f"任务3步骤1跳过: ExpAreaName字段为空，跳过ExpAreaName匹配")
        
        # 步骤2：使用CityName在1002中匹配
        if city_name_str:
            logger.debug(f"任务3步骤2开始: 使用CityName='{city_name_str}'在region_type=1002中匹配")
            result = self.matcher.match_region_by_field(region_type, city_name_str, 'CityName')
            self._process_match_result(result, candidates, "任务3步骤2", 'CityName', city_name_str, region_type)
        else:
            logger.debug(f"任务3步骤2跳过: CityName字段为空，跳过CityName匹配")
        
        # 去重：基于id去重
        seen_ids = set()
        unique_candidates = []
        for candidate in candidates:
            candidate_id = candidate.get('id')
            if candidate_id and candidate_id not in seen_ids:
                seen_ids.add(candidate_id)
                unique_candidates.append(candidate)
        
        return unique_candidates
    
    def task4_match_province_name(
        self,
        city_name_str: str,
        province_name_str: str
    ) -> List[Dict[str, Any]]:
        """
        任务4：region_type=1001匹配（省级别）
        使用CityName进行匹配，而后用ProvinceName进行匹配
        
        Args:
            city_name_str: CityName字段值
            province_name_str: ProvinceName字段值
        
        Returns:
            候选列表
        """
        region_type = self.region_type_map.get('ProvinceName')  # 1001
        candidates = []
        
        # 步骤1：使用CityName在1001中匹配
        if city_name_str:
            logger.debug(f"任务4步骤1开始: 使用CityName='{city_name_str}'在region_type=1001中匹配")
            result = self.matcher.match_region_by_field(region_type, city_name_str, 'CityName(1001)')
            self._process_match_result(result, candidates, "任务4步骤1", 'CityName', city_name_str, region_type)
        else:
            logger.debug(f"任务4步骤1跳过: CityName字段为空，跳过CityName匹配")
        
        # 步骤2：使用ProvinceName在1001中匹配
        if province_name_str:
            logger.debug(f"任务4步骤2开始: 使用ProvinceName='{province_name_str}'在region_type=1001中匹配")
            result = self.matcher.match_region_by_field(region_type, province_name_str, 'ProvinceName')
            # 如果匹配失败，尝试去掉"特别行政区"后缀再匹配
            if result is None:
                result = self.matcher._try_match_province_without_special_region(
                    region_type, province_name_str, 'ProvinceName'
                )
            self._process_match_result(result, candidates, "任务4步骤2", 'ProvinceName', province_name_str, region_type)
        else:
            logger.debug(f"任务4步骤2跳过: ProvinceName字段为空，跳过ProvinceName匹配")
        
        # 去重：基于id去重
        seen_ids = set()
        unique_candidates = []
        for candidate in candidates:
            candidate_id = candidate.get('id')
            if candidate_id and candidate_id not in seen_ids:
                seen_ids.add(candidate_id)
                unique_candidates.append(candidate)
        
        return unique_candidates
    
    def execute_stage1_parallel(self, data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        执行四个匹配任务，返回四个候选表
        
        Args:
            data: 输入数据字典，包含地址相关字段
        
        Returns:
            候选表字典，格式为：
            {
                "StreetName": [...],
                "ExpAreaName": [...],
                "CityName": [...],
                "ProvinceName": [...]
            }
        """
        # 提取字段值
        street_name_str = self._extract_region_name_from_field(data.get('StreetName'))
        areas_info_str = data.get('AreasInfo', '').strip() if isinstance(data.get('AreasInfo'), str) else ''
        address_str = data.get('Address', '').strip() if isinstance(data.get('Address'), str) else ''
        exp_area_name_str = self._extract_region_name_from_field(data.get('ExpAreaName'))
        city_name_str = self._extract_region_name_from_field(data.get('CityName'))
        province_name_str = self._extract_region_name_from_field(data.get('ProvinceName'))
        
        # 执行四个匹配任务
        street_candidates = self.task1_match_street_name(street_name_str, areas_info_str, address_str, data)
        
        # 重新获取AreasInfo和Address的值（可能在task1中被清除）
        areas_info_str = data.get('AreasInfo', '').strip() if isinstance(data.get('AreasInfo'), str) else ''
        address_str = data.get('Address', '').strip() if isinstance(data.get('Address'), str) else ''
        
        exp_area_candidates = self.task2_match_exp_area_name(street_name_str, areas_info_str, address_str, exp_area_name_str, data)
        city_candidates = self.task3_match_city_name(exp_area_name_str, city_name_str)
        province_candidates = self.task4_match_province_name(city_name_str, province_name_str)
        
        # 返回候选表
        candidate_tables = {
            'StreetName': street_candidates,
            'ExpAreaName': exp_area_candidates,
            'CityName': city_candidates,
            'ProvinceName': province_candidates
        }
        
        logger.info(f"第一阶段匹配完成: StreetName={len(street_candidates)}个候选, "
                   f"ExpAreaName={len(exp_area_candidates)}个候选, "
                   f"CityName={len(city_candidates)}个候选, "
                   f"ProvinceName={len(province_candidates)}个候选")
        
        return candidate_tables

