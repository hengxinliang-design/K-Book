# KBD-002：迁移 16 仅实现文件组织基础结构

## 状态

已确认

## 决策

K-Book 使用数据库迁移 16 实现第一期文件组织基础结构：

- Customer。
- Project。
- Notebook 适用范围。
- Folder。
- Reference 目录位置。
- DictionaryType 和 DictionaryItem。
- SourceProfile。
- SourceTag。
- NotebookLnVersion。

文件替换及 SourceRevision 不进入迁移 16，后续使用独立迁移实现。

## 原因

文件组织和上传分类可以独立交付。文件替换涉及暂存文件、暂存向量、原子切换和失败回滚，风险与复杂度明显更高，不应混入第一期基础迁移。

拆分迁移可以：

- 降低第一期发布风险。
- 使目录、字典和元数据功能先完成闭环。
- 让文件替换通过独立原型验证事务方案。
- 简化 Up、Down 和兼容性测试。

## 实现约束

- 迁移文件为 `16.surrealql` 和 `16_down.surrealql`。
- 必须手工注册到 `AsyncMigrationManager`。
- 迁移只创建系统字典类型，不创建未经确认的业务字典值。
- 旧 `source.topics` 不自动迁移为标签。
- 旧 Reference 默认处于知识库根目录。
- Down Migration 仅供开发测试使用。

