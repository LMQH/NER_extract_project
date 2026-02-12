"""
统计功能MySQL数据库连接模块
用于API使用统计和错误日志的独立数据库连接
"""
import os
import logging
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger("NER_API")


class StatisticsDatabaseConnection:
    """统计功能MySQL数据库连接管理器"""
    
    def __init__(self):
        """初始化数据库连接配置（使用独立的配置项）"""
        self.host = os.getenv('MYSQL_STATS_HOST', os.getenv('MYSQL_HOST', 'localhost'))
        self.port = int(os.getenv('MYSQL_STATS_PORT', os.getenv('MYSQL_PORT', '3306')))
        self.user = os.getenv('MYSQL_STATS_USER', os.getenv('MYSQL_USER', 'root'))
        self.password = os.getenv('MYSQL_STATS_PASSWORD', os.getenv('MYSQL_PASSWORD', ''))
        self.database = os.getenv('MYSQL_STATS_DATABASE', os.getenv('MYSQL_DATABASE', ''))
        self.charset = os.getenv('MYSQL_STATS_CHARSET', os.getenv('MYSQL_CHARSET', 'utf8mb4'))
        
        # 连接池配置
        self.max_connections = int(os.getenv('MYSQL_STATS_MAX_CONNECTIONS', os.getenv('MYSQL_MAX_CONNECTIONS', '10')))
        self.connect_timeout = int(os.getenv('MYSQL_STATS_CONNECT_TIMEOUT', os.getenv('MYSQL_CONNECT_TIMEOUT', '10')))
        
        # 验证必要配置
        if not self.database:
            logger.warning("MYSQL_STATS_DATABASE未配置，统计功能数据库可能无法使用")
    
    def _get_connection_without_database(self):
        """
        获取不指定数据库的连接（用于创建数据库）
        
        Returns:
            pymysql.Connection: 数据库连接对象
        """
        try:
            connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                charset=self.charset,
                connect_timeout=self.connect_timeout,
                cursorclass=DictCursor,
                autocommit=True  # 创建数据库需要自动提交
            )
            return connection
        except Exception as e:
            logger.error(f"统计数据库连接失败（无数据库）: {str(e)}")
            raise
    
    def create_database_if_not_exists(self) -> bool:
        """
        如果数据库不存在则创建数据库（用于地址智能解析接口统计功能）
        
        注意：MySQL的CREATE DATABASE语句不支持COMMENT子句，数据库注释功能在MySQL中不支持
        
        Returns:
            bool: 是否成功（数据库已存在或创建成功）
        """
        if not self.database:
            logger.warning("MYSQL_STATS_DATABASE未配置，无法创建数据库")
            return False
        
        connection = None
        try:
            # 先尝试连接指定数据库
            try:
                conn = self.get_connection()
                conn.close()
                # 数据库已存在
                logger.debug(f"统计数据库 {self.database} 已存在")
                return True
            except pymysql.Error as e:
                error_code = e.args[0] if e.args else 0
                if error_code != 1049:  # 1049 = Unknown database
                    # 其他错误，记录并返回False
                    logger.error(f"检查统计数据库是否存在时出错: {str(e)}")
                    return False
                # 数据库不存在（1049），继续创建
            
            # 数据库不存在，创建数据库
            connection = self._get_connection_without_database()
            with connection.cursor() as cursor:
                # 创建数据库，使用utf8mb4字符集和utf8mb4_unicode_ci排序规则
                # 注意：CREATE DATABASE不支持COMMENT子句，如果需要注释可以在创建后使用ALTER DATABASE
                create_db_sql = f"CREATE DATABASE IF NOT EXISTS `{self.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                cursor.execute(create_db_sql)
                logger.info(f"成功创建统计数据库: {self.database}（地址智能解析接口）")
                return True
        except Exception as e:
            logger.error(f"创建统计数据库失败 {self.database}: {str(e)}")
            return False
        finally:
            if connection:
                connection.close()
    
    def get_connection(self):
        """
        获取数据库连接
        
        Returns:
            pymysql.Connection: 数据库连接对象
            
        Raises:
            Exception: 连接失败时抛出异常
        """
        try:
            connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset=self.charset,
                connect_timeout=self.connect_timeout,
                cursorclass=DictCursor,
                autocommit=False
            )
            return connection
        except Exception as e:
            logger.error(f"统计数据库连接失败: {str(e)}")
            raise
    
    @contextmanager
    def get_cursor(self):
        """
        获取数据库游标的上下文管理器
        
        Usage:
            with db.get_cursor() as cursor:
                cursor.execute("SELECT * FROM table")
                results = cursor.fetchall()
        """
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            yield cursor
            connection.commit()
        except Exception as e:
            if connection:
                connection.rollback()
            logger.error(f"统计数据库操作失败: {str(e)}")
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def execute_query(self, sql: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        执行查询语句
        
        Args:
            sql: SQL查询语句
            params: 查询参数（可选）
            
        Returns:
            查询结果列表（字典格式）
        """
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()
    
    def execute_one(self, sql: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        """
        执行查询语句，返回单条记录
        
        Args:
            sql: SQL查询语句
            params: 查询参数（可选）
            
        Returns:
            查询结果（字典格式），如果没有结果则返回None
        """
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()
    
    def test_connection(self) -> bool:
        """
        测试数据库连接（如果数据库不存在则自动创建）
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 如果数据库不存在，尝试创建
            if not self.create_database_if_not_exists():
                return False
            
            # 测试连接
            with self.get_cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"统计数据库连接测试失败: {str(e)}")
            return False
    
    def table_exists(self, table_name: str) -> bool:
        """
        检查表是否存在
        
        Args:
            table_name: 表名
            
        Returns:
            bool: 表是否存在
        """
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) as count FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_name = %s",
                    (self.database, table_name)
                )
                result = cursor.fetchone()
                return result['count'] > 0 if result else False
        except Exception as e:
            logger.error(f"检查统计表是否存在失败 {table_name}: {str(e)}")
            return False
    
    def create_api_usage_table(self, table_name: str = None) -> bool:
        """
        创建API使用统计表
        
        Args:
            table_name: 表名，如果为None则从环境变量读取
            
        Returns:
            bool: 是否创建成功
        """
        if table_name is None:
            table_name = os.getenv('MYSQL_API_USAGE_TABLE', 'extract_api_usage')
        
        # 如果表已存在，直接返回
        if self.table_exists(table_name):
            logger.info(f"统计表 {table_name} 已存在，跳过创建")
            # 尝试添加 success_count 字段（如果不存在）
            try:
                with self.get_cursor() as cursor:
                    # 检查字段是否存在
                    check_column_sql = f"""
                    SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table_name}' AND COLUMN_NAME = 'success_count'
                    """
                    cursor.execute(check_column_sql)
                    column_exists = cursor.fetchone()[0] > 0

                    if not column_exists:
                        # 字段不存在，添加字段
                        alter_sql = f"""
                        ALTER TABLE `{table_name}`
                        ADD COLUMN success_count INT NOT NULL DEFAULT 0 COMMENT '成功调用次数'
                        AFTER call_count
                        """
                        cursor.execute(alter_sql)
                        logger.info(f"成功为统计表 {table_name} 添加 success_count 字段")
                    else:
                        logger.debug(f"统计表 {table_name} 的 success_count 字段已存在")
            except Exception as e:
                logger.warning(f"添加 success_count 字段失败（不影响功能）: {str(e)}")
            return True

        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            stat_date DATE NOT NULL,
            api_name VARCHAR(255) NOT NULL,
            call_count INT NOT NULL DEFAULT 0 COMMENT '总调用次数',
            success_count INT NOT NULL DEFAULT 0 COMMENT '成功调用次数',
            PRIMARY KEY (stat_date, api_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='地址提取接口使用统计';
        """

        try:
            with self.get_cursor() as cursor:
                cursor.execute(create_table_sql)
                logger.info(f"成功创建统计表 {table_name}")
                return True
        except Exception as e:
            logger.error(f"创建统计表 {table_name} 失败: {str(e)}")
            return False
    
    def create_api_error_log_table(self, table_name: str = None) -> bool:
        """
        创建API错误日志表
        
        Args:
            table_name: 表名，如果为None则从环境变量读取
            
        Returns:
            bool: 是否创建成功
        """
        if table_name is None:
            table_name = os.getenv('MYSQL_API_ERROR_LOG_TABLE', 'extract_api_error_log')
        
        # 如果表已存在，直接返回
        if self.table_exists(table_name):
            logger.info(f"统计表 {table_name} 已存在，跳过创建")
            return True
        
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(255) DEFAULT NULL,
            user_name VARCHAR(255) DEFAULT NULL,
            model_type VARCHAR(255) DEFAULT 'mgeo_geographic_composition_analysis_chinese_base',
            content TEXT,
            extract_data JSON,
            result_code VARCHAR(10) DEFAULT NULL,
            reason TEXT DEFAULT NULL,
            warning JSON,
            time DATETIME NOT NULL,
            INDEX idx_time (time),
            INDEX idx_model_type (model_type),
            INDEX idx_result_code (result_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='地址提取接口失败事件日志';
        """
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(create_table_sql)
                logger.info(f"成功创建统计表 {table_name}")
                return True
        except Exception as e:
            logger.error(f"创建统计表 {table_name} 失败: {str(e)}")
            return False
    
    def init_statistics_tables(self) -> bool:
        """
        初始化统计相关表（检查并创建）
        
        Returns:
            bool: 是否初始化成功
        """
        try:
            api_usage_table = os.getenv('MYSQL_API_USAGE_TABLE', 'extract_api_usage')
            api_error_log_table = os.getenv('MYSQL_API_ERROR_LOG_TABLE', 'extract_api_error_log')
            
            success = True
            success = self.create_api_usage_table(api_usage_table) and success
            success = self.create_api_error_log_table(api_error_log_table) and success
            
            return success
        except Exception as e:
            logger.error(f"初始化统计表失败: {str(e)}")
            return False

