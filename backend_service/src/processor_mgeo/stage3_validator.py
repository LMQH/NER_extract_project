"""
第三阶段：返回数据校验模块
检查空字段、候选值、未匹配字段，设置状态码和警告信息
"""
import logging
from typing import Dict, Any, List

logger = logging.getLogger("NER_API")


class Stage3Validator:
    """第三阶段校验器：数据校验和状态码设置"""
    
    def __init__(self, region_type_map: Dict[str, int]):
        """
        初始化第三阶段校验器
        
        Args:
            region_type_map: 区域类型映射字典
        """
        self.region_type_map = region_type_map
    
    def is_candidate_format(self, field_value: Any) -> bool:
        """
        检查字段是否为候选表格式
        
        Args:
            field_value: 字段值
        
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
    
    def is_unique_value(self, field_value: Any) -> bool:
        """
        检查字段是否为唯一确定的值
        
        Args:
            field_value: 字段值
        
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
            if isinstance(field_value, dict) and 'candidates' in field_value:
                candidates = field_value.get('candidates', [])
                
                # 如果只有一个候选值，转换为唯一值格式
                if isinstance(candidates, list) and len(candidates) == 1:
                    candidate = candidates[0]
                    
                    # 从候选元素中获取region_name，从顶层获取region_type
                    region_name = candidate.get('region_name', '')
                    region_type = field_value.get('region_type')
                    
                    # 转换为唯一值格式
                    result[field_name] = {
                        'id': candidate.get('id'),
                        'parent_id': candidate.get('parent_id'),
                        'region_name': region_name,
                        'region_type': region_type
                    }
                    logger.debug(f"{field_name}从单候选格式转换为唯一值格式: id={candidate.get('id')}, region_name='{region_name}'")
    
    def check_empty_fields(self, result: Dict[str, Any], warnings: List[str]) -> None:
        """
        检查四个关键数据块是否为空
        
        Args:
            result: 结果字典
            warnings: 警告信息列表（会被修改）
        """
        field_messages = {
            'StreetName': 'StreetName 街道乡镇级信息为空',
            'ExpAreaName': 'ExpAreaName 区县级信息为空',
            'CityName': 'CityName 城市级信息为空',
            'ProvinceName': 'ProvinceName 省域级信息为空'
        }
        
        for field_name, warning_msg in field_messages.items():
            field_value = result.get(field_name, {})
            
            # 检查是否为空
            # 1. 如果是候选表格式，则不为空（候选值检查会在check_candidate_fields中处理）
            if self.is_candidate_format(field_value):
                continue
            
            # 2. 如果是唯一值格式，则不为空
            if self.is_unique_value(field_value):
                continue
            
            # 3. 检查是否为空（空字典、空字符串、或id为空且region_name为空）
            is_empty = False
            if isinstance(field_value, dict):
                if not field_value:
                    is_empty = True
                elif not field_value.get('id') and not field_value.get('region_name'):
                    is_empty = True
            elif isinstance(field_value, str):
                if not field_value.strip():
                    is_empty = True
            else:
                is_empty = True
            
            if is_empty:
                # 对 StreetName 做特殊处理
                if field_name == 'StreetName':
                    # 检查 AreasInfo 和 Address 是否都为空
                    areas_info = result.get('AreasInfo', '')
                    address = result.get('Address', '')
                    
                    # 判断 AreasInfo 和 Address 是否都为空
                    areas_info_empty = not areas_info or (isinstance(areas_info, str) and not areas_info.strip())
                    address_empty = not address or (isinstance(address, str) and not address.strip())
                    
                    if areas_info_empty and address_empty:
                        # 都为空，使用原有警告信息
                        warnings.append(warning_msg)
                        logger.debug(f"检查到空字段: {field_name}")
                    else:
                        # 有值，使用新警告信息
                        warnings.append('StreetName 街道乡镇级信息在数据库中无匹配')
                        logger.debug(f"检查到空字段: {field_name} (但AreasInfo或Address有值)")
                else:
                    # 其他字段保持原有逻辑
                    warnings.append(warning_msg)
                    logger.debug(f"检查到空字段: {field_name}")
    
    def check_candidate_fields(self, result: Dict[str, Any], warnings: List[str]) -> None:
        """
        检查是否存在未确定的多个候选值
        
        Args:
            result: 结果字典
            warnings: 警告信息列表（会被修改）
        """
        field_messages = {
            'StreetName': 'StreetName 街道乡镇级信息存在多个候选值无法确定',
            'ExpAreaName': 'ExpAreaName 区县级信息存在多个候选值无法确定',
            'CityName': 'CityName 城市级信息存在多个候选值无法确定',
            'ProvinceName': 'ProvinceName 省域级信息存在多个候选值无法确定'
        }
        
        for field_name, warning_msg in field_messages.items():
            field_value = result.get(field_name, {})
            
            # 检查是否存在candidates
            if isinstance(field_value, dict) and 'candidates' in field_value:
                candidates = field_value.get('candidates', [])
                if isinstance(candidates, list) and len(candidates) > 0:
                    warnings.append(warning_msg)
                    logger.debug(f"检查到候选值: {field_name} 有{len(candidates)}个候选值")
    
    def check_unmatched_fields(self, result: Dict[str, Any], warnings: List[str]) -> None:
        """
        检查region_name不为空但是id为空的情况
        
        Args:
            result: 结果字典
            warnings: 警告信息列表（会被修改）
        """
        # 统一检查四个字段
        field_messages = {
            'ProvinceName': 'ProvinceName 省域级信息无法在数据库中确定',
            'CityName': 'CityName 城市级信息无法在数据库中确定',
            'ExpAreaName': 'ExpAreaName 区县级信息无法在数据库中确定',
            'StreetName': 'StreetName 街道乡镇级信息无法在数据库中确定'
        }
        
        for field_name, warning_msg in field_messages.items():
            field_value = result.get(field_name, {})
            
            # 只检查唯一值格式（候选表格式不在此检查范围内）
            if self.is_unique_value(field_value):
                region_name = field_value.get('region_name', '')
                region_id = field_value.get('id')
                
                if region_name and not region_id:
                    warnings.append(warning_msg)
                    logger.debug(f"检查到未匹配字段: {field_name} region_name={region_name}但id为空")
    
    def set_result_code(self, result: Dict[str, Any], warnings: List[str]) -> None:
        """
        根据校验结果设置状态码
        
        规则：
        - 存在空字段或候选值（情况1、2）→ 103
        - region_name不为空但id为空（情况3）→ 100（默认值，不处理）
        - "StreetName 街道乡镇级信息在数据库中无匹配"不触发103
        
        Args:
            result: 结果字典（会被修改）
            warnings: 警告信息列表
        """
        # 检查是否存在情况1或2的警告
        # 排除"StreetName 街道乡镇级信息在数据库中无匹配"这个警告
        has_empty_or_candidate = any(
            ('为空' in w or '存在多个候选值' in w) 
            and 'StreetName 街道乡镇级信息在数据库中无匹配' not in w
            for w in warnings
        )
        
        if has_empty_or_candidate:
            result['ResultCode'] = '103'
            result['Success'] = False
            result['Reason'] = '地址无法完全确定'
            logger.debug("设置状态码103: 地址信息缺失或存在多个候选值无法确定")
        else:
            # 默认状态码100
            if 'ResultCode' not in result:
                result['ResultCode'] = '100'
                result['Success'] = True
                result['Reason'] = '解析成功'
    
    def execute_stage3_validate(
        self,
        result: Dict[str, Any],
        warnings: List[str]
    ) -> None:
        """
        执行所有校验步骤
        
        Args:
            result: 结果字典（会被修改）
            warnings: 警告信息列表（会被修改）
        """
        logger.debug("第三阶段开始 进行数据返回阶段校验")
        
        # 1. 检查空字段
        logger.debug("步骤1 检查四个关键数据块是否为空 开始")
        self.check_empty_fields(result, warnings)
        logger.debug("步骤1 检查四个关键数据块是否为空 已完成")
        
        # 2. 检查候选值
        logger.debug("步骤2 检查是否存在未确定的多个候选值 开始")
        self.check_candidate_fields(result, warnings)
        logger.debug("步骤2 检查是否存在未确定的多个候选值 已完成")
        
        # 3. 检查未匹配字段
        logger.debug("步骤3 检查region_name不为空但是id为空的情况 开始")
        self.check_unmatched_fields(result, warnings)
        logger.debug("步骤3 检查region_name不为空但是id为空的情况 已完成")
        
        # 4. 设置状态码
        logger.debug("步骤4 根据校验结果设置状态码 开始")
        self.set_result_code(result, warnings)
        logger.debug("步骤4 根据校验结果设置状态码 已完成")
        
        # 5. 设置警告信息
        result['Warning'] = warnings if warnings else []
        
        # 合并为一条INFO日志
        result_code = result.get('ResultCode', '100')
        reason = result.get('Reason', '解析成功')
        logger.info(f"第三阶段结果校验完成：状态码{result_code} {reason}")

