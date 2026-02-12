#!/bin/bash

# Linux后台启动脚本
# 启动Inference Service（后台运行模式）

# 获取脚本所在目录（bin目录）
BIN_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# 获取项目根目录（bin的父目录）
PROJECT_ROOT="$( cd "$BIN_DIR/.." && pwd )"

# 切换到项目根目录
cd "$PROJECT_ROOT"

# 设置Python路径
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# PID文件路径
PID_FILE="$PROJECT_ROOT/inference_service.pid"
LOG_FILE="$PROJECT_ROOT/logs/app.log"

# 确保logs目录存在
mkdir -p "$PROJECT_ROOT/logs"

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

# 检查是否已经有服务在运行
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "警告: 服务已在运行中 (PID: $OLD_PID)"
        echo "如果确实需要重启，请先运行 stop.sh 停止服务"
        exit 1
    else
        # PID文件存在但进程不存在，删除旧的PID文件
        rm -f "$PID_FILE"
    fi
fi

# 检查端口是否被占用
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "警告: 端口 8000 已被占用"
    echo "请先停止现有服务，或使用 stop.sh 脚本停止服务"
    exit 1
fi

echo "============================================================"
echo "Inference Service 后台启动 (FastAPI)"
echo "============================================================"
echo "项目目录: $PROJECT_ROOT"
echo "日志文件: $LOG_FILE"
echo "PID文件: $PID_FILE"
echo "正在启动服务..."

# 后台启动FastAPI服务（不使用reload，适合生产环境）
nohup python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 > "$LOG_FILE" 2>&1 &
NEW_PID=$!

# 保存PID到文件
echo $NEW_PID > "$PID_FILE"

# 等待一下，检查进程是否启动成功
sleep 2

if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "服务已成功启动 (PID: $NEW_PID)"
    echo "API文档: http://localhost:8000/docs"
    echo "API文档 (ReDoc): http://localhost:8000/redoc"
    echo "============================================================"
    echo "使用以下命令查看日志: tail -f $LOG_FILE"
    echo "使用以下命令停止服务: $BIN_DIR/stop.sh"
    echo "============================================================"
else
    echo "错误: 服务启动失败"
    rm -f "$PID_FILE"
    echo "请查看日志文件: $LOG_FILE"
    exit 1
fi
