"""
环境配置加载模块
根据域名自动加载对应的配置文件

加载逻辑：
1. 根据当前域名/IP自动匹配环境（prod > show > dev）
2. 加载对应的环境配置文件（prod.env、show.env 或 dev.env）
3. 如果所有环境文件加载失败，最后尝试加载 .env 作为兼容备选
"""
import logging
import os
import platform
import socket
from pathlib import Path
from typing import Optional, Dict, Any, List
from dotenv import dotenv_values

# 只设置特定日志记录器的级别，不覆盖主日志配置
logging.getLogger("httpx").setLevel(logging.WARNING)
# 注意：不在这里调用 basicConfig，避免覆盖 app.py 中的日志配置
# 如果日志系统还未初始化，getLogger 会返回一个默认的日志记录器
logger = logging.getLogger("Env_Loader")

# 环境域名映射配置（在代码中定义，便于维护）
# 格式：{环境名称: [域名列表]}
ENV_DOMAIN_MAPPING: Dict[str, List[str]] = {
    'dev': [
        'localhost',
        '127.0.0.1',
        'dev.example.com',
        # 可以根据实际情况添加更多开发环境域名
    ],
    'show': [
        '172.16.64.104',
        '172.16.64.105',
        # 可以根据实际情况添加更多演示环境域名
    ],
    'prod': [
        'prod.example.com',
        'www.example.com',
        '172.16.64.100',
        '172.16.64.101',
        '172.16.64.103'
        # 可以根据实际情况添加更多生产环境域名
    ]
}


def get_local_ip() -> Optional[str]:
    """
    获取本地IP地址
    
    Returns:
        本地IP地址或None
    """
    try:
        # 通过连接外部地址获取本机IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        logger.warning(f"获取本地IP地址失败: {e}")
        return None


def get_current_domain() -> Optional[str]:
    """
    获取当前服务器IP地址（仅用于环境配置匹配）
    
    只获取IP地址，不获取域名或主机名，确保根据服务器IP地址加载对应的环境配置文件
    
    Returns:
        当前服务器IP地址或None
    """
    # 获取本地IP地址
    local_ip = get_local_ip()
    if local_ip:
        logger.info(f"获取本地IP地址: {local_ip}")
        return local_ip
    
    logger.warning("无法获取本地IP地址")
    return None


def load_env_file(env_file: str) -> Dict[str, Any]:
    """
    加载.env文件并返回配置字典
    
    Args:
        env_file: .env文件路径
        
    Returns:
        配置字典
    """
    if not Path(env_file).exists():
        logger.warning(f"配置文件不存在: {env_file}")
        return {}
    
    try:
        config = dotenv_values(env_file)
        logger.info(f"成功加载配置文件: {env_file}")
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败 {env_file}: {e}")
        return {}


def _match_domain(current_domain: str, domain_list: list) -> bool:
    """
    匹配域名是否在域名列表中
    
    Args:
        current_domain: 当前域名
        domain_list: 域名列表
        
    Returns:
        是否匹配
    """
    for domain in domain_list:
        if domain and domain.strip():
            domain = domain.strip()
            # 精确匹配或包含匹配
            is_match = (
                domain == current_domain or 
                domain in current_domain or 
                current_domain in domain or
                (domain == 'localhost' and current_domain in ['localhost', '127.0.0.1']) or
                (domain == '127.0.0.1' and current_domain in ['localhost', '127.0.0.1'])
            )
            # 如果是IP地址，进行精确匹配
            if not is_match:
                try:
                    # 检查是否为IP地址格式
                    import ipaddress
                    domain_ip = ipaddress.ip_address(domain)
                    current_ip = ipaddress.ip_address(current_domain)
                    is_match = domain_ip == current_ip
                except (ValueError, AttributeError):
                    # 不是有效的IP地址，继续其他匹配方式
                    pass
            
            if is_match:
                return True
    return False


def load_config() -> Dict[str, Any]:
    """
    根据域名自动加载对应的配置文件
    
    逻辑：
    1. 获取当前域名
    2. 根据代码中定义的域名列表（ENV_DOMAIN_MAPPING）进行匹配
    3. 匹配优先级：prod > show > dev（生产环境优先级最高）
    4. 根据匹配结果加载对应的配置文件（prod.env、show.env 或 dev.env）
    5. 如果所有环境文件加载失败或返回空配置，最后尝试加载 .env 作为兼容备选
    
    Returns:
        配置字典
    """
    try:
        project_root = Path(__file__).parent.parent.parent
        current_domain = get_current_domain()
        
        config = {}
        loaded_file = None
        
        if not current_domain:
            logger.warning("无法获取当前域名，使用默认配置 dev.env")
            config_file = project_root / "dev.env"
            config = load_env_file(str(config_file))
            if config:
                loaded_file = "dev.env"
        else:
            logger.info(f"当前域名: {current_domain}")
            logger.info(f"开发环境域名列表: {ENV_DOMAIN_MAPPING.get('dev', [])}")
            logger.info(f"演示环境域名列表: {ENV_DOMAIN_MAPPING.get('show', [])}")
            logger.info(f"生产环境域名列表: {ENV_DOMAIN_MAPPING.get('prod', [])}")
            
            # 优先匹配生产环境（prod）
            prod_domains = ENV_DOMAIN_MAPPING.get('prod', [])
            if prod_domains and _match_domain(current_domain, prod_domains):
                logger.info(f"当前域名/IP {current_domain} 在生产环境域名列表中，加载 prod.env")
                prod_env_file = project_root / "prod.env"
                config = load_env_file(str(prod_env_file))
                if config:
                    loaded_file = "prod.env"
            
            # 如果生产环境未匹配或加载失败，尝试演示环境（show）
            if not config:
                show_domains = ENV_DOMAIN_MAPPING.get('show', [])
                if show_domains and _match_domain(current_domain, show_domains):
                    logger.info(f"当前域名/IP {current_domain} 在演示环境域名列表中，加载 show.env")
                    show_env_file = project_root / "show.env"
                    config = load_env_file(str(show_env_file))
                    if config:
                        loaded_file = "show.env"
            
            # 如果演示环境未匹配或加载失败，尝试开发环境（dev）
            if not config:
                dev_domains = ENV_DOMAIN_MAPPING.get('dev', [])
                if dev_domains and _match_domain(current_domain, dev_domains):
                    logger.info(f"当前域名/IP {current_domain} 在开发环境域名列表中，加载 dev.env")
                    dev_env_file = project_root / "dev.env"
                    config = load_env_file(str(dev_env_file))
                    if config:
                        loaded_file = "dev.env"
            
            # 如果所有环境都未匹配，默认使用开发环境配置
            if not config:
                logger.info(f"当前域名 {current_domain} 未匹配到任何环境，默认使用 dev.env")
                dev_env_file = project_root / "dev.env"
                config = load_env_file(str(dev_env_file))
                if config:
                    loaded_file = "dev.env"
        
        # 如果所有环境文件加载失败或返回空配置，尝试加载 .env 作为兼容备选
        if not config:
            logger.warning("所有环境配置文件加载失败或为空，尝试加载 .env 作为兼容备选")
            env_file = project_root / ".env"
            config = load_env_file(str(env_file))
            if config:
                loaded_file = ".env"
                logger.info("成功加载 .env 作为兼容备选配置")
            else:
                logger.error("所有配置文件加载失败，将使用系统环境变量")
        
        if loaded_file:
            logger.info(f"✓ 已加载环境变量文件: {loaded_file}")
            # 记录加载的关键配置项数量
            redis_configs = [k for k in config.keys() if 'REDIS' in k]
            mysql_configs = [k for k in config.keys() if 'MYSQL' in k]
            logger.info(f"  已加载配置项: 总计{len(config)}个, Redis相关{len(redis_configs)}个, MySQL相关{len(mysql_configs)}个")
        else:
            logger.warning("⚠ 未加载任何环境变量文件，将使用系统环境变量或默认值")
        
        return config
        
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        # 最后尝试加载 .env 作为兼容备选
        try:
            project_root = Path(__file__).parent.parent.parent
            env_file = project_root / ".env"
            config = load_env_file(str(env_file))
            if config:
                logger.info("✓ 已加载 .env 作为兼容备选配置")
                return config
        except Exception as e2:
            logger.error(f"加载 .env 兼容备选配置也失败: {e2}")
        
        # 返回空字典，使用系统环境变量
        return {}


if __name__ == "__main__":
    config = load_config()
    logger.info(f"配置类型: {type(config)}")
    logger.info("配置内容:")
    for key, value in config.items():
        logger.info(f"  {key} = {value}")

