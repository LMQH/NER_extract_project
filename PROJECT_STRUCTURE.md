# NER Extract Project 项目结构说明

> 本文档用于快速理解 `ner_extract_project` 的代码组织、模块职责与服务调用关系。

## 1. 总体架构

该项目由三个子系统组成：

1. `backend_service`：对外业务 API（参数校验、调用推理、地址补全、统计与错误日志）。
2. `inference_service`：模型推理服务（模型加载、实体抽取、健康检查）。
3. `load_test_tools`：压测工具（单测、批量测试、多阶段脚本、报告生成）。

服务关系：

- 客户端调用 `backend_service` 的 `/api/extract`。
- `backend_service` 通过 `InferenceClient` 以 HTTP 调用 `inference_service` 的 `/inference/extract`。
- `backend_service` 在推理结果基础上执行地址补全与结果规范化后返回。

## 2. 目录结构

```text
ner_extract_project/
├── backend_service/                    # 对外后端服务
│   ├── app.py / start.py              # 启动入口
│   ├── dev.env / show.env / prod.env  # 环境配置
│   ├── entity_mapping.json            # 实体映射配置
│   ├── src/
│   │   ├── main.py                    # FastAPI 应用工厂
│   │   ├── api/                       # 接口层（路由、schema、依赖注入）
│   │   │   ├── routes/
│   │   │   │   ├── extract.py         # 核心抽取接口
│   │   │   │   ├── system.py          # 健康检查/模型列表接口
│   │   │   │   └── file.py            # 已废弃上传接口
│   │   │   ├── schemas.py             # 请求/响应模型
│   │   │   └── dependencies.py        # 全局依赖初始化与注入
│   │   ├── client/
│   │   │   └── inference_client.py    # 推理服务 HTTP 客户端
│   │   ├── processor_mgeo/            # 地址补全与匹配流程（三阶段）
│   │   ├── database/                  # MySQL/Redis/统计数据库相关模块
│   │   ├── config/                    # 环境与业务配置加载
│   │   ├── tasks/                     # 后台任务（如统计同步）
│   │   └── utils/                     # 通用工具（日志、异常、解析）
│   └── bin/                           # 启停脚本
│
├── inference_service/                  # 推理服务
│   ├── app.py / start.py              # 启动入口
│   ├── dev.env                        # 环境配置
│   ├── models/
│   │   └── mgeo_geographic_composition_analysis_chinese_base/
│   │       ├── config.json
│   │       ├── pytorch_model.bin
│   │       └── vocab.txt
│   ├── src/
│   │   ├── main.py                    # FastAPI 应用工厂
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── inference.py       # 推理接口
│   │   │   │   └── system.py          # 健康检查/模型列表
│   │   │   └── schemas.py             # 推理请求响应模型
│   │   ├── models/                    # 模型抽象、模型管理、模型实现
│   │   ├── processor/                 # 推理结果格式转换
│   │   ├── config/                    # 常量与环境配置
│   │   └── utils/                     # 日志与异常
│   └── bin/                           # 启停脚本
│
└── load_test_tools/                    # 压测工具
    ├── load_test_config.json          # 压测配置
    ├── README.md                      # 压测工具说明
    ├── core/
    │   ├── load_test_core.py          # 核心压测引擎（并发请求/统计）
    │   ├── load_test_runner.py        # 单测/批量/序列测试编排
    │   ├── load_test_reporter.py      # 文本/JSON/汇总报告生成
    │   └── load_test_config.py        # 配置加载与合并
    ├── test_scripts/
    │   ├── stage1_baseline_test.py    # 阶段1：基准测试
    │   ├── stage2_rampup_test.py      # 阶段2：线性增长测试
    │   ├── stage3_inflection_test.py  # 阶段3：拐点测试
    │   ├── stage4_stress_test.py      # 阶段4：压力测试
    │   ├── stage5_stability_test.py   # 阶段5：稳定性测试
    │   └── custom_config_test.py      # 自定义配置测试
    └── reports/                       # 报告输出目录（按阶段分组）
```

## 3. 核心调用链

### 3.1 在线推理链路

1. 请求进入 `backend_service/src/api/routes/extract.py`。
2. 执行输入校验与危险字符检测（`InputValidator`）。
3. 通过 `InferenceClient` 调用 `inference_service`。
4. `inference_service/src/api/routes/inference.py` 负责：
   - 选择/加载模型（`ModelManager`）。
   - 执行 `model.extract_entities`。
   - 格式化并返回推理结果。
5. `backend_service` 对推理结果执行格式转换和地址补全（`processor_mgeo`）。
6. 最终返回统一的 `ExtractResponse`（含 `ResultCode`、`Warning` 等）。

### 3.2 地址补全链路（backend）

`processor_mgeo` 采用三阶段处理：

1. Stage1：候选匹配（街道/区县/城市/省域）。
2. Stage2：候选解析与上下级关系约束（含追溯、补全、去重）。
3. Stage3：结果校验与状态码生成。

该模块细节文档见：`backend_service/src/processor_mgeo/README.md`。

## 4. 配置与环境

### 4.1 backend_service

- 通过 `src/config/env_loader.py` 根据本机 IP 匹配环境并加载：`prod.env` / `show.env` / `dev.env`。
- 关键变量包括：
  - 推理服务地址：`INFERENCE_SERVICE_URL`
  - Redis：`REDIS_HOST`、`REDIS_PORT`、`REDIS_DB`
  - MySQL：`MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_DATABASE`

### 4.2 inference_service

- `src/config/constants.py` 定义支持模型与模型类型映射。
- 模型文件默认位于 `inference_service/models/...`。

### 4.3 load_test_tools

- 主配置文件：`load_test_tools/load_test_config.json`。
- 支持并发、请求总量/持续时长、阈值（T1/T2）、输出目录、批量冷却时间等参数。

## 5. 统计与可观测性

`backend_service` 集成了基础统计能力：

1. `database/api_usage_counter.py`：基于 Redis 的 API 调用计数（总量/成功量）。
2. `database/api_error_logger.py`：将失败请求上下文写入统计数据库。
3. `utils/logger.py`：统一日志输出，启动时会初始化日志目录。

## 6. 运行入口

### 6.1 backend_service

- 入口文件：`backend_service/app.py`、`backend_service/start.py`。
- 核心应用工厂：`backend_service/src/main.py`。

### 6.2 inference_service

- 入口文件：`inference_service/app.py`、`inference_service/start.py`。
- 核心应用工厂：`inference_service/src/main.py`。

### 6.3 load_test_tools

- 阶段化脚本入口：`load_test_tools/test_scripts/stage*.py`。
- 自定义配置入口：`load_test_tools/test_scripts/custom_config_test.py`。

## 7. 当前代码结构特征（阅读结论）

1. 架构上已完成“后端服务与推理服务拆分”，backend 不再本地加载模型，而是转为 HTTP 调用。
2. `backend_service` 的业务复杂度主要集中在 `processor_mgeo`（地址标准化与补全）。
3. `load_test_tools` 相对独立，适合持续做容量评估与回归压测。
4. 目录分层清晰：`api`（接口）/`models`（模型）/`processor`（处理逻辑）/`config`（配置）/`database`（存储）。

---

如需下一步，我可以继续补一份“开发者快速上手文档”（启动顺序、依赖、联调与常见故障排查）。
