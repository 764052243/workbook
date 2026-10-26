# 真实任务用量记录

只记录完整任务的短标签和数值，不记录提示词、源码、客户数据、路径或密钥。默认数据在本机 `CODEX_HOME/workbook/measurements.jsonl`，不上传 Git。

```text
python tools/measure.py record --task-id 唯一短编号 --family 同类任务 --group after --model 本次实际模型 --effort xhigh --basis 相同统计口径 --source 指标来源 --success
python tools/measure.py report
```

可加实际取得的 `--input-tokens`、`--cached-tokens`、`--output-tokens`、`--elapsed-seconds`、`--tool-calls`、`--retries`。没取得就省略，保存为 null；失败任务用 `--failed`。一个编号在同一组只记录一次；不要让重复录入提高样本数。

`--group before` 为真实优化前基线，`after` 为优化后；没有优化前数据就留待比较，不把当前数据假装成过去的数据。可用命令最前面的 `--file 路径` 指定本地数据文件。

计算口径：输入 Token 已含缓存子集，总量只加 input + output；缓存单独报告。若推理 Token 已包含在来源的 output 中，不再次加算。失败任务的已耗 Token 计入组总量，再除以成功任务数，体现返工成本。任一任务缺少 input/output 时，这组不报告完整总量或精确减少率。

仅在同 family、model、effort、basis 下，before/after 各至少 3 项且成功率未下降、Token 指标完整时显示观察到的平均成功任务消耗差异。仍需人工核对任务难度、代码基线、环境、并发和缓存条件；这不是因果证明，不据此承诺 80%。

账户共享额度不是单个任务 Token；同时运行的聊天会干扰额度比较。工具不调用模型，不抓取所有聊天，不自动造样本。
