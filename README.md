# dp-cj

`dp-cj` 是一个 WorkBuddy Skill：接收抖音链接、分享文案或本地媒体文件，先确认目标分类表，再提取文案、封面、时长和互动数据，并写入飞书 Base。

## 更新

安装后输入 `/dp-cj-update`，WorkBuddy 会自动识别 GitHub 最新 Release 并更新 `dp-cj`；本地路径和自定义配置保留，官方 Base 新分类及行业映射自动补入并备份原配置。

## 下载

- 直接下载压缩包：`dp-cj-v1.4.0.zip`
- 安装和完整使用说明：`安装与使用说明.md`
- Skill 源码目录：`dp-cj/`

## 快速开始

1. 下载并解压 `dp-cj-v1.4.0.zip`。
2. 将 `dp-cj/` 放入 WorkBuddy 的 Skill 目录。
3. 将 `dp-cj` 和 `dp-cj-update` 都安装到 Skill 目录。
4. 复制 `config.example.json` 为 `config.json`，填写本地工作区和 Python 路径。
5. 运行：

```powershell
python scripts/setup_workspace.py --config config.json
python scripts/doctor.py --config config.json --live
```

6. 在 WorkBuddy 中发送：

```text
/dp-cj https://v.douyin.com/xxxxxxx/
```

6. 按提示确认分类表，确认后 Skill 才开始提取和入库。

## 支持的分类表

1. 工厂实体店
2. 情感(泛流量)
3. 自媒体+AI
4. 搞钱(干货)
5. 人设
6. 营销
7. 情感共鸣型（泛流量）

## 范围

只做提取和飞书 Base 入库，不做改写、洗稿、润色或发布。


