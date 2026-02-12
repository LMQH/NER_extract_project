"""
API错误日志记录模块
用于记录接口失败事件的完整上下文信息
"""
import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from collections import OrderedDict
from src.database.statistics_db_connection import StatisticsDatabaseConnection

logger = logging.getLogger("NER_API")


class ApiErrorLogger:
    """API错误日志记录器"""
    
    def __init__(self, db_connection: Optional[StatisticsDatabaseConnection] = None):
        """
        初始化API错误日志记录器
        
        Args:
            db_connection: 统计数据库连接对象，如果为None则创建新连接
        """
        self.db_connection = db_connection or StatisticsDatabaseConnection()
        self.table_name = os.getenv('MYSQL_API_ERROR_LOG_TABLE', 'extract_api_error_log')
        self.enabled = True
    
    def log_api_error(
        self,
        content: str,
        extract_data: Dict[str, Any],
        warning: List[str] = None,
        model_type: str = 'mgeo_geographic_composition_analysis_chinese_base',
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        result_code: Optional[str] = None,
        reason: Optional[str] = None,
        error_time: Optional[datetime] = None
    ) -> bool:
        """
        记录API错误日志
        
        Args:
            content: 请求的文本内容
            extract_data: 提取的数据（字典格式，将存储为JSON）
            warning: 警告信息列表（元素为字符串）
            model_type: 模型类型，默认'mgeo_geographic_composition_analysis_chinese_base'
            user_id: 用户ID，默认None
            user_name: 用户名，默认None
            result_code: 结果状态码，默认None
            reason: 原因说明，默认None
            error_time: 错误时间，如果为None则使用当前时间
            
        Returns:
            bool: 是否记录成功（失败时返回False但不抛出异常）
        """
        if not self.enabled:
            return False
        
        if error_time is None:
            error_time = datetime.now()
        
        if warning is None:
            warning = []
        
        try:
            # 确保extract_data字段顺序正确（与接口返回格式一致）
            # 字段顺序：ProvinceName, CityName, ExpAreaName, StreetName, AreasInfo, Address, others, Mobile, Name
            if extract_data:
                ordered_data = OrderedDict([
                    ("ProvinceName", extract_data.get("ProvinceName", "")),
                    ("CityName", extract_data.get("CityName", "")),
                    ("ExpAreaName", extract_data.get("ExpAreaName", "")),
                    ("StreetName", extract_data.get("StreetName", "")),
                    ("AreasInfo", extract_data.get("AreasInfo", "")),
                    ("Address", extract_data.get("Address", "")),
                    ("others", extract_data.get("others", "")),
                    ("Mobile", extract_data.get("Mobile", "")),
                    ("Name", extract_data.get("Name", ""))
                ])
            else:
                ordered_data = None
            
            # 序列化JSON字段（使用OrderedDict保持字段顺序）
            extract_data_json = json.dumps(ordered_data, ensure_ascii=False) if ordered_data else None
            warning_json = json.dumps(warning, ensure_ascii=False) if warning else None
            
            # 构建插入SQL
            insert_sql = f"""
            INSERT INTO `{self.table_name}` 
            (user_id, user_name, model_type, content, extract_data, result_code, reason, warning, time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            params = (
                user_id,
                user_name,
                model_type,
                content,
                extract_data_json,
                result_code,
                reason,
                warning_json,
                error_time
            )
            
            # 执行插入
            with self.db_connection.get_cursor() as cursor:
                cursor.execute(insert_sql, params)
            
            logger.debug(f"API错误日志记录成功: model_type={model_type}, content_length={len(content) if content else 0}")
            return True
            
        except Exception as e:
            # 记录错误但不抛出异常，避免影响接口响应
            logger.error(f"记录API错误日志失败: {str(e)}")
            return False
    
    def log_api_error_from_response(
        self,
        content: str,
        response_data: Dict[str, Any],
        model_type: str = 'mgeo_geographic_composition_analysis_chinese_base',
        user_id: Optional[str] = None,
        user_name: Optional[str] = None
    ) -> bool:
        """
        从响应数据记录API错误日志（便捷方法）
        
        Args:
            content: 请求的文本内容
            response_data: 接口响应数据（包含Data、Warning、ResultCode、Reason等字段）
            model_type: 模型类型
            user_id: 用户ID
            user_name: 用户名
            
        Returns:
            bool: 是否记录成功
        """
        extract_data = response_data.get('Data', {})
        warning = response_data.get('Warning', [])
        result_code = response_data.get('ResultCode', None)
        reason = response_data.get('Reason', None)
        
        return self.log_api_error(
            content=content,
            extract_data=extract_data,
            warning=warning,
            model_type=model_type,
            user_id=user_id,
            user_name=user_name,
            result_code=result_code,
            reason=reason
        )

