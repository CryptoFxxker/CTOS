# 资讯文章目录

这个目录用于存放资讯系统的 Markdown 文章文件。

## 文件格式

每篇文章应该是一个 Markdown 文件（`.md` 扩展名），支持以下格式：

### Front Matter（元数据）

在文件开头使用 YAML 格式的 front matter 来定义文章元数据：

```yaml
---
title: 文章标题
slug: article-slug
category: 分类名称
tags: 标签1,标签2,标签3
excerpt: 文章摘要（可选）
cover_image: https://example.com/image.jpg
published_at: 2024-12-15T10:00:00Z
is_published: true
---
```

### 必需字段

- `title`: 文章标题
- `slug`: URL 别名（唯一标识符，建议使用英文和连字符）

### 可选字段

- `category`: 文章分类（默认：未分类）
- `tags`: 标签，用逗号分隔（默认：空）
- `excerpt`: 文章摘要（默认：从内容自动提取）
- `cover_image`: 封面图片 URL（默认：使用系统默认图片）
- `published_at`: 发布时间（ISO 格式，默认：当前时间）
- `is_published`: 是否发布（默认：true）

## 文章目录配置

文章目录的配置在 `website/settings.py` 中：

```python
# 资讯系统配置
ARTICLES_DIR = os.path.join(BASE_DIR, 'articles')
```

**配置说明**：
- 默认目录：`website/articles`（相对于项目根目录）
- 可以通过环境变量 `ARTICLES_DIR` 覆盖默认配置
- 支持绝对路径和相对路径（相对路径会基于 `BASE_DIR` 解析）

**修改目录位置**：
1. 直接修改 `settings.py` 中的 `ARTICLES_DIR`
2. 或设置环境变量：`export ARTICLES_DIR=/path/to/your/articles`

## 使用方法

### 方法 1：批量导入所有文章

```bash
# 使用 settings.py 中配置的目录（推荐）
python manage.py import_all_markdown --author=admin

# 指定自定义目录（会覆盖 settings 配置）
python manage.py import_all_markdown --dir=/path/to/articles --author=admin

# 更新已存在的文章
python manage.py import_all_markdown --author=admin --update
```

### 方法 2：导入单个文章

```bash
# 导入单个文件
python manage.py import_markdown articles/my_article.md

# 指定作者
python manage.py import_markdown articles/my_article.md --author=admin

# 更新已存在的文章
python manage.py import_markdown articles/my_article.md --update
```

## 文章命名建议

- 使用有意义的文件名，如：`01-系统介绍.md`
- 文件名中的数字可以用于排序
- 避免使用特殊字符，建议使用连字符（`-`）分隔单词

## 示例文章

目录中已包含以下示例文章：

1. `01-系统介绍.md` - CTOS 系统介绍
2. `02-账户管理指南.md` - 账户管理功能使用指南
3. `03-指标分析详解.md` - 技术指标分析功能详解
4. `04-快速开始指南.md` - 系统快速开始指南
5. `05-策略管理入门.md` - 策略管理功能入门
6. `06-系统更新日志.md` - 系统更新日志

## Markdown 语法支持

文章内容支持标准 Markdown 语法：

- **标题**：使用 `#` 符号
- **粗体**：使用 `**文本**`
- **斜体**：使用 `*文本*`
- **列表**：使用 `-` 或 `*` 或数字
- **链接**：使用 `[文本](URL)`
- **代码**：使用反引号 `` `代码` ``
- **代码块**：使用三个反引号

## 注意事项

1. 确保 `slug` 字段唯一，如果重复会提示错误
2. 使用 `--update` 参数可以更新已存在的文章
3. 文件编码应为 UTF-8
4. 图片建议使用图床服务（如 Unsplash）的 URL

## 查看导入的文章

导入成功后，您可以：

1. 访问 `/news/` 查看资讯列表
2. 访问 `/admin/` 在管理后台查看和编辑文章
3. 点击文章标题查看详情

---

**提示**：如果您修改了 Markdown 文件，记得使用 `--update` 参数重新导入以更新文章内容。

