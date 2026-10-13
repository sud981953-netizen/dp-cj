---
name: dp-cj
description: |
  触发方式：/dp-cj、/短视频提取、「提取这条视频」「把链接入库」。
  接收抖音链接、分享文案或本地媒体文件，先确认要进入的飞书 Base 分类表，再提取标题、口播全文、开头金句、选题、平台、发布日期等字段并写入对应表；只做提取和入库，不做改写。
metadata:
  version: "1.2.0"
---

# dp-cj：短视频文案提取入库

本 skill 只负责三件事：**确认分类表 → 提取视频文案与元数据 → 按对应表字段写入飞书 Base**。不生成改写稿，不创建云文档，不维护额外个性化资料。

## 强制前置提问

只要用户发送视频链接或分享文案，第一条回复必须先询问分类，**不得立即提取、转写、加工或写库**。即使用户在发链接时顺便猜了一个分类，也必须等用户明确确认后再执行。

固定提问：

```text
请确认这条链接要放入哪张表：
1. 工厂实体店
2. 情感(泛流量)
3. 自媒体+AI
4. 搞钱(干货)
5. 人设
6. 营销

回复表名或编号即可。确认前我不会开始提取或入库。
```

用户必须明确回复以下名称之一，或回复编号 1–6：

- 工厂实体店
- 情感(泛流量)
- 自媒体+AI
- 搞钱(干货)
- 人设
- 营销

如果回复含糊、出现多个分类或要求“你帮我判断”，继续询问，不执行任务。

## 版本检查

每次进入本 Skill，先运行：

```bash
python scripts/check-update.py
```

脚本有输出时，将更新提醒追加在本次回复最末尾；无输出或失败时跳过，不影响当前任务。

## 配置检查

首次使用运行：

```bash
python scripts/setup_workspace.py --config config.json
python scripts/doctor.py --config config.json --live
```

配置不存在时复制 `config.example.json` 为 `config.json`。脚本查找顺序：`--config` → 环境变量 `DP_CJ_CONFIG` → skill 根目录 `config.json`。

## 执行流程

### 1. 确认目标表

用户确认分类后，从 `feishu.tables` 取得对应 `table_id` 和 `field_map`。不要把内容写入其他表。

### 2. 提取

链接/分享文案：

```bash
<python_executable> scripts/douyin_transcript.py --config config.json --category "<用户确认的分类>" --payload-out "_tmp/payload.json" "<链接或分享文案>"
```

本地媒体：

```bash
<python_executable> scripts/douyin_transcript.py --config config.json --category "<用户确认的分类>" --payload-out "_tmp/payload.json" --file "<文件>" --author "<作者>" --link "<原链接，如有>"
```

读取输出的 Markdown 与 `[payload]` JSON，自动取得标题、作者、发布时间、时长、互动数据、封面和口播全文；优先使用 JSON payload，避免手工抄写统计字段。机器转写写入前只校正明显的同音字、领域词和断句错误，不改写原文；报告中注明“已做最小转写校对”。链接模式优先官方字幕，其次音频流语音识别，再从视频音轨识别，最后才用 OCR 硬字幕兜底。

### 3. 填字段

只填写目标表已有字段，详见 `references/field-extraction.md`：

- 标题
- 文案全文
- 开头+金句
- 选题
- 链接
- 平台
- 发布日期
- 视频时长
- 点赞数
- 评论数
- 收藏数
- 分享数
- 文案类型（选中分类与该字段一致；工厂实体店没有此字段则不填）
- 赞藏数（仅工厂实体店、搞钱(干货)表有；按点赞数 + 收藏数计算，缺失写 0）
- 原始内容类型（仅搞钱(干货)表有；仅在输入或元数据明确提供时填）
- 封面 / 标题截图 / 赞藏截图（封面优先从视频详情提取；write_record.py 会自动下载并上传附件。截图只有提供本地文件或 URL 时才上传）

“开头+金句”格式：

```text
开头：{原文第一句}
金句：
1. {原文金句}
2. {原文金句}
```

### 4. 写入

payload 必须包含用户确认的 `category`：

```bash
<python_executable> scripts/write_record.py --config config.json --payload "<payload.json>" --dry-run
<python_executable> scripts/write_record.py --config config.json --payload "<payload.json>"
```

脚本会按分类选择对应表、映射字段，并按“链接”查重：同一链接更新原记录，不新增重复行。

### 5. 报告

只报告：分类表、标题、平台、发布日期、来源链接、写入动作（created/updated）、Base 链接。不得展示内部 JSON、token、会话字段或调试日志。

## 边界

- 只做提取与字段入库，不做洗稿、改写、润色、选题策划或文案创作。
- 没有用户分类确认，不得执行任何提取或写入。
- 表内不存在的字段必须跳过，不自行新增列。
- 附件无法可靠取得时留空，不伪造截图或封面；能取得封面 URL 时必须下载并上传到「封面」字段。
- 配置中的工作区路径属于使用者本地环境；共享 Base 地址由 `config.example.json` 提供。







