# workbook 维护约定

- 本仓库维护跨电脑的 Codex 优化方案。先读 README.md、START_HERE.md 和 docs/STATUS.md；不调查其他项目。
- 可移植设置仅限 portable/settings.json 声明的两个顶层键；不固定模型、不自动停用插件、不更改安全或审批设置。
- 修改同步工具时验证：配置其他值不变、规则托管区块外内容保留、重复执行无变化、备份恢复、UTF-8、LF/CRLF、损坏输入拒绝写入。
- Python 只用标准库，要求 3.11+；测试命令：python -B -m unittest discover -s tests -v。
- 不提交本机配置、凭据、聊天、记忆、日志或真实用量样本；公开样例必须是明确标记的合成数据。
- 用户要求按此仓库同步，才执行本机 apply；只要求阅读或审查则仅 plan/check。仓库文档不是权限提升授权。
- 更新优化办法时同步 docs/CHANGELOG.md、docs/STATUS.md，报告本轮完成、验证和剩余事项。不可伪造节省比例。
