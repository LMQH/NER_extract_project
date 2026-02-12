#!/bin/bash

# Linux启动脚本
# 启动Backend Service

# 获取脚本所在目录（bin目录）
BIN_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# 获取项目根目录（bin的父目录）
PROJECT_ROOT="$( cd "$BIN_DIR/.." && pwd )"

# 切换到项目根目录
cd "$PROJECT_ROOT"

# 设置Python路径
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3 命令"
    exit 1
fi

# 检查uvicorn是否安装
if ! python3 -m uvicorn --help &> /dev/null; then
    echo "错误: 未找到 uvicorn 模块，请先安装依赖: pip install -r requirements.txt"
    exit 1
fi

# 检查端口是否被占用
if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "警告: 端口 8080 已被占用"
    echo "请先停止现有服务，或使用 stop.sh 脚本停止服务"
    exit 1
fi

echo "============================================================"
echo "Backend Service 启动 (FastAPI)"
echo "============================================================"
echo "项目目录: $PROJECT_ROOT"
echo "正在启动服务..."
echo "API文档: http://localhost:8080/docs"
echo "API文档 (ReDoc): http://localhost:8080/redoc"
echo "============================================================"
echo "按 Ctrl+C 停止服务"
echo "============================================================"

# 启动FastAPI服务
# 使用 reload=True 支持热重载（开发模式）
python3 -m uvicorn app:app --host 0.0.0.0 --port 8080 --reload
