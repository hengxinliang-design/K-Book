# K-Book 后端实现拆分设计

## 1. 文档目的

本文档把 K-Book 第一期后端能力拆成可执行的实现单元。

优先范围：

1. 上传配置。
2. 字典。
3. 目录。
4. 文件列表。

不在本轮实现拆分范围：

- 上传批次实际处理。
- 文件替换和重新学习。
- 前端页面和组件。
- 用户、角色和项目权限。
- Podcast 删除或后端清理。

## 2. 当前代码基线判断

现有后端结构：

- FastAPI 入口：`api/main.py`。
- 路由目录：`api/routers/`。
- 现有 Source 路由：`api/routers/sources.py`。
- 现有 Notebook 路由：`api/routers/notebooks.py`。
- 现有数据库访问：`open_notebook.database.repository.repo_query`。
- 自动迁移：`open_notebook/database/async_migrate.py`。
- 当前迁移注册到 `15.surrealql`。

K-Book 设计要求的表：

- `dictionary_type`
- `dictionary_item`
- `folder`
- `source_profile`
- `source_tag`
- `notebook_ln_version`
- `customer`
- `project`
- `reference.folder`

这些结构当前尚未通过正式迁移落库。因此实现顺序必须先处理迁移 16，再实现依赖数据库表的 API。

## 3. 总体拆分原则

### 3.1 新增 K-Book 后端模块

新增模块建议：

```text
api/
├─ kbook_models.py
├─ kbook_errors.py
├─ kbook_services/
│  ├─ __init__.py
│  ├─ upload_config.py
│  ├─ dictionary.py
│  ├─ folders.py
│  └─ files.py
└─ routers/
   ├─ kbook_upload_config.py
   ├─ kbook_dictionary.py
   ├─ kbook_folders.py
   └─ kbook_files.py
```

路由统一挂载到：

```text
/api/kbook/*
```

原因：

- 前端已有 API 统一使用 `/api` 前缀。
- 契约文档里的 `/kbook/*` 是业务路径，实际 FastAPI 挂载后为 `/api/kbook/*`。
- 避免改动现有 `/api/sources` 和 `/api/notebooks`，降低上游同步冲突。

### 3.2 服务层必须独立

路由只做：

- 参数解析。
- Pydantic 校验。
- 调用服务。
- 转换 HTTP 错误。

业务规则放在服务层：

- 字典类型校验。
- 字典项 active 校验。
- Folder 属于 Notebook。
- Folder 循环检测。
- 文件列表组合查询。

### 3.3 先实现读多写少

优先顺序：

1. 上传配置：不依赖迁移，最安全。
2. 迁移 16：字典、目录、文件列表依赖它。
3. 字典查询和种子：支撑上传向导。
4. 目录树和目录 CRUD：支撑文件管理。
5. 文件列表查询：支撑页面主体。

不建议先做上传批次。上传批次涉及文件保存、Source 创建、Reference、Profile、Tag 和异步处理任务，失败补偿复杂度更高。

## 4. 任务切分

### BE-001：上传配置 API

目标：

实现：

```http
GET /api/kbook/upload/config
```

新增文件：

- `api/kbook_services/upload_config.py`
- `api/routers/kbook_upload_config.py`
- `tests/test_kbook_upload_config_api.py`

建议常量：

```python
KBOOK_SUPPORTED_UPLOAD_EXTENSIONS = [
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    "txt", "md", "epub", "html",
    "mp4", "avi", "mov", "wmv",
    "mp3", "wav", "m4a", "aac",
    "jpg", "jpeg", "png", "tiff",
    "zip", "tar", "gz",
]
```

响应字段：

- `max_file_size_mb`
- `max_files_per_batch`
- `accept`
- `format_summary`
- `extensions`

测试：

- 返回 200。
- `accept` 与 `extensions` 一致。
- 包含当前前端已有上传白名单。
- 不包含未确认格式。

验收：

- 前端可以直接用响应渲染灰色格式备注。
- 后续上传批次可以复用同一份扩展名配置做后端校验。

### BE-002：迁移 16 正式实现

目标：

把已完成的数据库迁移规格落成正式迁移文件。

新增或修改：

- `open_notebook/database/migrations/16.surrealql`
- `open_notebook/database/migrations/16_down.surrealql`
- `open_notebook/database/async_migrate.py`
- `docs/K-BOOK-DATABASE-MIGRATION-SPEC.md` 如需记录实现偏差
- `tests/test_kbook_migration_16.py`

必须包含：

- `customer`
- `project`
- `folder`
- `dictionary_type`
- `dictionary_item`
- `source_profile`
- `source_tag`
- `notebook_ln_version`
- `reference.folder`
- `reference.created`
- `reference.updated`
- 必要索引、事件和种子字典类型

必须先做 Preflight：

- 检查重复 `reference(in, out)`。
- 检查悬空 Reference。
- 存在问题时中止迁移并给出可清理信息。

风险控制：

- 不要把 SourceRevision 放入迁移 16。
- 不要把权限表放入迁移 16。
- 不要删除或重建现有 `source`、`notebook`、`reference`。

测试：

- 空库从 0 到 16。
- 已有 Source、Notebook、Reference 的库从 15 到 16。
- 重复 Reference 时迁移中止。
- Up 后唯一索引阻止重复 Source + Notebook Reference。
- Down 后 K-Book 新增表和字段被移除，原核心表保留。

验收：

- API 启动时可自动迁移到 16。
- 字典、目录、文件列表 API 可以依赖正式表结构。

### BE-003：K-Book 错误响应工具

目标：

统一 K-Book API 错误结构，避免有的接口返回 `detail`，有的接口返回自定义结构。

新增：

- `api/kbook_errors.py`

建议实现：

```python
class KBookHTTPException(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        ...
```

响应结构：

```json
{
  "error": {
    "code": "folder_not_found",
    "message": "Folder not found",
    "details": {}
  }
}
```

测试：

- 服务层抛出 KBook 错误时，路由返回统一结构。
- 常见 code 与 API 契约一致。

说明：

第一期可以只在 K-Book 新路由中使用，不改现有 Open Notebook 路由。

### BE-004：字典查询 API

目标：

实现字典类型和字典项查询，支撑上传向导下拉选择。

接口：

```http
GET /api/kbook/dictionary-types
GET /api/kbook/dictionary-items
```

新增：

- `api/kbook_services/dictionary.py`
- `api/routers/kbook_dictionary.py`
- `tests/test_kbook_dictionary_api.py`

服务函数：

- `list_dictionary_types()`
- `list_dictionary_items(type=None, active_only=True, keyword=None, limit=100, offset=0)`
- `get_dictionary_type_by_code(code)`
- `validate_dictionary_item(item_id, expected_type, require_active=True)`

查询规则：

- `type` 使用字典类型 `code`，不是 record id。
- `active_only=true` 默认只返回 active。
- `keyword` 匹配 `name`、`code` 或 `normalized_name`。
- 结果按 `sort_order ASC, name ASC`。

测试：

- 返回预置 5 个系统字典类型。
- 按 type 过滤正确。
- `active_only=true` 不返回 inactive。
- keyword 过滤正确。
- 错误 type 返回空列表或 `400 validation_failed`，实现前需固定一种行为；建议返回 `400 validation_failed`。

验收：

- 上传向导可加载标签、模块、文档类型、状态。
- 后续 Notebook 设置可加载 LN 版本。

### BE-005：字典写入 API

目标：

提供第一期最小字典维护能力。

接口：

```http
POST /api/kbook/dictionary-items
PATCH /api/kbook/dictionary-items/{item_id}
```

服务函数：

- `create_dictionary_item(type, code, name, description, sort_order)`
- `update_dictionary_item(item_id, patch)`
- `normalize_dictionary_name(name)`

规则：

- 同一字典类型下 `code` 唯一。
- 同一字典类型下 `normalized_name` 唯一。
- `status` 只能是 `active` 或 `inactive`。
- 系统字典类型不可由 API 删除。
- 已被引用字典项本阶段不提供删除。

测试：

- 创建 active 字典项成功。
- 重复 code 失败。
- 重复 normalized_name 失败。
- 停用字典项成功。
- 修改系统字典项 code 被拒绝。

验收：

- 管理员可维护上传向导所需选项。

### BE-006：目录树查询 API

目标：

实现文件管理页面左侧目录树。

接口：

```http
GET /api/kbook/notebooks/{notebook_id}/folders
```

新增：

- `api/kbook_services/folders.py`
- `api/routers/kbook_folders.py`
- `tests/test_kbook_folders_api.py`

服务函数：

- `list_folder_tree(notebook_id)`
- `folder_belongs_to_notebook(folder_id, notebook_id)`
- `build_folder_tree(flat_rows)`

响应：

- 返回树形结构。
- 每个节点包含 `source_count`。
- 根目录不作为实体返回。

查询规则：

- 只返回当前 Notebook 的 Folder。
- `source_count` 统计当前目录直接文件数量；是否包含子目录数量后续可扩展，第一期先直接数量。

测试：

- 空目录树返回空列表。
- 多级目录正确组树。
- 不同 Notebook 的目录互不出现。
- source_count 按 `reference.folder` 统计。

### BE-007：目录写入 API

目标：

实现新建、重命名、移动和删除空目录。

接口：

```http
POST /api/kbook/notebooks/{notebook_id}/folders
PATCH /api/kbook/notebooks/{notebook_id}/folders/{folder_id}
POST /api/kbook/notebooks/{notebook_id}/folders/{folder_id}/move
DELETE /api/kbook/notebooks/{notebook_id}/folders/{folder_id}
```

服务函数：

- `create_folder(notebook_id, parent, name, description, sort_order)`
- `update_folder(notebook_id, folder_id, patch)`
- `move_folder(notebook_id, folder_id, parent, sort_order)`
- `delete_empty_folder(notebook_id, folder_id)`
- `assert_no_folder_cycle(folder_id, new_parent)`
- `assert_folder_depth(folder_id, new_parent, max_depth=20)`

规则：

- `parent` 必须属于同一 Notebook。
- 不能移动到自身。
- 不能移动到自身后代。
- 同一父目录下名称唯一。
- 非空目录不能删除。
- 删除目录不删除 Source。

测试：

- 创建根目录成功。
- 创建子目录成功。
- 同级重名失败。
- 跨 Notebook parent 失败。
- 移动到自身失败。
- 移动到后代失败。
- 删除空目录成功。
- 删除含子目录或文件的目录失败。

### BE-008：文件列表查询 API

目标：

实现文件管理页面主体列表。

接口：

```http
GET /api/kbook/notebooks/{notebook_id}/files
GET /api/kbook/notebooks/{notebook_id}/files/{source_id}
```

新增：

- `api/kbook_services/files.py`
- `api/routers/kbook_files.py`
- `tests/test_kbook_files_api.py`

服务函数：

- `list_notebook_files(notebook_id, filters, pagination, sort)`
- `get_notebook_file_detail(notebook_id, source_id)`
- `resolve_folder_path(folder_id)`
- `map_processing_status(source_row)`

筛选：

- `folder_id`
- `tag_ids`
- `module_id`
- `document_type_id`
- `status_id`
- `business_version`
- `keyword`
- `processing_status`
- `limit`
- `offset`
- `sort_by`
- `sort_order`

查询实现建议：

- 先从 `reference WHERE out = notebook_id` 确定候选 Source。
- 目录筛选走 `reference.folder`。
- 标签筛选关联 `source_tag`。
- Profile 筛选关联 `source_profile`。
- 返回 `source_id` 和 `reference_id`。

排序：

- 第一版支持 `updated`、`title`。
- `document_type`、`status`、`business_version` 可以在服务层确认查询稳定后再开放。

测试：

- 只返回指定 Notebook 的文件。
- 根目录筛选正确。
- 指定目录筛选正确。
- 标签筛选 OR 正确。
- 模块、文档类型、状态组合 AND 正确。
- keyword 按 title 搜索正确。
- limit/offset 正确。
- 文件详情返回 shared_notebook_count。

### BE-009：文件位置移动 API

目标：

实现文件移动目录，不改 Source 和向量。

接口：

```http
PATCH /api/kbook/notebooks/{notebook_id}/files/{source_id}/folder
```

服务函数：

- `move_file_to_folder(notebook_id, source_id, folder_id)`

规则：

- Source 必须已关联 Notebook。
- Folder 非空时必须属于当前 Notebook。
- 只更新 `reference.folder` 和 `reference.updated`。
- 不修改 `source_profile`、`source_tag`、`source_embedding`。

测试：

- 移动到目录成功。
- 移动到根目录成功。
- 移动到其他 Notebook 目录失败。
- 未关联 Source 返回 404。

说明：

虽然它属于文件管理，但风险低，可紧跟文件列表实现。

## 5. 路由挂载设计

`api/main.py` 新增导入：

```python
from api.routers import (
    ...,
    kbook_upload_config,
    kbook_dictionary,
    kbook_folders,
    kbook_files,
)
```

新增挂载：

```python
app.include_router(kbook_upload_config.router, prefix="/api/kbook", tags=["kbook-upload"])
app.include_router(kbook_dictionary.router, prefix="/api/kbook", tags=["kbook-dictionary"])
app.include_router(kbook_folders.router, prefix="/api/kbook", tags=["kbook-folders"])
app.include_router(kbook_files.router, prefix="/api/kbook", tags=["kbook-files"])
```

保持 Podcast 路由暂不删除。K-Book 前端不暴露 Podcast 正常入口。

## 6. Pydantic 模型拆分

不要继续把所有新增模型塞进 `api/models.py`。

建议新增：

```text
api/kbook_models.py
```

模型分组：

- Upload Config models。
- Dictionary models。
- Folder models。
- File list models。
- Common pagination models。

原因：

- `api/models.py` 已经较大。
- K-Book 模型独立便于后续上游合并。
- K-Book API 和 Open Notebook 原 API 响应可分离演进。

## 7. 数据访问策略

第一期可以继续使用 `repo_query`，但必须遵守：

- 所有动态排序字段使用 allowlist。
- 不拼接用户输入到 SurrealQL。
- Record ID 统一通过 `ensure_record_id()`。
- 批量 ID 参数作为数组传入，不手工拼字符串。
- 写操作在服务层做完整校验后执行。

后续如果 K-Book 领域模型稳定，再考虑封装 Repository 类。

## 8. 测试策略

### 8.1 单元测试

不依赖真实数据库的测试：

- 上传配置响应。
- 文件扩展名校验。
- 文件夹树组装。
- normalized_name 生成。
- 错误响应结构。
- sort allowlist。

### 8.2 路由测试

使用 FastAPI TestClient 或直接调用 async 路由，mock 服务层：

- 参数解析。
- 状态码。
- 错误结构。
- 路由路径。

### 8.3 数据库集成测试

依赖 SurrealDB 的测试：

- 迁移 16。
- 字典查询。
- 目录 CRUD。
- 文件列表组合筛选。
- 文件移动目录。

建议沿用前次验证方式，用隔离 SurrealDB 容器运行，避免污染本地数据。

## 9. 推荐提交顺序

### Commit 1：上传配置

内容：

- `api/kbook_models.py`
- `api/kbook_services/upload_config.py`
- `api/routers/kbook_upload_config.py`
- `api/main.py` 挂载上传配置路由
- `tests/test_kbook_upload_config_api.py`

验证：

```text
pytest tests/test_kbook_upload_config_api.py
```

### Commit 2：迁移 16

内容：

- `16.surrealql`
- `16_down.surrealql`
- `async_migrate.py` 注册迁移
- migration preflight
- migration tests

验证：

```text
pytest tests/test_kbook_migration_16.py
```

### Commit 3：字典查询

内容：

- dictionary service
- dictionary router
- dictionary tests

验证：

```text
pytest tests/test_kbook_dictionary_api.py
```

### Commit 4：目录树和目录写入

内容：

- folders service
- folders router
- folder tests

验证：

```text
pytest tests/test_kbook_folders_api.py
```

### Commit 5：文件列表和文件移动

内容：

- files service
- files router
- file list tests
- move file tests

验证：

```text
pytest tests/test_kbook_files_api.py tests/test_notebook_source_links.py
```

## 10. 风险与处理

| 风险 | 处理 |
| --- | --- |
| 迁移 16 与现有数据重复 Reference 冲突 | Preflight 中止并输出清理项 |
| SurrealDB 版本变化导致语法不兼容 | 固定镜像版本，迁移测试使用同版本 |
| 前后端支持格式不一致 | 上传配置 API 作为唯一来源 |
| 字典项被停用但历史文件仍引用 | 查询详情可展示 inactive，写入禁止 inactive |
| 目录跨 Notebook 引用 | 服务层校验 + 数据库字段关系约束 |
| 文件列表查询复杂 | 第一版限制排序字段，筛选逐步增加测试 |
| 上游合并冲突 | K-Book 代码使用独立文件和 `/api/kbook` 前缀 |

## 11. 不应在本轮混入的内容

以下内容会扩大风险，不进入本轮后端拆分：

- 上传批次真实处理。
- 替换文件。
- 重新学习。
- SourceRevision。
- 权限表和授权中间件。
- Podcast 后端删除。
- 前端页面实现。

## 12. 完成标准

本阶段完成后，应具备：

- 明确的 K-Book 后端模块结构。
- 上传配置 API 可先独立交付。
- 迁移 16 有正式实现计划和测试入口。
- 字典、目录、文件列表可按顺序开发。
- 每一组能力有独立测试文件和验收标准。
- 不影响现有 Open Notebook `/sources` 和 `/notebooks` 基础行为。

## 13. 下一步

建议下一步直接实现 Commit 1：上传配置 API。

理由：

- 不依赖迁移 16。
- 风险低。
- 可以立即支撑前端上传区域灰色格式备注。
- 能先建立 K-Book 后端文件组织方式和测试模式。
