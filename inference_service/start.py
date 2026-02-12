"""
Inference Service 启动脚本
用于Windows开发环境快速启动
"""
import sys
import subprocess
from pathlib import Path

# 项目根目录：inference_service/ 目录作为此项目的根目录
project_root = Path(__file__).parent.resolve()

print("=" * 60)
print("Inference Service 启动")
print("=" * 60)
print(f"项目目录: {project_root}")
print(f"Python 环境: {sys.executable}")
print("正在启动推理服务...")
print("=" * 60)

# 启动FastAPI服务（使用reload支持热重载）
# 工作目录设置为 inference_service/，作为此项目的根目录
try:
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "13111", "--reload"],
        cwd=project_root,
        check=True
    )
except KeyboardInterrupt:
    print("\n服务已停止")
except subprocess.CalledProcessError as e:
    print(f"\n启动失败: 服务进程异常退出 (退出码: {e.returncode})")
    print("\n提示: 如果看到 'No module named' 错误，请检查依赖是否已安装：")
    print(f"  使用当前 Python 环境安装: {sys.executable} -m pip install -r requirements.txt")
    input("\n按任意键退出...")
except Exception as e:
    error_msg = str(e)
    if "No module named" in error_msg or "ModuleNotFoundError" in str(type(e).__name__):
        print(f"\n启动失败: 缺少依赖模块")
        print(f"错误详情: {error_msg}")
        print(f"\n当前 Python 环境: {sys.executable}")
        print("\n请使用当前 Python 环境安装缺失的依赖：")
        print(f"  {sys.executable} -m pip install -r requirements.txt")
        print("\n或者如果使用 conda 环境，请确保已激活正确的环境：")
        print("  conda activate lmqh_ai_extract")
        print("  pip install -r requirements.txt")
    else:
        print(f"\n启动失败: {error_msg}")
    input("\n按任意键退出...")
