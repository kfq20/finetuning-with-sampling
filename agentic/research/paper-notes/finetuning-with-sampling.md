# 原论文方法导读：Finetuning with Sampling

[返回研究提案](../README.md)

阅读目标：理解“专家引导生成、学生自身分布评分、反复修订、最后SFT”怎样连接起来。以下区分**论文理论、官方代码近似、我们的Agent改造**。公式统一换用本文符号；数值小例子为教学示例，不是论文实验结果。

原文：[Finetuning with Sampling: SFT Learns Better Than You Think](https://arxiv.org/abs/2610.02140)，Karan、Chen、Du，2026。方法定位：[§4.1信息投影](https://arxiv.org/html/2610.02140v1#S4.SS1)、[§4.2 MH](https://arxiv.org/html/2610.02140v1#S4.SS2)、[§4.3与Algorithm 1](https://arxiv.org/html/2610.02140v1#S4.SS3)、[附录C.2实际近似](https://arxiv.org/html/2610.02140v1#A3.SS2)。

## 1. 先固定符号和问题

| 符号 | 含义 |
|---|---|
| $q$ | 一道题的输入 |
| $e$ | 对应的完整专家解答，不只最终答案 |
| $p_0(y\mid q)$ | 采样阶段保持冻结的学生模型对回答$y$的概率 |
| $y$、$y'$ | 当前学生回答/前缀，以及新提出的改写候选 |
| $\mathcal C(q,e)$ | 保留所需正确性或知识信息的回答集合 |
| $\kappa_e(y'\mid y)$ | 看到专家参考后，从当前回答提出新回答的proposal核 |
| $B$、$N$ | 每阶段扩展的token额度、阶段内修订次数 |

专家可以提供学生很难自行发现的信息，但专家的表达和求解路线未必适合学生直接模仿。希望改变的是**训练目标的分布**，而不是首先改一个更复杂的训练loss。参考对生成有帮助，也不意味着参考应该出现在最终训练输入里。

## 2. 为什么目标是信息投影

先考虑一般概率问题：在所有满足约束的分布中，寻找最接近原分布的分布。固定$q$，把条件省略：

$$
p_{\mathcal C}=\arg\min_{\rho:\operatorname{supp}(\rho)\subseteq\mathcal C}
D_{\mathrm{KL}}(\rho\|p_0)
=\frac{p_0(y)\mathbf1[y\in\mathcal C]}{Z_{\mathcal C}},
\quad Z_{\mathcal C}=\sum_{z\in\mathcal C}p_0(z).
$$

直觉是：**排除不合格回答，保留原模型在合格回答之间的相对偏好。** 它不是从所有正确回答中均匀抽一个，也不是只保留全局概率最高的那个。

可用下面的恒等式自己验证。对任何支持集在$\mathcal C$内的$\rho$：

$$
D_{\mathrm{KL}}(\rho\|p_0)
=D_{\mathrm{KL}}(\rho\|p_{\mathcal C})-\log Z_{\mathcal C}.
$$

第二项与$\rho$无关，所以取$\rho=p_{\mathcal C}$达到最小值。这里KL方向是$\rho\|p_0$，不能随意交换。

如果学生本来很容易成功，可以生成后按正确性拒绝采样。真正困难的是$Z_{\mathcal C}$很小时：大量无参考尝试都进不了合格集合，专家信息才可能显著改善搜索效率。[论文目标定义与讨论](https://arxiv.org/html/2610.02140v1#S4.SS1)

## 3. 生成与评分为什么使用不同上下文

将参考条件化proposal写成：

$$
\widetilde p_e(y_{m:L}\mid q,y_{<m})
:=p_0\bigl(y_{m:L}\mid\operatorname{Prompt}(q,e,y_{<m})\bigr).
$$

它利用完整专家$e$，在当前学生前缀后续写。生成出的目标仍要按照不含专家的$p_0(y\mid q)$评估：

$$
\log p_0(y\mid q)=\sum_{t=1}^{|y|}\log p_0(y_t\mid q,y_{<t}).
$$

这两个问题分别是“得到参考后会怎样写”和“没有参考时对这段指定回答赋多大概率”。把候选固定下来、拼在$q$后做一次teacher-forced forward，才得到后一项；不用让模型重新生成另一个回答。生成API返回的带参考output logprob不能代替它。

这里的“teacher-forced”只表示强制喂入指定token，不意味着用外部专家模型评分。生成与评分都可由同一个学生模型完成。官方代码对应`proposal_vLLM`和`get_logprobs_vLLM`。[代码](https://github.com/aakaran/finetuning-with-sampling/blob/main/boost_math.py)

## 4. 理论上的MH怎样接受候选

对一般目标分布$\pi$和proposal核$\kappa$，标准Metropolis–Hastings接受概率为：

$$
\alpha(y\to y')=
\min\left(1,
\frac{\pi(y')\,\kappa(y\mid y')}{\pi(y)\,\kappa(y'\mid y)}
\right).
$$

将$\pi=p_{\mathcal C}$代入：若$y'$不合格则拒绝；若新旧候选都在$\mathcal C$内，归一化常数抵消，得到：

$$
\alpha=\min\left(1,
\frac{p_0(y'\mid q)}{p_0(y\mid q)}
\frac{\kappa_e(y\mid y')}{\kappa_e(y'\mid y)}
\right).
$$

再抽$u\sim U(0,1)$，仅在$u\le\alpha$时替换当前回答。proposal的正反向概率修正很重要：**并不是$p_0(y')$较高，就一定接受。** 例如目标概率比为2、反向/正向proposal比为0.1，则接受概率是0.2。

MH修正的是proposal的偏好；它不是简单给几个候选排序。只有满足相应支持集、转移和收敛条件，才能将链与目标分布联系起来。专家prompt在实践中可能帮助保持信息，但不能当成候选永远正确的数学保证。[论文§4.2](https://arxiv.org/html/2610.02140v1#S4.SS2)

## 5. 为什么还要分块和随机截断

直接对完整长回答反复重生成会很贵。论文Algorithm 1逐步增长当前长度，再在该长度范围内修订。可按下面的教学版伪代码理解：

```text
输入：题目q，完整专家e，冻结学生p0，块额度B，阶段修订次数N
当前学生序列y = 空
每个阶段：
    参考e，把y向后扩展至当前阶段长度上限L
    重复N次：
        在当前全部前缀位置中随机取切点m
        保留y在m之前的token，参考e重生成m至L的后缀，得到y'
        按理论MH规则，或实际代码的近似比较规则，更新y
    若触发最终EOS终止逻辑则结束；否则进入下一阶段
输出：最终的一条学生序列y_hat；中间候选另存分析
```

**切点可以落在此前的块内，不只落在刚增加的那一块。** 所以“进入下一阶段”不等于所有旧token永久不可修改。专家参考$e$始终是完整解答；被截断的是当前学生序列$y$，不是专家解答。

### 一个自造的小例子

设$B=4$、$N=2$：

| 阶段 | 当前长度上限 | 一次可能的切法 | 发生什么 |
|---|---:|---|---|
| 1 | 4 | 保留token1，重写2–4 | 初始化后再做两次修订 |
| 2 | 8 | 保留1–2，重写3–8 | 切点回到第一块，旧内容也可能变化 |
| 3 | 12 | 保留1–9，重写10–12 | 也可以只改很短的尾部 |

代码通过生成的`max_tokens`限制每次最多补多少token；不是让语言模型精确写满每块。EOS可以使输出提前结束，因此实际长度、阶段数和调用数可能小于上限。

### 32块、58块、每阶段10次是什么意思

以下是当前仓库数学/化学入口的默认值及其调用，不是声称所有论文实验只有这一种配置：

| 入口 | 总新token上限$T_{max}$ | 块数$K$ | 每阶段额度$B=T_{max}/K$ | 每阶段修订$N$ |
|---|---:|---:|---:|---:|
| `boost_math.py` | 1856 | 32 | 58 token | 10 |
| `boost_sci.py` | 1856 | 58 | 32 token | 10 |

数学配置若没有提前EOS并走满阶段，proposal调用数最多为$32\times(1+10)=352$：32次阶段扩展，加320次修订。**352是内部候选生成调用数，不是352条训练数据。** 一道题的一次完整采样通常只贡献最终的一条$(q,\widehat y)$；中间`trace`是另一类产物。[数学代码](https://github.com/aakaran/finetuning-with-sampling/blob/main/boost_math.py) · [化学代码](https://github.com/aakaran/finetuning-with-sampling/blob/main/boost_sci.py)

## 6. 论文理论与官方实际代码：必须区分

附录C.2明确使用了更高likelihood时替换的近似。核对本仓库官方数学实现可见：

$$
s(y;q)=\frac1{|y|}\sum_t\log p_0(y_t\mid q,y_{<t}),
\qquad y\leftarrow y'\ \text{if }s(y';q)>s(y;q).
$$

| 项目 | 理论MH | 当前检查到的官方数学代码 |
|---|---|---|
| 目标 | 正确/信息等价约束下的信息投影 | 无参考平均logprob引导修订 |
| 接受 | 概率接受，含proposal正反向比 | 新候选均值更高就替换 |
| 参考 | 用于proposal核 | `proposal_vLLM`输入完整专家与当前前缀 |
| 无参考评分 | 目标概率所需项 | `get_logprobs_vLLM`额外forward指定回答 |
| 初始化 | 理论可从合格轨迹初始化 | 实际函数`gen=[]`，借助专家逐阶段生成，并非直接复制专家的token块 |

不能把理论的精确采样保证直接赋给这个贪心、长度归一化的实现。也不能把我们的Agent版差别仅描述为“原论文严格MH，我们改成贪心”；原论文实际实现已经做了这一步近似。[附录C.2](https://arxiv.org/html/2610.02140v1#A3.SS2)

## 7. 最后怎样变成SFT数据

记最终采样数据为$\widehat{\mathcal D}=\{(q_i,\widehat y_i)\}$，随后训练普通自回归SFT：

$$
\mathcal L_{SFT}(\phi)=
-\frac1{n}\sum_{i=1}^{n}\sum_t
\log p_\phi(\widehat y_{i,t}\mid q_i,\widehat y_{i,<t}).
$$

关键是训练输入只有$q_i$及训练时正常可用的前缀，**不包含专家参考$e_i$**。采样时$p_0$冻结；训练时才更新参数$\phi$。目标是让一次无参考生成吸收采样阶段找到的行为，而不是每次推理都重做搜索。

官方脚本将最终`gen`、最终分数及`is_correct`等写入结果，另存中间`trace`。候选调用、阶段数、最终回答数和训练条目数需要分别数。不要仅凭`is_correct`字段，就推定脚本已自动对所有训练材料执行了我们当前的“双环境评分硬门禁”；正式训练选取规则需要随实际数据整理manifest声明。

## 8. 对应到我们当前的Agent管线

| 论文中的对象 | 当前Agent中的对应 | 保留或变化 |
|---|---|---|
| 题目$q$ | instruction、绑定初态及工具协议 | 必须有可执行环境，不只题目文本 |
| 完整专家$e$ | 完整可观察专家交互 | 保留完整参考；不导出provider隐藏reasoning |
| 学生文本前缀$y_{<m}$ | 学生已执行的动作与真实反馈$h_t$ | 反馈不能从专家轨迹复制 |
| token块 | 一次完整assistant动作JSON | 一个块可能包含多条shell命令 |
| 随机截断重写后缀 | 固定当前边界生成8候选 | 不回退已经改变的环境 |
| 候选目标评分 | 无专家参考的学生action mean-logprob | 保留“生成/评分条件不同”的核心分工 |
| 多次替换当前序列 | 每块8选1后真实执行 | 只执行选中动作；不是严格MH |
| 最终训练样本 | 学生完整公开轨迹及assistant-only mask | 双评分、hash、引用与格式验收后入池 |

由此可见，我们保留的是**专家信息引导、学生自身概率、特权参考不进入训练、采样后普通SFT**；舍弃的是跨历史位置修订，以换取不反复回退环境的工程可行性。局部高似然能否转化为更好的长程行为及训练收益，需要与直接参考和原专家SFT对照，而不能由这些公式直接推出。

## 阅读顺序与代码定位

先读第1–3节辨清目标和条件，再读第4–6节区分理论与实现，最后看第7–8节理解训练单位和Agent改造。若回原文，按§4.1→§4.2→Algorithm 1→附录C.2顺序即可。核对实现时先看`get_logprobs_vLLM`、`proposal_vLLM`，再看`proj_samp_vLLM`；prompt在[constants.py](https://github.com/aakaran/finetuning-with-sampling/blob/main/constants.py)。本导读依据本地保留的上游代码检查，文档更新不改采样算法或正在运行的实验。
