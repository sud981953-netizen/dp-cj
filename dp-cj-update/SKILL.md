---
name: dp-cj-update
description: |
  触发方式：/dp-cj-update、/更新dp-cj、「更新 dp-cj」「检查 dp-cj 版本」。
  从 GitHub 识别 dp-cj 最新 Release，并更新本机 WorkBuddy Skill；保留用户 config.json 和本地工作区。
metadata:
  version: "1.0.0"
---

# dp-cj-update：更新 dp-cj

用户明确输入 `/dp-cj-update` 或明确要求更新 dp-cj 时，直接执行更新，不再做第二次确认。

## 更新范围

- 只更新 GitHub 仓库 `sud981953-netizen/dp-cj` 中的 `dp-cj` 和 `dp-cj-update`。
- 保留已存在的 `config.json`，不覆盖用户的工作区、Python、转写内核及自定义飞书配置；setup 会为官方 Base 增量补充缺失分类与行业映射，并备份原配置。
- 保留其他 WorkBuddy Skill 和用户文件。
- 不创建后台任务、定时任务或 Agent Hook。

## 执行步骤

### 1. 检查最新版本

```bash
python scripts/update_dp_cj.py --check-only
```

脚本会读取 GitHub 最新 Release，并与本机 `dp-cj` 版本比较。

### 2. 执行更新

确认有新版本，或用户明确要求强制更新时运行：

```bash
python scripts/update_dp_cj.py
```

脚本会：

1. 下载 GitHub 最新 Release 压缩包。
2. 校验 SHA-256。
3. 备份当前 `dp-cj`。
4. 更新 `dp-cj` 与 `dp-cj-update`，但跳过 `config.json`。
5. 运行 `setup_workspace.py`，备份并迁移官方 Base 的缺失分类/行业配置，再运行 `doctor.py --live`。

### 3. 回复格式

成功：

> dp-cj 已从 vX.X.X 更新到 vY.Y.Y，config.json 已保留。当前对话如果还没读取到新能力，请新建一次对话后使用。

已是最新：

> 当前 dp-cj 已是最新版本 vX.X.X，无需更新。

失败：

> dp-cj 没有更新完成：{简短原因}。处理完网络、权限或路径问题后，再输入 /dp-cj-update。

## 边界

- 用户只问版本、更新内容或是否需要更新时，先运行 `--check-only` 回答，不执行更新。
- 不使用 `npx skills update`，避免更新用户安装的其他 Skill。
- 如果找不到本机 `dp-cj` 目录，要求用户先安装 Skill。
- 如果 doctor 失败，可以报告“文件已更新但自检失败”，不能假装全部成功。

---

完成当前任务后直接结束。
