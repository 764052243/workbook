# workbook · Codex 优化办法

维护者自己的跨电脑 Codex 配置和工作方法。当前版本：**2026.10.26.1**。

把下面这段发给任意一台电脑上的 Codex：

> 请读取 https://github.com/764052243/workbook/blob/main/START_HERE.md ，按其中方案同步本机 Codex 优化：先检查和预览，在保留本机模型、插件、凭据、安全设置及额外个人规范的前提下应用，做好备份并验证。保留默认 xhigh；完成后列出还有什么未做。然后继续我的当前任务。

这段请求授权本次本机同步。若只是让 Codex 阅读或审查，不应执行写入。

## 会同步什么

- 全局工作规则：最小改动、定位后精读、必要验收、短报告、创作完整交付、无项目边界、每轮剩余事项。
- 两个可移植设置：`model_reasoning_effort = "xhigh"`、`tool_output_token_limit = 8000`。
- 任务模板、只读检查、恢复和真实用量对照工具。

不会复制整份本机配置；本机模型、插件、MCP、记忆、权限和凭据保持原样。账户可用模型、已安装插件、操作系统及客户端版本仍会影响能力；阅读文档不能让缺失能力凭空安装，也不保证实际消耗完全一样。

## 本机执行

Python 3.11+，只用标准库，不安装第三方包。Git 已可用时：

```text
git clone https://github.com/764052243/workbook.git
cd workbook
python tools/codex_optimize.py plan
python tools/codex_optimize.py apply
python tools/codex_optimize.py check
```

Windows 也可用 `py -3.11`，macOS/Linux 常用 `python3`。Codex 桌面环境可先查已有捆绑 Python；没有合适 Python 时按 START_HERE 的手工步骤合并，不自动安装依赖。

工具默认使用现有 `CODEX_HOME`，否则为用户目录下 `.codex`；可在子命令后加 `--codex-home 路径`。不设置或重定向该环境变量。

`apply` 自动备份并验证，只维护两个设置和规则托管区块。重复执行无变化时不再写文件或创建备份。未知的原有规则保留在区块外，输出提示由 Codex 在本机核对冲突；不自动删减个人规范。符号链接、异常 TOML 或损坏托管标记会被拒绝。

恢复：`python tools/codex_optimize.py restore --backup 上次输出的backup_id`。如果安装后又改过文件，恢复会拒绝覆盖，需先在本机比较。

## 更新与优化

已有本地仓库时先检查未提交改动，再 `git pull --ff-only`；存在本地修改先保护现场，不自动 stash/reset。然后重新运行 plan/apply/check。普通任务不每轮联网检查本仓库。

- [其他电脑的完整入口](START_HERE.md)
- [当前方案与未完成项](docs/STATUS.md)
- [常用任务模板](docs/TEMPLATES.md)
- [真实用量记录](docs/MEASUREMENT.md)
- [更新记录](docs/CHANGELOG.md)

## 用户提供的资料

- [Windows ChatGPT 桌面端升级流程.docx](docs/reference/Windows%20ChatGPT%20桌面端升级流程.docx)：按用户要求原样归档，未读取或核验正文。

维护变更后运行：`python -B -m unittest discover -s tests -v`。本仓库不承诺降低 80%；文件缩小、单次工具预算和任务总消耗是不同指标。
