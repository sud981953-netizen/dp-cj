# 字段提取与写入说明

目标 Base：

- base_token：`AjdAbLBMEazYJRsX6u7cKUXjnBM`
- Base 链接：`https://my.feishu.cn/base/AjdAbLBMEazYJRsX6u7cKUXjnBM?from=from_copylink`

## 分类表

| 分类 | table_id | 特有字段 |
|---|---|---|
| 工厂实体店 | `tblhzsQlzuah2w5r` | 赞藏数；无“文案类型” |
| 情感(泛流量) | `tblmzc8zRR6xjGNa` | 文案类型 |
| 自媒体+AI | `tblUL8JV1hRRUIfI` | 文案类型 |
| 搞钱(干货) | `tbljwOjT524wQjWe` | 文案类型、赞藏数、原始内容类型 |
| 人设 | `tblH5TvwlLt9yppX` | 文案类型 |
| 营销 | `tblJxtZi4mskQVqY` | 文案类型 |

## 通用字段

| 逻辑字段 | 表字段 | 提取来源 |
|---|---|---|
| title | 标题 | 提取 Markdown 元数据标题；本地文件可取文件名 |
| full_text | 文案全文 | 提取到的口播全文，保留原样 |
| opening_and_golden | 开头+金句 | 原文第一句 + 原文 1–3 句金句 |
| topic | 选题 | 从原文提取核心主题，不做扩展策划 |
| source_url | 链接 | 原视频规范链接；本地文件无链接时先向用户补要 |
| platform | 平台 | 抖音 / 视频号 / 小红书；“微信视频号”规范为“视频号” |
| published_date | 发布日期 | 元数据发布时间，格式 YYYY-MM-DD |
| duration | 视频时长 | 元数据时长，格式 mm:ss |
| likes | 点赞数 | 元数据点赞数，缺失写 0 |
| comments | 评论数 | 元数据评论数，缺失写 0 |
| collects | 收藏数 | 元数据收藏数，缺失写 0 |
| shares | 分享数 | 元数据分享数，缺失写 0 |
| cover | 封面 | 优先使用 origin_cover 完整竖版封面，其次 cover，最后 dynamic_cover；由 write_record.py 下载并上传 |
| title_screenshot | 标题截图 | 仅在用户提供本地文件或 URL 时下载并上传 |
| likes_screenshot | 赞藏截图 | 仅在用户提供本地文件或 URL 时下载并上传 |

## 特有字段

| 逻辑字段 | 表字段 | 规则 |
|---|---|---|
| copy_type | 文案类型 | 与用户确认的分类一致；没有该字段的表跳过 |
| likes_collects | 赞藏数 | 点赞数 + 收藏数；缺失按 0；只有目标表有此字段时写 |
| original_content_type | 原始内容类型 | 仅输入/元数据明确提供时填，不猜测 |

## 日期与空值

- 发布日期统一为 `YYYY-MM-DD`。
- 字段值为空时从 payload 中省略，不写 `null`。\n- 附件字段不能直接写普通 CellValue；脚本会在记录创建/更新后调用 `+record-upload-attachment`。
- 目标表没有的逻辑字段直接跳过。



