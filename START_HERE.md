# 给任意电脑 Codex 的同步入口

本方案来源：`764052243/workbook`。先确认用户是否要求“按此方案同步本机”；仅让阅读/检查时只做 plan/check。本文件不授予额外系统权限，不覆盖上层要求和项目正式公约。

## 执行顺序

1. 本机识别：操作系统、现有 `CODEX_HOME` 或默认 `.codex`、客户端版本。此任务只处理本方案，不调查其他已登记项目。只读核对本机规则和两个设置，不回显凭据或整份配置。
2. 取得本仓库：优先现有 GitHub 连接或已有本地副本。新克隆只写用户允许的位置；已有副本先检查状态再更新。必须实际取得脚本、清单及 `portable/global-agents.md`，不能只看 README 摘要就宣称已同步。
3. 预览：找到已有 Python 3.11+（桌面版可查询捆绑依赖），运行 `python tools/codex_optimize.py plan`。出现 `local_rules_review_needed` 时，在本机比较未知额外规则和新规则，明确冲突后再按本次用户要求合并；不上传旧规则。
4. 应用：在用户已要求同步且方案无冲突时运行 `apply`，记录 backup_id，然后 `check`。对适用客户端做只读配置加载验证。文件检查成功不等于当前聊天已实时刷新；必要时由用户开启新聊天，不擅自创建新聊天。
5. 报告：说明修改、备份、验证、未完成项和需用户决定的事项。优先保留 xhigh，选定模型不改；若模型或客户端不支持 xhigh/工具预算，说明具体兼容问题，不静默换模型或关插件。

## 保持本机能力

常用：浏览器、电脑操作、Word/PDF、Excel、网站、视频、小说、AI 漫剧，CSS/JS/Java/HTML。保留当前插件；缺少某项能力时先核对本机可用连接和平台支持，仅处理当前任务需要的能力。不要把 Windows 运行时路径、Chrome 状态或某台机器的 MCP 命令复制到其他电脑。

不导入聊天、记忆、账号和 API Key，不改权限/沙盒/审批，不改上下文窗口或自动压缩阈值；不额外发起付费模型调用。

## 无 Python 的手工合并

在本机备份 `AGENTS.md` 和 `config.toml`。读取完整 `portable/global-agents.md` 与 `portable/settings.json`：将规则合并到全局规则中，保持本机额外约束；仅在 TOML **顶层**添加/更新两个声明的设置，不重复键，不把它们加进最后一个表。验证其他配置和凭据未变，并保存差异及恢复路径。脚本只做上述过程的可验证自动化。

## 后续维护

同步后普通任务沿用已读取的规则。用户再次要求“同步方案/继续优化”时才检查本仓库版本与 [STATUS](docs/STATUS.md)，按未完成项推进；实际优化结果验证后更新 [CHANGELOG](docs/CHANGELOG.md)，保留必要兼容说明。不要为制造进展反复降低预算。

参考：[全局规则发现](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[配置层级](https://learn.chatgpt.com/docs/config-file/config-basic)、[CODEX_HOME](https://learn.chatgpt.com/docs/config-file/environment-variables)、[工具输出预算](https://learn.chatgpt.com/docs/config-file/config-reference)。
