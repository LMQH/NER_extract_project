# 动态批量推理迭代计划

**文档版本:** v1.0
**创建日期:** 2026-02-11
**项目名称:** NER 实体抽取推理服务
**当前分支:** dev

---

## 一、项目概述

### 1.1 背景说明

当前推理服务 ([`inference_service`](../src)) 采用**单条推理模式**，每个请求仅处理一条文本。这种模式在低并发场景下表现良好，但在高并发或批量处理场景下存在以下问题：

- **GPU 利用率低**：单条推理无法充分利用 GPU 并行计算能力
- **吞吐量受限**：受限于串行处理模式，QPS 提升空间有限
- **延迟不稳定**：突发流量时容易出现排队延迟
- **资源浪费**：频繁的小批量推理导致 GPU 空转

### 1.2 目标定义

实现**动态批量推理 (Dynamic Batch Inference)** 机制，具备以下核心能力：

| 能力维度 | 当前状态 | 目标状态 |
|---------|---------|---------|
| 推理模式 | 单条处理 | 动态批量聚合 |
| 批量大小 | 固定为 1 | 1-32 动态调整 |
| 吞吐量 | ~50 QPS | ~200 QPS (4x) |
| P95 延迟 | ~100ms | <150ms |
| GPU 利用率 | ~40% | >80% |
| 超时策略 | 固定超时 | 动态超时控制 |

---

## 二、当前架构分析

### 2.1 现有代码结构

```
inference_service/
├── src/
│   ├── api/
│   │   └── routes/
│   │       └── inference.py       # 单条推理接口
│   ├── models/
│   │   ├── model_manager.py       # 模型管理器
│   │   └── mgeo_model.py          # MGeo 模型封装
│   └── processor/
│       └── converters.py          # 结果格式化
```

### 2.2 核心代码分析

#### 单条推理入口 ([`inference.py:18`](../src/api/routes/inference.py#L18))

```python
@router.post("/extract")
async def extract_entities(request: InferenceRequest):
    # 1. 加载模型
    model = model_manager.load_model(model_name)
    # 2. 单条推理
    result = model.extract_entities(request.Content)
    # 3. 返回结果
    return formatted_result
```

#### 模型推理方法 ([`mgeo_model.py:69`](../src/models/mgeo_model.py#L69))

```python
def extract_entities(self, text: str) -> Dict[str, Any]:
    # 使用 ModelScope pipeline 进行单条推理
    result = self.pipeline(input=text)
    return {"text": text, "entities": result}
```

### 2.3 痛点总结

1. **无批量聚合机制**：每个请求独立处理，无法利用批处理加速
2. **无请求队列**：缺乏智能队列管理，无法动态聚合请求
3. **无超时控制**：等待时间不可控，可能导致长尾延迟
4. **无并发保护**：高并发下可能出现 OOM

---

## 三、技术方案设计

### 3.1 架构设计

```
                    ┌─────────────────┐
                    │  FastAPI Router │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Batch Manager  │ ◄─── 动态批量管理器
                    │  - BatchQueue    │
                    │  - TimeoutCtrl   │
                    │  - SizeStrategy  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Model Executor │
                    │  - BatchInfer   │
                    │  - ThreadSafe    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  MGeo Model     │
                    │  (GPU Pipeline) │
                    └─────────────────┘
```

### 3.2 核心组件

#### 3.2.1 BatchManager (批量管理器)

**职责：** 请求聚合、批量调度、超时控制

```python
class BatchManager:
    def __init__(self,
                 max_batch_size: int = 32,
                 max_wait_time: float = 0.1):
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.queue = asyncio.Queue()

    async def submit(self, text: str) -> BatchFuture:
        """提交推理请求，返回 Future"""
        pass

    async def _batch_loop(self):
        """批量循环：聚合 + 调度"""
        while True:
            batch = await self._collect_batch()
            await self._execute_batch(batch)
```

#### 3.2.2 BatchExecutor (批量执行器)

**职责：** 批量推理执行、结果分发

```python
class BatchExecutor:
    async def execute_batch(self,
                            texts: List[str],
                            futures: List[BatchFuture]):
        """执行批量推理，分发结果"""
        # 1. 批量推理
        results = await self.model.batch_extract(texts)
        # 2. 结果分发
        for future, result in zip(futures, results):
            future.set_result(result)
```

#### 3.2.3 DynamicBatchStrategy (动态批量策略)

**职责：** 根据负载动态调整批量大小

```python
class DynamicBatchStrategy:
    def adjust_batch_size(self,
                          current_qps: float,
                          avg_latency: float) -> int:
        """根据 QPS 和延迟动态调整批量大小"""
        if avg_latency > self.latency_threshold:
            return max(1, self.current_batch_size // 2)
        elif current_qps > self.qps_threshold:
            return min(self.max_batch_size,
                       self.current_batch_size + 4)
        return self.current_batch_size
```

### 3.3 数据流设计

```
请求流：
Client Request 1 ──┐
Client Request 2 ──┼──► BatchQueue ──► [Batch Aggregation]
Client Request 3 ──┤                     (到达 max_size 或 max_wait)
Client Request 4 ──┘                              │
                                                  ▼
                                      [Batch Execution]
                                                  │
                                                  ▼
                                      [Result Distribution]
                                                  │
                       ┌──────────────────────────┼──────────────────────────┐
                       ▼                          ▼                          ▼
                 Response 1                  Response 2                  Response 3
```

---

## 四、迭代计划

### 阶段一：基础批量推理能力 (Week 1-2)

**目标：** 实现静态批量推理，验证技术可行性

| 任务 | 文件 | 工作内容 | 产出 |
|-----|------|---------|------|
| 1.1 | `src/batch/batch_manager.py` | 实现 BatchManager 基础框架 | 请求队列管理 |
| 1.2 | `src/models/mgeo_model.py` | 新增 `batch_extract_entities()` | 批量推理方法 |
| 1.3 | `src/api/routes/inference.py` | 新增 `/extract_batch` 接口 | 批量推理 API |
| 1.4 | `src/api/schemas.py` | 新增 `BatchInferenceRequest` | 批量请求模型 |
| 1.5 | `tests/test_batch_inference.py` | 单元测试 | 测试覆盖 >80% |

**验收标准：**
- [ ] 批量推理接口可正常运行
- [ ] 批量大小 32 时吞吐量 > 单条推理的 2x
- [ ] 单元测试全部通过

---

### 阶段二：动态批量聚合机制 (Week 3-4)

**目标：** 实现请求自动聚合，动态批量处理

| 任务 | 文件 | 工作内容 | 产出 |
|-----|------|---------|------|
| 2.1 | `src/batch/dynamic_batcher.py` | 实现动态批量聚合器 | 自动聚合逻辑 |
| 2.2 | `src/batch/batch_manager.py` | 集成超时控制机制 | 超时保护 |
| 2.3 | `src/config/batch_config.py` | 批量配置管理 | 配置模块 |
| 2.4 | `src/api/routes/inference.py` | 重构为批量模式 | 透明批量处理 |
| 2.5 | `tests/test_dynamic_batch.py` | 动态批量测试 | 测试套件 |

**核心逻辑：**

```python
async def dynamic_batch_loop():
    while True:
        # 收集请求：max_batch_size 或 max_wait_time
        batch = await collect_batch(
            max_size=dynamic_batch_size,
            max_wait=0.1  # 100ms 超时
        )
        # 执行批量推理
        await execute_batch(batch)
```

**验收标准：**
- [ ] 单条请求自动聚合为批量
- [ ] 批量超时机制生效 (max_wait_time)
- [ ] 低并发下不增加延迟 (<10ms)

---

### 阶段三：性能优化与监控 (Week 5-6)

**目标：** 优化性能，建立监控体系

| 任务 | 文件 | 工作内容 | 产出 |
|-----|------|---------|------|
| 3.1 | `src/batch/performance_monitor.py` | 性能监控模块 | QPS/延迟/GPU 指标 |
| 3.2 | `src/batch/dynamic_strategy.py` | 动态批量策略 | 自适应批量大小 |
| 3.3 | `src/utils/timer.py` | 高精度计时器 | 性能统计工具 |
| 3.4 | `src/api/routes/metrics.py` | Prometheus 指标接口 | 监控暴露 |
| 3.5 | `docs/performance_report.md` | 性能测试报告 | 基准数据 |

**优化方向：**

1. **GPU 优化**
   - 预分配 GPU 内存
   - 使用 CUDA Stream 并行
   - 混合精度推理 (FP16)

2. **CPU 优化**
   - 异步数据预处理
   - 结果序列化优化
   - 减少数据拷贝

3. **批量策略**
   ```python
   # 根据延迟动态调整批量大小
   if p95_latency > 150ms:
       batch_size = max(1, batch_size // 2)
   elif gpu_utilization < 70%:
       batch_size = min(32, batch_size + 4)
   ```

**验收标准：**
- [ ] 吞吐量提升至 200 QPS
- [ ] P95 延迟 < 150ms
- [ ] GPU 利用率 > 80%

---

### 阶段四：高可用与容错 (Week 7-8)

**目标：** 增强系统稳定性，实现优雅降级

| 任务 | 文件 | 工作内容 | 产出 |
|-----|------|---------|------|
| 4.1 | `src/batch/circuit_breaker.py` | 熔断器机制 | 故障隔离 |
| 4.2 | `src/batch/timeout_controller.py` | 超时控制优化 | 长尾请求保护 |
| 4.3 | `src/utils/health_check.py` | 健康检查增强 | 存活探针 |
| 4.4 | `src/api/routes/system.py` | 降级接口 | 优雅降级 |
| 4.5 | `docs/runbook.md` | 运维手册 | 故障处理指南 |

**容错机制：**

1. **熔断策略**
   - 连续失败 > 阈值 → 熔断
   - 熔断后降级为单条推理
   - 半开状态探测恢复

2. **超时策略**
   - 批量推理超时 → 拆分为小批量
   - 单条请求超时 → 返回部分结果

3. **内存保护**
   - 监控 GPU 内存使用
   - 超限拒绝新请求
   - 自动降级批量大小

**验收标准：**
- [ ] 熔断机制正确触发
- [ ] 故障恢复时间 < 30s
- [ ] 无内存泄漏

---

### 阶段五：压测与上线 (Week 9-10)

**目标：** 全面的压力测试，平滑上线

| 任务 | 工作内容 | 产出 |
|-----|---------|------|
| 5.1 | 编写压测脚本 | 压测工具 |
| 5.2 | 执行全链路压测 | 压测报告 |
| 5.3 | 灰度发布 (20% → 50% → 100%) | 上线计划 |
| 5.4 | 监控告警配置 | 告警规则 |
| 5.5 | 文档完善 | API 文档、运维手册 |

**压测场景：**

| 场景 | 并发 | 持续时间 | 目标 |
|-----|------|---------|------|
| 基准测试 | 10 | 10min | QPS > 100 |
| 峰值测试 | 100 | 5min | 无错误 |
| 稳定性测试 | 50 | 1h | 无内存泄漏 |
| 长尾测试 | 20 (文本长度 1k+) | 10min | P99 < 300ms |

**上线计划：**

```
Week 9: 灰度 20% (内部测试)
Week 10: 灰度 50% (部分用户)
Week 11: 全量发布 (监控 48h)
```

---

## 五、风险评估

### 5.1 技术风险

| 风险 | 概率 | 影响 | 应对措施 |
|-----|------|------|---------|
| MGeo 模型不支持批量推理 | 中 | 高 | 提前验证模型 API，准备 fallback 方案 |
| GPU 内存不足 | 中 | 中 | 实施内存监控，动态调整批量大小 |
| 批量推理延迟增加 | 低 | 中 | 设置最大等待时间，低并发退化为单条 |
| 并发竞争问题 | 低 | 高 | 使用 asyncio 锁和队列保护 |

### 5.2 业务风险

| 风险 | 影响 | 应对措施 |
|-----|------|---------|
| 单条请求延迟增加 | 用户体验下降 | 保留单条推理接口作为降级选项 |
| 批量失败影响范围扩大 | 故障放大 | 实施熔断和降级机制 |
| 新旧 API 兼容性 | 客户端升级 | 保持单条接口兼容，逐步迁移 |

---

## 六、配置参数

### 6.1 批量配置

```yaml
# config/batch_config.yaml
batch:
  # 基础配置
  enabled: true                    # 是否启用批量推理
  max_batch_size: 32               # 最大批量大小
  min_batch_size: 1                # 最小批量大小
  initial_batch_size: 8            # 初始批量大小

  # 超时配置
  max_wait_time: 0.1               # 最大等待时间 (秒)
  timeout_per_request: 5.0         # 单条请求超时 (秒)

  # 动态策略
  dynamic_sizing: true             # 启用动态批量大小
  adjust_interval: 10              # 调整间隔 (秒)
  latency_threshold: 0.15          # 延迟阈值 (秒)
  qps_threshold: 100               # QPS 阈值

  # 熔断配置
  circuit_breaker:
    enabled: true
    failure_threshold: 5           # 失败阈值
    recovery_timeout: 30           # 恢复超时 (秒)
    half_open_max_calls: 3         # 半开状态最大调用数

  # 降级配置
  fallback:
    enabled: true
    fallback_mode: single          # 降级模式: single / small_batch
    fallback_batch_size: 4         # 降级批量大小
```

### 6.2 环境变量

```bash
# .env
BATCH_ENABLED=true
MAX_BATCH_SIZE=32
MAX_WAIT_TIME=0.1
DYNAMIC_SIZING=true
LATENCY_THRESHOLD=0.15
GPU_MEMORY_THRESHOLD=0.9
```

---

## 七、监控指标

### 7.1 核心指标

| 指标 | 类型 | 目标值 |
|-----|------|-------|
| `batch_inference_qps` | Gauge | > 200 |
| `batch_inference_latency_p50` | Histogram | < 50ms |
| `batch_inference_latency_p95` | Histogram | < 150ms |
| `batch_inference_latency_p99` | Histogram | < 300ms |
| `batch_size_current` | Gauge | 1-32 |
| `batch_queue_length` | Gauge | < 100 |
| `gpu_utilization` | Gauge | > 80% |
| `gpu_memory_used` | Gauge | < 90% |

### 7.2 告警规则

```yaml
alerts:
  - name: HighLatency
    condition: p95_latency > 200ms
    duration: 5m
    severity: warning

  - name: LowThroughput
    condition: qps < 100
    duration: 10m
    severity: warning

  - name: HighGPUMemory
    condition: gpu_memory > 95%
    duration: 2m
    severity: critical

  - name: CircuitBreakerOpen
    condition: circuit_breaker_state == open
    duration: 1m
    severity: critical
```

---

## 八、测试策略

### 8.1 单元测试

```bash
# 运行单元测试
pytest tests/test_batch_inference.py -v --cov=src/batch
```

**测试覆盖目标：** > 80%

### 8.2 集成测试

```bash
# 运行集成测试
pytest tests/integration/test_batch_api.py -v
```

### 8.3 压力测试

使用现有的压测工具 ([`load_test_tools`](../../load_test_tools/)):

```bash
# 执行批量推理压测
python load_test_tools/test_scripts/batch_inference_test.py \
  --concurrent 50 \
  --duration 300 \
  --batch-size 16
```

---

## 九、回滚计划

### 9.1 回滚触发条件

- P95 延迟 > 300ms 持续 5 分钟
- 错误率 > 5% 持续 2 分钟
- GPU 内存 OOM
- 熔断器连续触发 3 次

### 9.2 回滚步骤

1. **紧急回滚** (配置变更)
   ```bash
   # 禁用批量推理
   export BATCH_ENABLED=false
   systemctl restart inference-service
   ```

2. **代码回滚** (Git 操作)
   ```bash
   git revert <commit-hash>
   git push origin dev
   ```

3. **流量切换** (Nginx/网关)
   ```bash
   # 切换到旧版本服务
   nginx -s reload
   ```

---

## 十、后续优化方向

1. **模型优化**
   - 模型量化 (INT8/FP16)
   - 模型蒸馏
   - TensorRT 加速

2. **架构优化**
   - 多 GPU 并行
   - 分布式推理
   - 推理服务网格

3. **功能增强**
   - 优先级队列
   - 多租户隔离
   - 缓存机制 (Redis)

---

## 十一、附录

### A. 相关文件清单

| 文件路径 | 说明 | 状态 |
|---------|------|------|
| `src/api/routes/inference.py` | 推理接口 | 需修改 |
| `src/models/mgeo_model.py` | 模型封装 | 需扩展 |
| `src/api/schemas.py` | 数据模型 | 需扩展 |
| `src/batch/batch_manager.py` | 批量管理器 | 新建 |
| `src/batch/dynamic_batcher.py` | 动态批量器 | 新建 |
| `src/batch/performance_monitor.py` | 性能监控 | 新建 |
| `src/config/batch_config.py` | 批量配置 | 新建 |

### B. 参考文档

- [MGeo 模型文档](../models/mgeo_geographic_composition_analysis_chinese_base/README.md)
- [FastAPI 异步编程指南](https://fastapi.tiangolo.com/async/)
- [ModelScope Pipeline 文档](https://modelscope.cn/docs)
- [PyTorch 批量推理最佳实践](https://pytorch.org/tutorials/advanced/gpu_quantization.html)

### C. 关键联系人

| 角色 | 姓名 | 职责 |
|-----|------|------|
| 技术负责人 | - | 架构设计、技术决策 |
| 开发工程师 | - | 功能开发、单元测试 |
| 运维工程师 | - | 部署、监控、故障处理 |
| 测试工程师 | - | 集成测试、压测执行 |

---

**文档维护：** 本文档随项目进展持续更新，每次重大变更需更新版本号。

**最后更新：** 2026-02-11
