"""
API使用频次统计Redis计数器模块
用于实时统计API调用次数
"""
import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("NER_API")

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis库未安装，API使用统计功能将不可用。请安装: pip install redis")


class ApiUsageCounter:
    """API使用频次统计Redis计数器"""
    
    def __init__(self):
        """初始化API使用统计Redis计数器"""
        self.redis_client = None
        self.enabled = False
        
        if not REDIS_AVAILABLE:
            logger.warning("Redis库未安装，API使用统计功能已禁用")
            return
        
        try:
            # 从环境变量获取Redis配置
            redis_host = os.getenv('REDIS_HOST', 'localhost')
            redis_port = int(os.getenv('REDIS_PORT', '6379'))
            redis_db = int(os.getenv('REDIS_DB', '0'))
            redis_password = os.getenv('REDIS_PASSWORD', None)
            
            # 从环境变量获取超时配置（单位：秒，默认3秒）
            redis_connect_timeout = int(os.getenv('REDIS_CONNECT_TIMEOUT', '3'))
            redis_socket_timeout = int(os.getenv('REDIS_SOCKET_TIMEOUT', '3'))
            
            # 创建Redis连接
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True,  # 返回字符串，便于处理
                socket_connect_timeout=redis_connect_timeout,
                socket_timeout=redis_socket_timeout
            )
            
            # 测试连接
            self.redis_client.ping()
            self.enabled = True
            logger.info(f"API使用统计Redis计数器已启用 - Host: {redis_host}:{redis_port}, DB: {redis_db}")
        except Exception as e:
            logger.warning(f"API使用统计Redis连接失败，功能已禁用: {str(e)}")
            self.enabled = False
            self.redis_client = None
    
    def _get_count_key(self, api_name: str, date: datetime = None, success: bool = None) -> str:
        """
        生成计数Key

        Args:
            api_name: API名称
            date: 日期，如果为None则使用当前日期
            success: 是否成功，如果为True则生成成功计数Key，如果为False或不指定则生成总计数Key

        Returns:
            Redis Key字符串，格式：
            - api:count:{api_name}:{yyyyMMdd} (总计数)
            - api:count:success:{api_name}:{yyyyMMdd} (成功计数)
        """
        if date is None:
            date = datetime.now()
        date_str = date.strftime('%Y%m%d')
        if success is True:
            return f"api:count:success:{api_name}:{date_str}"
        return f"api:count:{api_name}:{date_str}"
    
    def increment_api_count(self, api_name: str, success: bool = None) -> bool:
        """
        增加API调用计数

        Args:
            api_name: API名称，例如 "/api/extract"
            success: 是否成功，True时增加成功计数，False或不指定时增加总计数

        Returns:
            bool: 是否成功增加计数
        """
        if not self.enabled or not self.redis_client:
            return False

        try:
            count_key = self._get_count_key(api_name, success=success)
            # 使用INCR命令，如果key不存在则创建并设置为1
            count = self.redis_client.incr(count_key)
            count_type = "成功计数" if success else "总计数"
            logger.info(f"API{count_type}增加: {api_name}, Key: {count_key}, 当前计数: {count}")
            return True
        except Exception as e:
            logger.warning(f"增加API计数失败 {api_name}: {str(e)}")
            return False
    
    def get_api_count(self, api_name: str, date: datetime = None, success: bool = None) -> Optional[int]:
        """
        获取API调用计数

        Args:
            api_name: API名称
            date: 日期，如果为None则使用当前日期
            success: 是否获取成功计数，True时获取成功计数，False或不指定时获取总计数

        Returns:
            调用次数，如果key不存在或Redis不可用则返回None
        """
        if not self.enabled or not self.redis_client:
            return None

        try:
            count_key = self._get_count_key(api_name, date, success)
            count_str = self.redis_client.get(count_key)
            if count_str is None:
                return None
            return int(count_str)
        except Exception as e:
            logger.warning(f"获取API计数失败 {api_name}: {str(e)}")
            return None
    
    def delete_count_key(self, api_name: str, date: datetime = None, success: bool = None) -> bool:
        """
        删除计数Key

        Args:
            api_name: API名称
            date: 日期，如果为None则使用当前日期
            success: 是否删除成功计数Key，True时删除成功计数Key，False或不指定时删除总计数Key

        Returns:
            bool: 是否成功删除
        """
        if not self.enabled or not self.redis_client:
            return False

        try:
            count_key = self._get_count_key(api_name, date, success)
            deleted = self.redis_client.delete(count_key)
            logger.debug(f"删除API计数Key: {count_key}, 删除结果: {deleted > 0}")
            return deleted > 0
        except Exception as e:
            logger.warning(f"删除API计数Key失败 {api_name}: {str(e)}")
            return False

