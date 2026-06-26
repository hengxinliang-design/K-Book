# K-Book 第一期数据库迁移规格

## 1. 目的

本文档将《K-Book 领域模型与数据关系设计》转换为第一期可实施的 SurrealDB 迁移规格。

范围包括：

- 客户和项目。
- 知识库适用范围。
- 逻辑目录。
- 统一字典。
- 文件业务元数据。
- 文件标签。
- 知识库适用 LN 版本。
- 文件与知识库关联上的目录位置。

不包括：

- 文件替换和 `source_revision`。
- 用户、角色和权限。
- 搜索函数的最终改造。
- API 和前端实现。

## 2. 迁移编号与执行器要求

当前最新迁移为 `15.surrealql`，本期使用：

```text
open_notebook/database/migrations/16.surrealql
open_notebook/database/migrations/16_down.surrealql
```

当前 `AsyncMigrationManager` 手工维护迁移文件列表，不会扫描目录。实现时必须同步修改：

```text
open_notebook/database/async_migrate.py
```

在 `up_migrations` 和 `down_migrations` 末尾分别注册迁移 16。

验收要求：

- 数据库版本从 15 升级到 16。
- 重启服务不会重复创建数据或报错。
- 执行一次 down 后版本回到 15。

## 3. SurrealDB 关系方向约定

SurrealDB 执行：

```surrealql
RELATE source:1->reference->notebook:1;
```

得到：

- `reference.in = source:1`
- `reference.out = notebook:1`

因此 K-Book 统一采用：

```text
source (in) -> reference -> notebook (out)
source (in) -> source_tag -> dictionary_item (out)
notebook (in) -> notebook_ln_version -> dictionary_item (out)
```

代码、文档、查询和测试均按此约定，不再使用“out 是 source”的错误注释。

## 4. 迁移前检查

迁移 16 不应静默修复不确定的业务数据。部署前执行以下检查。

### 4.1 Reference 重复关系

检查同一 Source 和 Notebook 是否存在多个 Reference：

```surrealql
SELECT *
FROM (
    SELECT in, out, count() AS total
    FROM reference
    GROUP BY in, out
)
WHERE total > 1;
```

如果存在重复：

- 由运维或迁移工具明确选择一个关系保留。
- 删除其余重复关系。
- 本期尚无目录信息，因此无需合并 Folder。

在没有清理重复关系前，不创建 `reference(in, out)` 唯一索引。

由于迁移由 API 启动时自动执行，正式实现必须在执行迁移 16 前增加
`validate_migration_16_preconditions()`。发现重复或悬空 Reference 时：

- 中止迁移。
- 输出 Source、Notebook 和重复数量。
- 不自动选择要保留的关系。

现有重复关系可能来自旧版 `add_source_to_notebook` 的方向判断错误，因此不能假设生产数据一定干净。

### 4.2 悬空关系

检查 `reference.in` 或 `reference.out` 对应记录是否不存在。悬空关系必须删除。

### 4.3 数据库版本

迁移只能在当前版本为 15 时执行。若版本更高，不能直接套用本规格。

## 5. 表和字段定义

以下代码是迁移实现的目标形态。正式编码时应在当前 SurrealDB v2 容器中验证语法。

### 5.1 Customer

```surrealql
DEFINE TABLE IF NOT EXISTS customer SCHEMAFULL;

DEFINE FIELD IF NOT EXISTS code
ON TABLE customer TYPE string;

DEFINE FIELD IF NOT EXISTS name
ON TABLE customer TYPE string;

DEFINE FIELD IF NOT EXISTS normalized_name
ON TABLE customer TYPE string;

DEFINE FIELD IF NOT EXISTS status
ON TABLE customer TYPE string
DEFAULT 'active'
ASSERT $value IN ['active', 'inactive'];

DEFINE FIELD IF NOT EXISTS description
ON TABLE customer TYPE option<string>;

DEFINE FIELD IF NOT EXISTS created
ON TABLE customer TYPE datetime
DEFAULT time::now()
VALUE $before OR time::now();

DEFINE FIELD IF NOT EXISTS updated
ON TABLE customer TYPE datetime
DEFAULT time::now()
VALUE time::now();
```

索引：

```surrealql
DEFINE INDEX IF NOT EXISTS idx_customer_code
ON TABLE customer FIELDS code UNIQUE;

DEFINE INDEX IF NOT EXISTS idx_customer_normalized_name
ON TABLE customer FIELDS normalized_name;

DEFINE INDEX IF NOT EXISTS idx_customer_status
ON TABLE customer FIELDS status;
```

### 5.2 Project

```surrealql
DEFINE TABLE IF NOT EXISTS project SCHEMAFULL;

DEFINE FIELD IF NOT EXISTS code
ON TABLE project TYPE string;

DEFINE FIELD IF NOT EXISTS name
ON TABLE project TYPE string;

DEFINE FIELD IF NOT EXISTS normalized_name
ON TABLE project TYPE string;

DEFINE FIELD IF NOT EXISTS customer
ON TABLE project TYPE record<customer>;

DEFINE FIELD IF NOT EXISTS status
ON TABLE project TYPE string
DEFAULT 'active'
ASSERT $value IN ['active', 'closed', 'inactive'];

DEFINE FIELD IF NOT EXISTS description
ON TABLE project TYPE option<string>;

DEFINE FIELD IF NOT EXISTS created
ON TABLE project TYPE datetime
DEFAULT time::now()
VALUE $before OR time::now();

DEFINE FIELD IF NOT EXISTS updated
ON TABLE project TYPE datetime
DEFAULT time::now()
VALUE time::now();
```

索引：

```surrealql
DEFINE INDEX IF NOT EXISTS idx_project_code
ON TABLE project FIELDS code UNIQUE;

DEFINE INDEX IF NOT EXISTS idx_project_customer
ON TABLE project FIELDS customer;

DEFINE INDEX IF NOT EXISTS idx_project_customer_name
ON TABLE project FIELDS customer, normalized_name UNIQUE;

DEFINE INDEX IF NOT EXISTS idx_project_status
ON TABLE project FIELDS status;
```

### 5.3 扩展 Notebook

```surrealql
DEFINE FIELD IF NOT EXISTS customer
ON TABLE notebook TYPE option<record<customer>>;

DEFINE FIELD IF NOT EXISTS project
ON TABLE notebook TYPE option<record<project>>;

DEFINE FIELD IF NOT EXISTS scope
ON TABLE notebook TYPE option<string>;
```

索引：

```surrealql
DEFINE INDEX IF NOT EXISTS idx_notebook_customer
ON TABLE notebook FIELDS customer;

DEFINE INDEX IF NOT EXISTS idx_notebook_project
ON TABLE notebook FIELDS project;
```

客户与项目一致性不能仅靠字段类型保证。API 服务层必须验证：

```text
notebook.project.customer == notebook.customer
```

如果只选择项目，服务层应自动填充项目所属客户，避免产生不一致记录。

### 5.4 Folder

```surrealql
DEFINE TABLE IF NOT EXISTS folder SCHEMAFULL;

DEFINE FIELD IF NOT EXISTS notebook
ON TABLE folder TYPE record<notebook>;

DEFINE FIELD IF NOT EXISTS parent
ON TABLE folder TYPE option<record<folder>>;

DEFINE FIELD IF NOT EXISTS name
ON TABLE folder TYPE string;

DEFINE FIELD IF NOT EXISTS normalized_name
ON TABLE folder TYPE string;

DEFINE FIELD IF NOT EXISTS description
ON TABLE folder TYPE option<string>;

DEFINE FIELD IF NOT EXISTS sort_order
ON TABLE folder TYPE int
DEFAULT 0;

DEFINE FIELD IF NOT EXISTS created
ON TABLE folder TYPE datetime
DEFAULT time::now()
VALUE $before OR time::now();

DEFINE FIELD IF NOT EXISTS updated
ON TABLE folder TYPE datetime
DEFAULT time::now()
VALUE time::now();
```

索引：

```surrealql
DEFINE INDEX IF NOT EXISTS idx_folder_notebook
ON TABLE folder FIELDS notebook;

DEFINE INDEX IF NOT EXISTS idx_folder_parent
ON TABLE folder FIELDS parent;

DEFINE INDEX IF NOT EXISTS idx_folder_sibling_name
ON TABLE folder FIELDS notebook, parent, normalized_name UNIQUE;
```

必须由服务层验证：

- Parent 与 Folder 属于同一 Notebook。
- Parent 不是 Folder 自身。
- Parent 不是 Folder 的后代。
- 最大目录深度第一期限制为 20 层，避免循环错误导致无限遍历。

`normalized_name` 由应用层生成：

```text
trim -> Unicode NFKC -> casefold
```

显示名称保留用户原始大小写和字符。

### 5.5 扩展 Reference

现有定义：

```surrealql
TYPE RELATION FROM source TO notebook
```

增加：

```surrealql
DEFINE FIELD IF NOT EXISTS folder
ON TABLE reference TYPE option<record<folder>>;

DEFINE FIELD IF NOT EXISTS created
ON TABLE reference TYPE datetime
DEFAULT time::now()
VALUE $before OR time::now();

DEFINE FIELD IF NOT EXISTS updated
ON TABLE reference TYPE datetime
DEFAULT time::now()
VALUE time::now();
```

索引：

```surrealql
DEFINE INDEX IF NOT EXISTS idx_reference_source_notebook
ON TABLE reference FIELDS in, out UNIQUE;

DEFINE INDEX IF NOT EXISTS idx_reference_folder
ON TABLE reference FIELDS folder;
```

必须由服务层验证：

```text
reference.folder.notebook == reference.out
```

旧 Reference 自动获得：

- `folder = NONE`
- `created` 和 `updated` 由迁移执行时间补齐

这表示所有既有文件初始位于对应知识库根目录。

### 5.6 DictionaryType

```surrealql
DEFINE TABLE IF NOT EXISTS dictionary_type SCHEMAFULL;

DEFINE FIELD IF NOT EXISTS code
ON TABLE dictionary_type TYPE string;

DEFINE FIELD IF NOT EXISTS name
ON TABLE dictionary_type TYPE string;

DEFINE FIELD IF NOT EXISTS description
ON TABLE dictionary_type TYPE option<string>;

DEFINE FIELD IF NOT EXISTS system
ON TABLE dictionary_type TYPE bool
DEFAULT false;

DEFINE FIELD IF NOT EXISTS created
ON TABLE dictionary_type TYPE datetime
DEFAULT time::now()
VALUE $before OR time::now();

DEFINE FIELD IF NOT EXISTS updated
ON TABLE dictionary_type TYPE datetime
DEFAULT time::now()
VALUE time::now();
```

索引：

```surrealql
DEFINE INDEX IF NOT EXISTS idx_dictionary_type_code
ON TABLE dictionary_type FIELDS code UNIQUE;
```

### 5.7 DictionaryItem

```surrealql
DEFINE TABLE IF NOT EXISTS dictionary_item SCHEMAFULL;

DEFINE FIELD IF NOT EXISTS dictionary_type
ON TABLE dictionary_item TYPE record<dictionary_type>;

DEFINE FIELD IF NOT EXISTS code
ON TABLE dictionary_item TYPE string;

DEFINE FIELD IF NOT EXISTS name
ON TABLE dictionary_item TYPE string;

DEFINE FIELD IF NOT EXISTS normalized_name
ON TABLE dictionary_item TYPE string;

DEFINE FIELD IF NOT EXISTS description
ON TABLE dictionary_item TYPE option<string>;

DEFINE FIELD IF NOT EXISTS status
ON TABLE dictionary_item TYPE string
DEFAULT 'active'
ASSERT $value IN ['active', 'inactive'];

DEFINE FIELD IF NOT EXISTS sort_order
ON TABLE dictionary_item TYPE int
DEFAULT 0;

DEFINE FIELD IF NOT EXISTS color
ON TABLE dictionary_item TYPE option<string>;

DEFINE FIELD IF NOT EXISTS created
ON TABLE dictionary_item TYPE datetime
DEFAULT time::now()
VALUE $before OR time::now();

DEFINE FIELD IF NOT EXISTS updated
ON TABLE dictionary_item TYPE datetime
DEFAULT time::now()
VALUE time::now();
```

索引：

```surrealql
DEFINE INDEX IF NOT EXISTS idx_dictionary_item_type_code
ON TABLE dictionary_item FIELDS dictionary_type, code UNIQUE;

DEFINE INDEX IF NOT EXISTS idx_dictionary_item_type_name
ON TABLE dictionary_item
FIELDS dictionary_type, normalized_name UNIQUE;

DEFINE INDEX IF NOT EXISTS idx_dictionary_item_type_status
ON TABLE dictionary_item FIELDS dictionary_type, status;
```

`color` 第一阶段仅接受：

- `#RRGGBB`
- `#RRGGBBAA`
- `NONE`

格式由 API 校验，不在迁移中实现复杂正则。

### 5.8 SourceProfile

```surrealql
DEFINE TABLE IF NOT EXISTS source_profile SCHEMAFULL;

DEFINE FIELD IF NOT EXISTS source
ON TABLE source_profile TYPE record<source>;

DEFINE FIELD IF NOT EXISTS module
ON TABLE source_profile TYPE option<record<dictionary_item>>;

DEFINE FIELD IF NOT EXISTS document_type
ON TABLE source_profile TYPE option<record<dictionary_item>>;

DEFINE FIELD IF NOT EXISTS business_version
ON TABLE source_profile TYPE option<string>;

DEFINE FIELD IF NOT EXISTS status
ON TABLE source_profile TYPE option<record<dictionary_item>>;

DEFINE FIELD IF NOT EXISTS original_filename
ON TABLE source_profile TYPE option<string>;

DEFINE FIELD IF NOT EXISTS created
ON TABLE source_profile TYPE datetime
DEFAULT time::now()
VALUE $before OR time::now();

DEFINE FIELD IF NOT EXISTS updated
ON TABLE source_profile TYPE datetime
DEFAULT time::now()
VALUE time::now();
```

索引：

```surrealql
DEFINE INDEX IF NOT EXISTS idx_source_profile_source
ON TABLE source_profile FIELDS source UNIQUE;

DEFINE INDEX IF NOT EXISTS idx_source_profile_module
ON TABLE source_profile FIELDS module;

DEFINE INDEX IF NOT EXISTS idx_source_profile_document_type
ON TABLE source_profile FIELDS document_type;

DEFINE INDEX IF NOT EXISTS idx_source_profile_status
ON TABLE source_profile FIELDS status;

DEFINE INDEX IF NOT EXISTS idx_source_profile_business_version
ON TABLE source_profile FIELDS business_version;
```

字典类型匹配由服务层验证：

- `module` -> `dictionary_type.code = module`
- `document_type` -> `dictionary_type.code = document_type`
- `status` -> `dictionary_type.code = document_status`

### 5.9 SourceTag

```surrealql
DEFINE TABLE IF NOT EXISTS source_tag
TYPE RELATION
FROM source
TO dictionary_item
SCHEMAFULL;

DEFINE FIELD IF NOT EXISTS created
ON TABLE source_tag TYPE datetime
DEFAULT time::now()
VALUE $before OR time::now();
```

索引：

```surrealql
DEFINE INDEX IF NOT EXISTS idx_source_tag_unique
ON TABLE source_tag FIELDS in, out UNIQUE;

DEFINE INDEX IF NOT EXISTS idx_source_tag_tag
ON TABLE source_tag FIELDS out;
```

服务层必须验证目标项属于 `tag` 字典，并且状态为 `active`。

### 5.10 NotebookLnVersion

```surrealql
DEFINE TABLE IF NOT EXISTS notebook_ln_version
TYPE RELATION
FROM notebook
TO dictionary_item
SCHEMAFULL;

DEFINE FIELD IF NOT EXISTS created
ON TABLE notebook_ln_version TYPE datetime
DEFAULT time::now()
VALUE $before OR time::now();
```

索引：

```surrealql
DEFINE INDEX IF NOT EXISTS idx_notebook_ln_version_unique
ON TABLE notebook_ln_version FIELDS in, out UNIQUE;

DEFINE INDEX IF NOT EXISTS idx_notebook_ln_version_value
ON TABLE notebook_ln_version FIELDS out;
```

服务层必须验证目标项属于 `ln_version` 字典，并且状态为 `active`。

## 6. 系统字典类型种子

迁移只创建字典类型，不擅自创建业务字典值。

使用固定记录 ID，确保幂等和代码引用稳定：

```surrealql
UPSERT dictionary_type:tag CONTENT {
    code: 'tag',
    name: '标签',
    description: '文件的多维内容标签',
    system: true
};

UPSERT dictionary_type:module CONTENT {
    code: 'module',
    name: 'LN 模块',
    description: 'Infor LN 产品或业务模块',
    system: true
};

UPSERT dictionary_type:document_type CONTENT {
    code: 'document_type',
    name: '文档类型',
    description: '需求、蓝图、产品设计、方案设计、技术设计、代码设计等',
    system: true
};

UPSERT dictionary_type:document_status CONTENT {
    code: 'document_status',
    name: '文档状态',
    description: '文档当前使用状态',
    system: true
};

UPSERT dictionary_type:ln_version CONTENT {
    code: 'ln_version',
    name: 'LN 版本',
    description: '知识库适用的 Infor LN 版本',
    system: true
};
```

首次启动后的业务字典值通过管理界面或单独初始化脚本创建。

## 7. 既有数据迁移

### 7.1 Existing Reference

为已有关系补充时间：

```surrealql
UPDATE reference
SET created = created OR time::now(),
    updated = updated OR time::now();
```

所有现有 Reference 保持 `folder = NONE`。

### 7.2 Existing Notebook

现有 Notebook 保持：

- `customer = NONE`
- `project = NONE`
- `scope = NONE`

它们在产品上解释为“尚未定义适用范围”，而不是自动判定为通用知识库。

### 7.3 Existing Source

不为所有 Source 强制创建空的 SourceProfile。

理由：

- Profile 为可选一对一对象。
- 延迟创建减少无意义记录。
- 首次编辑元数据或新上传时再创建。

### 7.4 Existing Topics

迁移 16 不自动把 `source.topics` 转成统一标签。

原因：

- Topics 可能是模型自动提取主题，不一定是人工管理标签。
- 自动转换会污染标签字典。
- 不同语言、大小写和近义词需要人工归并。

后续提供独立迁移工具：

1. 列出旧 Topics 及使用次数。
2. 管理员选择合并、忽略或创建标签。
3. 批量创建 SourceTag。

## 8. 删除清理事件

本期增加独立事件，不覆盖上游已有 `source_delete`。

### 8.1 Source 删除

```surrealql
DEFINE EVENT IF NOT EXISTS kbook_source_cleanup
ON TABLE source
WHEN ($after == NONE)
THEN {
    DELETE source_profile WHERE source = $before.id;
    DELETE source_tag WHERE in = $before.id;
};
```

### 8.2 Notebook 删除

```surrealql
DEFINE EVENT IF NOT EXISTS kbook_notebook_cleanup
ON TABLE notebook
WHEN ($after == NONE)
THEN {
    DELETE folder WHERE notebook = $before.id;
    DELETE notebook_ln_version WHERE in = $before.id;
};
```

说明：

- Notebook 原有删除流程会删除 Reference。
- Project 和 Customer 不做数据库级联删除。
- DictionaryItem 不做级联删除，业务层应阻止删除已引用项。

## 9. Down Migration

Down Migration 是破坏性操作，只允许开发和测试环境使用。

执行顺序必须先删依赖对象，再删被依赖对象：

```surrealql
REMOVE EVENT IF EXISTS kbook_source_cleanup ON TABLE source;
REMOVE EVENT IF EXISTS kbook_notebook_cleanup ON TABLE notebook;

REMOVE TABLE IF EXISTS notebook_ln_version;
REMOVE TABLE IF EXISTS source_tag;
REMOVE TABLE IF EXISTS source_profile;

REMOVE INDEX IF EXISTS idx_reference_source_notebook ON TABLE reference;
REMOVE INDEX IF EXISTS idx_reference_folder ON TABLE reference;
REMOVE FIELD IF EXISTS folder ON TABLE reference;
REMOVE FIELD IF EXISTS created ON TABLE reference;
REMOVE FIELD IF EXISTS updated ON TABLE reference;

REMOVE INDEX IF EXISTS idx_notebook_customer ON TABLE notebook;
REMOVE INDEX IF EXISTS idx_notebook_project ON TABLE notebook;
REMOVE FIELD IF EXISTS customer ON TABLE notebook;
REMOVE FIELD IF EXISTS project ON TABLE notebook;
REMOVE FIELD IF EXISTS scope ON TABLE notebook;

REMOVE TABLE IF EXISTS folder;
REMOVE TABLE IF EXISTS dictionary_item;
REMOVE TABLE IF EXISTS dictionary_type;
REMOVE TABLE IF EXISTS project;
REMOVE TABLE IF EXISTS customer;
```

风险：

- 所有客户、项目、目录、字典、标签和 Profile 数据都会丢失。
- Down 后原 Source、Notebook、Reference、全文和向量仍保留。
- Reference 的目录位置和时间字段不可恢复。

生产环境回滚应优先使用向前修复迁移，不执行 Down。

## 10. 应用层校验职责

以下规则不能仅依赖迁移字段类型：

| 规则 | 校验位置 |
| --- | --- |
| 项目属于所选客户 | Notebook API / Project Service |
| Folder Parent 属于同一 Notebook | Folder Service |
| Folder 不形成循环 | Folder Service |
| Folder 深度不超过 20 | Folder Service |
| Reference Folder 属于目标 Notebook | Source/Notebook Association Service |
| Profile 字段引用正确字典类型 | Source Metadata Service |
| Tag 引用 tag 类型且 active | Tag Service |
| LN 版本引用 ln_version 类型且 active | Notebook Service |
| 停用字典项不能建立新关系 | 所有写入服务 |
| 有引用字典项不可物理删除 | Dictionary Service |
| normalized_name 正确生成 | API Schema / Service |

所有批量写入必须在服务层先完成整体验证，再开始数据库变更，避免部分成功。

## 11. 事务边界

第一期建议以下操作使用单个 SurrealQL 事务：

- 创建 Notebook，同时写入客户、项目、Scope 和 LN 版本关系。
- 更新 Notebook 和替换 LN 版本关系。
- 创建 Folder。
- 移动 Folder。
- 将 Source 加入 Notebook 并设置 Folder。
- 移动 Source 到 Folder。
- 更新 SourceProfile 和 SourceTag。

批量上传不要求所有文件共用一个大事务。每个文件独立提交，批次记录成功与失败数量。

## 12. 性能索引目标

第一期典型查询和对应索引：

| 查询 | 关键索引 |
| --- | --- |
| 按客户列知识库 | `idx_notebook_customer` |
| 按项目列知识库 | `idx_notebook_project` |
| 加载知识库目录树 | `idx_folder_notebook`、`idx_folder_parent` |
| 加载目录文件 | `idx_reference_folder` |
| 查文件元数据 | `idx_source_profile_source` |
| 按模块过滤 | `idx_source_profile_module` |
| 按类型过滤 | `idx_source_profile_document_type` |
| 按状态过滤 | `idx_source_profile_status` |
| 按标签过滤 | `idx_source_tag_tag` |
| 按 LN 版本过滤知识库 | `idx_notebook_ln_version_value` |

迁移后应使用至少以下规模进行查询验证：

- 1,000 个知识库。
- 100,000 个 Source。
- 300,000 个 Reference。
- 10,000 个 Folder。
- 每个 Source 平均 5 个 Tag。

这不是第一期必须达到的实际容量，而是避免明显全表扫描的设计检查规模。

## 13. 迁移测试

迁移 16 正式文件已实现，并已在 `SurrealDB 2.6.5` 上按实际迁移执行器方式完成基础 Up 和 Down 验证。
完整规模、兼容性和生产数据演练仍需在发布前重新执行本节全部测试。

### 13.1 Up Migration

- 空数据库从 0 连续迁移到 16。
- 现有版本 15 数据库迁移到 16。
- 迁移执行器确实注册了 Up 和 Down 文件。
- 迁移后系统字典类型恰好各一条。
- 已有 Source、Notebook、Reference 数量不变。
- 已有 Reference 位于根目录。
- 对 `INFO FOR DB` 或等价 Schema 查询进行断言，防止多语句迁移出现部分定义缺失。

### 13.2 幂等性

- API 重启不重复创建字典类型。
- 重复执行迁移 SQL 不产生重复索引或种子记录。

版本表不会正常重复执行同一迁移，但迁移本身仍尽量使用 `IF NOT EXISTS` 和 `UPSERT`。

### 13.3 约束

- 重复客户编码失败。
- 同一客户下重复项目名称失败。
- 同一父目录下重复目录名称失败。
- 同一 Source 和 Notebook 重复 Reference 失败。
- 同一 Source 重复标签失败。
- 同一 Notebook 重复 LN 版本失败。
- 同一 Source 重复 SourceProfile 失败。

### 13.4 Down Migration

- 版本 16 降回 15。
- K-Book 新增表和字段被移除。
- 原 Source、Notebook、Reference、Embedding 和 Note 仍存在。

### 13.5 兼容性回归

- 原 Notebook 列表仍可加载。
- 原 Source 上传、处理和向量化仍可运行。
- 原 Source 可以关联 Notebook。
- 原全文和向量搜索结果不因迁移本身改变。
- 原聊天与引用仍能使用 Source ID。

### 13.6 数据库版本固定

当前 Compose 使用浮动镜像 `surrealdb/surrealdb:v2`。它在本次验证时解析为
`2.6.5`，但未来可能自动变化。

K-Book 首次发布迁移 16 时必须：

- 将生产镜像固定到通过测试的精确版本或镜像摘要。
- 在升级 SurrealDB 前重新执行 Up、Down、约束和兼容性测试。
- 禁止生产环境使用 `pull_policy: always` 搭配浮动 `v2` 标签。

## 14. 实现前待确认项

以下问题不阻塞迁移表结构，但会影响种子数据和 UI：

1. LN 版本是否允许一个知识库选择多个版本。当前设计为允许。
2. 文件业务版本当前设计为自由文本，是否需要格式规则。
3. 项目编码和客户编码由人工维护还是从外部系统导入。
4. 第一批模块、文档类型和文档状态值。
5. 目录名称是否区分大小写。当前设计为不区分。
