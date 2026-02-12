"""
Backend Service 启动脚本
用于Windows开发环境快速启动
"""
import sys
import subprocess
from pathlib import Path

# 切换到脚本所在目录
script_dir = Path(__file__).parent
project_root = script_dir.parent

print("=" * 60)
print("Backend Service 启动")
print("=" * 60)
print(f"项目目录: {project_root}")
print("正在启动后端服务...")
print("=" * 60)

# 启动FastAPI服务（使用reload支持热重载）
try:
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--reload"],
        cwd=project_root,
        check=True
    )
except KeyboardInterrupt:
    print("\n服务已停止")
except Exception as e:
    print(f"启动失败: {e}")
    input("按任意键退出...")
