"""
MySQL数据库连接模块
支持通过环境变量配置数据库连接
"""
import os
import logging
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger("NER_API")


class DatabaseConnection:
    """MySQL数据库连接管理器"""
    
    def __init__(self):
        """初始化数据库连接配置"""
        self.host = os.getenv('MYSQL_HOST', 'localhost')
        self.port = int(os.getenv('MYSQL_PORT', '3306'))
        self.user = os.getenv('MYSQL_USER', 'root')
        self.password = os.getenv('MYSQL_PASSWORD', '')
        self.database = os.getenv('MYSQL_DATABASE', '')
        self.charset = os.getenv('MYSQL_CHARSET', 'utf8mb4')
        
        # 连接池配置
        self.max_connections = int(os.getenv('MYSQL_MAX_CONNECTIONS', '10')) # 连接池最大连接数
        self.connect_timeout = int(os.getenv('MYSQL_CONNECT_TIMEOUT', '10')) # 连接超时时间
        
        # 验证必要配置
        if not self.database:
            logger.warning("MYSQL_DATABASE未配置，数据库功能可能无法使用")
    
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
            logger.error(f"数据库连接失败: {str(e)}")
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
            logger.error(f"数据库操作失败: {str(e)}")
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
        测试数据库连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"数据库连接测试失败: {str(e)}")
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
            logger.error(f"检查表是否存在失败 {table_name}: {str(e)}")
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
            logger.info(f"表 {table_name} 已存在，跳过创建")
            return True
        
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            stat_date DATE NOT NULL,
            api_name VARCHAR(255) NOT NULL,
            call_count INT NOT NULL DEFAULT 0,
            PRIMARY KEY (stat_date, api_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='地址提取接口使用统计';
        """
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(create_table_sql)
                logger.info(f"成功创建表 {table_name}")
                return True
        except Exception as e:
            logger.error(f"创建表 {table_name} 失败: {str(e)}")
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
            logger.info(f"表 {table_name} 已存在，跳过创建")
            return True
        
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(255) DEFAULT NULL,
            user_name VARCHAR(255) DEFAULT NULL,
            model_type VARCHAR(255) DEFAULT 'mgeo_geographic_composition_analysis_chinese_base',
            content TEXT,
            extract_data JSON,
            warning JSON,
            time DATETIME NOT NULL,
            INDEX idx_time (time),
            INDEX idx_model_type (model_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='地址提取接口失败事件日志';
        """
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(create_table_sql)
                logger.info(f"成功创建表 {table_name}")
                return True
        except Exception as e:
            logger.error(f"创建表 {table_name} 失败: {str(e)}")
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

