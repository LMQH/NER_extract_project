# MGeo 数据匹配处理逻辑说明文档

## 目录

1. [概述](#概述)
2. [系统架构](#系统架构)
3. [核心组件](#核心组件)
4. [处理流程](#处理流程)
5. [详细说明](#详细说明)
6. [数据格式](#数据格式)
7. [状态码说明](#状态码说明)

---

## 概述

`processor_mgeo` 模块是一个三阶段的地址数据匹配处理系统，用于将模型提取的地址信息与数据库中的标准地址数据进行匹配、补全和校验。

### 主要功能

- **地址匹配**: 通过双向模糊匹配算法，将输入地址字段与数据库中的标准地址进行匹配
- **候选处理**: 处理多个候选结果，通过上下级关系确定唯一结果
- **数据校验**: 检查空字段、候选值、未匹配字段，设置状态码和警告信息
- **地址补全**: 根据已确定的地址信息，向上追溯补全缺失的上级地址信息

### 处理层级

系统处理四个层级的地址信息：
- **ProvinceName** (省域级, region_type=1001)
- **CityName** (城市级, region_type=1002)
- **ExpAreaName** (区县级, region_type=1003)
- **StreetName** (街道乡镇级, region_type=1004)

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    AddressCompleter                          │
│                  (地址补全协调器)                              │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Stage1Matcher│    │Stage2Resolver │    │Stage3Validator│
│  (第一阶段)   │    │  (第二阶段)    │    │  (第三阶段)    │
│  地址数据匹配  │    │  候选结果处理  │    │  数据校验      │
└──────────────┘    └──────────────┘    └──────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                    ┌───────▼───────┐
                    │ RegionMatcher  │
                    │  (区域匹配器)   │
                    └───────────────┘
```

---

## 核心组件

### 1. AddressCompleter (地址补全器)

**位置**: `address_completer.py`

**职责**: 
- 协调三个阶段的处理流程
- 处理直辖市数据调整（预处理）
- 初始化各个阶段的处理器

**主要方法**:
- `complete_address_info()`: 执行完整的地址补全流程
- `complete_extract_response()`: 补全ExtractResponse格式的响应数据
  - 支持状态码优先级检查：如果原始响应已有101或102状态码，不会被103覆盖
- `_preprocess_direct_city_fix()`: 预处理修复直辖市数据
- `get_parent_chain()`: 获取父级链，从当前区域向上查找所有父级
- `complete_all_fields_from_chain()`: 从区域链补全所有字段（向上追溯）

### 2. Stage1Matcher (第一阶段匹配器)

**位置**: `stage1_matcher.py`

**职责**: 执行四个匹配任务，收集所有候选结果

**四个匹配任务**:

1. **任务1: StreetName匹配** (region_type=1004)
   - 依次使用 StreetName → AreasInfo → Address 进行匹配
   - 匹配成功后，从AreasInfo或Address中清除已匹配的region_name

2. **任务2: ExpAreaName匹配** (region_type=1003)
   - 使用 StreetName、AreasInfo、Address 在1003中匹配（收集所有结果）
   - 无论上一步是否成功，都使用 ExpAreaName 在1003中匹配

3. **任务3: CityName匹配** (region_type=1002)
   - 使用 ExpAreaName → CityName 进行匹配

4. **任务4: ProvinceName匹配** (region_type=1001)
   - 使用 CityName → ProvinceName 进行匹配
   - 支持去掉"特别行政区"后缀后再次匹配

**输出**: 四个候选表
```python
{
    'StreetName': [...],
    'ExpAreaName': [...],
    'CityName': [...],
    'ProvinceName': [...]
}
```

### 3. Stage2Resolver (第二阶段解析器)

**位置**: `stage2_resolver.py`

**职责**: 从最高级别向下筛选，通过parent_id关系确定唯一结果

**处理优先级**: ProvinceName > CityName > ExpAreaName > StreetName

**主要执行方法**:
- `execute_stage2_resolve()`: 执行完整的第二阶段处理流程，包括：
  1. 按优先级处理四个字段的候选表（resolve阶段）
  2. 执行方法1-6的后续处理

**核心方法**:

1. **向下过滤** (`filter_by_parent_id`)
   - 根据上级的id筛选下级候选表中的parent_id
   - 如果筛选后只有1个结果，确定为唯一值

2. **中间层级补全** (`complete_middle_level_from_candidates`)
   - 包含两个流程：上下级关联验证和补全（新流程）、中间层级补全（原有流程）
   
   **新流程：上下级关联验证和补全**
   - 触发条件：上级ID有效、本级不为空、下级唯一确定
   - 判断下级的parent_id是否在本级结果中匹配：
     - 如果本级是唯一值：检查下级的parent_id == 本级的id
     - 如果本级是候选表：检查下级的parent_id是否在候选列表的id集合中
   - 处理三种情况：
     - 无匹配 → 调用上下级补全函数 (`complete_middle_level_with_upper_and_lower`)
     - 有匹配但上级不匹配 → 调用上下级补全函数
     - 上级、本级、下级均关联 → 选择此条记录为本级的唯一值
   
   **原有流程：中间层级补全**
   - 触发条件：本级的上级id唯一，且本级信息为空
   - 从缓存中过滤出本级的候选表（通过region_type初筛，不会查询所有数据）
   - 支持所有层级：CityName、ExpAreaName、StreetName
   - 如果过滤后只有一个值，采用唯一值格式
   - 如果过滤后有多个值，尝试通过下级唯一值进行筛选：
     - 查找下级字段（CityName的下级是ExpAreaName，ExpAreaName的下级是StreetName）
     - 如果下级是唯一值，根据下级值的parent_id筛选本级候选表
     - 筛选成功则得到本级唯一值，失败则保留当前候选表格式
   
   **上下级补全函数** (`complete_middle_level_with_upper_and_lower`)
   - 通过上级ID从缓存筛选本级候选表
   - 用下级的parent_id筛选本级候选表
   - 如果筛选后唯一确定，设置为唯一值格式；否则恢复原始值

3. **候选值级联匹配** (`cascade_match_candidates` 和 `cascade_match_unique_to_upper`)
   - 由下到上依次判断相邻字段（StreetName → ExpAreaName → CityName → ProvinceName）
   - **情况1：本级是候选表** (`cascade_match_candidates`)
     - 如果本级是候选表，上级是候选表或唯一值，则执行级联匹配
     - 提取上级的有效id集合
     - 筛选本级候选：只保留parent_id在上级id集合中的候选
     - 如果筛选后本级候选唯一，筛选上级候选只保留对应的项
     - 如果筛选后本级候选为空，恢复原始值并记录级联匹配失败状态
   - **情况2：本级是唯一值** (`cascade_match_unique_to_upper`)
     - 如果本级是唯一值，上级是候选表或唯一值，则执行级联匹配
     - 提取上级的有效id集合
     - 检查本级的parent_id是否在上级的id集合中
     - 如果不在，记录级联匹配失败状态（用于触发方法4的特殊情况处理）
   - 级联匹配失败状态会传递给方法4，用于优化触发条件

4. **特殊情况中间层级确定** (`resolve_middle_levels_by_tracing`)
   - 触发条件：
     - **条件一（硬性条件，必须满足）**：
       - ProvinceName唯一确定
       - StreetName为候选表格式
     - **条件二（可选）**：
       - CityName不具备唯一值（为空或候选表）**AND** ExpAreaName不具备唯一值（为空或候选表）
     - **条件三（可选）**：
       - CityName与ExpAreaName级联匹配失败 **AND** ExpAreaName与StreetName级联匹配失败
     - **最终触发条件**：条件一 AND (条件二 OR 条件三)
   - 逻辑：
     - 在循环外先获取一次缓存数据（ExpAreaName和CityName的所有记录），避免重复获取
     - 遍历StreetName候选表，追溯每条候选的上级信息链（StreetName → ExpAreaName → CityName）
     - 验证CityName的parent_id是否等于ProvinceName的id
     - 如果找到匹配的信息链，将所有相关字段设置为唯一值

5. **向上追溯** (`trace_upward_recursively`)
   - 步骤0：转换单候选格式为唯一值格式（在向上追溯之前执行）
   - 从下到上依次检查唯一确定的字段（StreetName → ExpAreaName → CityName → ProvinceName）
   - 递归向上追溯所有上级，通过parent_id查找上级区域信息
   - 字段为空时直接补全；字段是候选表时尝试筛选；字段是唯一值但id不一致时，直接用追溯到的值替换原有值

6. **去除重复** (`remove_duplicate_region_names`)
   - 检查上下级region_name是否重复
   - 如果重复且是相邻层级，清除下级

**辅助功能**:
- `truncate_candidates()`: 截断候选表，保留前max_candidates_count个元素（通过环境变量MAX_CANDIDATES_COUNT配置，默认20）
- `convert_candidate_tables_to_result_format()`: 将第一阶段返回的候选列表转换为result字典中的候选表格式
- `convert_single_candidate_to_unique()`: 将仅有一个候选的候选格式转换为唯一值格式（在第一阶段完成后执行）
- `get_unique_record()`: 从result中提取唯一值记录
- `merge_candidate()`: 将追溯到的值去重后追加到候选表中（基于id去重）
- `convert_unique_to_candidates()`: 将唯一值格式转换为候选表格式

**输出**: 更新后的result字典，包含唯一值或候选表

### 4. Stage3Validator (第三阶段校验器)

**位置**: `stage3_validator.py`

**职责**: 检查空字段、候选值、未匹配字段，设置状态码和警告信息

**校验步骤**:

1. **检查空字段**: 检查四个关键数据块是否为空
2. **检查候选值**: 检查是否存在未确定的多个候选值
3. **检查未匹配字段**: 检查region_name不为空但是id为空的情况
4. **设置状态码**: 根据校验结果设置ResultCode

**注意**: 转换单候选格式为唯一值已在第一阶段完成后执行

### 5. RegionMatcher (区域匹配器)

**位置**: `matcher.py`

**职责**: 提供双向模糊匹配功能

**匹配策略**:

1. **精确匹配** (对于非AreasInfo/Address字段)
   - `region_name = field_value`

2. **双向模糊匹配** (LIKE匹配)
   - 正向匹配: `region_name LIKE %field_value%`
   - 反向匹配: `field_value LIKE %region_name%`

3. **匹配质量评分**
   - 精确匹配: 1.0
   - 正向匹配: 基础分 + 长度相似度 + 覆盖率
   - 反向匹配: 基础分 + 长度相似度 + 覆盖率

4. **过滤机制**
   - 最小长度检查 (MIN_MATCH_LENGTH)
   - 黑名单过滤 (GENERIC_TERMS_BLACKLIST)

**返回结果**:
- 唯一结果: `Dict[str, Any]`
- 多个结果: `List[Dict[str, Any]]`
- 无结果: `None`

### 6. InputValidator (输入数据校验器)

**位置**: `input_validator.py`

**职责**: 校验和清洗输入数据，确保数据格式统一、安全可靠

**校验内容**:
- 类型统一: 字典类型提取region_name
- 去除空格和标点符号
- 长度限制 (MAX_FIELD_LENGTH=50)
- 敏感词过滤 (防止SQL注入等攻击)

### 7. Converters (格式转换器)

**位置**: `converters.py`

**职责**: 将不同模型的返回结果转换为统一格式

**主要函数**:
- `convert_mgeo_tagging_to_output_format()`: 转换mgeo_geographic_elements_tagging_chinese_base模型结果
- `convert_mgeo_to_output_format()`: 转换mgeo模型结果
- `reorder_data_fields()`: 重新排序Data字段

---

## 处理流程

### 完整流程

```
输入数据
    │
    ▼
[预处理] 处理直辖市数据调整
    │
    ▼
[第一阶段] 地址数据匹配
    │
    ├─ 任务1: StreetName匹配 (1004)
    ├─ 任务2: ExpAreaName匹配 (1003)
    ├─ 任务3: CityName匹配 (1002)
    └─ 任务4: ProvinceName匹配 (1001)
    │
    ▼
生成四个候选表
    │
    ▼
[第一阶段完成后] 格式转换
    │
    ├─ 将候选表转换为result格式
    └─ 转换单候选格式为唯一值格式
    │
    ▼
[第二阶段] 候选结果处理
    │
    ├─ [Resolve阶段] 按优先级处理四个字段的候选表
    │   ├─ ProvinceName → CityName → ExpAreaName → StreetName
    │   └─ 在resolve过程中已整合方法1和方法2的逻辑
    │
    ├─ 方法1: 向下过滤 (根据上级id筛选下级，已整合在resolve阶段)
    ├─ 方法2: 中间层级补全 (使用上级id从缓存过滤本级数据，已整合在resolve阶段)
    ├─ 方法3: 候选值级联匹配 (情况1: 本级候选表级联匹配；情况2: 本级唯一值级联匹配)
    ├─ 方法4: 特殊情况中间层级确定 (通过追溯StreetName候选的上级信息链确定中间层级)
    ├─ 方法5: 向上追溯 (从唯一值递归追溯上级)
    └─ 方法6: 去除重复 (清除上下级重复的region_name)
    │
    ▼
[第三阶段] 数据校验
    │
    ├─ 检查空字段
    ├─ 检查候选值
    ├─ 检查未匹配字段
    └─ 设置状态码和警告信息
    │
    ▼
输出结果
```

### 详细流程说明

#### 阶段1: 地址数据匹配

**任务1: StreetName匹配** (region_type=1004)

```
步骤1: 使用StreetName匹配
    ├─ 成功 → 返回结果
    └─ 失败 → 继续步骤2

步骤2: 使用AreasInfo匹配
    ├─ 成功 → 返回结果，清除AreasInfo中匹配到的region_name
    └─ 失败 → 继续步骤3

步骤3: 使用Address匹配
    ├─ 成功 → 返回结果，清除Address中匹配到的region_name
    └─ 失败 → 返回空列表
```

**任务2: ExpAreaName匹配** (region_type=1003)

```
步骤1: 使用StreetName在1003中匹配 (收集所有结果)
步骤2: 使用AreasInfo在1003中匹配 (收集所有结果，清除AreasInfo)
步骤3: 使用Address在1003中匹配 (收集所有结果，清除Address)
步骤4: 使用ExpAreaName在1003中匹配 (收集所有结果)
    │
    ▼
去重 (基于id)
```

**任务3: CityName匹配** (region_type=1002)

```
步骤1: 使用ExpAreaName在1002中匹配
步骤2: 使用CityName在1002中匹配
    │
    ▼
去重 (基于id)
```

**任务4: ProvinceName匹配** (region_type=1001)

```
步骤1: 使用CityName在1001中匹配
步骤2: 使用ProvinceName在1001中匹配
    ├─ 成功 → 返回结果
    └─ 失败 → 尝试去掉"特别行政区"后缀再匹配
    │
    ▼
去重 (基于id)
```

#### 阶段1完成后: 格式转换

**步骤1: 将候选表转换为result格式**
- 将第一阶段返回的候选列表转换为result字典中的候选表格式
- 单候选值也会先转换为候选表格式，由下一步处理

**步骤2: 转换单候选格式为唯一值格式**
- 检查所有字段（ProvinceName, CityName, ExpAreaName, StreetName）
- 如果字段是候选格式且只有一个候选值，转换为唯一值格式
- 此步骤在第一阶段完成后立即执行，确保后续处理时单候选值已经是唯一值格式

#### 阶段2: 候选结果处理

**处理顺序**: ProvinceName → CityName → ExpAreaName → StreetName

**方法1: 向下过滤**

```
如果上级已确定 (唯一值)
    │
    ▼
根据上级的id筛选下级候选表中的parent_id
    │
    ├─ 筛选后只有1个结果 → 确定为唯一值
    ├─ 筛选后有多个结果 → 保留候选表
    └─ 筛选后没有结果 → 保留原候选表，添加警告
```

**方法2: 中间层级补全**

包含两个流程：

**流程1: 上下级关联验证和补全（新流程）**

```
触发条件：上级ID有效、本级不为空、下级唯一确定
    │
    ▼
判断下级的parent_id是否在本级结果中匹配
    │
    ├─ 本级是唯一值 → 检查下级的parent_id == 本级的id
    ├─ 本级是候选表 → 检查下级的parent_id是否在候选列表的id集合中
    │
    ▼
处理三种情况：
    │
    ├─ 情况1：无匹配 → 调用上下级补全函数
    │   │
    │   ├─ 通过上级ID从缓存筛选本级候选表
    │   ├─ 用下级的parent_id筛选本级候选表
    │   ├─ 筛选成功（唯一确定） → 设置为唯一值格式
    │   └─ 筛选失败 → 恢复原始值
    │
    ├─ 情况2：有匹配但上级不匹配 → 调用上下级补全函数
    │   └─ （同上）
    │
    └─ 情况3：上级、本级、下级均关联 → 选择此条记录为本级的唯一值
```

**流程2: 中间层级补全（原有流程）**

```
触发条件：本级的上级id唯一，且本级信息为空
    │
    ▼
使用上级的唯一id从缓存中过滤本级数据
    │
    ├─ 通过region_type初筛（不会查询所有数据）
    │   └─ 从缓存获取指定region_type的所有记录
    │
    ▼
使用upper_parent_id过滤出parent_id匹配的记录
    │
    ├─ 过滤后只有1个结果 → 本级数据采用唯一值格式
    ├─ 过滤后有多个结果 → 尝试通过下级唯一值进行筛选
    │   │
    │   ├─ 查找下级字段（CityName的下级是ExpAreaName，ExpAreaName的下级是StreetName）
    │   │
    │   ├─ 下级是唯一值？
    │   │   ├─ 是 → 根据下级值的parent_id筛选本级候选表
    │   │   │   ├─ 筛选成功（只有1个结果） → 本级数据采用唯一值格式
    │   │   │   └─ 筛选失败 → 保留当前候选表格式
    │   │   └─ 否 → 保留当前候选表格式
    │   │
    │   └─ 没有下级字段 → 保留当前候选表格式
    │
    └─ 过滤后没有结果 → 返回None

支持所有层级：
- ProvinceName已确定 → 补全CityName
- ProvinceName或CityName已确定 → 补全ExpAreaName
- ExpAreaName、CityName或ProvinceName已确定 → 补全StreetName
```

**方法3: 候选值级联匹配**

包含两种情况：

**情况1：本级是候选表** (`cascade_match_candidates`)

```
由下到上依次判断相邻字段（StreetName → ExpAreaName → CityName → ProvinceName）
    │
    ▼
如果本级是候选表，且上级是候选表或唯一值
    │
    ▼
提取上级的有效id集合
    │
    ▼
筛选本级候选：只保留parent_id在上级id集合中的候选
    │
    ├─ 筛选后本级候选为空
    │   ├─ 恢复原始值
    │   └─ 记录级联匹配失败状态（用于触发方法4）
    ├─ 筛选后本级候选唯一
    │   ├─ 更新本级为唯一值
    │   └─ 如果上级是候选表，筛选上级候选只保留对应的id
    │       └─ 如果上级筛选后唯一，转换为唯一值格式
    └─ 筛选后本级候选不唯一
        ├─ 更新本级候选表
        └─ 如果上级是候选表，筛选上级候选只保留有对应关系的id
            └─ 如果上级筛选后唯一，转换为唯一值格式
```

**情况2：本级是唯一值** (`cascade_match_unique_to_upper`)

```
由下到上依次判断相邻字段（StreetName → ExpAreaName → CityName → ProvinceName）
    │
    ▼
如果本级是唯一值，且上级是候选表或唯一值
    │
    ▼
提取上级的有效id集合
    │
    ▼
检查本级的parent_id是否在上级的id集合中
    │
    ├─ 匹配成功 → 记录成功，继续处理
    └─ 匹配失败 → 记录级联匹配失败状态（用于触发方法4）
```

**方法4: 特殊情况中间层级确定**

```
触发条件检查：
    │
    ├─ 条件一（硬性条件，必须满足）：
    │   ├─ ProvinceName唯一确定 ✓
    │   └─ StreetName为候选表格式 ✓
    │
    ├─ 条件二（可选）：
    │   ├─ CityName不具备唯一值（为空或候选表） ✓
    │   └─ ExpAreaName不具备唯一值（为空或候选表） ✓
    │
    ├─ 条件三（可选）：
    │   ├─ CityName与ExpAreaName级联匹配失败 ✓
    │   └─ ExpAreaName与StreetName级联匹配失败 ✓
    │
    └─ 最终触发条件：条件一 AND (条件二 OR 条件三)
    │
    ▼
优化：在循环外先获取一次缓存数据
    ├─ 获取ExpAreaName的所有记录（通过region_type初筛）
    └─ 获取CityName的所有记录（通过region_type初筛）
    │
    ▼
遍历StreetName候选表
    │
    ▼
对每条StreetName候选：
    │
    ├─ 获取parent_id（ExpAreaName的id）
    │   └─ 从已获取的缓存中查找ExpAreaName记录
    │
    ├─ 获取ExpAreaName的parent_id（CityName的id）
    │   └─ 从已获取的缓存中查找CityName记录
    │
    └─ 验证信息链：
        ├─ CityName的parent_id == ProvinceName的id
        │   └─ 找到匹配的信息链，设置所有相关字段为唯一值，方法成功，结束循环
        └─ 不匹配 → 继续下一条候选
    │
    ▼
如果所有候选都遍历完仍未找到匹配的信息链 → 方法失败，保持原状态
```

**方法5: 向上追溯**

```
从下到上依次检查唯一确定的字段
(StreetName → ExpAreaName → CityName → ProvinceName)
    │
    ▼
通过parent_id查找直接上级
    │
    ├─ 字段为空 → 直接补全
    ├─ 字段是候选表 → 尝试筛选
    │   ├─ 筛选成功 → 更新为唯一值
    │   └─ 筛选失败 → 直接用追溯到的值替换原有值，记录警告
    └─ 字段是唯一值 → 检查id是否一致
        ├─ 一致 → 记录成功对应
        └─ 不一致 → 直接用追溯到的值替换原有值，记录警告
            └─ 警告信息："{字段名}检测到与下级信息不匹配，已根据数据库完成替换"
    │
    ▼
递归追溯更上级
```

**方法6: 去除重复**

```
由上往下检查
    │
    ▼
如果本级是唯一值，且region_name与下级重复
    │
    ▼
检查region_type是否相邻层级
    │
    ├─ 是相邻层级 → 清空下级
    └─ 不是相邻层级 → 保留
```

#### 阶段3: 数据校验

**注意**: 转换单候选格式为唯一值已在第一阶段完成后执行，此处不再重复执行

**步骤1: 检查空字段**

```
检查四个关键数据块是否为空
    │
    ├─ StreetName为空 → 检查AreasInfo和Address
    │   ├─ 都为空 → "StreetName 街道乡镇级信息为空"
    │   └─ 有值 → "StreetName 街道乡镇级信息在数据库中无匹配"
    └─ 其他字段为空 → 添加对应警告信息
```

**步骤2: 检查候选值**

```
检查是否存在未确定的多个候选值
    │
    ├─ 存在 → 添加警告信息
    └─ 不存在 → 跳过
```

**步骤3: 检查未匹配字段**

```
检查region_name不为空但是id为空的情况
    │
    ├─ 存在 → 添加警告信息
    └─ 不存在 → 跳过
```

**步骤4: 设置状态码**

```
检查是否存在空字段或候选值警告
    │
    ├─ 存在 (排除"StreetName 街道乡镇级信息在数据库中无匹配")
    │   └─ ResultCode = '103', Success = False
    └─ 不存在
        └─ ResultCode = '100', Success = True
```

---

## 详细说明

### 匹配算法

#### 双向模糊匹配

系统使用双向模糊匹配算法，支持以下匹配方式：

1. **精确匹配**
   ```python
   region_name == field_value
   ```

2. **正向匹配**
   ```python
   field_value in region_name
   # 例如: "北京" in "北京市"
   ```

3. **反向匹配**
   ```python
   region_name in field_value
   # 例如: "北京市" in "北京市朝阳区"
   ```

#### 匹配质量评分

匹配结果会根据以下因素计算得分：

- **精确匹配**: 1.0分
- **正向匹配**: 基础分(0.5) + 长度相似度(0-0.3) + 覆盖率(0-0.2)
- **反向匹配**: 基础分(0.3) + 长度相似度(0-0.3) + 覆盖率(0-0.2)

如果最高分明显高于次高分（差距>0.2），返回唯一结果；否则返回候选列表。

#### 过滤机制

1. **最小长度检查**: 区域名称长度必须 >= MIN_MATCH_LENGTH
2. **黑名单过滤**: 过滤通用词（如"区"、"县"、"市"等）

### 上下级关系处理

系统通过 `parent_id` 字段维护地址的上下级关系：

```
ProvinceName (1001)
    │
    └─ CityName (1002) [parent_id = ProvinceName.id]
        │
        └─ ExpAreaName (1003) [parent_id = CityName.id]
            │
            └─ StreetName (1004) [parent_id = ExpAreaName.id]
```

### 直辖市处理

系统对直辖市进行特殊处理：

1. **识别直辖市**: 检查CityName是否为"北京市"、"天津市"、"上海市"、"重庆市"
2. **数据调整**:
   - 将CityName的数据移动到ProvinceName
   - 将ExpAreaName移动到CityName
   - 清空ExpAreaName

### 特别行政区处理

1. **预处理**: 删除type="PD"且span="特别行政区"的条目
2. **后处理**: 如果ProvinceName为"香港"或"澳门"，且原始文本包含"特别行政区"，补全为"香港特别行政区"或"澳门特别行政区"
3. **匹配**: 如果ProvinceName匹配失败，尝试去掉"特别行政区"后缀再匹配

---

## 数据格式

### 输入数据格式

```python
{
    "ProvinceName": "广东省",  # 字符串或字典
    "CityName": "深圳市",
    "ExpAreaName": "龙岗区",
    "StreetName": "坂田街道",
    "AreasInfo": "坂田街道长坑路",
    "Address": "长坑路西2巷2号202",
    "Mobile": "13800138000",
    "Name": "张三"
}
```

### 输出数据格式

#### 唯一值格式

```python
{
    "ProvinceName": {
        "id": 1001,
        "parent_id": 0,
        "region_name": "广东省",
        "region_type": 1001
    },
    "CityName": {
        "id": 2001,
        "parent_id": 1001,
        "region_name": "深圳市",
        "region_type": 1002
    }
}
```

#### 候选表格式

```python
{
    "ProvinceName": {
        "candidates": [
            {"id": 1001, "parent_id": 0, "region_name": "广东省"},
            {"id": 1002, "parent_id": 0, "region_name": "广西壮族自治区"}
        ],
        "region_type": 1001
    }
}
```

#### 完整响应格式

```python
{
    "EBusinessID": "2223333",
    "Data": {
        "ProvinceName": {...},
        "CityName": {...},
        "ExpAreaName": {...},
        "StreetName": {...},
        "AreasInfo": "坂田街道长坑路",
        "Address": "长坑路西2巷2号202",
        "others": "",
        "Mobile": "13800138000",
        "Name": "张三"
    },
    "Success": True,
    "Reason": "解析成功",
    "ResultCode": "100",
    "Warning": []
}
```

---

## 状态码说明

### ResultCode 状态码

- **100**: 解析成功，所有地址信息都已确定
- **103**: 地址无法完全确定（存在空字段或候选值）

### Warning 警告信息

常见的警告信息包括：

- `"ProvinceName 省域级信息为空"`
- `"CityName 城市级信息为空"`
- `"ExpAreaName 区县级信息为空"`
- `"StreetName 街道乡镇级信息为空"`
- `"StreetName 街道乡镇级信息在数据库中无匹配"`
- `"ProvinceName 省域级信息存在多个候选值无法确定"`
- `"CityName 城市级信息存在多个候选值无法确定"`
- `"ExpAreaName 区县级信息存在多个候选值无法确定"`
- `"StreetName 街道乡镇级信息存在多个候选值无法确定"`
- `"ProvinceName 信息无法在数据库中确定"`
- `"CityName 信息无法在数据库中确定"`
- `"ExpAreaName 信息无法在数据库中确定"`
- `"StreetName 信息无法在数据库中确定"`
- `"ExpAreaName与StreetName不存在级联关系"`
- `"CityName与ExpAreaName不存在级联关系"`
- `"ProvinceName与CityName不存在级联关系"`
- `"{字段名}检测到与下级信息不匹配，已根据数据库完成替换"` (如："CityName检测到与下级信息不匹配，已根据数据库完成替换")

---

## 使用示例

### 基本使用

```python
from src.processor_mgeo import AddressCompleter
from src.database import DatabaseConnection

# 初始化数据库连接
db = DatabaseConnection()

# 创建地址补全器
completer = AddressCompleter(db)

# 输入数据
input_data = {
    "ProvinceName": "广东省",
    "CityName": "深圳市",
    "ExpAreaName": "龙岗区",
    "StreetName": "坂田街道",
    "AreasInfo": "坂田街道长坑路",
    "Address": "长坑路西2巷2号202"
}

# 执行地址补全
result = completer.complete_address_info(input_data)

# 查看结果
print(f"ResultCode: {result['ResultCode']}")
print(f"Success: {result['Success']}")
print(f"Warning: {result['Warning']}")
```

### 处理ExtractResponse格式

```python
# ExtractResponse格式的响应
response = {
    "EBusinessID": "2223333",
    "Data": {
        "ProvinceName": "广东省",
        "CityName": "深圳市",
        "ExpAreaName": "龙岗区",
        "StreetName": "坂田街道",
        "AreasInfo": "坂田街道长坑路",
        "Address": "长坑路西2巷2号202",
        "Mobile": "13800138000",
        "Name": "张三"
    },
    "Success": True,
    "Reason": "解析成功",
    "ResultCode": "100"
}

# 补全地址信息
completed_response = completer.complete_extract_response(response)
```

---

## 注意事项

1. **数据库表结构**: 系统依赖数据库中的 `region_table` 表，表结构需包含以下字段：
   - `id`: 区域ID
   - `parent_id`: 父级区域ID
   - `region_name`: 区域名称
   - `region_type`: 区域类型 (1001/1002/1003/1004)
   - `is_deleted`: 删除标记

2. **缓存机制**: 系统使用Redis缓存区域数据，提高查询性能

3. **日志记录**: 系统使用Python logging模块记录详细的处理日志，便于调试和问题排查

4. **错误处理**: 系统在关键步骤都有异常处理，确保不会因为单个错误导致整个流程失败

5. **性能优化**: 
   - 使用缓存减少数据库查询
   - 批量处理候选结果
   - 按优先级处理，尽早确定唯一值
   - 候选表截断：通过环境变量MAX_CANDIDATES_COUNT（默认20）限制候选表的最大元素数量，避免候选表过大影响性能

---

## 扩展说明

### 添加新的区域类型

如果需要添加新的区域类型（如"社区"），需要：

1. 在 `region_type_map` 中添加新的映射
2. 在 `Stage1Matcher` 中添加新的匹配任务
3. 在 `Stage2Resolver` 中添加新的解析方法
4. 在 `Stage3Validator` 中添加新的校验逻辑

### 自定义匹配规则

可以通过修改 `RegionMatcher` 类中的 `calculate_match_score` 方法来自定义匹配评分规则。

### 自定义过滤规则

可以通过修改 `RegionMatcher` 类中的 `should_skip_region` 方法来自定义过滤规则。

---

## 版本历史

- **v1.0**: 初始版本，实现基本的三阶段处理流程
- **v1.1**: 添加直辖市处理逻辑
- **v1.2**: 添加特别行政区处理逻辑
- **v1.3**: 优化匹配算法，添加匹配质量评分
- **v1.4**: 添加向上追溯和去除重复功能
- **v1.5**: 重新设计中间层级补全方法，使用上级id从缓存过滤本级数据，支持所有层级
- **v1.6**: 优化向上追溯逻辑，字段不一致时直接替换而非转换为候选表；启用级联匹配警告信息
- **v1.7**: 将单候选格式转换提前到阶段2的方法5中执行；优化代码结构，提取公共方法减少重复代码
- **v1.8**: 添加方法4（特殊情况中间层级确定），用于解决省级唯一、街道级为候选表、中间两个层级均不具备唯一值时的特殊情况
- **v1.9**: 优化方法2（中间层级补全），新增上下级关联验证和补全流程，当本级不为空且下级是唯一值时，通过上下级关联验证确定本级唯一值；优化方法4触发条件，支持级联匹配失败状态；添加候选表截断功能，通过MAX_CANDIDATES_COUNT环境变量控制候选表最大元素数量
- **v1.10**: 优化方法3（候选值级联匹配），新增情况2：本级为唯一值的级联匹配（`cascade_match_unique_to_upper`），记录级联匹配失败状态；调整方法4和方法5的执行顺序，将特殊情况中间层级确定提前到向上追溯之前执行；优化方法4（特殊情况中间层级确定）的缓存获取逻辑，在循环外先获取一次缓存数据，避免重复获取；增强级联匹配失败状态传递机制，用于优化方法4的触发条件
- **v1.11**: 优化格式转换流程，将候选表转换为result格式和单候选值转换提前到第一阶段完成后立即执行；更新文档说明，明确格式转换步骤的执行时机；完善AddressCompleter的方法说明，添加get_parent_chain和complete_all_fields_from_chain方法；完善Stage2Resolver的辅助功能说明；添加complete_extract_response方法的状态码优先级检查说明

---

## 相关文档

- [实体映射配置说明](../md_document/entity_mapping_README.md)
- [候选结果处理说明](../md_document/candidates.md)
- [BUG解决方案分析](../md_document/BUG解决方案分析.md)

