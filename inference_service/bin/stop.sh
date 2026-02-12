#!/bin/bash

# Linux停止脚本
# 停止Inference Service

# 获取脚本所在目录（bin目录）
BIN_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# 获取项目根目录（bin的父目录）
PROJECT_ROOT="$( cd "$BIN_DIR/.." && pwd )"

# PID文件路径
PID_FILE="$PROJECT_ROOT/inference_service.pid"

echo "============================================================"
echo "Inference Service 停止脚本"
echo "============================================================"

PID=""

# 首先尝试从PID文件读取PID（后台运行模式）
if [ -f "$PID_FILE" ]; then
    PID_FROM_FILE=$(cat "$PID_FILE")
    if kill -0 "$PID_FROM_FILE" 2>/dev/null; then
        PID="$PID_FROM_FILE"
        echo "从PID文件找到运行中的服务: PID=$PID"
    else
        echo "PID文件存在但进程不存在，清理PID文件"
        rm -f "$PID_FILE"
    fi
fi

# 如果没有从PID文件找到，则通过端口查找（前台运行模式）
if [ -z "$PID" ]; then
    if command -v lsof &> /dev/null; then
        PID=$(lsof -ti:13111 2>/dev/null)
    elif command -v netstat &> /dev/null; then
        PID=$(netstat -tlnp 2>/dev/null | grep :13111 | awk '{print $7}' | cut -d'/' -f1 | head -1)
    elif command -v ss &> /dev/null; then
        PID=$(ss -tlnp 2>/dev/null | grep :13111 | awk '{print $NF}' | cut -d',' -f2 | cut -d'=' -f2 | head -1)
    fi

    if [ -n "$PID" ]; then
        echo "通过端口查找找到运行中的服务: PID=$PID"
    fi
fi

# 如果仍然找不到PID
if [ -z "$PID" ]; then
    echo "未找到运行在端口 13111 上的服务"
    echo "服务可能已经停止"
    # 清理可能存在的PID文件
    rm -f "$PID_FILE"
    exit 0
fi

echo "正在停止服务 (PID: $PID)..."

# 尝试优雅停止（发送SIGTERM信号）
kill -TERM "$PID" 2>/dev/null

# 等待进程结束（最多等待10秒）
for i in {1..10}; do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "服务已成功停止"
        # 清理PID文件
        rm -f "$PID_FILE"
        echo "============================================================"
        exit 0
    fi
    sleep 1
    echo "等待服务停止... ($i/10)"
done

# 如果进程仍在运行，强制停止（发送SIGKILL信号）
if kill -0 "$PID" 2>/dev/null; then
    echo "警告: 优雅停止失败，正在强制停止..."
    kill -KILL "$PID" 2>/dev/null
    sleep 1

    if ! kill -0 "$PID" 2>/dev/null; then
        echo "服务已强制停止"
        # 清理PID文件
        rm -f "$PID_FILE"
        echo "============================================================"
        exit 0
    else
        echo "错误: 无法停止服务进程"
        echo "============================================================"
        exit 1
    fi
fi

echo "============================================================"
