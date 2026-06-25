# KBD-001：K-Book 文件组织领域边界

## 状态

已确认

## 决策

K-Book 使用增量领域对象扩展 Open Notebook，不将目录、标签、客户、项目和全部元数据直接写入核心 `source`。

具体边界：

- 目录位置保存在 `source -> reference -> notebook` 关联上。
- 文件固有业务元数据保存在一对一 `source_profile`。
- 统一标签使用 `source_tag` 关联受控 `dictionary_item`。
- 客户和项目使用独立实体。
- LN 版本、模块、文档类型和文档状态使用统一字典。
- 文件替换保持 `source.id` 稳定，通过 `source_revision` 管理内容版本。
- 现有 `source.topics` 为上游兼容字段，不作为 K-Book 标签权威来源。

## 原因

Open Notebook 已支持同一 Source 关联多个 Notebook。若目录直接存在 Source 上，同一文件无法在不同知识库使用不同目录位置。

客户和项目未来参与权限控制，需要稳定 ID 和明确关系，不能降级为自由文本标签。

保持核心 Source 模型稳定可以降低后续合并 Open Notebook 上游更新的冲突。

## 影响

- 文件列表查询需要组合 Reference、Folder、SourceProfile 和字典关系。
- 元数据筛选需要在检索候选阶段生效。
- 上传向导需要同时创建或更新多个关联对象。
- 删除与替换操作必须处理关联对象的生命周期。
- 第一、二期数据库迁移分开，先实现组织管理，再实现替换事务。

