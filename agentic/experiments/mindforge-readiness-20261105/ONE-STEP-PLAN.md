# Qwen3.8-27B 1-step训练验收：提交前配置

状态：数据注册完成；模板对齐未通过；尚未创建训练任务或模型版本。

数据版本`sft_v4`，531条方法轨迹。平台校验0错误/0警告；平台三样本预检verdict=ok，但独立对齐核查发现训练上下文不一致。

| 参数组 | 拟提交值 | 来源 |
|---|---|---|
| 模型／类型 | Qwen/Qwen3.8-27B；LoRA SFT；base_version空、reference_ref=null | 用户目标；当前支持模型列表 |
| 数据 | sft_v4，531条；原始数据SHA12d9b6… | 本批已验证数据与平台注册 |
| 规模 | num_epochs=1，batch_size=1，max_steps=1，max_length=131072 | 本次验收明确覆盖默认值 |
| 优化 | learning_rate=1e-4，weight_decay=0，lr_schedule=constant，warmup_steps=0，warmup_ratio=0 | LR/衰减来自CLI默认；其余明确覆盖，避免1-step只做warmup |
| LoRA／监督 | rank=32，packed，all_assistant_messages，train_on_cot=false | rank/模式/监督继承默认，与预检一致 |
| 自动评测 | benchmark空，关闭；target=official_test、split=test、concurrency=4、max_tokens=65536均不生效；background=false、thinking=false | 明确关闭，不自动触发TB2.1评测 |
| 其他 | rollout_config=null，reward_config=null，不恢复旧checkpoint | SFT不使用RL配置 |
| 服务 | MindForge认证远程模式；MinT由账号/平台配置选择，未覆盖mint_endpoint；观测test/test3可调度 | 线上只读状态，不预留资源 |
| 提交与等待 | 仅提交一次；wait timeout=60秒、interval=5秒；超时继续同一ID，不重提 | 操作设置，非训练截止时间 |
| 成本／物理资源 | 费用、训练GPU类型和数量未在提交前暴露 | 不从部署H20资源推定训练资源 |

客户端无法覆盖的后端参数（线上待日志核实）：本地ECS trainer3e52e3f为Adam beta1=.9、beta2=.999、eps=1e-8、seed=42、save_every=100、LoRA目标MLP/attention/unembed。不能把这些本地默认值当作已验证的生产配置。完整非敏感payload与来源标注见one-step-plan.json。

## 模板与mask的实测

| 样本行 | 本地序列token | 平台序列token | assistant监督token本地／平台 | 监督内容逐字相等 |
|---|---:|---:|---:|---|
| 0 | 12,696 | 12,669 | 3,232／3,232 | 是 |
| 177 | 7,551 | 7,530 | 2,334／2,334 | 是 |
| 354 | 9,801 | 9,784 | 2,450／2,450 | 是 |
| 41 | 48,205 | 48,094 | 19,073／19,073 | 是 |

- 所有样本均未截断；全部assistant目标内容逐字匹配，但完整序列不匹配。
- 冻结chat_template.jinja默认preserve_thinking=True，历史assistant保留空think边界；线上MindLab/qwen35只对最后一回合保留。另有用户消息空白归一化、边界换行差异。
- train_on_cot=false仅表示不学习额外reasoning_content；它不能替代历史模板的preserve_thinking语义。原生JSON analysis/plan仍是公开assistant内容。
- 目前平台预检的ok只证明其自身协议可渲染，不证明与本研究采样/评分输入一致。

## 处理与验收范围

推荐先由平台对齐训练renderer/冻结模板并复测。另一种选择是保留已知模板差异，仅跑1-step验证训练和checkpoint链路；这不能算模板验收通过，也不能放行正式SFT。等待用户选择，不擅自改变研究协议。

真正提交后须记录精确task_id/version_id：确认实际forward/backward与optimizer step1、有限loss与非零监督权重、训练完成、checkpoint/sampler和模型/数据身份；产物加载/调用另留真实证据。仅到Creating LoRA client或只拿到路径不等于全部验收通过。正式两组SFT仍需固定公平token预算与完整配置。

平台skill要求：训练提交前展示全部非敏感参数及默认值，用户确认后才提交；协议变化重新确认。此次没有提交训练、部署、正式对照或额外模型采样。
