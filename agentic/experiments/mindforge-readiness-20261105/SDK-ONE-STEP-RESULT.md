# 独立 MinT SDK 1-step 验收，2026-11-05

用户明确覆盖本次 MindForge CLI 入口约定。实际使用 SDK 0.2.0 / Tinker 0.22.0，
endpoint `https://mintcn.macaron.xin/train`，HTTPX transport 正常校验证书。
没有部署 MindForge 补丁、启动正式 SFT 或修改其他实验。

| 验收项 | 结果 |
|---|---|
| 实际模型 | Qwen/Qwen3.8-27B，LoRA rank32，MLP/attention开启，unembedding关闭 |
| 数据 | 531条全量逐token对齐；seed42选row519执行本步 |
| 输入 / 监督 | 5898序列token / 1742监督token；batch1、仅1次optimizer提交及确认 |
| 参数 | LR1e-4，Adam β=(.9,.999)、eps1e-8，weight_decay0，grad_clip1，无warmup，max_length131072 |
| Forward/backward | 57.835秒，NLL0.1730746084，grad_norm0.1893332452 |
| Optimizer | 2.188秒；后端原始step=832，作用域未知，不当作本次步数 |
| State / sampler保存 | 152.664秒 / 37.338秒；两份checkpoint |
| State回载 | 含optimizer回载成功；回载后forward有限 |
| 小范围forward | 16个监督token；NLL从0.75183773变为0.80049384，不构成收益证据 |
| Sampler生成 | 16token smoke长期pending；1token诊断HTTP408，queue_state=active |
| 清理 | 仅本次session已关闭；清理后两份checkpoint仍可查询 |

训练和state回载验收通过；sampler推理闭环尚未通过，所以整体验收不标绿，正式SFT未启动。
采样等待超过600秒后由操作者结束，不是已观测的服务端600秒超时。

- 原采样future：`01a1aa9f-8486-7712-b43d-1dca9b0033b8`
- 诊断future：`01a1aaa5-f62e-7736-b8d2-e1f8dab9bcbd`
- 诊断HTTP request ID：`d00cda77-c7b9-46e3-88c9-28a6fd1b7679`
- 独立model ID：`01a1aa9b-9bca-75a4-8903-a2b7c6a836c4_0`

原始产物、冻结worker、完整参数、事件与清理收据：
`/Users/fancy/project/finetuning-with-sampling-data/mint-sdk-one-step-20261105-a1/`。
分阶段结论为`final-review.json`，可读报告`RESULT.md`，完整参数`plan.json`。
原`error.json`和`status.json`保留；SDK worker原进程退出0不视为完整验收成功。

本轮冻结执行源码为`5f0f3df`，没有重跑训练。后续源代码改进仅用于未来新运行：
正确保存SDK dataclass/TensorData的数值证据，失败退出非零，支持显式配置采样等待窗口。
没有回填或改写本轮原始响应；修复采样服务后直接复用已保存产物，不需要重新训练。
