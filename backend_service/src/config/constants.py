"""
常量定义模块
集中管理项目中使用的常量
"""
from typing import Dict, List

# 模型相关常量
SUPPORTED_MODELS: Dict[str, str] = {
    'mgeo_geographic_composition_analysis_chinese_base': 'model/mgeo_geographic_composition_analysis_chinese_base',
    # 'qwen-flash': None  # 已废弃：qwen-flash不需要本地模型路径，使用API调用（保留代码但不再使用）
}

MODEL_TYPES: Dict[str, str] = {
    'mgeo_geographic_composition_analysis_chinese_base': 'mgeo',
    # 'qwen-flash': 'qwen_flash'  # 已废弃（保留代码但不再使用）
}

# 文件扩展名
SUPPORTED_FILE_EXTENSIONS: set = {'.txt', '.md', '.docx', '.doc', '.pdf'}

# 地址相关常量
ADDRESS_KEYWORDS: List[str] = [
    '省', '市', '区', '县', '镇', '街道', '路', '街', '号', '村', '组',
    '小区', '大厦', '广场', '园区', '工业区', '开发区', '新区', '大道',
    '巷', '弄', '里', '幢', '栋', '单元', '室', '层', '自治区', '特别行政区'
]

DIRECT_CITIES: Dict[str, str] = {
    "北京市": "北京",
    "上海市": "上海",
    "天津市": "天津",
    "重庆市": "重庆"
}

# 实体类型常量
ENTITY_TYPE_PROVINCE: str = "PB"
ENTITY_TYPE_CITY: str = "PC"
ENTITY_TYPE_DISTRICT: str = "PD"
ENTITY_TYPE_STREET: str = "PF"
ENTITY_TYPE_ROAD: str = "RD"
ENTITY_TYPE_UNIT_ADDRESS: str = "UA"
ENTITY_TYPE_NUMBER_ENG: str = "NumEng"
ENTITY_TYPE_OTHER: str = "ZZ"

# 正则表达式模式
PHONE_PATTERN: str = r'1[3-9]\d{9}'
FIXED_PHONE_PATTERN: str = r'0\d{2,3}-?\d{7,8}'
CHINESE_NAME_PATTERN: str = r'^[\u4e00-\u9fa5]{2,4}$'

# 地址解析模式
PROVINCE_PATTERN: str = r'^([^省市区县]+(?:省|自治区|特别行政区))'
CITY_PATTERN: str = r'^([^省市区县]+市)'
DISTRICT_PATTERN: str = r'^([^省市区县街道镇乡]+(?:区|县))'
STREET_PATTERN: str = r'^([^省市区县街道镇乡]+(?:街道|镇|乡))'

# 响应格式常量
DEFAULT_EBUSINESS_ID: str = "2223333"
DEFAULT_SUCCESS_CODE: str = "100"
DEFAULT_ERROR_CODE: str = "103"
DEFAULT_SUCCESS_REASON: str = "解析成功"
DEFAULT_ERROR_REASON: str = "解析失败"

# 输出字段映射
OUTPUT_FIELDS = {
    "ProvinceName": "ProvinceName",
    "CityName": "CityName",
    "ExpAreaName": "ExpAreaName",
    "StreetName": "StreetName",
    "AreasInfo": "AreasInfo",
    "Address": "Address",
    "others": "others",
    "Mobile": "Mobile",
    "Name": "Name"
}

# 默认实体映射配置
DEFAULT_ENTITY_MAPPING = {
    "ProvinceName": {
        "entity_types": ["地理位置"],
        "patterns": ["省", "自治区", "特别行政区"]
    },
    "CityName": {
        "entity_types": ["地理位置"],
        "patterns": ["市"]
    },
    "ExpAreaName": {
        "entity_types": ["地理位置"],
        "patterns": ["区", "县"]
    },
    "StreetName": {
        "entity_types": ["地理位置"],
        "patterns": ["街道", "镇", "乡"]
    },
    "Address": {
        "entity_types": ["地理位置"],
        "patterns": ["路", "街", "大道", "巷", "号", "弄", "里"]
    },
    "Name": {
        "entity_types": ["人物"],
        "patterns": []
    }
}

# 双向匹配配置常量
# 通用词黑名单（不应该独立匹配的词）
GENERIC_TERMS_BLACKLIST: set = {
    '街道', '镇', '乡', '村', '社区',
    '路', '街', '巷', '弄', '里',
    '区', '县', '市', '省'
}

# 最小匹配长度（字符数）
MIN_MATCH_LENGTH: int = 2

# 匹配质量评分权重
MATCH_SCORE_WEIGHTS: Dict[str, float] = {
    'exact_match': 1.0,      # 精确匹配
    'forward_match': 0.8,     # 正向匹配
    'backward_match': 0.5,    # 反向匹配
    'length_similarity': 0.3, # 长度相似度
    'coverage': 0.2           # 覆盖率
}

