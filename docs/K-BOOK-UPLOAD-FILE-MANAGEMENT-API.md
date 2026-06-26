# K-Book 上传与文件管理 API 契约设计

## 1. 文档目的

本文档定义 K-Book 第一期上传向导和文件管理页面所需的 API 契约。

设计目标：

- 在不破坏 Open Notebook 现有 `/sources`、`/notebooks` 接口的前提下，增加 K-Book 文件组织能力。
- 支持目录、标签、业务元数据、上传批次、文件筛选和知识库关联管理。
- 明确请求、响应、校验、错误码和事务边界。
- 为后续用户、角色和项目权限保留服务层入口。

本文档是 API 设计，不代表代码已经实现。

## 2. 设计原则

### 2.1 保留现有接口

现有 Open Notebook 接口继续保留：

- `GET /sources`
- `POST /sources`
- `GET /sources/{source_id}`
- `PUT /sources/{source_id}`
- `DELETE /sources/{source_id}`
- `POST /notebooks/{notebook_id}/sources/{source_id}`
- `DELETE /notebooks/{notebook_id}/sources/{source_id}`

K-Book 一期新增接口优先使用 `/kbook/*` 前缀，降低与上游同步冲突。

### 2.2 Notebook 上下文优先

文件管理页面所有目录和文件列表接口必须带 `notebook_id`。

原因：

- 目录属于 Notebook。
- 文件在 Notebook 中的位置保存于 `reference.folder`。
- 后续权限也会以 Notebook、Project、Folder 和 Source 为判断入口。

### 2.3 Source 全局属性与 Reference 局部属性分离

API 必须明确区分：

| 类型 | 写入位置 | 示例 |
| --- | --- | --- |
| Source 全局属性 | `source`、`source_profile`、`source_tag` | 标题、模块、文档类型、标签、业务版本、状态 |
| Notebook 内位置 | `reference` | 目录 |

同一 Source 被多个 Notebook 共享时，修改 SourceProfile 和 SourceTag 会影响所有知识库中的该 Source 展示。API 响应需要暴露该事实，供前端提示。

### 2.4 批量上传按文件独立提交

批量上传不是一个大事务。

要求：

- 批次有统一 ID。
- 每个文件有独立状态。
- 单个文件失败不影响其他文件。
- 单个文件内部必须尽量保持 Source、Reference、Profile、Tag 一致。

## 3. 通用对象

### 3.1 Record ID

所有记录 ID 使用 SurrealDB 字符串格式：

```json
"notebook:abc"
```

API 入参允许客户端传入完整 Record ID。服务端统一使用 `ensure_record_id()` 处理。

### 3.2 Error Response

统一错误响应：

```json
{
  "error": {
    "code": "folder_not_found",
    "message": "Folder not found",
    "details": {
      "folder_id": "folder:123"
    }
  }
}
```

常用错误码：

| HTTP | code | 场景 |
| --- | --- | --- |
| 400 | validation_failed | 请求字段不合法 |
| 400 | unsupported_file_type | 文件格式不支持 |
| 400 | folder_not_empty | 删除非空目录 |
| 400 | folder_cycle | 移动目录形成循环 |
| 400 | dictionary_item_inactive | 使用停用字典项 |
| 400 | dictionary_type_mismatch | 字典项类型不匹配 |
| 400 | duplicate_reference | Source 已在 Notebook 中 |
| 404 | notebook_not_found | 知识库不存在 |
| 404 | source_not_found | Source 不存在 |
| 404 | folder_not_found | 目录不存在 |
| 409 | concurrent_update | 数据已被其他操作更新 |
| 413 | file_too_large | 文件超出大小限制 |
| 500 | internal_error | 未预期错误 |

### 3.3 Pagination

列表接口统一使用：

```text
limit: 1..100，默认 50
offset: >= 0，默认 0
```

响应：

```json
{
  "items": [],
  "total": 120,
  "limit": 50,
  "offset": 0
}
```

## 4. 上传配置 API

### 4.1 获取上传配置

```http
GET /kbook/upload/config
```

用途：

- 上传页面展示灰色格式备注。
- 前端文件选择框设置 `accept`。
- 前端预校验文件类型和大小。
- 避免 UI 硬编码一套支持格式。

响应：

```json
{
  "max_file_size_mb": 100,
  "max_files_per_batch": 50,
  "accept": ".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.md,.epub,.html,.mp4,.avi,.mov,.wmv,.mp3,.wav,.m4a,.aac,.jpg,.jpeg,.png,.tiff,.zip,.tar,.gz",
  "format_summary": "PDF、Word、PPT、Excel、文本、Markdown、网页、图片、音视频、压缩包等",
  "extensions": [
    "pdf",
    "doc",
    "docx",
    "ppt",
    "pptx",
    "xls",
    "xlsx",
    "txt",
    "md",
    "epub",
    "html",
    "mp4",
    "avi",
    "mov",
    "wmv",
    "mp3",
    "wav",
    "m4a",
    "aac",
    "jpg",
    "jpeg",
    "png",
    "tiff",
    "zip",
    "tar",
    "gz"
  ]
}
```

校验要求：

- 后端实际上传校验必须使用同一份扩展名配置。
- 前端展示的灰色备注使用 `format_summary`。
- 完整悬浮提示使用 `extensions`。

## 5. 字典 API

### 5.1 查询字典类型

```http
GET /kbook/dictionary-types
```

响应：

```json
{
  "items": [
    {
      "id": "dictionary_type:tag",
      "code": "tag",
      "name": "标签",
      "system": true,
      "description": "文件标签"
    }
  ]
}
```

### 5.2 查询字典项

```http
GET /kbook/dictionary-items?type=tag&active_only=true&keyword=蓝图
```

查询参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| type | 否 | `tag`、`module`、`document_type`、`document_status`、`ln_version` |
| active_only | 否 | 默认 `true` |
| keyword | 否 | 按名称或编码搜索 |
| limit | 否 | 默认 100 |
| offset | 否 | 默认 0 |

响应：

```json
{
  "items": [
    {
      "id": "dictionary_item:ln-logistics",
      "type": "module",
      "code": "LN_LOGISTICS",
      "name": "物流",
      "status": "active",
      "description": "Infor LN 物流相关模块",
      "sort_order": 10
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

### 5.3 创建字典项

```http
POST /kbook/dictionary-items
```

请求：

```json
{
  "type": "tag",
  "code": "BLUEPRINT",
  "name": "蓝图",
  "description": "项目蓝图资料",
  "sort_order": 10
}
```

响应：`201 Created`

```json
{
  "id": "dictionary_item:blueprint",
  "type": "tag",
  "code": "BLUEPRINT",
  "name": "蓝图",
  "status": "active",
  "description": "项目蓝图资料",
  "sort_order": 10
}
```

### 5.4 更新字典项

```http
PATCH /kbook/dictionary-items/{item_id}
```

请求：

```json
{
  "name": "项目蓝图",
  "description": "项目蓝图和流程确认资料",
  "status": "inactive",
  "sort_order": 20
}
```

规则：

- 系统字典类型不可修改编码。
- 字典项停用后不可被新上传或新编辑引用。
- 已被引用的字典项不建议物理删除。

## 6. 目录 API

### 6.1 查询目录树

```http
GET /kbook/notebooks/{notebook_id}/folders
```

响应：

```json
{
  "notebook_id": "notebook:abc",
  "items": [
    {
      "id": "folder:req",
      "name": "需求",
      "description": "",
      "parent": null,
      "sort_order": 10,
      "source_count": 12,
      "children": [
        {
          "id": "folder:req-gap",
          "name": "差异分析",
          "description": "",
          "parent": "folder:req",
          "sort_order": 10,
          "source_count": 4,
          "children": []
        }
      ]
    }
  ]
}
```

规则：

- 根目录不是实体记录。
- 根目录文件通过 `folder_id=null` 查询。

### 6.2 创建目录

```http
POST /kbook/notebooks/{notebook_id}/folders
```

请求：

```json
{
  "parent": null,
  "name": "蓝图设计",
  "description": "蓝图和流程确认文档",
  "sort_order": 10
}
```

响应：`201 Created`

```json
{
  "id": "folder:blueprint",
  "notebook_id": "notebook:abc",
  "parent": null,
  "name": "蓝图设计",
  "description": "蓝图和流程确认文档",
  "sort_order": 10,
  "created": "2026-06-25T12:00:00Z",
  "updated": "2026-06-25T12:00:00Z"
}
```

校验：

- `parent` 必须属于当前 Notebook。
- 同一父目录下名称唯一。
- 名称 trim 后不能为空。

### 6.3 更新目录

```http
PATCH /kbook/notebooks/{notebook_id}/folders/{folder_id}
```

请求：

```json
{
  "name": "方案蓝图",
  "description": "确认后的方案蓝图资料",
  "sort_order": 20
}
```

### 6.4 移动目录

```http
POST /kbook/notebooks/{notebook_id}/folders/{folder_id}/move
```

请求：

```json
{
  "parent": "folder:target-parent",
  "sort_order": 30
}
```

校验：

- 目标父目录属于同一 Notebook。
- 不能移动到自身。
- 不能移动到自身后代。
- 目录深度不能超过服务层限制，建议第一期限制为 20。

### 6.5 删除目录

```http
DELETE /kbook/notebooks/{notebook_id}/folders/{folder_id}
```

规则：

- 第一期仅允许删除空目录。
- 非空目录返回 `400 folder_not_empty`。

## 7. 文件列表 API

### 7.1 查询知识库文件

```http
GET /kbook/notebooks/{notebook_id}/files
```

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| folder_id | string/null | 指定目录；不传表示全部文件，传 `root` 表示根目录 |
| tag_ids | string[] | 多个标签，默认 OR |
| module_id | string | 模块 |
| document_type_id | string | 文档类型 |
| status_id | string | 文档状态 |
| business_version | string | 版本关键字 |
| keyword | string | 文件名关键字 |
| processing_status | string | `queued`、`processing`、`ready`、`failed` 等 |
| sort_by | string | `updated`、`title`、`document_type`、`status`、`business_version` |
| sort_order | string | `asc` 或 `desc` |
| limit | int | 默认 50 |
| offset | int | 默认 0 |

响应：

```json
{
  "items": [
    {
      "source_id": "source:abc",
      "reference_id": "reference:def",
      "title": "采购订单蓝图设计",
      "original_filename": "PO_Blueprint_v1.docx",
      "folder": {
        "id": "folder:blueprint",
        "path": "蓝图设计/采购"
      },
      "tags": [
        {
          "id": "dictionary_item:blueprint",
          "name": "蓝图"
        }
      ],
      "profile": {
        "module": {
          "id": "dictionary_item:ln-procurement",
          "name": "采购"
        },
        "document_type": {
          "id": "dictionary_item:solution-design",
          "name": "方案设计"
        },
        "business_version": "v1.0",
        "status": {
          "id": "dictionary_item:effective",
          "name": "有效"
        }
      },
      "processing": {
        "status": "ready",
        "embedded": true,
        "error": null
      },
      "created": "2026-06-25T12:00:00Z",
      "updated": "2026-06-25T12:00:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

查询规则：

- 必须从 `reference.out = notebook_id` 开始过滤。
- 目录条件使用 `reference.folder`。
- 标签条件使用 `source_tag`。
- 模块、文档类型、版本、状态使用 `source_profile`。
- 不同筛选字段之间为 AND。
- 多个标签默认 OR。

## 8. 上传批次 API

### 8.1 创建上传批次

```http
POST /kbook/upload-batches
Content-Type: multipart/form-data
```

表单字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| notebook_id | 是 | 目标知识库 |
| files | 是 | 一个或多个文件 |
| items | 是 | JSON 字符串，逐文件业务信息 |
| async_processing | 否 | 默认 `true` |
| embed | 否 | 默认 `true` |

`items` 示例：

```json
[
  {
    "client_file_id": "local-1",
    "filename": "PO_Blueprint_v1.docx",
    "title": "采购订单蓝图设计",
    "folder_id": "folder:blueprint",
    "tag_ids": ["dictionary_item:blueprint"],
    "module_id": "dictionary_item:ln-procurement",
    "document_type_id": "dictionary_item:solution-design",
    "business_version": "v1.0",
    "status_id": "dictionary_item:effective"
  }
]
```

响应：`202 Accepted`

```json
{
  "batch_id": "upload_batch:abc",
  "status": "queued",
  "total": 1,
  "accepted": 1,
  "rejected": 0,
  "items": [
    {
      "client_file_id": "local-1",
      "filename": "PO_Blueprint_v1.docx",
      "status": "queued",
      "source_id": null,
      "error": null
    }
  ]
}
```

校验：

- `items.length` 必须等于文件数量。
- `filename` 必须能匹配上传文件。
- `notebook_id` 必须存在。
- `folder_id` 非空时必须属于目标 Notebook。
- `tag_ids` 必须全部为 active 的 `tag` 类型字典项。
- `module_id` 必须为 active 的 `module` 类型字典项。
- `document_type_id` 必须为 active 的 `document_type` 类型字典项。
- `status_id` 必须为 active 的 `document_status` 类型字典项。
- 文件扩展名必须在 `/kbook/upload/config` 返回的清单中。

处理规则：

- 每个文件独立保存、创建 Source、创建 Reference、写入 SourceProfile、写入 SourceTag，并提交解析向量任务。
- 如果 Source 创建后 Reference/Profile/Tag 写入失败，该文件不得进入 `ready`，必须记录错误并进入可补偿状态。
- 上传批次接口不直接等待向量化完成。

### 8.2 查询上传批次状态

```http
GET /kbook/upload-batches/{batch_id}
```

响应：

```json
{
  "batch_id": "upload_batch:abc",
  "status": "processing",
  "total": 2,
  "queued": 0,
  "processing": 1,
  "ready": 1,
  "failed": 0,
  "items": [
    {
      "client_file_id": "local-1",
      "filename": "PO_Blueprint_v1.docx",
      "source_id": "source:abc",
      "reference_id": "reference:def",
      "status": "ready",
      "error": null
    },
    {
      "client_file_id": "local-2",
      "filename": "PO_Technical_Design.docx",
      "source_id": "source:ghi",
      "reference_id": "reference:jkl",
      "status": "processing",
      "error": null
    }
  ]
}
```

状态汇总：

| 批次状态 | 说明 |
| --- | --- |
| queued | 所有文件等待处理 |
| processing | 至少一个文件处理中 |
| completed | 所有文件 ready |
| completed_with_errors | 部分文件 failed |
| failed | 所有文件 failed 或批次级错误 |

## 9. 文件详情与编辑 API

### 9.1 获取文件详情

```http
GET /kbook/notebooks/{notebook_id}/files/{source_id}
```

响应结构与文件列表单项一致，额外返回：

```json
{
  "source_id": "source:abc",
  "reference_id": "reference:def",
  "shared_notebook_count": 2,
  "global_metadata_warning": true,
  "full_text_available": true
}
```

`global_metadata_warning=true` 表示标签和 SourceProfile 是全局属性，修改会影响该 Source 在其他 Notebook 的展示。

### 9.2 更新显示名称

```http
PATCH /kbook/sources/{source_id}/title
```

请求：

```json
{
  "title": "采购订单蓝图设计"
}
```

规则：

- 写入 `source.title`。
- 名称 trim 后不能为空。
- 不修改物理文件名。
- 不触发重新学习。

### 9.3 移动文件目录

```http
PATCH /kbook/notebooks/{notebook_id}/files/{source_id}/folder
```

请求：

```json
{
  "folder_id": "folder:blueprint"
}
```

规则：

- `folder_id=null` 表示移动到根目录。
- Folder 必须属于当前 Notebook。
- 只更新 `reference.folder`。
- 不修改 Source、SourceProfile、SourceTag 或向量。

### 9.4 更新文件元数据

```http
PUT /kbook/sources/{source_id}/profile
```

请求：

```json
{
  "module_id": "dictionary_item:ln-procurement",
  "document_type_id": "dictionary_item:solution-design",
  "business_version": "v1.0",
  "status_id": "dictionary_item:effective"
}
```

响应：

```json
{
  "source_id": "source:abc",
  "module_id": "dictionary_item:ln-procurement",
  "document_type_id": "dictionary_item:solution-design",
  "business_version": "v1.0",
  "status_id": "dictionary_item:effective",
  "updated": "2026-06-25T12:00:00Z"
}
```

规则：

- 不存在 SourceProfile 时创建。
- 字典项必须 active 且类型正确。
- 不触发重新学习。

### 9.5 更新文件标签

```http
PUT /kbook/sources/{source_id}/tags
```

请求：

```json
{
  "tag_ids": [
    "dictionary_item:blueprint",
    "dictionary_item:procurement"
  ]
}
```

规则：

- 采用替换语义：请求中的标签集合即最终标签集合。
- 所有标签必须为 active 的 `tag` 类型字典项。
- 服务层先整体验证，验证通过后再替换 SourceTag。
- 不触发重新学习。

### 9.6 从知识库移除文件

```http
DELETE /kbook/notebooks/{notebook_id}/files/{source_id}
```

规则：

- 删除 `reference`。
- 不默认删除 Source。
- 如果 Source 仍关联其他 Notebook，不影响其他 Notebook。
- 如果 Source 无任何 Reference，是否清理进入后续后台清理策略。

## 10. 添加已有 Source API

### 10.1 搜索可添加 Source

```http
GET /kbook/sources/search?keyword=采购&exclude_notebook_id=notebook:abc
```

响应：

```json
{
  "items": [
    {
      "source_id": "source:abc",
      "title": "采购订单蓝图设计",
      "original_filename": "PO_Blueprint_v1.docx",
      "tags": [],
      "profile": {},
      "shared_notebook_count": 1
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### 10.2 添加已有 Source 到知识库

```http
POST /kbook/notebooks/{notebook_id}/files
```

请求：

```json
{
  "source_id": "source:abc",
  "folder_id": "folder:blueprint"
}
```

响应：`201 Created` 或 `200 OK`

```json
{
  "source_id": "source:abc",
  "reference_id": "reference:def",
  "notebook_id": "notebook:target",
  "folder_id": "folder:blueprint",
  "already_exists": false
}
```

规则：

- 如果关系已存在，返回 `200 OK`，`already_exists=true`，不重复创建 Reference。
- 新建关系使用 `source -> reference -> notebook`。
- `folder_id` 必须属于当前 Notebook。

## 11. 知识库属性 API 扩展

现有 `/notebooks` 响应需要在 K-Book 接口中扩展属性，不直接改变旧响应模型。

### 11.1 查询 K-Book 知识库

```http
GET /kbook/notebooks
```

响应：

```json
{
  "items": [
    {
      "id": "notebook:abc",
      "name": "A 客户 LN 项目知识库",
      "description": "实施项目资料",
      "customer": {
        "id": "customer:a",
        "name": "A 客户"
      },
      "project": {
        "id": "project:a-ln",
        "name": "A 客户 LN 实施"
      },
      "ln_versions": [
        {
          "id": "dictionary_item:ln-10-8",
          "name": "LN 10.8"
        }
      ],
      "scope": "仅适用于 A 客户 LN 10.8 实施项目",
      "source_count": 120,
      "created": "2026-06-25T12:00:00Z",
      "updated": "2026-06-25T12:00:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### 11.2 更新 K-Book 知识库属性

```http
PATCH /kbook/notebooks/{notebook_id}
```

请求：

```json
{
  "name": "A 客户 LN 项目知识库",
  "description": "实施项目资料",
  "customer_id": "customer:a",
  "project_id": "project:a-ln",
  "ln_version_ids": ["dictionary_item:ln-10-8"],
  "scope": "仅适用于 A 客户 LN 10.8 实施项目"
}
```

规则：

- 如果同时传入 `customer_id` 和 `project_id`，项目必须属于该客户。
- `ln_version_ids` 必须为 active 的 `ln_version` 类型字典项。
- 更新 LN 版本采用替换语义。

## 12. 服务层校验职责

| 规则 | API |
| --- | --- |
| Folder 属于 Notebook | 目录、上传、移动文件、添加已有 Source |
| Folder 不形成循环 | 移动目录 |
| 同级目录名称唯一 | 创建目录、重命名目录 |
| Reference 不重复 | 上传、添加已有 Source |
| 字典项 active | 上传、更新 Profile、更新 Tag、更新 LN 版本 |
| 字典项类型正确 | 上传、更新 Profile、更新 Tag、更新 LN 版本 |
| 项目属于客户 | 更新 K-Book 知识库 |
| 文件扩展名支持 | 上传配置、上传批次 |
| Source/Profile/Tag 写入一致 | 上传批次、元数据更新 |

## 13. 前端缓存与刷新建议

前端使用 TanStack Query 时建议 Query Key：

```text
kbook.uploadConfig
kbook.dictionaryItems(type, activeOnly, keyword)
kbook.folderTree(notebookId)
kbook.files(notebookId, filters)
kbook.fileDetail(notebookId, sourceId)
kbook.uploadBatch(batchId)
kbook.notebooks(filters)
```

变更后的失效规则：

| 操作 | 需要刷新 |
| --- | --- |
| 创建/更新/删除目录 | folderTree、files |
| 上传批次创建 | files、uploadBatch |
| 上传状态变化 | files、uploadBatch、fileDetail |
| 移动文件 | files、fileDetail、folderTree |
| 更新 Profile | files、fileDetail |
| 更新 Tags | files、fileDetail、dictionary usage |
| 移除文件 | files、folderTree |
| 更新知识库属性 | kbook.notebooks、当前 notebook detail |

## 14. 与现有接口的关系

第一期建议：

- 保留现有 `/sources` 供 Open Notebook 原页面使用。
- K-Book 文件管理页面使用 `/kbook/notebooks/{notebook_id}/files`。
- K-Book 上传向导使用 `/kbook/upload-batches`。
- K-Book 目录管理使用 `/kbook/notebooks/{notebook_id}/folders`。
- K-Book 字典管理使用 `/kbook/dictionary-items`。
- 现有 `POST /notebooks/{notebook_id}/sources/{source_id}` 可以继续保留，但 K-Book 页面优先使用支持 `folder_id` 的新增接口。

后续如果确认 K-Book 不再暴露原 Open Notebook 上传入口，可以把旧上传入口隐藏，但后端接口暂不删除。

## 15. 验收测试清单

API 实现后至少覆盖：

1. 上传配置返回格式摘要、accept 和完整扩展名。
2. 不支持扩展名上传返回 `unsupported_file_type`。
3. 创建根目录和子目录成功。
4. 同一父目录同名创建失败。
5. 移动目录到自身或后代失败。
6. 删除非空目录失败。
7. 上传文件到根目录成功。
8. 上传文件到指定目录成功。
9. 上传时使用停用标签失败。
10. 上传时使用错误类型字典项失败。
11. 批量上传部分成功、部分失败时返回逐文件状态。
12. 文件列表按目录筛选正确。
13. 文件列表按标签、模块、文档类型、状态组合筛选正确。
14. 移动文件只更新 Reference，不修改 SourceProfile。
15. 更新 Profile 不触发重新学习。
16. 更新 Tags 使用替换语义。
17. 添加已有 Source 到同一 Notebook 幂等。
18. 从 Notebook 移除 Source 不影响其他 Notebook。
19. K-Book 知识库更新时校验项目属于客户。
20. 页面正常入口不出现 Podcast API 调用。

## 16. 后续设计项

完成本文档后，建议进入：

1. [第一批后端实现拆分：字典、目录、文件列表、上传配置](K-BOOK-BACKEND-IMPLEMENTATION-SPLIT.md)。
2. 上传批次任务模型设计。
3. 前端路由和组件拆分设计。
4. 文件替换、重新学习、事务切换和失败回滚 API。
