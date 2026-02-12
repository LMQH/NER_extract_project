"""
Redis缓存模块
用于缓存region_type粗筛选结果，提高查询性能
"""
import os
import json
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("NER_API")

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis库未安装，缓存功能将不可用。请安装: pip install redis")


class RegionCache:
    """区域数据Redis缓存管理器"""
    
    # 定义需要缓存的关键字段
    CACHE_FIELDS = {'id', 'parent_id', 'region_name', 'region_type'}
    
    def __init__(self):
        """初始化Redis缓存管理器"""
        self.redis_client = None
        self.enabled = False
        
        if not REDIS_AVAILABLE:
            logger.warning("Redis库未安装，缓存功能已禁用")
            return
        
        try:
            # 从环境变量获取Redis配置
            redis_host = os.getenv('REDIS_HOST', 'localhost')
            redis_port = int(os.getenv('REDIS_PORT', '6379'))
            redis_db = int(os.getenv('REDIS_DB', '0'))
            redis_password = os.getenv('REDIS_PASSWORD', None)
            self.cache_ttl = int(os.getenv('REDIS_CACHE_TTL', '3600'))  # 默认1小时
            
            # 从环境变量获取超时配置（单位：秒，默认3秒）
            redis_connect_timeout = int(os.getenv('REDIS_CONNECT_TIMEOUT', '3'))
            redis_socket_timeout = int(os.getenv('REDIS_SOCKET_TIMEOUT', '3'))
            
            # 创建Redis连接
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=False,  # 返回bytes，需要手动解码
                socket_connect_timeout=redis_connect_timeout,
                socket_timeout=redis_socket_timeout
            )
            
            # 测试连接
            self.redis_client.ping()
            self.enabled = True
            logger.debug(f"Redis缓存已启用 - {redis_host}:{redis_port}/{redis_db}")
        except Exception as e:
            logger.warning(f"Redis连接失败，缓存功能已禁用: {str(e)}")
            self.enabled = False
            self.redis_client = None
    
    def _filter_region_fields(self, region: Dict[str, Any]) -> Dict[str, Any]:
        """
        过滤区域记录，只保留关键字段
        
        Args:
            region: 区域记录字典（可能包含多个字段）
            
        Returns:
            只包含关键字段的字典：id, parent_id, region_name, region_type
        """
        return {key: value for key, value in region.items() if key in self.CACHE_FIELDS}
    
    def _filter_regions_list(self, regions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        过滤区域记录列表，只保留关键字段
        
        Args:
            regions: 区域记录列表（每个记录可能包含多个字段）
            
        Returns:
            只包含关键字段的记录列表
        """
        return [self._filter_region_fields(region) for region in regions]
    
    def _get_cache_key(self, region_type: int) -> str:
        """
        生成缓存键
        
        Args:
            region_type: 区域类型
            
        Returns:
            缓存键字符串
        """
        return f"region:type:{region_type}"
    
    def get_cached_regions(self, region_type: int) -> Optional[List[Dict[str, Any]]]:
        """
        从缓存获取指定region_type的所有区域记录
        
        Args:
            region_type: 区域类型（1001, 1002, 1003, 1004）
            
        Returns:
            区域记录列表，如果缓存不存在或Redis不可用则返回None
        """
        if not self.enabled or not self.redis_client:
            return None
        
        try:
            cache_key = self._get_cache_key(region_type)
            cached_data = self.redis_client.get(cache_key)
            
            if cached_data is None:
                return None
            
            # 反序列化JSON数据
            regions = json.loads(cached_data.decode('utf-8'))
            logger.debug(f"从缓存获取region_type={region_type}的记录，共{len(regions)}条")
            return regions
        except Exception as e:
            logger.warning(f"从Redis缓存读取失败: {str(e)}")
            return None
    
    def get_cached_regions_batch(self, region_types: List[int]) -> Dict[int, List[Dict[str, Any]]]:
        """
        批量从缓存获取多个region_type的所有区域记录（使用Pipeline批量查询）
        
        使用Redis Pipeline减少网络往返次数，提高批量查询性能
        
        Args:
            region_types: 区域类型列表（如[1001, 1002, 1003, 1004]）
            
        Returns:
            字典，键为region_type，值为区域记录列表
            如果某个region_type的缓存不存在，则不会包含在返回字典中
        """
        if not self.enabled or not self.redis_client:
            return {}
        
        if not region_types:
            return {}
        
        try:
            # 使用Pipeline批量查询
            pipe = self.redis_client.pipeline()
            cache_keys = []
            for region_type in region_types:
                cache_key = self._get_cache_key(region_type)
                cache_keys.append((region_type, cache_key))
                pipe.get(cache_key)
            
            # 一次性执行所有GET操作
            results = pipe.execute()
            
            # 解析结果
            cached_data = {}
            for i, (region_type, cache_key) in enumerate(cache_keys):
                if results[i] is not None:
                    try:
                        regions = json.loads(results[i].decode('utf-8'))
                        cached_data[region_type] = regions
                        logger.debug(f"批量查询：从缓存获取region_type={region_type}的记录，共{len(regions)}条")
                    except Exception as e:
                        logger.warning(f"批量查询：解析region_type={region_type}的缓存数据失败: {str(e)}")
            
            if cached_data:
                logger.debug(f"批量查询完成：成功获取{len(cached_data)}个region_type的缓存数据")
            
            return cached_data
        except Exception as e:
            logger.warning(f"批量从Redis缓存读取失败: {str(e)}")
            return {}
    
    def cache_regions(self, region_type: int, regions: List[Dict[str, Any]]) -> bool:
        """
        将区域记录列表缓存到Redis（只缓存关键字段）
        
        优化：直接使用setex，Redis会自动覆盖已存在的key，减少一次exists查询
        
        Args:
            region_type: 区域类型（1001, 1002, 1003, 1004）
            regions: 区域记录列表，每个记录可能包含多个字段，但只会缓存关键字段
        
        Returns:
            是否缓存成功
        """
        if not self.enabled or not self.redis_client:
            return False
        
        if not regions:
            return False
        
        try:
            cache_key = self._get_cache_key(region_type)
            
            # 过滤字段，只保留关键字段：id, parent_id, region_name, region_type
            filtered_regions = self._filter_regions_list(regions)
            
            # 序列化为JSON
            json_data = json.dumps(filtered_regions, ensure_ascii=False)
            
            # 直接存储到Redis，设置TTL（Redis会自动覆盖已存在的key）
            self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                json_data.encode('utf-8')
            )
            logger.debug(f"已缓存region_type={region_type}的记录到Redis，共{len(filtered_regions)}条，TTL={self.cache_ttl}秒（仅缓存关键字段）")
            return True
        except Exception as e:
            logger.warning(f"写入Redis缓存失败: {str(e)}")
            return False
    
    def clear_cache(self, region_type: Optional[int] = None) -> bool:
        """
        清除缓存
        
        Args:
            region_type: 区域类型，如果为None则清除所有region_type缓存
            
        Returns:
            是否清除成功
        """
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            if region_type is not None:
                # 清除指定region_type的缓存
                cache_key = self._get_cache_key(region_type)
                self.redis_client.delete(cache_key)
                logger.info(f"已清除region_type={region_type}的缓存")
            else:
                # 清除所有region_type缓存
                for rt in [1001, 1002, 1003, 1004]:
                    cache_key = self._get_cache_key(rt)
                    self.redis_client.delete(cache_key)
                logger.info("已清除所有region_type缓存")
            return True
        except Exception as e:
            logger.warning(f"清除Redis缓存失败: {str(e)}")
            return False

