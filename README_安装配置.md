# dp-cj 纯提取版模板包 v1.1.0`n`n> 完整安装和使用步骤见同目录 `安装与使用说明.md`；Skill 安装后也可查看 `dp-cj/使用说明.md`。

这个版本只做：**先确认飞书 Base 分类表 → 提取视频文案和元数据 → 按对应表字段写入**。

不包含个性化资料维护、改写、洗稿、云文档创建或文案润色。

## 发给接收人时建议这样说

> 解压后把 `dp-cj` 放到 Skill 目录，复制 `config.example.json` 为 `config.json`，填写自己的工作区路径和 Python 路径，然后运行 setup 与 doctor。收到视频链接后，Skill 会先问你要放入哪张表，确认后才开始提取入库。

## 安装

1. 解压压缩包。
2. 将 `dp-cj/` 放到 Skill 目录，例如：

```text
你的项目/.workbuddy/skills/dp-cj/
```

3. 复制配置：

```powershell
Copy-Item config.example.json config.json
```

4. 修改 `config.json`：
   - `workspace_root`：接收人的本地工作区绝对路径。
   - `python_executable`：装有 `requests / av / playwright / sherpa_onnx` 的 Python。
   - `extraction.transcribe_script`：本地 `transcribe.py` 路径；没有本地 ASR 可留空。
5. 初始化并体检：

```powershell
python scripts/setup_workspace.py --config config.json
python scripts/doctor.py --config config.json --live
```

## 飞书 Base

默认对接共享 Base：

https://my.feishu.cn/base/AjdAbLBMEazYJRsX6u7cKUXjnBM?from=from_copylink

分类表：

1. 工厂实体店
2. 情感(泛流量)
3. 自媒体+AI
4. 搞钱(干货)
5. 人设
6. 营销

每次收到链接，都必须先让用户确认进入哪张表；确认前不提取、不写库。

## 目录结构

```text
dp-cj/
├── SKILL.md
├── config.example.json
├── payload.example.json
├── references/
│   └── field-extraction.md
└── scripts/
    ├── config_util.py
    ├── setup_workspace.py
    ├── doctor.py
    ├── douyin_transcript.py
    ├── ocr_frames.ps1
    └── write_record.py
```

## 注意

- `config.example.json` 中的 Base 地址和 table_id 是目标共享表；其余本地路径仍需接收人配置。
- 不要发送已经填好个人本地路径的 `config.json`。
- 封面会从视频详情提取并自动下载上传；标题截图、赞藏截图只有提供本地文件或 URL 时才上传。



