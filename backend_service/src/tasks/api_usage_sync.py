"""
API使用统计同步任务
定时任务：扫描昨天的Redis Key，写入MySQL，删除Redis Key
"""
import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import redis

from src.database.statistics_db_connection import StatisticsDatabaseConnection
from src.database.api_usage_counter import ApiUsageCounter

logger = logging.getLogger("NER_API")


class ApiUsageSyncTask:
    """API使用统计同步任务"""
    
    def __init__(
        self,
        db_connection: Optional[StatisticsDatabaseConnection] = None,
        redis_client: Optional[redis.Redis] = None,
        sync_interval: int = None,
        day_offset: int = None
    ):
        """
        初始化同步任务
        
        Args:
            db_connection: 统计数据库连接对象
            redis_client: Redis客户端对象（如果为None则创建新的ApiUsageCounter）
            sync_interval: 同步间隔（秒），如果为None则从环境变量读取
            day_offset: 同步日期偏移（默认1，即同步昨天的数据）
        """
        self.db_connection = db_connection or StatisticsDatabaseConnection()
        self.sync_interval = sync_interval or int(os.getenv('API_USAGE_SYNC_INTERVAL', '3600'))
        self.day_offset = day_offset or int(os.getenv('API_USAGE_SYNC_DAY_OFFSET', '1'))
        self.table_name = os.getenv('MYSQL_API_USAGE_TABLE', 'extract_api_usage')
        
        # 获取Redis客户端
        if redis_client:
            self.redis_client = redis_client
        else:
            # 创建ApiUsageCounter以获取Redis连接
            counter = ApiUsageCounter()
            self.redis_client = counter.redis_client if counter.enabled else None
        
        self.enabled = self.redis_client is not None
        self._running = False
    
    def _get_lock_key(self, date: datetime) -> str:
        """
        获取分布式锁Key
        
        Args:
            date: 日期
            
        Returns:
            Redis Key字符串，格式：lock:api_usage_daily:{yyyyMMdd}
        """
        date_str = date.strftime('%Y%m%d')
        return f"lock:api_usage_daily:{date_str}"
    
    def _acquire_lock(self, lock_key: str, timeout: int = 300) -> bool:
        """
        获取分布式锁
        
        Args:
            lock_key: 锁的Key
            timeout: 锁的超时时间（秒），默认300秒（5分钟）
            
        Returns:
            bool: 是否成功获取锁
        """
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            # 使用SET NX EX实现分布式锁
            result = self.redis_client.set(lock_key, "locked", nx=True, ex=timeout)
            return result is True
        except Exception as e:
            logger.error(f"获取分布式锁失败 {lock_key}: {str(e)}")
            return False
    
    def _release_lock(self, lock_key: str) -> bool:
        """
        释放分布式锁
        
        Args:
            lock_key: 锁的Key
            
        Returns:
            bool: 是否成功释放锁
        """
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            self.redis_client.delete(lock_key)
            return True
        except Exception as e:
            logger.warning(f"释放分布式锁失败 {lock_key}: {str(e)}")
            return False
    
    def _get_count_keys_for_date(self, date: datetime) -> List[str]:
        """
        获取指定日期的所有计数Key

        Args:
            date: 日期

        Returns:
            Key列表，格式：api:count:*:{yyyyMMdd} 或 api:count:success:*:{yyyyMMdd}
        """
        if not self.enabled or not self.redis_client:
            return []

        try:
            date_str = date.strftime('%Y%m%d')
            # 同时扫描总计数和成功计数的Key
            pattern1 = f"api:count:*:{date_str}"
            pattern2 = f"api:count:success:*:{date_str}"
            keys = list(self.redis_client.scan_iter(match=pattern1)) + list(self.redis_client.scan_iter(match=pattern2))
            return [key.decode('utf-8') if isinstance(key, bytes) else key for key in keys]
        except Exception as e:
            logger.error(f"获取计数Key失败: {str(e)}")
            return []
    
    def _extract_api_name_from_key(self, key: str) -> tuple[Optional[str], bool]:
        """
        从Key中提取API名称和是否为成功计数

        Args:
            key: Redis Key，格式：
                - api:count:{api_name}:{yyyyMMdd} (总计数)
                - api:count:success:{api_name}:{yyyyMMdd} (成功计数)

        Returns:
            (API名称, 是否成功计数)，如果格式不正确则返回 (None, False)
        """
        try:
            parts = key.split(':')
            if len(parts) >= 4 and parts[0] == 'api' and parts[1] == 'count':
                # 检查是否为成功计数Key
                is_success = len(parts) >= 5 and parts[2] == 'success'
                if is_success:
                    # api:count:success:{api_name}:{yyyyMMdd}
                    api_name = ':'.join(parts[3:-1])
                else:
                    # api:count:{api_name}:{yyyyMMdd}
                    api_name = ':'.join(parts[2:-1])
                return api_name, is_success
            return None, False
        except Exception:
            return None, False
    
    def _sync_date_data(self, date: datetime) -> bool:
        """
        同步指定日期的数据
        
        Args:
            date: 要同步的日期
            
        Returns:
            bool: 是否同步成功
        """
        lock_key = self._get_lock_key(date)
        
        # 尝试获取分布式锁
        if not self._acquire_lock(lock_key):
            logger.info(f"获取分布式锁失败，可能其他实例正在同步 {date.strftime('%Y%m%d')} 的数据")
            return False
        
        try:
            # 获取该日期的所有计数Key
            count_keys = self._get_count_keys_for_date(date)
            if not count_keys:
                logger.info(f"日期 {date.strftime('%Y%m%d')} 没有需要同步的数据")
                return True
            
            logger.info(f"开始同步日期 {date.strftime('%Y%m%d')} 的数据，共 {len(count_keys)} 个Key")
            
            # 批量获取计数
            sync_data = []  # [(api_name, count, date, is_success), ...]

            for key in count_keys:
                try:
                    count_str = self.redis_client.get(key)
                    if count_str is None:
                        continue

                    count = int(count_str)
                    api_name, is_success = self._extract_api_name_from_key(key)

                    if api_name:
                        sync_data.append((api_name, count, date, is_success))
                        count_type = "成功计数" if is_success else "总计数"
                        logger.debug(f"准备同步: api_name={api_name}, count_type={count_type}, count={count}, date={date.strftime('%Y%m%d')}")
                except Exception as e:
                    logger.warning(f"处理Key {key} 失败: {str(e)}")
                    continue

            if not sync_data:
                logger.info(f"日期 {date.strftime('%Y%m%d')} 没有有效数据需要同步")
                return True

            # 批量执行UPSERT（幂等操作）
            # 支持总计数和成功计数
            upsert_sql = f"""
            INSERT INTO `{self.table_name}` (stat_date, api_name, call_count, success_count)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                call_count = call_count + VALUES(call_count),
                success_count = success_count + VALUES(success_count)
            """

            with self.db_connection.get_cursor() as cursor:
                for api_name, count, sync_date, is_success in sync_data:
                    try:
                        if is_success:
                            # 成功计数
                            cursor.execute(upsert_sql, (sync_date.date(), api_name, 0, count))
                            logger.debug(f"同步成功计数: api_name={api_name}, success_count={count}, date={sync_date.strftime('%Y%m%d')}")
                        else:
                            # 总计数
                            cursor.execute(upsert_sql, (sync_date.date(), api_name, count, 0))
                            logger.debug(f"同步总计数: api_name={api_name}, call_count={count}, date={sync_date.strftime('%Y%m%d')}")
                    except Exception as e:
                        logger.error(f"同步失败: api_name={api_name}, count={count}, is_success={is_success}, date={sync_date.strftime('%Y%m%d')}, error={str(e)}")
                        continue
            
            # 删除已同步的Redis Key
            deleted_count = 0
            for key in count_keys:
                try:
                    if self.redis_client.delete(key):
                        deleted_count += 1
                except Exception as e:
                    logger.warning(f"删除Key {key} 失败: {str(e)}")
            
            logger.info(f"同步完成: 日期 {date.strftime('%Y%m%d')}, 同步 {len(sync_data)} 条记录, 删除 {deleted_count} 个Key")
            return True
            
        except Exception as e:
            logger.error(f"同步日期 {date.strftime('%Y%m%d')} 的数据失败: {str(e)}")
            return False
        finally:
            # 释放分布式锁
            self._release_lock(lock_key)
    
    def sync_yesterday(self) -> bool:
        """
        同步昨天的数据
        
        Returns:
            bool: 是否同步成功
        """
        yesterday = datetime.now() - timedelta(days=self.day_offset)
        return self._sync_date_data(yesterday)
    
    async def run_periodic(self):
        """
        周期性运行同步任务（异步）
        """
        if not self.enabled:
            logger.warning("API使用统计同步任务已禁用（Redis不可用）")
            return
        
        self._running = True
        logger.debug(f"API使用统计同步任务已启动，同步间隔: {self.sync_interval}秒")
        
        while self._running:
            try:
                # 同步昨天的数据
                self.sync_yesterday()
            except Exception as e:
                logger.error(f"同步任务执行失败: {str(e)}")
            
            # 等待指定间隔
            await asyncio.sleep(self.sync_interval)
    
    def stop(self):
        """停止同步任务"""
        self._running = False
        logger.info("API使用统计同步任务已停止")

