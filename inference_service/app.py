"""
Inference Service 主入口
提供RESTful API接口，支持模型推理
"""
import sys
import os
from pathlib import Path
from datetime import datetime

# 调整 Python 路径优先级：确保 conda 环境的包优先于用户安装目录的包
# 移除用户安装目录，然后重新添加到末尾，这样 conda 环境的包会优先加载
user_site_packages = None
for i, path in enumerate(sys.path):
    if 'AppData\\Roaming\\Python' in path or 'Roaming\\Python' in path:
        user_site_packages = sys.path.pop(i)
        break

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

# 如果之前移除了用户安装目录，将其添加到末尾（作为后备）
if user_site_packages:
    sys.path.append(user_site_packages)

from src.main import create_app
from src.utils.logger import get_logger

# 创建应用实例
app = create_app()
logger = get_logger("Inference_API")

if __name__ == "__main__":
    import uvicorn

    # 从环境变量读取端口
    port = int(os.getenv('INFERENCE_PORT', '8000'))

    logger.info("=" * 60)
    logger.info("Inference Service 启动")
    logger.info("=" * 60)
    logger.info(f"服务地址: http://0.0.0.0:{port}")
    logger.info(f"API文档: http://localhost:{port}/docs")
    logger.info(f"API文档 (ReDoc): http://localhost:{port}/redoc")
    logger.info("=" * 60)

    # 启动FastAPI服务
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True)
