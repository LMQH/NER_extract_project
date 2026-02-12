"""
第二阶段：候选结果处理模块
从最高级别向下筛选，通过parent_id关系确定唯一结果
"""
import os
import logging
import copy
from typing import Dict, Any, List, Optional, Tuple
from .matcher import RegionMatcher

logger = logging.getLogger("NER_API")


class Stage2Resolver:
    """第二阶段解析器：处理候选表，确定唯一结果"""
    
    def __init__(self, matcher: RegionMatcher, region_type_map: Dict[str, int]):
        """
        初始化第二阶段解析器
        
        Args:
            matcher: 区域匹配器实例
            region_type_map: 区域类型映射字典
        """
        self.matcher = matcher
        self.region_type_map = region_type_map
        
        # 候选表最大元素数量（从环境变量读取，默认20）
        max_candidates_str = os.getenv('MAX_CANDIDATES_COUNT', '20')
        try:
            self.max_candidates_count = int(max_candidates_str)
            if self.max_candidates_count < 1:
                logger.warning(f"MAX_CANDIDATES_COUNT配置值无效: {max_candidates_str}，使用默认值20")
                self.max_candidates_count = 20
        except (ValueError, TypeError):
            logger.warning(f"MAX_CANDIDATES_COUNT配置值无效: {max_candidates_str}，使用默认值20")
            self.max_candidates_count = 20
        
        logger.debug(f"候选表最大元素数量限制: {self.max_candidates_count}")
        
        # 字段名到region_type的映射（用于向上追溯）
        self.field_to_region_type = {
            'ProvinceName': self.region_type_map.get('ProvinceName'),
            'CityName': self.region_type_map.get('CityName'),
            'ExpAreaName': self.region_type_map.get('ExpAreaName'),
            'StreetName': self.region_type_map.get('StreetName')
        }
        
        # region_type到字段名的映射（用于向上追溯）
        self.region_type_to_field = {
            self.region_type_map.get('ProvinceName'): 'ProvinceName',
            self.region_type_map.get('CityName'): 'CityName',
            self.region_type_map.get('ExpAreaName'): 'ExpAreaName',
            self.region_type_map.get('StreetName'): 'StreetName'
        }
        
        # 字段的上级字段映射
        self.field_to_upper_field = {
            'StreetName': 'ExpAreaName',
            'ExpAreaName': 'CityName',
            'CityName': 'ProvinceName',
            'ProvinceName': None  # 最高级别，无上级
        }
        
        # 字段的下级字段映射
        self.field_to_lower_field = {
            'ProvinceName': 'CityName',
            'CityName': 'ExpAreaName',
            'ExpAreaName': 'StreetName',
            'StreetName': None  # 最低级别，无下级
        }
    
    def truncate_candidates(self, candidates: List[Dict[str, Any]], field_name: str = '') -> List[Dict[str, Any]]:
        """
        截断候选表，保留前max_candidates_count个元素
        
        Args:
            candidates: 候选列表
            field_name: 字段名（用于日志）
        
        Returns:
            截断后的候选列表
        """
        if not candidates or len(candidates) <= self.max_candidates_count:
            return candidates
        
        original_count = len(candidates)
        truncated = candidates[:self.max_candidates_count]
        logger.warning(f"{field_name}候选表数量超过限制: 原始数量={original_count}, 最大限制={self.max_candidates_count}, 已截断为{len(truncated)}个")
        return truncated
    
    def _build_candidate_list(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        构建候选列表，统一格式
        
        Args:
            candidates: 原始候选列表
        
        Returns:
            格式化后的候选列表
        """
        return [
            {
                'id': c.get('id'),
                'parent_id': c.get('parent_id'),
                'region_name': c.get('region_name', '')
            }
            for c in candidates
            if c.get('id') is not None
        ]
    
    def _set_unique_value(self, result: Dict[str, Any], field_name: str, record: Dict[str, Any]) -> None:
        """
        设置唯一值格式
        
        Args:
            result: 结果字典（会被修改）
            field_name: 字段名
            record: 区域记录字典
        """
        result[field_name] = {
            'id': record.get('id'),
            'parent_id': record.get('parent_id'),
            'region_name': record.get('region_name'),
            'region_type': record.get('region_type')
        }
    
    def _set_candidate_format(self, result: Dict[str, Any], field_name: str, candidates: List[Dict[str, Any]]) -> None:
        """
        设置候选表格式
        
        Args:
            result: 结果字典（会被修改）
            field_name: 字段名
            candidates: 候选列表
        """
        candidate_list = self._build_candidate_list(candidates)
        candidate_list = self.truncate_candidates(candidate_list, field_name)
        result[field_name] = {
            'candidates': candidate_list,
            'region_type': candidates[0].get('region_type') if candidates else None
        }
    
    def filter_by_parent_id(
        self, 
        candidates: List[Dict[str, Any]], 
        parent_id: int,
        expected_region_type: Optional[int] = None
    ) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        根据parent_id向下过滤候选表
        
        Args:
            candidates: 候选记录列表
            parent_id: 父级ID
            expected_region_type: 期望的region_type（用于验证）
        
        Returns:
            (唯一匹配记录, 筛选后的候选列表)
            - 如果筛选后只有1个结果：返回 (该结果, [])
            - 如果筛选后有多个结果：返回 (None, 筛选后的候选列表)
            - 如果筛选后没有结果：返回 (None, [])
        """
        if not candidates or parent_id is None:
            return None, []
        
        # 如果指定了期望的region_type，先验证候选表的一致性
        if expected_region_type is not None:
            region_types = {c.get('region_type') for c in candidates if c.get('region_type') is not None}
            if len(region_types) > 1:
                logger.warning(f"候选表中存在多个不同的region_type: {region_types}，期望region_type={expected_region_type}")
                candidates = [c for c in candidates if c.get('region_type') == expected_region_type]
            elif len(region_types) == 1 and expected_region_type not in region_types:
                logger.warning(f"候选表的region_type={region_types.pop()}与期望的region_type={expected_region_type}不匹配")
                return None, []
        
        # 根据parent_id筛选
        matches = [c for c in candidates if c.get('parent_id') == parent_id]
        
        if len(matches) == 1:
            return matches[0], []
        elif len(matches) > 1:
            logger.debug(f"根据parent_id={parent_id}过滤候选表时找到{len(matches)}条匹配记录")
            return None, matches
        else:
            logger.debug(f"根据parent_id={parent_id}过滤候选表时未找到匹配记录")
            return None, []
    
    def _is_field_empty(self, field_value: Any) -> bool:
        """
        检查字段是否为空
        
        Args:
            field_value: 字段值
        
        Returns:
            True 如果字段为空（空字典、或没有id且没有candidates）
        """
        if not isinstance(field_value, dict):
            return True
        
        # 空字典
        if not field_value:
            return True
        
        # 没有id且没有candidates
        if not field_value.get('id') and 'candidates' not in field_value:
            return True
        
        return False
    
    def complete_middle_level_with_upper_and_lower(
        self,
        middle_region_type: int,
        upper_parent_id: int,
        lower_parent_id: int,
        result: Dict[str, Any],
        field_name: str
    ) -> bool:
        """
        上下级补全函数：通过上级和下级ID筛选补全本级
        
        逻辑：
        1. 保存本级原始值（用于恢复）
        2. 通过上级ID从缓存筛选本级候选表
        3. 完全替换本级原始值为候选表格式
        4. 用下级的parent_id筛选本级候选表
        5. 如果筛选后唯一确定，设置为唯一值格式，返回 True
        6. 如果失败，恢复原始值，返回 False
        
        Args:
            middle_region_type: 本级区域类型
            upper_parent_id: 上级的唯一id
            lower_parent_id: 下级的parent_id（用于筛选）
            result: 结果字典（会被修改）
            field_name: 本级字段名
        
        Returns:
            True 如果补全成功，False 如果失败
        """
        # 保存原始值
        original_value = copy.deepcopy(result.get(field_name, {}))
        logger.debug(f"上下级补全开始: {field_name}, 上级id={upper_parent_id}, 下级parent_id={lower_parent_id}")
        
        try:
            # 从缓存获取指定region_type的所有记录
            all_regions = self.matcher.get_regions_by_type(middle_region_type)
            
            if not all_regions:
                logger.debug(f"上下级补全失败: {field_name}在region_type={middle_region_type}中没有记录")
                return False
            
            # 通过上级ID筛选本级候选表
            filtered_by_upper = [
                r for r in all_regions
                if r.get('parent_id') == upper_parent_id
            ]
            
            if not filtered_by_upper:
                logger.debug(f"上下级补全失败: {field_name}在region_type={middle_region_type}中未找到parent_id={upper_parent_id}的记录")
                return False
            
            # 完全替换本级原始值为候选表格式
            self._set_candidate_format(result, field_name, filtered_by_upper)
            logger.debug(f"上下级补全: {field_name}已替换为候选表格式，包含{len(filtered_by_upper)}个候选值")
            
            # 用下级的parent_id筛选本级候选表
            filtered_by_lower = [
                r for r in filtered_by_upper
                if r.get('id') == lower_parent_id
            ]
            
            if len(filtered_by_lower) == 1:
                # 筛选成功，设置为唯一值
                unique_record = filtered_by_lower[0]
                self._set_unique_value(result, field_name, unique_record)
                logger.debug(f"上下级补全成功: {field_name}找到唯一值 (id={unique_record.get('id')}, region_name={unique_record.get('region_name')})")
                return True
            else:
                # 筛选失败，恢复原始值
                result[field_name] = original_value
                logger.debug(f"上下级补全失败: {field_name}通过下级parent_id筛选后未找到唯一值，已恢复原始值")
                return False
                
        except Exception as e:
            # 发生异常，恢复原始值
            result[field_name] = original_value
            logger.error(f"上下级补全异常: {field_name}发生错误: {str(e)}，已恢复原始值")
            return False
    
    def complete_middle_level_from_candidates(
        self,
        middle_region_type: int,
        upper_parent_id: int,
        result: Dict[str, Any],
        field_name: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
        """
        中间层级补全方法：使用上级的唯一id从缓存中过滤本级数据
        
        支持所有层级：CityName、ExpAreaName、StreetName
        
        逻辑：
        1. 检查本级信息是否为空
        2. 从缓存获取指定region_type的所有记录（通过region_type初筛）
        3. 使用upper_parent_id过滤出parent_id匹配的记录
        4. 如果唯一，返回唯一值；如果多个，返回候选列表；如果为空，返回None
        
        Args:
            middle_region_type: 本级区域类型（可能是CityName、ExpAreaName或StreetName的region_type）
            upper_parent_id: 上级的唯一id（可能是ProvinceName、CityName或ExpAreaName的id）
            result: 结果字典（用于检查本级是否为空）
            field_name: 本级字段名（'CityName'、'ExpAreaName'或'StreetName'）
        
        Returns:
            (唯一值记录, None): 如果找到唯一值
            (None, 候选列表): 如果找到多个候选值
            (None, None): 如果没有找到或本级不为空
        """
        # ========== 新流程：上下级关联验证和补全 ==========
        # 条件检查：上级ID有效、本级不为空、下级唯一确定
        current_field_value = result.get(field_name, {})
        
        # 检查上级ID是否有效
        if upper_parent_id and upper_parent_id != 0:
            # 检查本级是否不为空
            if not self._is_field_empty(current_field_value):
                # 获取下级字段名
                lower_field_name = self.field_to_lower_field.get(field_name)
                if lower_field_name:
                    lower_field_value = result.get(lower_field_name, {})
                    
                    # 检查下级是否为唯一值
                    if self.is_unique_value(lower_field_value):
                        lower_parent_id = lower_field_value.get('parent_id')
                        if lower_parent_id:
                            logger.debug(f"上下级关联验证开始: {field_name}, 上级id={upper_parent_id}, 下级parent_id={lower_parent_id}")
                            
                            # 判断下级的parent_id是否在本级结果中匹配
                            matched_record = None
                            
                            if self.is_unique_value(current_field_value):
                                # 本级是唯一值：检查 下级的parent_id == 本级的id
                                current_id = current_field_value.get('id')
                                if lower_parent_id == current_id:
                                    matched_record = {
                                        'id': current_field_value.get('id'),
                                        'parent_id': current_field_value.get('parent_id'),
                                        'region_name': current_field_value.get('region_name'),
                                        'region_type': current_field_value.get('region_type')
                                    }
                                    logger.debug(f"上下级关联验证: {field_name}为唯一值，下级的parent_id({lower_parent_id})匹配本级的id({current_id})")
                                else:
                                    logger.debug(f"上下级关联验证: {field_name}为唯一值，下级的parent_id({lower_parent_id})不匹配本级的id({current_id})")
                            
                            elif self.is_candidate_format(current_field_value):
                                # 本级是候选表：检查 下级的parent_id in [候选列表中所有项的id集合]
                                candidates = current_field_value.get('candidates', [])
                                candidate_ids = {c.get('id') for c in candidates if c.get('id') is not None}
                                
                                if lower_parent_id in candidate_ids:
                                    # 找到匹配的候选记录
                                    matched_record = next(
                                        (c for c in candidates if c.get('id') == lower_parent_id),
                                        None
                                    )
                                    if matched_record:
                                        # 补充region_type信息
                                        matched_record['region_type'] = current_field_value.get('region_type')
                                    logger.debug(f"上下级关联验证: {field_name}为候选表，下级的parent_id({lower_parent_id})在候选列表中找到匹配记录")
                                else:
                                    logger.debug(f"上下级关联验证: {field_name}为候选表，下级的parent_id({lower_parent_id})不在候选列表中")
                            
                            # 处理三种情况
                            if matched_record is None:
                                # 情况1：无匹配 → 调用上下级补全函数
                                logger.debug(f"上下级关联验证: {field_name}无匹配结果，启动上下级补全函数")
                                success = self.complete_middle_level_with_upper_and_lower(
                                    middle_region_type, upper_parent_id, lower_parent_id, result, field_name
                                )
                                if success:
                                    logger.debug(f"上下级关联验证: {field_name}通过上下级补全函数成功补全")
                                else:
                                    logger.debug(f"上下级关联验证: {field_name}上下级补全函数执行失败")
                            else:
                                # 有匹配结果，检查上级id是否与本级此条对应结果的parent_id匹配
                                matched_record_parent_id = matched_record.get('parent_id')
                                if matched_record_parent_id == upper_parent_id:
                                    # 情况3：上级、本级、下级均关联 → 选择此条记录为本级的唯一值
                                    logger.debug(f"上下级关联验证成功: {field_name}上级、本级、下级均关联，设置为唯一值 (id={matched_record.get('id')}, region_name={matched_record.get('region_name')})")
                                    self._set_unique_value(result, field_name, matched_record)
                                else:
                                    # 情况2：有匹配但上级不匹配 → 启动上下级补全函数
                                    logger.debug(f"上下级关联验证: {field_name}有匹配记录但上级不匹配 (匹配记录的parent_id={matched_record_parent_id}, 上级id={upper_parent_id})，启动上下级补全函数")
                                    success = self.complete_middle_level_with_upper_and_lower(
                                        middle_region_type, upper_parent_id, lower_parent_id, result, field_name
                                    )
                                    if success:
                                        logger.debug(f"上下级关联验证: {field_name}通过上下级补全函数成功补全")
                                    else:
                                        logger.debug(f"上下级关联验证: {field_name}上下级补全函数执行失败")
                        else:
                            logger.debug(f"上下级关联验证跳过: {field_name}的下级{lower_field_name}没有parent_id")
                    else:
                        logger.debug(f"上下级关联验证跳过: {field_name}的下级{lower_field_name}不是唯一值")
                else:
                    logger.debug(f"上下级关联验证跳过: {field_name}没有下级字段")
        
        # ========== 原有流程：中间层级补全 ==========
        # 检查触发条件：本级信息必须为空
        current_field_value = result.get(field_name, {})
        if not self._is_field_empty(current_field_value):
            logger.debug(f"中间层级补全跳过: {field_name}不为空，无需补全")
            return None, None
        
        # 检查upper_parent_id是否有效
        if not upper_parent_id or upper_parent_id == 0:
            logger.debug(f"中间层级补全跳过: {field_name}的上级id无效")
            return None, None
        
        try:
            # 从缓存获取指定region_type的所有记录（通过region_type初筛，不会查询所有数据）
            all_regions = self.matcher.get_regions_by_type(middle_region_type)
            
            if not all_regions:
                logger.debug(f"中间层级补全失败: region_type={middle_region_type}没有记录")
                return None, None
            
            # 使用upper_parent_id过滤出parent_id匹配的记录
            filtered_regions = [
                r for r in all_regions
                if r.get('parent_id') == upper_parent_id
            ]
            
            if not filtered_regions:
                logger.debug(f"中间层级补全失败: {field_name}在region_type={middle_region_type}中未找到parent_id={upper_parent_id}的记录")
                return None, None
            
            if len(filtered_regions) == 1:
                # 找到唯一值
                unique_record = filtered_regions[0]
                logger.debug(f"中间层级补全成功: {field_name}找到唯一值 (id={unique_record.get('id')}, region_name={unique_record.get('region_name')})")
                return unique_record, None
            else:
                # 找到多个候选值，尝试通过下级唯一值进行筛选
                logger.debug(f"中间层级补全: {field_name}找到{len(filtered_regions)}个候选值，尝试通过下级唯一值进行筛选")
                
                # 查找下级字段
                lower_field_name = self.field_to_lower_field.get(field_name)
                if lower_field_name:
                    lower_field_value = result.get(lower_field_name, {})
                    
                    # 检查下级是否为唯一值
                    if self.is_unique_value(lower_field_value):
                        lower_parent_id = lower_field_value.get('parent_id')
                        if lower_parent_id:
                            # 根据下级值的parent_id筛选本级候选表
                            filtered_by_lower = [
                                r for r in filtered_regions
                                if r.get('id') == lower_parent_id
                            ]
                            
                            if len(filtered_by_lower) == 1:
                                # 筛选成功，得到唯一值
                                unique_record = filtered_by_lower[0]
                                logger.debug(f"中间层级补全成功: {field_name}通过下级{lower_field_name}筛选后找到唯一值 (id={unique_record.get('id')}, region_name={unique_record.get('region_name')})")
                                return unique_record, None
                            elif len(filtered_by_lower) > 1:
                                # 筛选后仍有多个（理论上不应该发生，但保留处理）
                                logger.warning(f"中间层级补全: {field_name}通过下级{lower_field_name}筛选后仍有{len(filtered_by_lower)}个候选值")
                                return None, filtered_by_lower
                            else:
                                # 筛选失败，保留当前候选表
                                logger.debug(f"中间层级补全: {field_name}通过下级{lower_field_name}筛选失败，保留当前{len(filtered_regions)}个候选值")
                                return None, filtered_regions
                        else:
                            logger.debug(f"中间层级补全: {field_name}的下级{lower_field_name}没有parent_id，无法筛选")
                    else:
                        logger.debug(f"中间层级补全: {field_name}的下级{lower_field_name}不是唯一值，无法筛选")
                else:
                    logger.debug(f"中间层级补全: {field_name}没有下级字段，无法通过下级筛选")
                
                # 返回多个候选值
                return None, filtered_regions
                
        except Exception as e:
            logger.error(f"中间层级补全查询失败: {str(e)}")
            return None, None
    
    def resolve_province_name(
        self,
        candidates: List[Dict[str, Any]],
        result: Dict[str, Any],
        warnings: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        处理ProvinceName候选表
        
        Args:
            candidates: ProvinceName候选列表
            result: 结果字典
            warnings: 警告信息列表
        
        Returns:
            如果唯一确定，返回ProvinceName记录；否则返回None
        """
        # 如果result中已经有唯一值，直接返回，不覆盖
        # 注意：ProvinceName是最高级别，没有上级，所以不需要验证parent_id
        existing_value = result.get('ProvinceName', {})
        if self.is_unique_value(existing_value):
            logger.debug(f"ProvinceName已有唯一值，跳过处理: {existing_value.get('region_name')} (id={existing_value.get('id')})")
            return existing_value
        
        if not candidates:
            result['ProvinceName'] = {}
            return None
        
        if len(candidates) == 1:
            # 唯一值，直接设置
            province = candidates[0]
            self._set_unique_value(result, 'ProvinceName', province)
            logger.debug(f"ProvinceName唯一确定: {province.get('region_name')} (id={province.get('id')})")
            return province
        else:
            # 多个候选，设置为候选对象格式
            # 格式：{"candidates": [{"id": ..., "parent_id": ..., "region_name": ...}, ...], "region_type": ...}
            self._set_candidate_format(result, 'ProvinceName', candidates)
            logger.debug(f"ProvinceName存在{len(candidates)}个候选值，无法确定")
            return None
    
    def resolve_city_name(
        self,
        candidates: List[Dict[str, Any]],
        province_record: Optional[Dict[str, Any]],
        result: Dict[str, Any],
        warnings: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        处理CityName候选表
        
        Args:
            candidates: CityName候选列表
            province_record: ProvinceName的唯一记录（如果已确定）
            result: 结果字典
            warnings: 警告信息列表
        
        Returns:
            如果唯一确定，返回CityName记录；否则返回None
        """
        # 如果result中已经有唯一值，需要验证是否与上级匹配
        existing_value = result.get('CityName', {})
        if self.is_unique_value(existing_value):
            # 如果上级已确定，验证parent_id是否匹配
            if province_record:
                existing_parent_id = existing_value.get('parent_id')
                province_id = province_record.get('id')
                if existing_parent_id is not None and province_id is not None and existing_parent_id != province_id:
                    # 不匹配，清除这个唯一值，继续处理
                    logger.warning(f"CityName的唯一值(id={existing_value.get('id')}, parent_id={existing_parent_id})与ProvinceName(id={province_id})不匹配，清除唯一值")
                    result['CityName'] = {}
                else:
                    # 匹配或无法验证，直接返回
                    logger.debug(f"CityName已有唯一值，跳过处理: {existing_value.get('region_name')} (id={existing_value.get('id')})")
                    return existing_value
            else:
                # 上级未确定，直接返回
                logger.debug(f"CityName已有唯一值，跳过处理: {existing_value.get('region_name')} (id={existing_value.get('id')})")
                return existing_value
        
        if not candidates:
            result['CityName'] = {}
            # 如果ProvinceName已确定但CityName为空，尝试补全CityName
            if province_record:
                province_id = province_record.get('id')
                city_unique, city_candidates = self.complete_middle_level_from_candidates(
                    self.region_type_map.get('CityName'), province_id, result, 'CityName'
                )
                if city_unique:
                    self._set_unique_value(result, 'CityName', city_unique)
                    logger.debug(f"通过中间层级补全CityName: {city_unique.get('region_name')}")
                    return city_unique
                elif city_candidates:
                    self._set_candidate_format(result, 'CityName', city_candidates)
                    logger.debug(f"通过中间层级补全CityName: 找到{len(city_candidates)}个候选值")
                    return None
            return None
        
        # 如果上一步存在唯一值，根据其id筛选本候选表中的parent_id
        if province_record:
            province_id = province_record.get('id')
            city_match, filtered_candidates = self.filter_by_parent_id(
                candidates, province_id, self.region_type_map.get('CityName')
            )
            
            if city_match:
                # 筛选后唯一，直接设置
                self._set_unique_value(result, 'CityName', city_match)
                logger.debug(f"CityName通过上级筛选后唯一确定: {city_match.get('region_name')} (id={city_match.get('id')})")
                return city_match
            elif filtered_candidates:
                # 筛选后仍有多个结果
                self._set_candidate_format(result, 'CityName', filtered_candidates)
                # warnings.append("CityName与上级信息不匹配")
                logger.debug(f"CityName通过上级筛选后仍有{len(filtered_candidates)}个候选值")
                return None
            else:
                # 筛选失败，返回原有候选表
                self._set_candidate_format(result, 'CityName', candidates)
                # warnings.append("CityName与上级信息不匹配")
                logger.debug(f"CityName通过上级筛选失败，返回原有候选表")
                return None
        else:
            # 上一步不存在唯一值，处理流程参照上一步
            if len(candidates) == 1:
                city = candidates[0]
                self._set_unique_value(result, 'CityName', city)
                logger.debug(f"CityName唯一确定: {city.get('region_name')} (id={city.get('id')})")
                return city
            else:
                self._set_candidate_format(result, 'CityName', candidates)
                logger.debug(f"CityName存在多个候选值，无法确定")
                return None
    
    def resolve_exp_area_name(
        self,
        candidates: List[Dict[str, Any]],
        province_record: Optional[Dict[str, Any]],
        city_record: Optional[Dict[str, Any]],
        result: Dict[str, Any],
        warnings: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        处理ExpAreaName候选表
        
        Args:
            candidates: ExpAreaName候选列表
            province_record: ProvinceName的唯一记录（如果已确定）
            city_record: CityName的唯一记录（如果已确定）
            result: 结果字典
            warnings: 警告信息列表
        
        Returns:
            如果唯一确定，返回ExpAreaName记录；否则返回None
        """
        # 如果result中已经有唯一值，需要验证是否与上级匹配
        existing_value = result.get('ExpAreaName', {})
        if self.is_unique_value(existing_value):
            # 如果上级已确定，验证parent_id是否匹配
            if city_record:
                existing_parent_id = existing_value.get('parent_id')
                city_id = city_record.get('id')
                if existing_parent_id is not None and city_id is not None and existing_parent_id != city_id:
                    # 不匹配，清除这个唯一值，继续处理
                    logger.warning(f"ExpAreaName的唯一值(id={existing_value.get('id')}, parent_id={existing_parent_id})与CityName(id={city_id})不匹配，清除唯一值")
                    result['ExpAreaName'] = {}
                else:
                    # 匹配或无法验证，直接返回
                    logger.debug(f"ExpAreaName已有唯一值，跳过处理: {existing_value.get('region_name')} (id={existing_value.get('id')})")
                    return existing_value
            else:
                # 上级未确定，直接返回
                logger.debug(f"ExpAreaName已有唯一值，跳过处理: {existing_value.get('region_name')} (id={existing_value.get('id')})")
                return existing_value
        
        # 验证：如果CityName已确定，检查result中已存在的ExpAreaName（包括唯一值和候选表格式）是否匹配
        if city_record:
            existing_exp_area = result.get('ExpAreaName', {})
            city_id = city_record.get('id')
            
            # 检查唯一值
            if self.is_unique_value(existing_exp_area):
                existing_parent_id = existing_exp_area.get('parent_id')
                if existing_parent_id is not None and city_id is not None and existing_parent_id != city_id:
                    # 不匹配，清除这个唯一值
                    logger.warning(f"ExpAreaName的唯一值(id={existing_exp_area.get('id')}, parent_id={existing_parent_id})与CityName(id={city_id})不匹配，清除唯一值")
                    result['ExpAreaName'] = {}
            
        
        if not candidates:
            result['ExpAreaName'] = {}
            return None
        
        # 如果上一步存在唯一值，根据其id筛选本候选表中的parent_id
        if city_record:
            city_id = city_record.get('id')
            exp_area_match, filtered_candidates = self.filter_by_parent_id(
                candidates, city_id, self.region_type_map.get('ExpAreaName')
            )
            
            if exp_area_match:
                self._set_unique_value(result, 'ExpAreaName', exp_area_match)
                logger.debug(f"ExpAreaName通过上级筛选后唯一确定: {exp_area_match.get('region_name')} (id={exp_area_match.get('id')})")
                return exp_area_match
            elif filtered_candidates:
                self._set_candidate_format(result, 'ExpAreaName', filtered_candidates)
                # warnings.append("ExpAreaName与上级信息不匹配")
                logger.debug(f"ExpAreaName通过上级筛选后仍有多个候选值")
                return None
            else:
                # 筛选失败，返回原有候选表
                self._set_candidate_format(result, 'ExpAreaName', candidates)
                # warnings.append("ExpAreaName与上级信息不匹配")
                logger.debug(f"ExpAreaName通过上级筛选失败，返回原有候选表")
                return None
        else:
            # 特殊情况：当ProvinceName唯一确定，而CityName为空时，尝试补全CityName
            if province_record:
                province_id = province_record.get('id')
                city_unique, city_candidates = self.complete_middle_level_from_candidates(
                    self.region_type_map.get('CityName'), province_id, result, 'CityName'
                )
                if city_unique:
                    self._set_unique_value(result, 'CityName', city_unique)
                    logger.debug(f"通过中间层级补全CityName: {city_unique.get('region_name')}")
                    # 更新city_record以便后续使用
                    city_record = city_unique
                    
                    # 用补全的CityName筛选ExpAreaName
                    city_id = city_record.get('id')
                    exp_area_match, filtered_candidates = self.filter_by_parent_id(
                        candidates, city_id, self.region_type_map.get('ExpAreaName')
                    )
                    
                    if exp_area_match:
                        self._set_unique_value(result, 'ExpAreaName', exp_area_match)
                        logger.debug(f"ExpAreaName通过补全的CityName筛选后唯一确定")
                        return exp_area_match
                    elif filtered_candidates:
                        self._set_candidate_format(result, 'ExpAreaName', filtered_candidates)
                        logger.debug(f"ExpAreaName通过补全的CityName筛选后仍有多个候选值")
                        return None
                elif city_candidates:
                    # 补全到候选表格式
                    self._set_candidate_format(result, 'CityName', city_candidates)
                    logger.debug(f"通过中间层级补全CityName: 找到{len(city_candidates)}个候选值")
                    # 即使CityName是候选表，也可以尝试用第一个候选的id筛选ExpAreaName
                    if city_candidates:
                        city_id = city_candidates[0].get('id')
                        exp_area_match, filtered_candidates = self.filter_by_parent_id(
                            candidates, city_id, self.region_type_map.get('ExpAreaName')
                        )
                        if exp_area_match:
                            self._set_unique_value(result, 'ExpAreaName', exp_area_match)
                            logger.debug(f"ExpAreaName通过补全的CityName候选筛选后唯一确定")
                            return exp_area_match
                        elif filtered_candidates:
                            self._set_candidate_format(result, 'ExpAreaName', filtered_candidates)
                            logger.debug(f"ExpAreaName通过补全的CityName候选筛选后仍有多个候选值")
                            return None
            
            # 如果CityName已确定但ExpAreaName为空，尝试补全ExpAreaName
            if city_record:
                city_id = city_record.get('id')
                exp_area_unique, exp_area_candidates = self.complete_middle_level_from_candidates(
                    self.region_type_map.get('ExpAreaName'), city_id, result, 'ExpAreaName'
                )
                if exp_area_unique:
                    self._set_unique_value(result, 'ExpAreaName', exp_area_unique)
                    logger.debug(f"通过中间层级补全ExpAreaName: {exp_area_unique.get('region_name')}")
                    return exp_area_unique
                elif exp_area_candidates:
                    self._set_candidate_format(result, 'ExpAreaName', exp_area_candidates)
                    logger.debug(f"通过中间层级补全ExpAreaName: 找到{len(exp_area_candidates)}个候选值")
                    return None
            
            # 上一步不存在唯一值，处理流程参照上一步
            if len(candidates) == 1:
                exp_area = candidates[0]
                self._set_unique_value(result, 'ExpAreaName', exp_area)
                logger.debug(f"ExpAreaName唯一确定: {exp_area.get('region_name')} (id={exp_area.get('id')})")
                return exp_area
            else:
                self._set_candidate_format(result, 'ExpAreaName', candidates)
                logger.debug(f"ExpAreaName存在{len(candidates)}个候选值，无法确定")
                return None
    
    def resolve_street_name(
        self,
        candidates: List[Dict[str, Any]],
        exp_area_record: Optional[Dict[str, Any]],
        city_record: Optional[Dict[str, Any]],
        province_record: Optional[Dict[str, Any]],
        result: Dict[str, Any],
        warnings: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        处理StreetName候选表
        
        Args:
            candidates: StreetName候选列表
            exp_area_record: ExpAreaName的唯一记录（如果已确定）
            city_record: CityName的唯一记录（如果已确定）
            province_record: ProvinceName的唯一记录（如果已确定）
            result: 结果字典
            warnings: 警告信息列表
        
        Returns:
            如果唯一确定，返回StreetName记录；否则返回None
        """
        # 如果result中已经有唯一值，需要验证是否与上级匹配
        existing_value = result.get('StreetName', {})
        if self.is_unique_value(existing_value):
            # 如果上级已确定，验证parent_id是否匹配
            if exp_area_record:
                existing_parent_id = existing_value.get('parent_id')
                exp_area_id = exp_area_record.get('id')
                if existing_parent_id is not None and exp_area_id is not None and existing_parent_id != exp_area_id:
                    # 不匹配，清除这个唯一值，继续处理
                    logger.warning(f"StreetName的唯一值(id={existing_value.get('id')}, parent_id={existing_parent_id})与ExpAreaName(id={exp_area_id})不匹配，清除唯一值")
                    result['StreetName'] = {}
                else:
                    # 匹配或无法验证，直接返回
                    logger.debug(f"StreetName已有唯一值，跳过处理: {existing_value.get('region_name')} (id={existing_value.get('id')})")
                    return existing_value
            else:
                # 上级未确定，直接返回
                logger.debug(f"StreetName已有唯一值，跳过处理: {existing_value.get('region_name')} (id={existing_value.get('id')})")
                return existing_value
        
        # 验证：如果ExpAreaName已确定，检查result中已存在的StreetName（包括唯一值和候选表格式）是否匹配
        if exp_area_record:
            existing_street = result.get('StreetName', {})
            exp_area_id = exp_area_record.get('id')
            
            # 检查唯一值
            if self.is_unique_value(existing_street):
                existing_parent_id = existing_street.get('parent_id')
                if existing_parent_id is not None and exp_area_id is not None and existing_parent_id != exp_area_id:
                    # 不匹配，清除这个唯一值
                    logger.warning(f"StreetName的唯一值(id={existing_street.get('id')}, parent_id={existing_parent_id})与ExpAreaName(id={exp_area_id})不匹配，清除唯一值")
                    result['StreetName'] = {}
            
        
        if not candidates:
            result['StreetName'] = {}
            return None
        
        # 如果上一步存在唯一值，根据其id筛选本候选表中的parent_id
        if exp_area_record:
            exp_area_id = exp_area_record.get('id')
            street_match, filtered_candidates = self.filter_by_parent_id(
                candidates, exp_area_id, self.region_type_map.get('StreetName')
            )
            
            if street_match:
                self._set_unique_value(result, 'StreetName', street_match)
                logger.debug(f"StreetName通过上级筛选后唯一确定: {street_match.get('region_name')} (id={street_match.get('id')})")
                return street_match
            elif filtered_candidates:
                self._set_candidate_format(result, 'StreetName', filtered_candidates)
                # warnings.append("StreetName与上级信息不匹配")
                logger.debug(f"StreetName通过上级筛选后仍有多个候选值")
                return None
            else:
                # 筛选失败，返回原有候选表
                self._set_candidate_format(result, 'StreetName', candidates)
                # warnings.append("StreetName与上级信息不匹配")
                logger.debug(f"StreetName通过上级筛选失败，返回原有候选表")
                return None
        else:
            # 特殊情况：当ExpAreaName未确定，但CityName或ProvinceName已确定时，尝试补全
            if city_record and not exp_area_record:
                city_id = city_record.get('id')
                exp_area_unique, exp_area_candidates = self.complete_middle_level_from_candidates(
                    self.region_type_map.get('ExpAreaName'), city_id, result, 'ExpAreaName'
                )
                if exp_area_unique:
                    self._set_unique_value(result, 'ExpAreaName', exp_area_unique)
                    logger.debug(f"通过中间层级补全ExpAreaName: {exp_area_unique.get('region_name')}")
                    # 更新exp_area_record以便后续使用
                    exp_area_record = exp_area_unique
                    
                    # 用补全的ExpAreaName筛选StreetName
                    exp_area_id = exp_area_record.get('id')
                    street_match, filtered_candidates = self.filter_by_parent_id(
                        candidates, exp_area_id, self.region_type_map.get('StreetName')
                    )
                    
                    if street_match:
                        self._set_unique_value(result, 'StreetName', street_match)
                        logger.debug(f"StreetName通过补全的ExpAreaName筛选后唯一确定")
                        return street_match
                    elif filtered_candidates:
                        self._set_candidate_format(result, 'StreetName', filtered_candidates)
                        logger.debug(f"StreetName通过补全的ExpAreaName筛选后仍有{len(filtered_candidates)}个候选值")
                        return None
                elif exp_area_candidates:
                    self._set_candidate_format(result, 'ExpAreaName', exp_area_candidates)
                    logger.debug(f"通过中间层级补全ExpAreaName: 找到{len(exp_area_candidates)}个候选值")
                    # 即使ExpAreaName是候选表，也可以尝试用第一个候选的id筛选StreetName
                    if exp_area_candidates:
                        exp_area_id = exp_area_candidates[0].get('id')
                        street_match, filtered_candidates = self.filter_by_parent_id(
                            candidates, exp_area_id, self.region_type_map.get('StreetName')
                        )
                        if street_match:
                            self._set_unique_value(result, 'StreetName', street_match)
                            logger.debug(f"StreetName通过补全的ExpAreaName候选筛选后唯一确定")
                            return street_match
                        elif filtered_candidates:
                            self._set_candidate_format(result, 'StreetName', filtered_candidates)
                            logger.debug(f"StreetName通过补全的ExpAreaName候选筛选后仍有{len(filtered_candidates)}个候选值")
                            return None
            
            # 如果ExpAreaName已确定但StreetName为空，尝试补全StreetName
            if exp_area_record:
                exp_area_id = exp_area_record.get('id')
                street_unique, street_candidates = self.complete_middle_level_from_candidates(
                    self.region_type_map.get('StreetName'), exp_area_id, result, 'StreetName'
                )
                if street_unique:
                    self._set_unique_value(result, 'StreetName', street_unique)
                    logger.debug(f"通过中间层级补全StreetName: {street_unique.get('region_name')}")
                    return street_unique
                elif street_candidates:
                    self._set_candidate_format(result, 'StreetName', street_candidates)
                    logger.debug(f"通过中间层级补全StreetName: 找到{len(street_candidates)}个候选值")
                    return None
            
            # 上一步不存在唯一值，处理流程参照上一步
            if len(candidates) == 1:
                street = candidates[0]
                self._set_unique_value(result, 'StreetName', street)
                logger.debug(f"StreetName唯一确定: {street.get('region_name')} (id={street.get('id')})")
                return street
            else:
                self._set_candidate_format(result, 'StreetName', candidates)
                logger.debug(f"StreetName存在多个候选值，无法确定")
                return None
    
    def execute_stage2_resolve(
        self,
        candidate_tables: Dict[str, List[Dict[str, Any]]],
        result: Dict[str, Any],
        warnings: List[str]
    ) -> None:
        """
        按优先级依次处理四个字段的候选表
        
        优先级：ProvinceName > CityName > ExpAreaName > StreetName
        
        Args:
            candidate_tables: 候选表字典
            result: 结果字典（会被修改）
            warnings: 警告信息列表（会被修改）
        """
        # 1. 处理ProvinceName
        province_candidates = candidate_tables.get('ProvinceName', [])
        province_record = self.resolve_province_name(province_candidates, result, warnings)
        
        # 2. 处理CityName
        city_candidates = candidate_tables.get('CityName', [])
        city_record = self.resolve_city_name(city_candidates, province_record, result, warnings)
        
        # 3. 处理ExpAreaName
        exp_area_candidates = candidate_tables.get('ExpAreaName', [])
        exp_area_record = self.resolve_exp_area_name(
            exp_area_candidates, province_record, city_record, result, warnings
        )
        
        # 4. 处理StreetName
        street_candidates = candidate_tables.get('StreetName', [])
        street_record = self.resolve_street_name(
            street_candidates, exp_area_record, city_record, province_record, result, warnings
        )
        
        logger.debug(f"第二阶段开始: ProvinceName={'已确定' if province_record else '未确定'}, "
                     f"CityName={'已确定' if city_record else '未确定'}, "
                     f"ExpAreaName={'已确定' if exp_area_record else '未确定'}, "
                     f"StreetName={'已确定' if street_record else '未确定'}")
        
        # 保存resolve阶段后的原始结果（用于级联匹配失败时恢复）
        original_result_after_resolve = copy.deepcopy(result)
        
        # ========== 方法1：向下过滤 ==========
        # 向下过滤逻辑已整合在resolve方法中执行
        # 检查是否有执行向下过滤的条件（上级已确定且下级是候选表）
        has_downward_filter = False
        if province_record and self.is_candidate_format(result.get('CityName', {})):
            has_downward_filter = True
        if city_record and self.is_candidate_format(result.get('ExpAreaName', {})):
            has_downward_filter = True
        if exp_area_record and self.is_candidate_format(result.get('StreetName', {})):
            has_downward_filter = True
        
        if has_downward_filter:
            logger.debug("方法1 向下过滤 已执行: 在resolve方法中根据上级id筛选下级候选表")
        else:
            logger.debug("方法1 向下过滤 未执行: 无符合条件的上级和下级候选表")
        
        # ========== 方法2：中间层级补全 ==========
        # 中间层级补全逻辑已整合在resolve方法中执行
        # 检查是否有执行中间层级补全的条件（上级已确定且本级为空）
        has_middle_level_complete = False
        if province_record and not result.get('CityName', {}):
            has_middle_level_complete = True
        if (province_record or city_record) and not result.get('ExpAreaName', {}):
            has_middle_level_complete = True
        if (province_record or city_record or exp_area_record) and not result.get('StreetName', {}):
            has_middle_level_complete = True
        
        if has_middle_level_complete:
            logger.debug("方法2 中间层级补全 已执行: 在resolve方法中使用上级id从缓存过滤本级数据")
        else:
            logger.debug("方法2 中间层级补全 未执行: 无符合条件的上级和本级")
        
        # ========== 方法3：候选值级联匹配 ==========
        # 定义状态变量：记录级联匹配失败的状态
        cascade_match_failed_states = {
            'CityName_ExpAreaName': False,  # CityName与ExpAreaName级联匹配失败
            'ExpAreaName_StreetName': False  # ExpAreaName与StreetName级联匹配失败
        }
        
        # 由下到上依次判断相邻字段
        field_pairs = [
            ('StreetName', 'ExpAreaName'),
            ('ExpAreaName', 'CityName'),
            ('CityName', 'ProvinceName')
        ]
        has_cascade_match = False
        for lower_field, upper_field in field_pairs:
            lower_value = result.get(lower_field, {})
            upper_value = result.get(upper_field, {})
            
            # 情况1：本级是候选表，上级可以是候选表或唯一值
            if self.is_candidate_format(lower_value) and (
                self.is_candidate_format(upper_value) or self.is_unique_value(upper_value)
            ):
                has_cascade_match = True
                logger.debug(f"开始级联匹配: {lower_field} -> {upper_field}")
                self.cascade_match_candidates(
                    lower_field, upper_field, result, warnings, original_result_after_resolve, cascade_match_failed_states
                )
            # 情况2：本级是唯一值，上级可以是候选表或唯一值
            elif self.is_unique_value(lower_value) and (
                self.is_candidate_format(upper_value) or self.is_unique_value(upper_value)
            ):
                has_cascade_match = True
                logger.debug(f"开始级联匹配（本级为唯一值）: {lower_field} -> {upper_field}")
                self.cascade_match_unique_to_upper(
                    lower_field, upper_field, result, warnings, cascade_match_failed_states
                )
        
        if has_cascade_match:
            logger.debug("方法3 候选值级联匹配 已执行")
        else:
            logger.debug("方法3 候选值级联匹配 未执行: 无符合条件的候选表对")
        
        # ========== 方法4：特殊情况中间层级确定 ==========
        has_special_resolve = self.resolve_middle_levels_by_tracing(
            result, warnings, 
            cascade_match_failed_city_exparea=cascade_match_failed_states.get('CityName_ExpAreaName', False),
            cascade_match_failed_exparea_street=cascade_match_failed_states.get('ExpAreaName_StreetName', False)
        )
        if has_special_resolve:
            logger.debug("方法4 特殊情况中间层级确定 已执行: 通过追溯StreetName候选的上级信息链确定中间层级")
        else:
            logger.debug("方法4 特殊情况中间层级确定 未执行: 不满足触发条件或未找到匹配的信息链")
        
        # ========== 方法5：向上追溯 ==========
        # 步骤0：转换单候选格式为唯一值格式（在向上追溯之前执行）
        logger.debug("方法5 步骤0 转换单候选格式为唯一值格式 开始")
        self.convert_single_candidate_to_unique(result)
        logger.debug("方法5 步骤0 转换单候选格式为唯一值格式 已完成")
        
        # 步骤1：从下到上依次检查唯一确定的字段，递归追溯所有上级
        # 优先从最底层（StreetName）开始追溯，确保从最底层向上补全
        field_order = ['StreetName', 'ExpAreaName', 'CityName', 'ProvinceName']
        has_upward_trace = False
        for field_name in field_order:
            unique_record = self.get_unique_record(result, field_name)
            if unique_record:
                has_upward_trace = True
                self.trace_upward_recursively(unique_record, result, warnings, candidate_tables)
        
        if has_upward_trace:
            logger.debug("方法5 向上追溯 已执行: 通过唯一确定字段的parent_id向上追溯所有上级")
        else:
            logger.debug("方法5 向上追溯 未执行: 无唯一确定的字段可追溯")
        
        # ========== 方法6：去除重复 ==========
        logger.debug("方法6 去除重复 开始执行: 检查并清除上下级重复的region_name")
        self.remove_duplicate_region_names(result, warnings)
        logger.debug("方法6 去除重复 已完成")
        
        # 检查最终状态
        province_record = self.get_unique_record(result, 'ProvinceName')
        city_record = self.get_unique_record(result, 'CityName')
        exp_area_record = self.get_unique_record(result, 'ExpAreaName')
        street_record = self.get_unique_record(result, 'StreetName')
        
        logger.info(f"第二阶段处理完成: ProvinceName={'已确定' if province_record else '未确定'}, "
                   f"CityName={'已确定' if city_record else '未确定'}, "
                   f"ExpAreaName={'已确定' if exp_area_record else '未确定'}, "
                   f"StreetName={'已确定' if street_record else '未确定'}")
    
    def is_unique_value(self, field_value: Any) -> bool:
        """
        检查字段是否为唯一确定的值
        
        Args:
            field_value: 字段值（可能是字典、列表或其他类型）
        
        Returns:
            True 如果字段有 id 且不是候选表格式
        """
        if not isinstance(field_value, dict):
            return False
        
        # 如果有 id 且没有 'candidates' 键，则是唯一值
        if 'id' in field_value and field_value.get('id') is not None:
            if 'candidates' not in field_value:
                return True
        
        return False
    
    def is_candidate_format(self, field_value: Any) -> bool:
        """
        检查字段是否为候选表格式
        
        Args:
            field_value: 字段值（可能是字典、列表或其他类型）
        
        Returns:
            True 如果字段是候选表格式（包含 'candidates' 键的字典）
        """
        if not isinstance(field_value, dict):
            return False
        
        # 如果有 'candidates' 键，则是候选表格式
        if 'candidates' in field_value:
            candidates = field_value.get('candidates', [])
            if isinstance(candidates, list) and len(candidates) > 0:
                return True
        
        return False
    
    def _validate_parent_id_match(
        self,
        field_name: str,
        candidate_record: Dict[str, Any],
        result: Dict[str, Any]
    ) -> bool:
        """
        验证候选记录的parent_id是否与已确定的上级匹配
        
        Args:
            field_name: 字段名（'ExpAreaName'或'StreetName'）
            candidate_record: 候选记录（包含id, parent_id等）
            result: 结果字典
        
        Returns:
            True 如果匹配或无法验证（上级未确定），False 如果不匹配
        """
        candidate_parent_id = candidate_record.get('parent_id')
        if candidate_parent_id is None:
            # 候选记录没有parent_id，无法验证，返回True
            return True
        
        # 获取上级字段名
        upper_field_name = self.field_to_upper_field.get(field_name)
        if not upper_field_name:
            # 没有上级字段（如ProvinceName），无法验证，返回True
            return True
        
        # 获取上级字段值
        upper_field_value = result.get(upper_field_name, {})
        
        # 检查上级是否为唯一值
        if not self.is_unique_value(upper_field_value):
            # 上级还未确定，无法验证，返回True
            return True
        
        # 上级已确定，检查parent_id是否匹配
        upper_id = upper_field_value.get('id')
        if upper_id is None:
            # 上级没有id，无法验证，返回True
            return True
        
        # 验证parent_id是否匹配
        if candidate_parent_id == upper_id:
            logger.debug(f"{field_name}验证通过: 候选记录的parent_id({candidate_parent_id})与{upper_field_name}的id({upper_id})匹配")
            return True
        else:
            logger.debug(f"{field_name}验证失败: 候选记录的parent_id({candidate_parent_id})与{upper_field_name}的id({upper_id})不匹配")
            return False
    
    def convert_candidate_tables_to_result_format(
        self,
        candidate_tables: Dict[str, List[Dict[str, Any]]],
        result: Dict[str, Any]
    ) -> None:
        """
        将candidate_tables转换为result格式
        
        将第一阶段返回的候选列表转换为result字典中的候选表格式
        注意：单候选值也会先转换为候选表格式，后续由convert_single_candidate_to_unique处理
        
        Args:
            candidate_tables: 候选表字典，键为字段名，值为候选列表
            result: 结果字典（会被修改）
        """
        field_names = ['ProvinceName', 'CityName', 'ExpAreaName', 'StreetName']
        
        for field_name in field_names:
            candidates = candidate_tables.get(field_name, [])
            
            if not candidates:
                # 没有候选，设置为空字典
                result[field_name] = {}
            else:
                # 无论单候选还是多候选，都先设置为候选表格式
                # 单候选值会由convert_single_candidate_to_unique方法处理
                self._set_candidate_format(result, field_name, candidates)
    
    def convert_single_candidate_to_unique(self, result: Dict[str, Any]) -> None:
        """
        将仅有一个候选的候选格式转换为唯一值格式
        
        检查所有字段（ProvinceName, CityName, ExpAreaName, StreetName），
        如果字段是候选格式且只有一个候选值，转换为唯一值格式
        
        Args:
            result: 结果字典（会被修改）
        """
        field_names = ['ProvinceName', 'CityName', 'ExpAreaName', 'StreetName']
        
        for field_name in field_names:
            field_value = result.get(field_name, {})
            
            # 检查是否为候选格式
            if self.is_candidate_format(field_value):
                candidates = field_value.get('candidates', [])
                
                # 如果只有一个候选值，转换为唯一值格式
                if isinstance(candidates, list) and len(candidates) == 1:
                    candidate = candidates[0]
                    
                    # 从候选元素中获取region_name，从顶层获取region_type
                    region_name = candidate.get('region_name', '')
                    region_type = field_value.get('region_type')
                    
                    # 转换为唯一值格式
                    self._set_unique_value(result, field_name, {
                        'id': candidate.get('id'),
                        'parent_id': candidate.get('parent_id'),
                        'region_name': region_name,
                        'region_type': region_type
                    })
    
    def get_unique_record(self, result: Dict[str, Any], field_name: str) -> Optional[Dict[str, Any]]:
        """
        从 result 中提取唯一值记录
        
        Args:
            result: 结果字典
            field_name: 字段名
        
        Returns:
            区域记录字典或 None
        """
        field_value = result.get(field_name, {})
        
        if self.is_unique_value(field_value):
            # 返回唯一值记录
            return {
                'id': field_value.get('id'),
                'parent_id': field_value.get('parent_id'),
                'region_name': field_value.get('region_name'),
                'region_type': field_value.get('region_type')
            }
        
        return None
    
    def merge_candidate(
        self,
        existing_candidates: List[Dict[str, Any]],
        new_record: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        将追溯到的值去重后追加到候选表中（基于 id 去重）
        
        Args:
            existing_candidates: 现有候选列表
            new_record: 要添加的新记录
        
        Returns:
            合并后的候选列表
        """
        if not existing_candidates:
            existing_candidates = []
        
        new_id = new_record.get('id')
        if new_id is None:
            return existing_candidates
        
        # 检查是否已存在（基于 id）
        existing_ids = {c.get('id') for c in existing_candidates if c.get('id') is not None}
        
        if new_id not in existing_ids:
            # 追加新记录
            existing_candidates.append({
                'id': new_record.get('id'),
                'parent_id': new_record.get('parent_id'),
                'region_name': new_record.get('region_name', '')
            })
        
        # 截断候选表
        return self.truncate_candidates(existing_candidates, '')
    
    def convert_unique_to_candidates(
        self,
        existing_unique: Dict[str, Any],
        traced_record: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        将唯一值格式转换为候选表格式
        
        Args:
            existing_unique: 现有的唯一值（字典格式）
            traced_record: 追溯到的记录
        
        Returns:
            候选表格式的字典
        """
        candidates = []
        
        # 添加原唯一值
        if existing_unique.get('id') is not None:
            candidates.append({
                'id': existing_unique.get('id'),
                'parent_id': existing_unique.get('parent_id'),
                'region_name': existing_unique.get('region_name', '')
            })
        
        # 添加追溯到的值（去重）
        if traced_record.get('id') is not None:
            traced_id = traced_record.get('id')
            existing_ids = {c.get('id') for c in candidates if c.get('id') is not None}
            if traced_id not in existing_ids:
                candidates.append({
                    'id': traced_record.get('id'),
                    'parent_id': traced_record.get('parent_id'),
                    'region_name': traced_record.get('region_name', '')
                })
        
        # 截断候选表
        candidates = self.truncate_candidates(candidates, '')
        
        # 返回候选表格式
        return {
            'candidates': candidates,
            'region_type': existing_unique.get('region_type')
        }
    
    def trace_upward_from_unique_value(
        self,
        unique_record: Dict[str, Any],
        upper_field_name: str,
        upper_region_type: int,
        result: Dict[str, Any],
        warnings: List[str],
        candidate_tables: Dict[str, List[Dict[str, Any]]]
    ) -> bool:
        """
        通过本级的唯一值的parent_id去追溯上级的id
        
        Args:
            unique_record: 唯一确定的区域记录（包含 id, parent_id, region_name, region_type）
            upper_field_name: 上级字段名（如 'CityName', 'ExpAreaName', 'ProvinceName'）
            upper_region_type: 上级区域类型
            result: 结果字典（会被修改）
            warnings: 警告信息列表（会被修改）
            candidate_tables: 候选表字典（用于筛选）
        
        Returns:
            True 如果追溯成功且得到唯一值，False 否则
        """
        parent_id = unique_record.get('parent_id')
        if not parent_id or parent_id == 0:
            # 没有上级，跳过
            return False
        
        # 通过 parent_id 查找上级区域
        upper_record = self.matcher.find_region_by_id(parent_id)
        
        if not upper_record:
            # 找不到上级，记录 warning
            warnings.append(f"{upper_field_name}在数据库中无上级信息")
            logger.warning(f"向上追溯失败: {upper_field_name}在数据库中无上级信息 (parent_id={parent_id})")
            return False
        
        # 检查上级记录的 region_type 是否匹配
        if upper_record.get('region_type') != upper_region_type:
            logger.warning(f"向上追溯失败: {upper_field_name}的region_type不匹配 (期望={upper_region_type}, 实际={upper_record.get('region_type')})")
            return False
        
        # 检查 result 中该字段的状态
        current_field_value = result.get(upper_field_name, {})
        
        # 判断字段是否为空：空字典、或没有id且没有candidates
        is_empty = (
            not current_field_value or
            (isinstance(current_field_value, dict) and 
             not current_field_value.get('id') and 
             'candidates' not in current_field_value)
        )
        
        if is_empty:
            # 字段为空，直接补全
            self._set_unique_value(result, upper_field_name, upper_record)
            logger.debug(f"{upper_field_name}通过向上追溯成功补全: {upper_record.get('region_name')} (id={upper_record.get('id')})")
            return True
        
        elif isinstance(current_field_value, dict) and 'candidates' in current_field_value:
            # 字段是候选表，尝试用找到的值筛选候选表
            existing_candidates = current_field_value.get('candidates', [])
            
            # 检查追溯到的值是否在候选表中
            traced_id = upper_record.get('id')
            matched_candidates = [c for c in existing_candidates if c.get('id') == traced_id]
            
            if len(matched_candidates) == 1:
                # 筛选成功，更新为唯一值
                self._set_unique_value(result, upper_field_name, upper_record)
                logger.debug(f"{upper_field_name}通过向上追溯成功筛选: {upper_record.get('region_name')} (id={upper_record.get('id')})")
                return True
            else:
                # 筛选失败，直接用追溯到的值替换候选表
                self._set_unique_value(result, upper_field_name, upper_record)
                warning_msg = f"{upper_field_name}检测到与下级信息不匹配，已根据数据库完成替换"
                warnings.append(warning_msg)
                logger.warning(f"{warning_msg}: 候选表中未找到追溯值 (追溯id={traced_id}, 候选表包含{len(existing_candidates)}个候选)")
                return True
        
        elif self.is_unique_value(current_field_value):
            # 字段已经是唯一值，检查 id 是否一致
            existing_id = current_field_value.get('id')
            traced_id = upper_record.get('id')
            
            if existing_id == traced_id:
                # id 一致，记录成功对应
                logger.debug(f"{upper_field_name}成功对应: id={existing_id}")
                return True
            else:
                # id 不一致，直接用追溯到的值替换原有值
                self._set_unique_value(result, upper_field_name, upper_record)
                warning_msg = f"{upper_field_name}检测到与下级信息不匹配，已根据数据库完成替换"
                warnings.append(warning_msg)
                logger.warning(f"{warning_msg}: 原id={existing_id}, 追溯id={traced_id}")
                return True
        
        return False
    
    def trace_upward_recursively(
        self,
        unique_record: Dict[str, Any],
        result: Dict[str, Any],
        warnings: List[str],
        candidate_tables: Dict[str, List[Dict[str, Any]]]
    ) -> None:
        """
        递归向上追溯所有上级
        
        Args:
            unique_record: 唯一确定的区域记录
            result: 结果字典（会被修改）
            warnings: 警告信息列表（会被修改）
            candidate_tables: 候选表字典
        """
        # 根据 unique_record 的 region_type 确定当前字段名和上级字段名
        current_region_type = unique_record.get('region_type')
        current_field_name = self.region_type_to_field.get(current_region_type)
        
        if not current_field_name:
            return
        
        upper_field_name = self.field_to_upper_field.get(current_field_name)
        
        if not upper_field_name:
            # 已经是最高级别（ProvinceName），无上级可追溯
            return
        
        upper_region_type = self.field_to_region_type.get(upper_field_name)
        if not upper_region_type:
            return
        
        # 调用 trace_upward_from_unique_value 追溯直接上级
        success = self.trace_upward_from_unique_value(
            unique_record,
            upper_field_name,
            upper_region_type,
            result,
            warnings,
            candidate_tables
        )
        
        # 检查追溯后的上级字段状态
        if success:
            # 追溯成功且得到唯一值，递归追溯更上级
            upper_record = self.get_unique_record(result, upper_field_name)
            if upper_record:
                self.trace_upward_recursively(upper_record, result, warnings, candidate_tables)
    
    def cascade_match_unique_to_upper(
        self,
        lower_field_name: str,
        upper_field_name: str,
        result: Dict[str, Any],
        warnings: List[str],
        cascade_match_failed_states: Optional[Dict[str, bool]] = None
    ) -> bool:
        """
        执行级联匹配（本级为唯一值格式）
        
        逻辑：
        1. 获取本级的唯一值（包含parent_id）
        2. 获取上级值（可能是候选表或唯一值）
        3. 提取上级的有效 id 集合
        4. 检查本级的parent_id是否在上级的id集合中
        5. 如果不在，记录级联匹配失败状态
        
        Args:
            lower_field_name: 本级字段名（如 'ExpAreaName'）
            upper_field_name: 上级字段名（如 'CityName'）
            result: 当前结果字典
            warnings: 警告信息列表（会被修改）
            cascade_match_failed_states: 状态变量字典，用于记录级联匹配失败的状态（可选）
        
        Returns:
            True 如果匹配成功，False 如果匹配失败
        """
        # 获取本级唯一值
        lower_value = result.get(lower_field_name, {})
        if not self.is_unique_value(lower_value):
            logger.debug(f"级联匹配（唯一值）跳过: {lower_field_name}不是唯一值格式")
            return False
        
        lower_parent_id = lower_value.get('parent_id')
        if not lower_parent_id or lower_parent_id == 0:
            logger.debug(f"级联匹配（唯一值）跳过: {lower_field_name}没有parent_id")
            return False
        
        # 获取上级值
        upper_value = result.get(upper_field_name, {})
        
        # 提取上级的有效 id 集合
        upper_ids = set()
        
        if self.is_unique_value(upper_value):
            # 上级是唯一值
            upper_unique_id = upper_value.get('id')
            if upper_unique_id is not None:
                upper_ids.add(upper_unique_id)
                logger.debug(f"级联匹配（唯一值）: {upper_field_name}是唯一值，id={upper_unique_id}")
        elif self.is_candidate_format(upper_value):
            # 上级是候选表
            upper_candidates = upper_value.get('candidates', [])
            upper_ids = {c.get('id') for c in upper_candidates if c.get('id') is not None}
            logger.debug(f"级联匹配（唯一值）: {upper_field_name}是候选表，包含{len(upper_ids)}个id")
        else:
            # 上级既不是唯一值也不是候选表，跳过
            logger.debug(f"级联匹配（唯一值）跳过: {upper_field_name}既不是唯一值也不是候选表")
            return False
        
        if not upper_ids:
            logger.debug(f"级联匹配（唯一值）跳过: {upper_field_name}没有有效的id")
            return False
        
        # 检查本级的parent_id是否在上级的id集合中
        if lower_parent_id in upper_ids:
            logger.debug(f"级联匹配（唯一值）成功: {lower_field_name}的parent_id({lower_parent_id})在{upper_field_name}的id集合中")
            return True
        else:
            # 匹配失败，记录状态
            warning_msg = f"{upper_field_name}与{lower_field_name}不存在级联关系"
            logger.warning(f"级联匹配（唯一值）失败: {warning_msg} (本级parent_id={lower_parent_id}, 上级id集合={upper_ids})")
            
            # 如果是特定字段对的级联匹配失败，设置状态变量
            if cascade_match_failed_states is not None:
                # CityName与ExpAreaName级联匹配失败
                if lower_field_name == 'ExpAreaName' and upper_field_name == 'CityName':
                    cascade_match_failed_states['CityName_ExpAreaName'] = True
                    logger.debug(f"设置级联匹配失败状态: CityName与ExpAreaName不存在级联关系")
                # ExpAreaName与StreetName级联匹配失败
                elif lower_field_name == 'StreetName' and upper_field_name == 'ExpAreaName':
                    cascade_match_failed_states['ExpAreaName_StreetName'] = True
                    logger.debug(f"设置级联匹配失败状态: ExpAreaName与StreetName不存在级联关系")
            
            return False
    
    def cascade_match_candidates(
        self,
        lower_field_name: str,
        upper_field_name: str,
        result: Dict[str, Any],
        warnings: List[str],
        original_result: Dict[str, Any],
        cascade_match_failed_states: Optional[Dict[str, bool]] = None
    ) -> bool:
        """
        执行候选值级联匹配
        
        逻辑：
        1. 获取本级候选表（必须是候选表格式）
        2. 获取上级值（可能是候选表或唯一值）
        3. 提取上级的有效 id 集合
        4. 筛选本级候选：只保留 parent_id 在上级 id 集合中的候选
        5. 如果筛选后本级候选为空，恢复原始值并添加警告
        6. 如果筛选后本级候选唯一，筛选上级候选只保留对应的 id
        7. 如果筛选后本级候选不唯一，筛选上级候选只保留有对应关系的 id
        
        Args:
            lower_field_name: 本级字段名（如 'StreetName'）
            upper_field_name: 上级字段名（如 'ExpAreaName'）
            result: 当前结果字典（会被修改）
            warnings: 警告信息列表（会被修改）
            original_result: resolve阶段后的原始结果（用于恢复）
            cascade_match_failed_states: 状态变量字典，用于记录级联匹配失败的状态（可选）
        
        Returns:
            True 如果执行成功，False 如果需要恢复原始值
        """
        # 获取本级候选表
        lower_value = result.get(lower_field_name, {})
        if not self.is_candidate_format(lower_value):
            logger.debug(f"级联匹配跳过: {lower_field_name}不是候选表格式")
            return False
        
        lower_candidates = lower_value.get('candidates', [])
        if not lower_candidates:
            logger.debug(f"级联匹配跳过: {lower_field_name}候选表为空")
            return False
        
        # 获取上级值
        upper_value = result.get(upper_field_name, {})
        
        # 提取上级的有效 id 集合
        upper_ids = set()
        upper_is_unique = False
        upper_unique_id = None
        
        if self.is_unique_value(upper_value):
            # 上级是唯一值
            upper_unique_id = upper_value.get('id')
            if upper_unique_id is not None:
                upper_ids.add(upper_unique_id)
                upper_is_unique = True
                logger.debug(f"级联匹配: {upper_field_name}是唯一值，id={upper_unique_id}")
        elif self.is_candidate_format(upper_value):
            # 上级是候选表
            upper_candidates = upper_value.get('candidates', [])
            upper_ids = {c.get('id') for c in upper_candidates if c.get('id') is not None}
            logger.debug(f"级联匹配: {upper_field_name}是候选表，包含{len(upper_ids)}个id")
        else:
            # 上级既不是唯一值也不是候选表，跳过
            logger.debug(f"级联匹配跳过: {upper_field_name}既不是唯一值也不是候选表")
            return False
        
        if not upper_ids:
            logger.debug(f"级联匹配跳过: {upper_field_name}没有有效的id")
            return False
        
        # 筛选本级候选：只保留 parent_id 在上级 id 集合中的候选
        filtered_lower_candidates = [
            c for c in lower_candidates
            if c.get('parent_id') is not None and c.get('parent_id') in upper_ids
        ]
        
        logger.debug(f"级联匹配: {lower_field_name}筛选前{len(lower_candidates)}个候选，筛选后{len(filtered_lower_candidates)}个候选")
        
        # 判断筛选结果
        if len(filtered_lower_candidates) == 0:
            # 筛选后本级候选为空，恢复原始值并添加警告
            result[lower_field_name] = copy.deepcopy(original_result.get(lower_field_name, {}))
            result[upper_field_name] = copy.deepcopy(original_result.get(upper_field_name, {}))
            warning_msg = f"{upper_field_name}与{lower_field_name}不存在级联关系"
            # warnings.append(warning_msg)
            logger.warning(f"级联匹配失败: {warning_msg}")
            
            # 如果是特定字段对的级联匹配失败，设置状态变量
            if cascade_match_failed_states is not None:
                # CityName与ExpAreaName级联匹配失败
                if lower_field_name == 'ExpAreaName' and upper_field_name == 'CityName':
                    cascade_match_failed_states['CityName_ExpAreaName'] = True
                    logger.debug(f"设置级联匹配失败状态: CityName与ExpAreaName不存在级联关系")
                # ExpAreaName与StreetName级联匹配失败
                elif lower_field_name == 'StreetName' and upper_field_name == 'ExpAreaName':
                    cascade_match_failed_states['ExpAreaName_StreetName'] = True
                    logger.debug(f"设置级联匹配失败状态: ExpAreaName与StreetName不存在级联关系")
            
            return False
        
        # 更新本级候选表
        lower_region_type = lower_value.get('region_type')
        if len(filtered_lower_candidates) == 1:
            # 筛选后本级候选唯一
            unique_candidate = filtered_lower_candidates[0]
            target_parent_id = unique_candidate.get('parent_id')
            
            # 更新本级为唯一值格式
            self._set_unique_value(result, lower_field_name, {
                'id': unique_candidate.get('id'),
                'parent_id': unique_candidate.get('parent_id'),
                'region_name': unique_candidate.get('region_name', ''),
                'region_type': lower_region_type
            })
            logger.debug(f"级联匹配: {lower_field_name}筛选后唯一确定，id={unique_candidate.get('id')}")
            
            # 如果上级是候选表，筛选上级候选只保留 id == target_parent_id 的项
            if not upper_is_unique and self.is_candidate_format(upper_value):
                upper_candidates = upper_value.get('candidates', [])
                filtered_upper_candidates = [
                    c for c in upper_candidates
                    if c.get('id') == target_parent_id
                ]
                
                if len(filtered_upper_candidates) == 1:
                    # 上级筛选后唯一，转换为唯一值格式
                    unique_upper = filtered_upper_candidates[0]
                    upper_region_type = upper_value.get('region_type')
                    result[upper_field_name] = {
                        'id': unique_upper.get('id'),
                        'parent_id': unique_upper.get('parent_id'),
                        'region_name': unique_upper.get('region_name', ''),
                        'region_type': upper_region_type
                    }
                    logger.debug(f"级联匹配: {upper_field_name}筛选后唯一确定，id={unique_upper.get('id')}")
                elif len(filtered_upper_candidates) > 1:
                    # 上级筛选后仍有多个（理论上不应该发生，但保留处理）
                    self._set_candidate_format(result, upper_field_name, filtered_upper_candidates)
                    logger.debug(f"级联匹配: {upper_field_name}筛选后仍有{len(filtered_upper_candidates)}个候选值")
                else:
                    # 上级筛选后为空（理论上不应该发生，但保留处理）
                    logger.warning(f"级联匹配: {upper_field_name}筛选后为空，保留原候选表")
        else:
            # 筛选后本级候选不唯一
            # 更新本级候选表
            self._set_candidate_format(result, lower_field_name, filtered_lower_candidates)
            logger.debug(f"级联匹配: {lower_field_name}筛选后仍有多个候选值")
            
            # 提取所有 parent_id 集合
            target_parent_ids = {c.get('parent_id') for c in filtered_lower_candidates if c.get('parent_id') is not None}
            
            # 如果上级是候选表，筛选上级候选只保留 id 在 target_parent_ids 集合中的项
            if not upper_is_unique and self.is_candidate_format(upper_value):
                upper_candidates = upper_value.get('candidates', [])
                filtered_upper_candidates = [
                    c for c in upper_candidates
                    if c.get('id') in target_parent_ids
                ]
                
                if len(filtered_upper_candidates) == 1:
                    # 上级筛选后唯一，转换为唯一值格式
                    unique_upper = filtered_upper_candidates[0]
                    upper_region_type = upper_value.get('region_type')
                    self._set_unique_value(result, upper_field_name, {
                        'id': unique_upper.get('id'),
                        'parent_id': unique_upper.get('parent_id'),
                        'region_name': unique_upper.get('region_name', ''),
                        'region_type': upper_region_type
                    })
                    logger.debug(f"级联匹配: {upper_field_name}筛选后唯一确定，id={unique_upper.get('id')}")
                elif len(filtered_upper_candidates) > 1:
                    # 上级筛选后仍有多个
                    self._set_candidate_format(result, upper_field_name, filtered_upper_candidates)
                    logger.debug(f"级联匹配: {upper_field_name}筛选后仍有{len(filtered_upper_candidates)}个候选值")
                else:
                    # 上级筛选后为空（理论上不应该发生，但保留处理）
                    logger.warning(f"级联匹配: {upper_field_name}筛选后为空，保留原候选表")
        
        return True
    
    def resolve_middle_levels_by_tracing(
        self,
        result: Dict[str, Any],
        warnings: List[str],
        cascade_match_failed_city_exparea: bool = False,
        cascade_match_failed_exparea_street: bool = False
    ) -> bool:
        """
        特殊情况中间层级确定方法
        
        触发条件：
        条件一（硬性条件，必须满足）：
        1. ProvinceName唯一确定
        2. StreetName为候选表格式
        
        条件二（可选）：
        - CityName不具备唯一值（为空或候选表）**AND** ExpAreaName不具备唯一值（为空或候选表）
        
        条件三（可选）：
        - CityName与ExpAreaName级联匹配失败 **AND** ExpAreaName与StreetName级联匹配失败
        
        最终触发条件：条件一 AND (条件二 OR 条件三)
        
        逻辑：
        遍历StreetName候选表，追溯每条候选的上级信息链，验证是否与ProvinceName匹配
        
        Args:
            result: 结果字典（会被修改）
            warnings: 警告信息列表
            cascade_match_failed_city_exparea: CityName与ExpAreaName级联匹配失败的状态
            cascade_match_failed_exparea_street: ExpAreaName与StreetName级联匹配失败的状态
        
        Returns:
            True 如果成功确定中间层级，False 如果跳过或失败
        """
        # 检查条件一：ProvinceName是否为唯一值
        province_record = self.get_unique_record(result, 'ProvinceName')
        if not province_record:
            # ProvinceName不是唯一值，尝试通过CityName向上追溯补全ProvinceName
            logger.debug("方法4 特殊情况中间层级确定: ProvinceName不是唯一值，尝试通过CityName向上追溯补全")
            city_record = self.get_unique_record(result, 'CityName')
            if city_record:
                city_parent_id = city_record.get('parent_id')
                if city_parent_id and city_parent_id != 0:
                    # 通过CityName的parent_id查找ProvinceName
                    province_region_type = self.region_type_map.get('ProvinceName')
                    if province_region_type:
                        try:
                            province_found = self.matcher.find_region_by_id(city_parent_id)
                            if province_found and province_found.get('region_type') == province_region_type:
                                # 补全成功，设置ProvinceName为唯一值
                                self._set_unique_value(result, 'ProvinceName', province_found)
                                province_record = province_found
                                logger.debug(f"方法4 特殊情况中间层级确定: 通过CityName向上追溯成功补全ProvinceName (id={province_found.get('id')}, region_name={province_found.get('region_name')})")
                            else:
                                logger.debug("方法4 特殊情况中间层级确定 未执行: 通过CityName向上追溯未找到匹配的ProvinceName")
                                return False
                        except Exception as e:
                            logger.error(f"方法4 特殊情况中间层级确定: 通过CityName向上追溯时发生错误: {str(e)}")
                            return False
                    else:
                        logger.debug("方法4 特殊情况中间层级确定 未执行: 无法获取ProvinceName的region_type")
                        return False
                else:
                    logger.debug("方法4 特殊情况中间层级确定 未执行: CityName没有有效的parent_id")
                    return False
            else:
                logger.debug("方法4 特殊情况中间层级确定 未执行: 条件一不满足 - ProvinceName不是唯一值且CityName也不是唯一值")
                return False
        
        province_id = province_record.get('id')
        
        # 检查条件一：StreetName是否为候选表格式
        street_value = result.get('StreetName', {})
        if not self.is_candidate_format(street_value):
            logger.debug("方法4 特殊情况中间层级确定 未执行: 条件一不满足 - StreetName不是候选表格式")
            return False
        
        street_candidates = street_value.get('candidates', [])
        if not street_candidates:
            logger.debug("方法4 特殊情况中间层级确定 未执行: 条件一不满足 - StreetName候选表为空")
            return False
        
        # 检查条件二：CityName和ExpAreaName是否都不具备唯一值
        city_value = result.get('CityName', {})
        exp_area_value = result.get('ExpAreaName', {})
        condition_two = not self.is_unique_value(city_value) and not self.is_unique_value(exp_area_value)
        
        # 检查条件三：两个级联匹配失败状态是否都为True
        condition_three = cascade_match_failed_city_exparea and cascade_match_failed_exparea_street
        
        # 判断是否满足触发条件：条件一 AND (条件二 OR 条件三)
        if not (condition_two or condition_three):
            logger.debug(f"方法4 特殊情况中间层级确定 未执行: 条件二({condition_two})和条件三({condition_three})都不满足")
            return False
        
        logger.debug(f"方法4 特殊情况中间层级确定 开始执行: 条件一满足, 条件二={condition_two}, 条件三={condition_three}")
        
        # 获取ExpAreaName和CityName的region_type
        exp_area_region_type = self.region_type_map.get('ExpAreaName')
        city_region_type = self.region_type_map.get('CityName')
        
        # 在循环外先获取一次缓存数据，避免重复获取
        try:
            all_exp_areas = self.matcher.get_regions_by_type(exp_area_region_type)
            all_cities = self.matcher.get_regions_by_type(city_region_type)
            
            if not all_exp_areas or not all_cities:
                logger.debug("方法4 特殊情况中间层级确定: 缓存数据为空，跳过处理")
                return False
        except Exception as e:
            logger.error(f"方法4 特殊情况中间层级确定: 获取缓存数据时发生错误: {str(e)}")
            return False
        
        # 遍历StreetName候选表
        for street_candidate in street_candidates:
            street_parent_id = street_candidate.get('parent_id')
            if not street_parent_id:
                continue
            
            # 追溯ExpAreaName：从已获取的缓存中查找parent_id等于street_parent_id的ExpAreaName记录
            try:
                # 过滤出id等于street_parent_id的ExpAreaName记录（使用已获取的all_exp_areas）
                exp_area_records = [
                    r for r in all_exp_areas
                    if r.get('id') == street_parent_id
                ]
                
                if not exp_area_records:
                    continue
                
                if len(exp_area_records) > 1:
                    logger.warning(f"方法4 特殊情况中间层级确定: 找到多个id={street_parent_id}的ExpAreaName记录，使用第一个")
                
                exp_area_record = exp_area_records[0]
                exp_area_parent_id = exp_area_record.get('parent_id')
                
                if not exp_area_parent_id:
                    continue
                
                # 追溯CityName：从已获取的缓存中查找id等于exp_area_parent_id的CityName记录
                # 过滤出id等于exp_area_parent_id的CityName记录（使用已获取的all_cities）
                city_records = [
                    r for r in all_cities
                    if r.get('id') == exp_area_parent_id
                ]
                
                if not city_records:
                    continue
                
                if len(city_records) > 1:
                    logger.warning(f"方法4 特殊情况中间层级确定: 找到多个id={exp_area_parent_id}的CityName记录，使用第一个")
                
                city_record = city_records[0]
                city_parent_id = city_record.get('parent_id')
                
                # 验证信息链：比较CityName的parent_id是否等于ProvinceName的id
                if city_parent_id == province_id:
                    # 找到匹配的信息链，设置所有相关字段为唯一值
                    self._set_unique_value(result, 'StreetName', street_candidate)
                    self._set_unique_value(result, 'ExpAreaName', exp_area_record)
                    self._set_unique_value(result, 'CityName', city_record)
                    return True
                else:
                    continue
                    
            except Exception as e:
                logger.error(f"方法4 特殊情况中间层级确定: 追溯过程中发生错误: {str(e)}")
                continue
        
        # 所有候选都遍历完仍未找到匹配的信息链
        return False
    
    def _are_adjacent_levels(self, upper_type: int, lower_type: int) -> bool:
        """
        检查两个region_type是否是相邻层级
        
        Args:
            upper_type: 上级region_type
            lower_type: 下级region_type
        
        Returns:
            True 如果是相邻层级
        """
        # 定义相邻层级关系
        adjacent_pairs = [
            (self.region_type_map.get('ProvinceName'), self.region_type_map.get('CityName')),
            (self.region_type_map.get('CityName'), self.region_type_map.get('ExpAreaName')),
            (self.region_type_map.get('ExpAreaName'), self.region_type_map.get('StreetName'))
        ]
        
        return (upper_type, lower_type) in adjacent_pairs
    
    def remove_duplicate_region_names(
        self,
        result: Dict[str, Any],
        warnings: List[str]
    ) -> None:
        """
        去重函数：由上往下检查，如果本级唯一值的region_name与下级重复，清除下级
        
        判断条件：
        1. 本级是唯一值（有id且不是候选表）
        2. 本级的region_name与下级的region_name完全相等
        3. 本级的region_type与下级的region_type是相邻层级（如ExpAreaName和StreetName）
        
        Args:
            result: 结果字典（会被修改）
            warnings: 警告信息列表（会被修改）
        """
        # 字段层级关系（上级 -> 下级）
        field_hierarchy = {
            'ProvinceName': 'CityName',
            'CityName': 'ExpAreaName',
            'ExpAreaName': 'StreetName'
        }
        
        # 由上往下检查
        for upper_field, lower_field in field_hierarchy.items():
            upper_value = result.get(upper_field, {})
            lower_value = result.get(lower_field, {})
            
            # 检查上级是否为唯一值
            if not self.is_unique_value(upper_value):
                continue
            
            upper_region_name = upper_value.get('region_name', '').strip()
            if not upper_region_name:
                continue
            
            # 检查下级是否有数据
            if not lower_value:
                continue
            
            # 情况1：下级是唯一值
            if self.is_unique_value(lower_value):
                lower_region_name = lower_value.get('region_name', '').strip()
                if lower_region_name == upper_region_name:
                    # 检查region_type是否相邻（避免误判）
                    upper_region_type = upper_value.get('region_type')
                    lower_region_type = lower_value.get('region_type')
                    
                    if self._are_adjacent_levels(upper_region_type, lower_region_type):
                        # 清空下级，保留结构（id=null, parent_id=null, region_name="", region_type=原值）
                        result[lower_field] = {
                            'id': None,
                            'parent_id': None,
                            'region_name': '',
                            'region_type': lower_region_type
                        }
                        # warnings.append(f"{lower_field}与{upper_field}的region_name重复('{upper_region_name}')，已清除{lower_field}")
                        logger.debug(f"去重: {upper_field}='{upper_region_name}'与{lower_field}='{lower_region_name}'重复，已清除{lower_field}")
            
            # 情况2：下级是候选表
            elif isinstance(lower_value, dict) and 'candidates' in lower_value:
                lower_region_name = lower_value.get('region_name', '').strip()
                if lower_region_name == upper_region_name:
                    # 检查region_type是否相邻
                    upper_region_type = upper_value.get('region_type')
                    lower_region_type = lower_value.get('region_type')
                    
                    if self._are_adjacent_levels(upper_region_type, lower_region_type):
                        # 清空候选表，保留结构（id=null, parent_id=null, region_name="", region_type=原值）
                        result[lower_field] = {
                            'id': None,
                            'parent_id': None,
                            'region_name': '',
                            'region_type': lower_region_type
                        }
                        # warnings.append(f"{lower_field}候选表与{upper_field}的region_name重复('{upper_region_name}')，已清除{lower_field}")
                        logger.debug(f"去重: {upper_field}='{upper_region_name}'与{lower_field}候选表重复，已清除{lower_field}")

