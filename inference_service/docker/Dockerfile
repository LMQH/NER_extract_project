# Inference Service Dockerfile
# 基于官方 Python 镜像构建 NER 推理服务

FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件（从上一级目录）
COPY ../inference_service/ /app/

# 安装 Python 依赖
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 创建日志目录
RUN mkdir -p /app/logs

# 暴露服务端口
EXPOSE 14467

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:14467/inference/health', timeout=5)" || exit 1

# 启动服务
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "14467"]
