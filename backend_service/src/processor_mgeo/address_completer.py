"""
地址补全模块（新版本）
协调三个阶段：匹配阶段、处理阶段、校验阶段
"""
import os
import time
import logging
from typing import Dict, Any, Optional
from src.database import DatabaseConnection, RegionCache
from .matcher import RegionMatcher
from .stage1_matcher import Stage1Matcher
from .stage2_resolver import Stage2Resolver
from .stage3_validator import Stage3Validator
from .converters import reorder_data_fields
from src.config.constants import DIRECT_CITIES

logger = logging.getLogger("NER_API")


class AddressCompleter:
    """地址补全器（新版本）"""
    
    def __init__(self, db_connection: DatabaseConnection):
        """
        初始化地址补全器
        
        Args:
            db_connection: 数据库连接对象
        """
        self.db = db_connection
        # 初始化Redis缓存
        self.region_cache = RegionCache()
        # 从环境变量获取表名，默认为region_table
        self.table_name = os.getenv('MYSQL_REGION_TABLE', 'region_table')
        # 区域类型映射
        self.region_type_map = {
            'ProvinceName': int(os.getenv('REGION_TYPE_PROVINCE', '1001')),  # 省
            'CityName': int(os.getenv('REGION_TYPE_CITY', '1002')),          # 市
            'ExpAreaName': int(os.getenv('REGION_TYPE_EXP_AREA', '1003')),   # 区/县
            'StreetName': int(os.getenv('REGION_TYPE_STREET', '1004'))       # 街道/镇
        }
        
        # 初始化匹配器
        self.matcher = RegionMatcher(
            self.db, 
            self.region_cache, 
            self.table_name, 
            self.region_type_map
        )
        
        # 初始化三个阶段
        self.stage1_matcher = Stage1Matcher(self.matcher, self.region_type_map)
        self.stage2_resolver = Stage2Resolver(self.matcher, self.region_type_map)
        self.stage3_validator = Stage3Validator(self.region_type_map)
    
    def get_parent_chain(self, start_region: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        获取父级链，从当前区域向上查找所有父级
        
        Args:
            start_region: 起始区域信息（包含id, parent_id, region_name, region_type）
        
        Returns:
            父级链字典，键为字段名（ProvinceName, CityName, ExpAreaName），值为区域信息
        """
        parent_chain = {}
        current_region = start_region
        
        while current_region:
            parent_id = current_region.get('parent_id')
            if not parent_id or parent_id == 0:
                break
            
            # 查找父级区域
            parent_region = self.matcher.find_region_by_id(parent_id)
            if not parent_region:
                break
            
            # 根据region_type确定字段名
            region_type = parent_region.get('region_type')
            if region_type == self.region_type_map.get('ProvinceName'):
                parent_chain['ProvinceName'] = parent_region
            elif region_type == self.region_type_map.get('CityName'):
                parent_chain['CityName'] = parent_region
            elif region_type == self.region_type_map.get('ExpAreaName'):
                parent_chain['ExpAreaName'] = parent_region
            
            # 继续向上查找
            current_region = parent_region
        
        return parent_chain
    
    def complete_all_fields_from_chain(
        self, 
        region: Dict[str, Any], 
        result: Dict[str, Any]
    ) -> None:
        """
        从区域链补全所有字段（向上追溯）
        
        Args:
            region: 起始区域信息
            result: 结果字典（会被修改）
        """
        # 获取完整的父级链
        parent_chain = self.get_parent_chain(region)
        
        # 将当前区域也加入链中
        region_type = region.get('region_type')
        if region_type == self.region_type_map.get('StreetName'):
            parent_chain['StreetName'] = region
        elif region_type == self.region_type_map.get('ExpAreaName'):
            parent_chain['ExpAreaName'] = region
        elif region_type == self.region_type_map.get('CityName'):
            parent_chain['CityName'] = region
        elif region_type == self.region_type_map.get('ProvinceName'):
            parent_chain['ProvinceName'] = region
        
        # 补全所有字段
        for field_name in ['ProvinceName', 'CityName', 'ExpAreaName', 'StreetName']:
            if field_name in parent_chain:
                region_info = parent_chain[field_name]
                result[field_name] = {
                    'id': region_info.get('id'),
                    'parent_id': region_info.get('parent_id'),
                    'region_name': region_info.get('region_name'),
                    'region_type': region_info.get('region_type')
                }
    
    def _extract_region_name_from_field(self, field_value: Any) -> str:
        """
        从字段值中提取区域名称
        
        Args:
            field_value: 字段值，可能是字符串或字典对象
        
        Returns:
            区域名称字符串
        """
        if not field_value:
            return ""
        
        # 如果是字典对象，提取 region_name 字段
        if isinstance(field_value, dict):
            region_name = field_value.get('region_name', '')
            if region_name:
                return str(region_name).strip()
            return ""
        
        # 如果是字符串，直接返回
        return str(field_value).strip()
    
    def _preprocess_direct_city_fix(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        预处理修复函数：识别并修复直辖市数据
        
        逻辑：
        1. 识别CityName是否为直辖市（北京市，天津市，上海市，重庆市）
        2. 支持字符串包含匹配（如"北京"匹配"北京市"）
        3. 如果识别到直辖市，则：
           - 将CityName的数据移动到ProvinceName
           - 将ExpAreaName移动到CityName（覆盖）
           - 删除原有的ExpAreaName数据，避免重复
        
        Args:
            data: 模型返回的数据字典，包含ProvinceName, CityName, ExpAreaName等字段
            
        Returns:
            修复后的数据字典
        """
        # 提取CityName的值（可能是字符串或对象格式）
        city_name_value = data.get('CityName')
        city_name_str = self._extract_region_name_from_field(city_name_value)
        
        # 如果没有CityName，直接返回
        if not city_name_str or not city_name_str.strip():
            return data
        
        # 检查CityName是否匹配直辖市（支持字符串包含）
        is_direct_city = False
        matched_direct_city = None
        
        for full_name, short_name in DIRECT_CITIES.items():
            # 支持双向包含匹配：CityName包含直辖市名，或直辖市名包含CityName
            if full_name in city_name_str or city_name_str in full_name or \
               short_name in city_name_str or city_name_str in short_name:
                is_direct_city = True
                matched_direct_city = full_name
                logger.debug(f"识别到直辖市: CityName='{city_name_str}' 匹配 '{full_name}'")
                break
        
        # 如果不是直辖市，直接返回
        if not is_direct_city:
            return data
        
        # 执行预处理修复
        result = data.copy()
        
        # 1. 将CityName的数据移动到ProvinceName
        # 如果CityName是对象格式，直接移动；如果是字符串，转换为对象格式
        if isinstance(city_name_value, dict):
            # 对象格式，直接移动，但需要更新region_type为省级（1001）
            result['ProvinceName'] = {
                'id': city_name_value.get('id'),
                'parent_id': city_name_value.get('parent_id'),
                'region_name': city_name_value.get('region_name', city_name_str),
                'region_type': self.region_type_map.get('ProvinceName')
            }
        else:
            # 字符串格式，转换为对象格式
            result['ProvinceName'] = {
                'id': None,
                'parent_id': None,
                'region_name': city_name_str,
                'region_type': self.region_type_map.get('ProvinceName')
            }
        
        logger.debug(f"预处理修复: 将CityName='{city_name_str}'移动到ProvinceName")
        
        # 2. 将ExpAreaName移动到CityName（覆盖）
        exp_area_name_value = data.get('ExpAreaName')
        exp_area_name_str = self._extract_region_name_from_field(exp_area_name_value)
        
        if exp_area_name_str and exp_area_name_str.strip():
            # 如果ExpAreaName是对象格式，直接移动；如果是字符串，转换为对象格式
            if isinstance(exp_area_name_value, dict):
                # 对象格式，直接移动，但需要更新region_type为市级（1002）
                result['CityName'] = {
                    'id': exp_area_name_value.get('id'),
                    'parent_id': exp_area_name_value.get('parent_id'),
                    'region_name': exp_area_name_value.get('region_name', exp_area_name_str),
                    'region_type': self.region_type_map.get('CityName')
                }
            else:
                # 字符串格式，转换为对象格式
                result['CityName'] = {
                    'id': None,
                    'parent_id': None,
                    'region_name': exp_area_name_str,
                    'region_type': self.region_type_map.get('CityName')
                }
            logger.debug(f"预处理修复: 将ExpAreaName='{exp_area_name_str}'移动到CityName")
        else:
            # ExpAreaName为空，清空CityName
            result['CityName'] = {
                'id': None,
                'parent_id': None,
                'region_name': '',
                'region_type': self.region_type_map.get('CityName')
            }
            logger.debug(f"预处理修复: ExpAreaName为空，清空CityName")
        
        # 3. 删除原有的ExpAreaName数据，避免重复
        result['ExpAreaName'] = {
            'id': None,
            'parent_id': None,
            'region_name': '',
            'region_type': self.region_type_map.get('ExpAreaName')
        }
        logger.debug(f"预处理修复: 清空ExpAreaName，避免重复")
        
        logger.info(f"预处理修复完成: 识别到直辖市'{matched_direct_city}'，已执行数据移动和清理")
        
        return result
    
    def complete_address_info(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        补全地址信息（新版本）
        
        整体流程：
        1. 预处理：处理直辖市数据调整
        2. 第一阶段：执行四个匹配任务，收集候选表
        3. 第二阶段：按优先级处理候选表，确定唯一结果
        4. 第三阶段：数据校验，设置状态码和警告信息
        
        Args:
            data: 模型返回的数据字典，包含ProvinceName, CityName, ExpAreaName, StreetName等字段
        
        Returns:
            补全后的数据字典，包含所有地址字段和状态信息
        """
        match_start_time = time.time()
        
        # 清除请求级别缓存，确保每个请求的数据隔离
        self.matcher.clear_request_cache()
        
        # ========== 预处理：处理直辖市数据调整 ==========
        data = self._preprocess_direct_city_fix(data)
        
        # 初始化结果字典
        result = {
            'ProvinceName': {},
            'CityName': {},
            'ExpAreaName': {},
            'StreetName': {},
            'AreasInfo': data.get('AreasInfo', ''),
            'Address': data.get('Address', ''),
            'others': data.get('others', ''),
            'Mobile': data.get('Mobile', ''),
            'Name': data.get('Name', ''),
            'Success': True,
            'Reason': '解析成功',
            'ResultCode': '100',
            'Warning': []
        }
        
        warnings = []
        
        try:
            logger.info("START 开始进行数据库匹配修正处理")
            
            # ========== 第一阶段：地址数据匹配 ==========
            candidate_tables = self.stage1_matcher.execute_stage1_parallel(data)
            
            # 同步更新AreasInfo和Address（可能在stage1中被清除）
            result['AreasInfo'] = data.get('AreasInfo', '')
            result['Address'] = data.get('Address', '')
            
            # ========== 第一阶段完成后：将候选表转换为result格式，并对单候选值进行唯一值格式化 ==========
            self.stage2_resolver.convert_candidate_tables_to_result_format(candidate_tables, result)
            self.stage2_resolver.convert_single_candidate_to_unique(result)
            
            # ========== 第二阶段：候选结果处理 ==========
            self.stage2_resolver.execute_stage2_resolve(candidate_tables, result, warnings)
            
            # ========== 第三阶段：返回数据校验 ==========
            self.stage3_validator.execute_stage3_validate(result, warnings)
            
            # 记录耗时
            match_end_time = time.time()
            match_duration = match_end_time - match_start_time
            logger.info(f"数据库匹配修正耗时: {match_duration:.4f}秒 ({match_duration*1000:.2f}毫秒)")
            
            return result
            
        except Exception as e:
            logger.error(f"地址补全处理失败: {str(e)}", exc_info=True)
            result['Success'] = False
            result['Reason'] = f"地址补全处理失败: {str(e)}"
            result['ResultCode'] = '103'
            result['Warning'] = warnings if warnings else ['地址补全处理异常']
            return result
        finally:
            # 确保在方法结束时清除请求级别缓存，释放内存
            self.matcher.clear_request_cache()
    
    def complete_extract_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        补全ExtractResponse格式的响应数据
        
        注意：调用此方法前，数据应该已经过数据校验和清洗（在API路由层完成）
        
        Args:
            response: ExtractResponse格式的响应字典，包含Data字段（应该已经过数据校验和清洗）
        
        Returns:
            补全后的响应字典
        """
        if not response.get('Data'):
            return response
        
        original_data = response.get('Data', {})
        
        # 检查原始数据是否有地址信息
        address_fields = ['ProvinceName', 'CityName', 'ExpAreaName', 'StreetName']
        has_address_info = False
        for field in address_fields:
            field_value = original_data.get(field)
            if field_value:
                if isinstance(field_value, str) and field_value.strip():
                    has_address_info = True
                    break
                elif isinstance(field_value, dict) and field_value.get('region_name'):
                    has_address_info = True
                    break
        
        if original_data.get('Address') or original_data.get('AreasInfo'):
            has_address_info = True
        
        # 如果没有地址信息，直接返回
        if not has_address_info:
            return response
        
        # 补全Data字段中的地址信息
        completed_data = self.complete_address_info(original_data)
        
        # 在重新排序之前，先保存元数据字段（Warning、ResultCode、Success、Reason）
        # 因为reorder_data_fields只返回固定的9个字段，会丢失这些元数据
        saved_metadata = {
            'ResultCode': completed_data.get('ResultCode', '100'),
            'Success': completed_data.get('Success', True),
            'Reason': completed_data.get('Reason', '解析成功'),
            'Warning': completed_data.get('Warning', [])
        }
        
        # 重新排序Data字段，确保顺序正确
        completed_data = reorder_data_fields(completed_data)
        
        # 从保存的元数据中提取状态信息
        result_code = saved_metadata['ResultCode']
        success = saved_metadata['Success']
        reason = saved_metadata['Reason']
        warnings = saved_metadata['Warning']
        
        # 创建新的响应对象
        result = response.copy()
        result['Data'] = completed_data
        
        # 优先级检查：如果已经有101或102，不应该被103覆盖
        current_code = response.get('ResultCode', '100')
        if current_code in ['101', '102']:
            # 保持原有的高优先级状态码
            result['ResultCode'] = current_code
            result['Success'] = response.get('Success', False) if current_code == '101' else response.get('Success', False)
            result['Reason'] = response.get('Reason', reason)
            logger.info(f"保持高优先级状态码 {current_code}，不设置103")
        else:
            # 使用地址补全返回的状态码
            result['ResultCode'] = result_code
            result['Success'] = success
            result['Reason'] = reason
        
        # 设置警告信息
        result['Warning'] = warnings
        
        return result

