# Inference Service Docker 部署说明

本文档介绍如何使用 Docker 部署 NER 推理服务。

---

## 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- 至少 4GB 可用内存
- 至少 3GB 可用磁盘空间

---

## 快速启动（推荐）

### 使用 Docker Compose

```bash
# 进入 docker 目录
cd docker

# 后台启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

**服务地址**：`http://localhost:14467`

**健康检查**：
```bash
curl http://localhost:14467/inference/health
```

---

## 手动构建

### 1. 构建镜像

```bash
cd docker
docker build -t inference-service -f Dockerfile ..
```

### 2. 运行容器

```bash
docker run -d \
  --name ner-inference-service \
  -p 14467:14467 \
  -v $(pwd)/../models:/app/models \
  -v $(pwd)/../logs:/app/logs \
  -v $(pwd)/../dev.env:/app/dev.env \
  --restart unless-stopped \
  inference-service
```

**Windows PowerShell**：
```powershell
docker run -d `
  --name ner-inference-service `
  -p 14467:14467 `
  -v "${PWD}/../models:/app/models" `
  -v "${PWD}/../logs:/app/logs" `
  -v "${PWD}/../dev.env:/app/dev.env" `
  --restart unless-stopped `
  inference-service
```

### 3. 管理容器

```bash
# 查看运行状态
docker ps

# 查看日志
docker logs ner-inference-service

# 停止容器
docker stop ner-inference-service

# 启动容器
docker start ner-inference-service

# 删除容器
docker rm ner-inference-service

# 删除镜像
docker rmi inference-service
```

---

## 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|--------|---------|------|
| INFERENCE_PORT | 14467 | 服务监听端口 |
| MODEL_PATH | models/ | 模型文件路径 |
| MODEL_EXISTS | true | 模型是否已存在 |
| CORS_ALLOW_ORIGINS | * | CORS 允许的来源 |
| LOG_LEVEL | INFO | 日志级别 |

### 目录挂载

| 宿主机路径 | 容器路径 | 说明 |
|------------|-----------|------|
| `../models` | `/app/models` | 模型文件（可选） |
| `../logs` | `/app/logs` | 日志文件 |
| `../dev.env` | `/app/dev.env` | 配置文件 |

---

## 验证部署

### 1. 健康检查

```bash
curl http://localhost:14467/inference/health
```

**预期响应**：
```json
{
    "status": "healthy",
    "message": "推理服务运行正常",
    "timestamp": "2026-02-12T10:30:00.000Z"
}
```

### 2. 模型列表

```bash
curl http://localhost:14467/inference/models
```

### 3. 实体抽取测试

```bash
curl -X POST http://localhost:14467/inference/extract \
  -H "Content-Type: application/json" \
  -d '{"Content": "广东省深圳市龙岗区坂田街道阿里巴巴"}'
```

---

## 生产环境优化

### 1. 资源限制

编辑 `docker-compose.yml`，调整资源限制：

```yaml
deploy:
  resources:
    limits:
      cpus: '4'      # CPU 核心数
      memory: 8G      # 最大内存
    reservations:
      cpus: '2'
      memory: 4G
```

### 2. 多副本部署

```bash
# 启动 3 个副本
docker-compose up -d --scale inference-service=3
```

### 3. 使用 Nginx 反向代理

```nginx
upstream inference_backend {
    server localhost:14467;
}

server {
    listen 80;
    server_name your-domain.com;

    location /inference/ {
        proxy_pass http://inference_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

---

## 常见问题

### Q1: 端口被占用

**错误**：`Bind for 0.0.0.0:14467 failed: port is already allocated`

**解决**：
```bash
# 查看占用端口的进程
netstat -tuln | grep 14467  # Linux
netstat -ano | findstr 14467  # Windows

# 或修改映射端口
docker run -p 8080:14467 inference-service
```

### Q2: 内存不足

**错误**：`Cannot allocate memory`

**解决**：
1. 增加 Docker 可用内存
2. 减少工作进程数
3. 使用更小的模型

### Q3: 模型加载慢

**原因**：首次启动需要加载模型（约 30-60 秒）

**解决**：
- 健康检查设置了 `start_period: 60s`
- 模型加载后会缓存在内存中
- 后续请求响应时间 < 1s

### Q4: 如何查看详细日志

```bash
# 查看容器日志
docker logs ner-inference-service

# 查看挂载的日志文件
tail -f ../logs/inference_*.log
```

### Q5: 更新代码后重新部署

```bash
# 重新构建镜像
docker-compose build

# 重启服务
docker-compose up -d
```

---

## 目录结构

```
docker/
├── Dockerfile              # 镜像构建文件
├── docker-compose.yml      # Compose 配置
├── .dockerignore          # 构建排除文件
└── README.md            # 本文档
```

---

## 参考资料

- [Docker 官方文档](https://docs.docker.com/)
- [Docker Compose 文档](https://docs.docker.com/compose/)
- [主文档](../document/README.md)

---

**版本**：v1.0
**最后更新**：2026-02-12
