# K-Book 当前设计基线测试报告

## 1. 结论

当前 K-Book 需求、领域模型和第一期数据库迁移规格已经完成一次系统性验收。

验收结论：

- 9 项已确认需求均有明确边界和开发阶段。
- 领域关系与 Open Notebook 现有 Source、Notebook 和 Reference 模型兼容。
- 迁移候选结构可在 SurrealDB 2.6.5 创建、约束和回滚。
- 发现并修复 1 个现有代码缺陷。
- 发现并修复 1 个迁移查询错误。
- 发现并修复 pip 开发安装缺少异步测试插件的问题。
- 后端完整测试通过。
- 前端单元测试通过，ESLint 无错误。

当前成果可以继续进入上传与文件管理 API 契约设计，但尚未进入迁移 16 和产品功能编码阶段。

## 2. 测试范围

本轮检查覆盖：

1. 需求到设计的可追踪性。
2. Source、Notebook、Reference 关系方向。
3. 目录、标签、业务字典和文件元数据的数据归属。
4. 删除、共享来源和文件替换边界。
5. SurrealDB 迁移语法和唯一约束。
6. 既有 Reference 的迁移兼容。
7. 删除清理事件。
8. Down Migration。
9. Open Notebook 后端回归测试。
10. 前端单元测试和静态检查。

未测试：

- 尚未实现的迁移 16 正式文件。
- 尚未实现的上传向导、目录页面和字典页面；上传与文件管理交互流程已完成设计。
- 文件替换与回滚实现。
- 权限实现。
- Podcast 屏蔽实现。
- 前端生产构建；详见限制说明。

## 3. 需求可追踪检查

| 需求 | 当前设计覆盖 | 阶段 | 结果 |
| --- | --- | --- | --- |
| KBR-001 逻辑目录 | Folder + Reference.folder | 第一期 | 通过 |
| KBR-002 文件标签 | DictionaryItem(tag) + SourceTag | 第一期 | 通过 |
| KBR-003 文件元数据 | SourceProfile | 第一期 | 通过 |
| KBR-004 知识库属性 | Customer、Project、Notebook Scope、LN Version | 第一期 | 通过 |
| KBR-005 统一标签字典 | DictionaryType + DictionaryItem | 第一期 | 通过 |
| KBR-006 上传分类命名 | 数据对象与交互流程已具备 | 第一期 | 设计通过 |
| KBR-007 替换与重新学习 | SourceRevision 和原子切换原则 | 第二期 | 设计边界通过 |
| KBR-008 用户角色权限 | 稳定资源 ID 和权限扩展点 | 后续 | 设计边界通过 |
| KBR-009 屏蔽 Podcast | 产品边界已确认，代码尚未实施 | 第一期实现 | 待实施 |

不存在把客服工单、问题转派或项目实施流程带入 K-Book 的情况。

## 4. 关系与边界检查

### 4.1 Reference 方向

实际关系：

```text
source (in) -> reference -> notebook (out)
```

已核对：

- Source 详情按 `in = source_id` 获取 Notebook。
- Notebook 删除按 `out = notebook_id` 删除 Reference。
- Source retry 按 `in = source_id` 获取 Notebook。
- 目录位置放在 Reference 上是正确边界。

### 4.2 目录归属

目录属于 Notebook。Source 在每个 Notebook 中通过不同 Reference 选择目录。

该设计支持：

- 一个 Source 被多个 Notebook 共享。
- 同一个 Source 在不同 Notebook 使用不同目录。
- 移动目录时不重建向量。

### 4.3 标签和元数据归属

标签和 SourceProfile 当前被定义为 Source 全局属性。

含义：

- 同一 Source 被多个 Notebook 共享时，标签、模块、文档类型、业务版本和状态保持一致。
- 如果未来要求同一文件在不同知识库使用不同业务元数据，必须把对应字段移到 Reference Profile。

当前需求没有提出这种差异化，现设计成立。

### 4.4 客户和项目

Customer 和 Project 使用独立实体，不使用自由文本。

这满足后续权限模型需要。Notebook 同时选择客户和项目时必须验证项目属于客户。

### 4.5 旧 Topics

旧 `source.topics` 不自动转成统一标签是正确选择。Topics 可能来自模型主题抽取，直接迁移会污染人工标签字典。

## 5. SurrealDB 实测

### 5.1 环境

- 数据库镜像：`surrealdb/surrealdb:v2`
- 实际版本：`2.6.5`
- 数据库：隔离内存数据库
- 不涉及现有业务数据

### 5.2 迁移候选语法

使用迁移规格生成完整候选 SQL并执行，结果：

- Customer、Project、Folder 创建成功。
- Notebook 和 Reference 扩展字段创建成功。
- DictionaryType、DictionaryItem 创建成功。
- SourceProfile 创建成功。
- SourceTag 和 NotebookLnVersion 关系表创建成功。
- 系统字典类型种子创建成功。
- Existing Reference 成功补充 created、updated，folder 保持 NONE。

### 5.3 约束测试

| 测试 | 结果 |
| --- | --- |
| 重复 Source + Notebook Reference | 被唯一索引拒绝 |
| 非法 Customer 状态 | 被 ASSERT 拒绝 |
| 根目录下同名目录 | 被唯一索引拒绝 |
| 同一 Source 创建两个 SourceProfile | 被唯一索引拒绝 |
| 同一 Source 重复关联标签 | 被唯一索引拒绝 |
| 同一 Notebook 重复关联 LN 版本 | 被唯一索引拒绝 |

### 5.4 删除事件

实测结果：

- 删除 Source 后，SourceProfile 被删除。
- 删除 Source 后，SourceTag 被删除。
- 删除 Notebook 后，Folder 被删除。
- 删除 Notebook 后，NotebookLnVersion 被删除。

### 5.5 Down Migration

Down Migration 成功执行：

- K-Book 新增表、字段、索引和事件被移除。
- 原 Source、Notebook 和 Reference 表保留。

### 5.6 发现的迁移问题

原规格使用：

```surrealql
GROUP BY in, out
HAVING total > 1
```

SurrealDB 2.6.5 不支持该 `HAVING` 写法。已经修正为分组子查询后使用 `WHERE total > 1`。

## 6. 代码缺陷及修复

### FIX-001：添加已有 Source 时重复检查方向错误

原查询：

```surrealql
WHERE out = $source_id AND in = $notebook_id
```

实际应为：

```surrealql
WHERE in = $source_id AND out = $notebook_id
```

影响：

- 原幂等检查无法识别已有关系。
- 接口可能重复创建 Reference。
- 迁移 16 增加唯一索引后会产生冲突。

修复：

- 修正查询方向。
- 新增 3 个回归测试，覆盖已有关系、新关系和删除关系。

## 7. 自动化测试结果

### 7.1 后端

运行环境：Python 3.12 隔离容器。

结果：

```text
206 passed
2 warnings
```

警告来自上游依赖：

- `surreal_commands` 使用旧式 Pydantic Config。
- FastAPI TestClient 引用的 Starlette httpx 接口存在弃用提示。

无失败测试。

### 7.2 前端

运行环境：Node.js 22 隔离容器。

单元测试：

```text
8 test files passed
53 tests passed
```

ESLint：

```text
0 errors
8 warnings
```

警告均存在于上游基线，包括 Hook dependency 和未使用变量，不影响当前设计文档及后端修复。

### 7.3 Python 安装边界

`pytest-asyncio` 原先只存在于 uv dependency group。使用 `pip install -e ".[dev]"` 时异步测试全部无法执行。

已修复：

- 将 `pytest-asyncio` 加入 `[project.optional-dependencies].dev`。
- pip 开发安装文档改为 `pip install -e ".[dev]"`。

## 8. 限制与剩余风险

### 8.1 浮动数据库版本

当前 Compose 使用 `surrealdb:v2` 和 `pull_policy: always`。这会让生产数据库版本在重启或重新部署时变化。

迁移 16 发布前必须固定到经过验证的精确版本或镜像摘要。

### 8.2 迁移前重复关系

旧版接口可能已经创建重复 Reference。正式迁移需要 Preflight：

- 检测重复关系。
- 输出具体 Source 和 Notebook。
- 中止并要求清理。

否则唯一索引创建可能导致 API 启动失败。

### 8.3 应用层约束

以下约束仍依赖未来服务层实现：

- 项目属于客户。
- Folder 不跨 Notebook。
- Folder 不形成循环。
- 字典项类型正确。
- 停用字典项不能建立新关系。

在相应 API 实现前，不能把迁移完成视为功能完成。

### 8.4 前端生产构建

前端生产构建在本机沙箱中尝试下载 Darwin SWC 到用户缓存目录时被文件权限阻止。

已通过的前端单元测试和 ESLint 不依赖该下载。正式进入前端开发后，应在 CI 或完整 Node 构建容器中增加 `npm run build` 作为合并门槛。

### 8.5 功能尚未实现

以下内容目前只有设计，没有代码：

- 目录管理。
- 字典管理。
- 文件元数据。
- 知识库客户、项目和 LN 版本。
- 上传分类命名。
- 文件替换。
- 权限。
- Podcast 屏蔽。

## 9. 发布门槛

迁移 16 和第一期功能进入开发后，必须满足：

1. 正式 SQL 在固定 SurrealDB 版本完成 Up 和 Down 测试。
2. Preflight 能识别重复及悬空 Reference。
3. 所有新增服务层约束有单元测试。
4. 后端完整测试通过。
5. 前端单元测试、Lint 和生产构建通过。
6. Podcast 从 K-Book 所有正常入口隐藏。
7. 上传和文件管理流程完成验收测试。
