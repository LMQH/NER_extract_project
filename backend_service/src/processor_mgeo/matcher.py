"""
双向模糊匹配方法模块
提供区域匹配的核心方法，包括黑名单过滤、最小长度检查、匹配质量评分等
"""
import logging
from typing import Dict, Any, Optional, List, Union
from src.config.constants import (
    GENERIC_TERMS_BLACKLIST,
    MIN_MATCH_LENGTH,
    MATCH_SCORE_WEIGHTS
)

logger = logging.getLogger("NER_API")


class RegionMatcher:
    """区域匹配器，提供双向模糊匹配功能"""
    
    def __init__(self, db_connection, region_cache, table_name: str, region_type_map: Dict[str, int]):
        """
        初始化区域匹配器
        
        Args:
            db_connection: 数据库连接对象
            region_cache: 区域缓存对象
            table_name: 数据库表名
            region_type_map: 区域类型映射字典
        """
        self.db = db_connection
        self.region_cache = region_cache
        self.table_name = table_name
        self.region_type_map = region_type_map
        
        # 请求级别内存缓存（每个请求开始时清除）
        self._request_cache = {}  # {region_type: regions} - 缓存按region_type查询的结果
        self._id_cache = {}  # {region_id: region} - 缓存按id查询的结果
        self._parent_child_cache = {}  # {(parent_id, region_type): regions} - 缓存按parent_id查询的结果
    
    def should_skip_region(self, region_name: str) -> bool:
        """
        判断是否应该跳过某个区域记录，防止长度过小或者是无意义名词
        
        Args:
            region_name: 区域名称
        
        Returns:
            True表示应该跳过，False表示可以匹配
        """
        if not region_name or not region_name.strip():
            return True
        
        region_name = region_name.strip()
        
        # 检查最小长度限制
        if len(region_name) < MIN_MATCH_LENGTH:
            return True
        
        # 检查黑名单
        if region_name in GENERIC_TERMS_BLACKLIST:
            logger.debug(f"跳过通用词黑名单: {region_name}")
            return True
        
        return False
    
    def calculate_match_score(
        self, 
        field_value: str, 
        region_name: str, 
        match_type: str
    ) -> float:
        """
        计算匹配质量得分
        
        Args:
            field_value: 查询字段值
            region_name: 数据库区域名称
            match_type: 匹配类型 ('exact', 'forward', 'backward')
        
        Returns:
            匹配得分（0-1之间）
        """
        # 精确匹配得满分
        if match_type == 'exact':
            return MATCH_SCORE_WEIGHTS['exact_match']
        
        # 长度相似度得分（0-0.3）
        len_diff = abs(len(field_value) - len(region_name))
        max_len = max(len(field_value), len(region_name))
        length_score = MATCH_SCORE_WEIGHTS['length_similarity'] * (1 - len_diff / max_len) if max_len > 0 else 0
        
        # 匹配类型基础得分
        if match_type == 'forward':
            type_score = MATCH_SCORE_WEIGHTS['forward_match']
            coverage = len(field_value) / len(region_name) if len(region_name) > 0 else 0
        else:  # backward
            type_score = MATCH_SCORE_WEIGHTS['backward_match']
            coverage = len(region_name) / len(field_value) if len(field_value) > 0 else 0
        
        # 覆盖率得分（0-0.2）
        coverage_score = MATCH_SCORE_WEIGHTS['coverage'] * coverage
        
        return type_score + length_score + coverage_score
    
    def get_regions_by_type(self, region_type: int) -> List[Dict[str, Any]]:
        """
        获取指定region_type的所有区域记录（带缓存）
        
        缓存优先级：
        1. 请求级别内存缓存（最快）
        2. Redis缓存
        3. 数据库查询
        
        Args:
            region_type: 区域类型（1001, 1002, 1003, 1004）
        
        Returns:
            区域记录列表，每个记录包含id, parent_id, region_name, region_type
        """
        # 1. 先检查请求级别内存缓存（最快）
        if region_type in self._request_cache:
            logger.debug(f"从请求级别缓存获取region_type={region_type}的记录，共{len(self._request_cache[region_type])}条")
            return self._request_cache[region_type]
        
        # 2. 再尝试从Redis缓存获取
        cached_regions = self.region_cache.get_cached_regions(region_type)
        if cached_regions is not None:
            # 存入请求级别缓存，下次直接从内存获取
            self._request_cache[region_type] = cached_regions
            return cached_regions
        
        # 3. 缓存未命中，从数据库查询
        try:
            sql = f"""
                SELECT id, parent_id, region_name, region_type
                FROM {self.table_name}
                WHERE region_type = %s AND is_deleted = 0
            """
            regions = self.db.execute_query(sql, (region_type,))
            
            # 缓存查询结果（Redis和请求级别缓存）
            if regions:
                self.region_cache.cache_regions(region_type, regions)
                self._request_cache[region_type] = regions
            
            return regions
        except Exception as e:
            logger.error(f"查询region_type={region_type}的区域记录失败: {str(e)}")
            return []
    
    def match_region_by_field(
        self, 
        region_type: int, 
        field_value: str, 
        field_name: str
    ) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        """
        可复用的双向LIKE匹配函数
        
        匹配策略：
        1. 对于AreasInfo和Address字段，直接使用LIKE匹配（跳过精确匹配）
        2. 对于其他字段，先精确匹配（region_name = field_value）
        3. 失败则双向模糊匹配（region_name LIKE %field_value% OR field_value LIKE %region_name%）
        4. 返回唯一结果（Dict）、候选列表（List[Dict]）或None
        
        Args:
            region_type: 区域类型（1001, 1002, 1003, 1004）
            field_value: 字段值（StreetName, AreasInfo, Address, ExpAreaName, CityName, ProvinceName）
            field_name: 字段名称（用于日志）
        
        Returns:
            - 唯一结果：Dict[str, Any]（包含id, parent_id, region_name, region_type）
            - 多个结果：List[Dict[str, Any]]
            - 无结果：None
        """
        if not field_value or not field_value.strip():
            logger.debug(f"{field_name}匹配跳过: field_value为空或仅包含空白字符")
            return None
        
        field_value = field_value.strip()
        
        # 判断是否跳过精确匹配，直接使用LIKE匹配
        # AreasInfo和Address字段应该直接使用LIKE匹配
        skip_exact_match = 'AreasInfo' in field_name or 'Address' in field_name
        
        logger.debug(f"{field_name}开始匹配: field_value='{field_value}', region_type={region_type}, skip_exact_match={skip_exact_match}")
        
        try:
            # 获取该region_type的所有记录（带缓存）
            all_regions = self.get_regions_by_type(region_type)
            
            if not all_regions:
                logger.debug(f"{field_name}匹配失败: region_type={region_type}没有记录")
                return None
            
            logger.debug(f"{field_name}获取到{len(all_regions)}条region_type={region_type}的记录")
            
            # 策略1：精确匹配（对于AreasInfo和Address字段跳过）
            if not skip_exact_match:
                logger.debug(f"{field_name}开始精确匹配: field_value='{field_value}'")
                exact_matches = [
                    r for r in all_regions
                    if r.get('region_name', '').strip() == field_value
                ]
                
                if len(exact_matches) == 1:
                    logger.debug(f"{field_name}精确匹配成功: {exact_matches[0].get('region_name')} (查询: {field_value})")
                    return exact_matches[0]
                elif len(exact_matches) > 1:
                    logger.debug(f"{field_name}精确匹配找到{len(exact_matches)}条记录，返回候选表")
                    return exact_matches
                else:
                    logger.debug(f"{field_name}精确匹配未找到: field_value='{field_value}'")
            
            # 策略2：双向模糊匹配（LIKE匹配）
            # 正向匹配：region_name LIKE %field_value%
            # 反向匹配：field_value LIKE %region_name%
            logger.debug(f"{field_name}开始双向模糊匹配: field_value='{field_value}', region_type={region_type}, 总记录数={len(all_regions)}")
            fuzzy_matches = []
            for region in all_regions:
                region_name = region.get('region_name', '').strip()
                field_value = field_value.strip()
                
                # 过滤检查
                if self.should_skip_region(region_name):
                    logger.debug(f"{field_name}跳过region: '{region_name}' (通过should_skip_region检查)")
                    continue
                
                # 判断匹配类型并计算得分
                match_type = None
                score = 0.0
                
                if field_value == region_name:
                    # 精确匹配
                    match_type = 'exact'
                    score = self.calculate_match_score(field_value, region_name, 'exact')
                    logger.debug(f"{field_name}发现精确匹配: region_name='{region_name}', score={score:.3f}")
                elif field_value in region_name:
                    # 正向匹配
                    match_type = 'forward'
                    score = self.calculate_match_score(field_value, region_name, 'forward')
                    logger.debug(f"{field_name}发现正向匹配: field_value='{field_value}' in region_name='{region_name}', score={score:.3f}")
                elif region_name in field_value:
                    # 反向匹配（需要额外验证）
                    # 只有当region_name足够长且不在黑名单中时才接受
                    logger.debug(f"{field_name}发现反向匹配候选: region_name='{region_name}' in field_value='{field_value}'")
                    if len(region_name) >= MIN_MATCH_LENGTH and region_name not in GENERIC_TERMS_BLACKLIST:
                        match_type = 'backward'
                        score = self.calculate_match_score(field_value, region_name, 'backward')
                        logger.debug(f"{field_name}反向匹配通过验证: region_name='{region_name}', len={len(region_name)}, score={score:.3f}")
                    else:
                        logger.debug(f"{field_name}反向匹配被跳过: region_name='{region_name}', len={len(region_name)}, in_blacklist={region_name in GENERIC_TERMS_BLACKLIST}")
                        continue  # 跳过过短或黑名单词
                
                if match_type and score > 0:
                    fuzzy_matches.append({
                        'region': region,
                        'match_type': match_type,
                        'score': score
                    })
            
            # 按得分排序
            logger.debug(f"{field_name}双向模糊匹配完成: 找到{len(fuzzy_matches)}个匹配结果")
            if len(fuzzy_matches) == 0:
                logger.debug(f"{field_name}双向模糊匹配未找到任何匹配: field_value='{field_value}', region_type={region_type}")
                return None
            elif len(fuzzy_matches) == 1:
                match_type_str = "LIKE匹配" if skip_exact_match else "双向模糊匹配"
                logger.debug(f"{field_name}{match_type_str}成功: {fuzzy_matches[0]['region'].get('region_name')} (查询: {field_value}, 得分: {fuzzy_matches[0]['score']:.3f})")
                return fuzzy_matches[0]['region']
            else:
                # 多个匹配结果，按得分排序
                fuzzy_matches.sort(key=lambda x: x['score'], reverse=True)
                
                # 如果最高分明显高于次高分（差距>0.2），返回唯一结果
                if fuzzy_matches[0]['score'] - fuzzy_matches[1]['score'] > 0.2:
                    match_type_str = "LIKE匹配" if skip_exact_match else "双向模糊匹配"
                    logger.debug(f"{field_name}{match_type_str}成功: {fuzzy_matches[0]['region'].get('region_name')} (查询: {field_value}, 得分: {fuzzy_matches[0]['score']:.3f})")
                    return fuzzy_matches[0]['region']
                else:
                    # 返回得分相近的候选列表
                    candidates = [m['region'] for m in fuzzy_matches]
                    match_type_str = "LIKE匹配" if skip_exact_match else "双向模糊匹配"
                    logger.debug(f"{field_name}{match_type_str}找到{len(candidates)}条记录，返回候选表")
                    return candidates
                    
        except Exception as e:
            logger.error(f"{field_name}匹配失败: {str(e)}, field_value={field_value}, region_type={region_type}")
            return None
    
    def _try_match_province_without_special_region(
        self,
        region_type: int,
        field_value: str,
        field_name: str
    ) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        """
        尝试去掉"特别行政区"后缀后再次匹配
        
        当ProvinceName匹配失败时，检查是否为"名称"+"特别行政区"格式，
        如果是则去掉"特别行政区"后缀再匹配一次
        
        Args:
            region_type: 区域类型（1001）
            field_value: ProvinceName值（如"香港特别行政区"）
            field_name: 字段名称（用于日志）
        
        Returns:
            - 唯一结果：Dict[str, Any]
            - 多个结果：List[Dict[str, Any]]
            - 无结果：None
        """
        if not field_value or not field_value.strip():
            return None
        
        field_value = field_value.strip()
        
        # 检查是否为"名称"+"特别行政区"格式
        if field_value.endswith("特别行政区"):
            # 去掉"特别行政区"后缀
            province_name_without_suffix = field_value[:-5]  # 去掉"特别行政区"（5个字符）
            
            if province_name_without_suffix:
                logger.debug(f"{field_name}匹配失败，尝试去掉'特别行政区'后缀再匹配: '{field_value}' -> '{province_name_without_suffix}'")
                # 使用去掉后缀的名称再次匹配
                return self.match_region_by_field(region_type, province_name_without_suffix, field_name)
        
        return None
    
    def find_region_by_id(self, region_id: int) -> Optional[Dict[str, Any]]:
        """
        根据区域ID查找区域信息（带缓存）
        
        缓存优先级：
        1. 请求级别ID缓存（最快）
        2. 从已加载的请求级别region_type数据中查找
        3. 数据库查询
        
        Args:
            region_id: 区域ID
        
        Returns:
            区域信息字典
        """
        if not region_id:
            return None
        
        # 1. 先检查请求级别ID缓存
        if region_id in self._id_cache:
            logger.debug(f"从请求级别ID缓存获取region_id={region_id}的记录")
            return self._id_cache[region_id]
        
        # 2. 从已加载的请求级别region_type数据中查找（遍历所有已加载的region_type）
        for regions in self._request_cache.values():
            for region in regions:
                if region.get('id') == region_id:
                    # 存入ID缓存
                    self._id_cache[region_id] = region
                    logger.debug(f"从已加载数据中找到region_id={region_id}的记录")
                    return region
        
        # 3. 缓存未命中，从数据库查询
        try:
            sql = f"""
                SELECT id, parent_id, region_name, region_type
                FROM {self.table_name}
                WHERE id = %s AND is_deleted = 0
                LIMIT 1
            """
            result = self.db.execute_one(sql, (region_id,))
            if result:
                # 存入ID缓存
                self._id_cache[region_id] = result
                # 如果该region_type的数据已加载，也更新到_request_cache中
                region_type = result.get('region_type')
                if region_type and region_type in self._request_cache:
                    # 检查是否已存在，如果不存在则添加
                    existing_ids = {r.get('id') for r in self._request_cache[region_type]}
                    if region_id not in existing_ids:
                        self._request_cache[region_type].append(result)
            return result
        except Exception as e:
            logger.error(f"根据region_id查找区域信息失败: {str(e)}, region_id={region_id}")
            return None
    
    def clear_request_cache(self):
        """
        清除请求级别的内存缓存
        
        应该在每个请求开始时调用，确保不同请求之间的数据隔离
        """
        self._request_cache.clear()
        self._id_cache.clear()
        self._parent_child_cache.clear()
        logger.debug("已清除请求级别内存缓存")
    
    def get_child_regions_by_parent_id(self, parent_id: int, region_type: int) -> List[Dict[str, Any]]:
        """
        根据parent_id和region_type获取所有子区域记录（带缓存）
        
        缓存优先级：
        1. 请求级别parent_child缓存（最快）
        2. 从已加载的对应region_type数据中过滤
        3. 数据库查询
        
        Args:
            parent_id: 父级区域ID
            region_type: 子区域类型（1001, 1002, 1003, 1004）
        
        Returns:
            子区域记录列表，每个记录包含id, parent_id, region_name, region_type
        """
        if parent_id is None:
            return []
        
        cache_key = (parent_id, region_type)
        
        # 1. 先检查请求级别parent_child缓存
        if cache_key in self._parent_child_cache:
            logger.debug(f"从请求级别parent_child缓存获取parent_id={parent_id}, region_type={region_type}的记录，共{len(self._parent_child_cache[cache_key])}条")
            return self._parent_child_cache[cache_key]
        
        # 2. 从已加载的对应region_type数据中过滤
        if region_type in self._request_cache:
            filtered_regions = [
                r for r in self._request_cache[region_type]
                if r.get('parent_id') == parent_id
            ]
            if filtered_regions:
                # 存入parent_child缓存
                self._parent_child_cache[cache_key] = filtered_regions
                logger.debug(f"从已加载数据中过滤出parent_id={parent_id}, region_type={region_type}的记录，共{len(filtered_regions)}条")
                return filtered_regions
        
        # 3. 缓存未命中，从数据库查询
        try:
            sql = f"""
                SELECT id, parent_id, region_name, region_type
                FROM {self.table_name}
                WHERE region_type = %s AND parent_id = %s AND is_deleted = 0
            """
            regions = self.db.execute_query(sql, (region_type, parent_id))
            if regions:
                # 存入parent_child缓存
                self._parent_child_cache[cache_key] = regions
                # 如果该region_type的数据已加载，确保这些记录也在_request_cache中
                if region_type in self._request_cache:
                    # 检查并添加缺失的记录
                    existing_ids = {r.get('id') for r in self._request_cache[region_type]}
                    for region in regions:
                        if region.get('id') not in existing_ids:
                            self._request_cache[region_type].append(region)
            return regions if regions else []
        except Exception as e:
            logger.error(f"查询parent_id={parent_id}, region_type={region_type}的子区域记录失败: {str(e)}")
            return []

