# Historical detail before consolidation

Superseded process snapshots for2026-11-06 through08. Current status is in ../2026-11.md.

## 2026-11-08：清理可重建缓存，恢复实际16并发

截至00:42 CST：CLI-Gym604/1000、SWE-Gym2/1000，共606条有效方法/专家配对数据；16个实际任务worker、15个排队，评分容量4。来源分别计数、验收和导出，不把候选/预检/异常充作SFT。

- 用户明确授权自行清理判断无用的文件与缓存。删除30份14天前的环境导出缓存，每份先验证原固定源manifest可读取，保留完整元数据、文件列表及恢复脚本；实际回收142.67GiB，1份缺固定源摘要保留。原始轨迹、评分、训练数据和运行容器未删，未执行全局Docker prune。
- 此前3个已批准的新SWE源缓存5529/9023/9082按精确digest核查无容器/排队引用后回收，实际释放2.93GiB。另对两个现有稀疏loop文件系统作在线FITRIM，不删文件/快照、不卸载；实际根盘回收1.55GiB，不能把命令报告的52.8GiB逻辑discard当物理释放。
- 恢复核查发现本人引入的`hold_path`函数作用域错误：接续的付费任务仍运行，新派发lane已退出，主循环却仍报运行。新测试先复现NameError，再修全局导入并增加lane失败门禁与带returncode的收尾。未启动的14个任务保留原身份后首次派发，未重跑付费尝试；886份原终态文件散列0漂移，原531数据SHA不变。
- 采样协调器冻结c78cef6；生产者单独接续a835dca，模型运行库字节相同，现有协调器和模型worker未重启。真实SDK9项生产回归、13项源契约/缓存保护检查通过。关闭日志无损压缩与可恢复源缓存回收接入现有生产者生命周期，每5分钟有限执行一次，无新增Codex定时任务；原始文件须终态静置600秒且无运行worker/打开FD，压缩后完整解压SHA核对。数据盘低于100GiB才回收已结束、未排队、无容器引用且固定registry config与原image ID一致的SWE缓存，目标120GiB；旧CLI镜像和共享Docker不动。

00:42数据盘仍有139.22GiB（制造继续使用空间），根盘16.52GiB；随后在线trim增加约1.55GiB根盘余量。ECS内存约454GiB可用，瓶颈是存储。CLI无模型全池核对得到483个不同未付费合同候选，包含真实环境hold/初态已通过，不能承诺483条新SFT；已完成教师但未启动学生的额外可直接复用候选为0。

可恢复私有文件系统工具方案暂存在隔离分支`study/cligym-private-control-fs-20261107`（ab3d4cf），尚未完成实际无模型校准，未接入生产、未改skill。后续优先修CLI剩余环境，继续分别达到两个1k目标。

[审计快照与选择身份](../evidence/storage-recovery-production-20261108.json)。ECS详细审计`/mnt/ecs-tb4/audits/storage-cleanup-20261107-late`；运行根仍为`/mnt/ecs-tb4/cli-gym-expansion-20261107`。

### 04:01：修复SWE供给的pytest-snail公共兼容问题

当前累计CLI604、SWE29，两个1k目标分别保留。学生任务容量16、评分槽位4；此前供给耗尽后实际降为1个worker，不能把容量当实际并发。新的4路无模型制造已恢复，等待新任务通过完整准入后自动补位。

真实Hydra2189预检定位两项公共问题：vendor插件错误地按实例参数注销字符串名称，造成收集完成后AssertionError；私有canary禁用cacheprovider又触发该插件的cache依赖错误。修复对固定site-packages文件做前后SHA绑定的一行API纠正；仅该新合同的canary使用独立临时cache。业务代码、测试、标记和断言不变。实际初态26项失败、gold310/310、独立fresh310/310；canary正常失败，solver恢复代码基线一致。首个旧失败仅为无模型制造，不是重复学生模型尝试。

冻结476574d接续coordinator/producer；原938份终态receipt/result SHA全不变，模型worker信号/重放均0。原source maker在空闲hold边界退出，新source maker4路、仅未来任务6000秒，使用2438官方train作用域内的2325条候选行，其中55条是上述插件问题的未付费制造修复。旧失败目录/hold完整保留；已发布或已付费unit不重放。首个修复包已接入实际专家运行。

回收29个本轮失败准备的可重建缓存净释放36.03GiB，保留原日志和固定registry digest；另清理两周前OS轮转日志约292MiB。失败准备缓存回收加入现有5分钟有限维护，使用同一互斥锁且在外层释放后调用，避免嵌套死锁。仍不动旧实验镜像和共享Docker。04:01数据盘93.85GiB、根盘11.98GiB（制造继续写入）。未证明吞吐已经提升，待新任务的有效SFT增量核验。

[实际控制、进程及旧文件散列核验](../evidence/hydra-source-recovery-20261108.json)。全部运行收据在选定root的`support/hydra-source-resume-20261108`；原失败pilot保留在`support/hydra-pytest-compat-20261108`。

### 04:10:35：恢复实际16任务，首条修复环境的学生SFT通过

累计CLI604、SWE30（新增1），分别向两个1k目标推进。真实/proc身份核对16个原协调器子worker，排队7；环境准备4路、27包通过、33包仍hold并跳过。新包数不计作SFT。生产者单独接续11a17f2，模型协调器3900264和已付费worker不动；维护回收还会保护未发布的修复包、正在准备的源和共享image，15项实际SDK回归通过。938份旧终态文件再次校验零变化。

Hydra2543专家13轮、原/fresh均1；学生4轮/32候选全部评分，59.06秒、原/fresh均1并训练准入。额外离线核对32份真实请求与响应：生成完整专家参考与固定模板一致，评分请求只含公开前缀＋候选、max_new_tokens=0、完整输入从0开始，逐token/候选边界对齐且每块选最高mean logprob。SFT重编码与assistant labels/mask一致，审计没有调用模型。该条队列等待max2.18秒，单例不能代表满16后的整体吞吐。

数据盘84.18GiB；例行有限缓存维护已完成一次，不改旧实验镜像/共享Docker。[16个实际worker、首条SFT及原始收据散列](../evidence/source-supply-full-concurrency-20261108.json)。

### 04:22:48：MyPy测试数据供给修复，队列补至22题

累计CLI604、SWE32（较上次新增2），实际16个模型worker、评分容量4，无provider hold。此前MyPy收集能看到新测试ID，实际评分却缺失该ID：私有归档只含Python测试加载器，遗漏官方test_patch的数据驱动fixture `test-data/`；旧xdist还忽略环境提示而开64进程。修复冻结完整官方fixture树、保留全部原required IDs、明确测试进程-n0，仅限MyPy新合同；不把gold业务源码放进grader，不降低断言或跳过测试。

无模型MyPy10432校准：初态有真实F2P失败，gold1、fresh1、负控正常失败、solver源码基线干净。31项实际SDK检查包括4线程SIGINT后在途准备仍全部完成的验证。旧source maker仅主线程收到SIGINT，线程池排空后退出；4个未发布结果/原失败保留，当前选定新source maker720746d。模型协调器接续保留16在途付费worker，977份既有receipt SHA不变，无模型重放。缓存维护覆盖新输出并保护未发布/进行中的修复包。

新MyPy16包均初态0/gold1，已排队；总队列22、准备器进入queue_full等待消费，不是停止或死锁。数据盘90.83GiB。包数仍不计SFT，继续等待新模型轨迹闭环。[实际worker、控制、排空及旧证据校验](../evidence/mypy-fixture-source-recovery-20261108.json)。

### 04:30：CLI扩样候选草案，保持派发关闭

在已完成且成功的CLI轨迹中，再核对596份原生expert及原student收据/数据SHA：两者均正常终止、原/fresh满分，input identity匹配，未包含100道留出集。为潜在的追加独立学生样本制作了596个唯一prospective sample ID；原expert可复用，不需要重跑教师，也不修改原学生尝试。这里是重复环境下的新样本，不是596个新环境。

草案明确dispatch_authorized=false，未注册到acquisition-plan，没有模型请求。仍等待此前“是否允许成功任务追加独立学生样本”的用户选择；没有把等待当批准。CLI当前604，距离1k还缺396条，候选数不代表将得到596条有效SFT。SWE独立16任务生产继续，实际付费2189的学生动作块15→16，当前SWE33，未发现provider hold。

[候选政策、来源摘要和草案hash](../evidence/cli-additional-student-draft-20261108.json)。完整只读草案在运行root的`support/cli-repeat-draft-20261108/draft.json`；不供现有监督器自动消费。

### 04:38：按来源冻结成对训练数据，SWE34对校验通过

离线冻结SWE34对，每组34条，原/fresh满分、相同有序input identity、无专家参考进入训练prompt、完整tokenizer重编码及assistant-only labels/mask全部通过，0 pair hold，无截断；没有模型/评分API请求或训练。方法组有监督131,730 tokens，专家组236,845 tokens；单条完整训练序列均值13,597/31,719 tokens，均未超过131072。该项是训练序列长度，不是生成＋评分累计token消耗，也不据此判断学习收益。

CLI604对直接复用此前已冻结验证包，重新核对所有导出文件SHA及当前CLI源train SHA一致，不重复导出604行。两个来源分别有SELECTED_RELEASE.json，运行root新增paired_export_selection.json绑定两份选择及散列；历史combined snapshot-v1和旧选择不改。冻结总数638对（CLI604＋SWE34），后续审计时实时生产已到CLI604＋SWE37，后者多出3条不冒称已纳入本快照。模型仍16任务/4评分，队列持续消费。

维护wrapper增加可选--sources，默认仍同时导出两源。完整校验与路径见[本次导出证据](../evidence/source-separated-paired-checkpoint-20261108.json)。CLI重复环境的新学生扩样仍未获确认、未派发。

### 05:02：首批MyPy实际模型结果，正常0分与基础设施异常分开

10432专家正常结束，54次交互、827.39秒，真实提交4551字节，修改两个业务Python文件及一个公开测试fixture；原/fresh都实际收集必需测试且FAILED，缺失0，canary正常拒绝。与初态0/gold1/fresh1控制对照，当前证据支持真实模型0分，不是测试没有运行或API异常；不启动学生、不补跑专家、不计有效SFT。原receipt/patch SHA绑定的审阅另存，原分数和费用保留。

同批已有另外6条MyPy专家原/fresh满分，均接入student_8_candidates。这证明一次正常模型0不会阻塞整个批次，也不能把首例失败概括成MyPy管线不通。其后学生的训练准入仍需各自原/fresh满分及格式校验，尚不把6份专家成功算成6份SFT。

[原始收据、提交散列、必需失败测试和其他6条专家闭环](../evidence/mypy-first-model-outcomes-20261108.json)。本次审阅只读，没有新模型请求。CLI69个旧控制hold未发现可复用此次MyPy fixture修复的同类项；官方HF HEAD与当前冻结552945c5相同，未发现新增官方版本。额外独立学生样本仍等待已有用户选择，未以扩样草案绕过授权。

### 05:28：定位两类ValueError，离线恢复一条完整正确轨迹

1006已完成执行且保存非空submission，但导出器报SFT full/incremental template mismatch。固定Qwen模板本来会对content应用trim；该条第4条消息末尾一个换行被模板去掉，旧loss span仍按未trim的原始消息定位。新导出器保留原始messages，仅按同一模板的外沿空白规则定位监督区间，并标记受影响消息；其他模板差异、token跨边界、非公开参考仍拒绝。原34对方法/专家共68条导出逐字段重算完全不变，16项实际SDK回归通过。

对原捕获补丁作两次独立fresh评分均1，确认最后两次native任务完成、teacher1/1、无私有路径或参考归因；恢复一份派生SFT准入，无生成/评分API请求、无solver重放。原status=hold、error、公开历史、context、patch等9份证据SHA不变。新receipt明确绑定derived_export_recovery，原异常仍保留为历史后处理失败，不把它抹成一次新正常运行。原计费和模型尝试均保留。

989则在第28块的8个正常返回候选中，全部触发隐藏推理封装限制，当前公开动作协议不接受。保留原hold和现场，不放宽解析、不自动补模型。两项错误均不按上游API故障归因。

只对新派发启用导出修复，保留16个在途worker；1052份既有receipt散列不变。新冻结身份明确记录为selected720746d＋export022b765＋recoveryada9fe3及完整文件hash，不假称是Git HEAD整棵树。原始绑定也保留。MyPy已有10689和11137两条学生原/fresh满分，分别11和9轮，进入真实SFT准入。[运行身份、恢复、原数据校验与模型结果](../evidence/export-trim-repair-20261108.json)。

### 05:46:56：SWE50对冻结导出，复用同类修复再恢复一条

独立SWE checkpoint-v2冻结50对（两组各50条），0 pair hold，完整tokenizer重编码与有序input identity/labels/mask校验通过；方法有监督203,393 tokens、专家355,972 tokens，两组均无131072以上序列、不截断。数据源单独SELECTED_RELEASE及主paired_export_selection指向新50对；CLI604包及选择不变，旧34对快照和旧选择副本保留。此次使用现选修复版export library叠加已维护的9e2e98f单源wrapper，完整文件SHA另存，没有调用模型。

扫描发现修复前在途MyPy10478也因同类outer-whitespace导出校验异常结束。复用已维护的recover_export，仅做原补丁的两次fresh评估，均1；原9份关键证据hash不变，保留原hold/error，并将派生SFT加入当前manifest。不是重跑学生或老师，费用不变。本研究累计两条此类后处理恢复，仍与原始异常记录分列。

审计时实时CLI604/SWE52，冻结包仍为CLI604/SWE50，差额留待后续快照。16任务/4评分继续运行。源证据：[checkpoint-v2与第二条离线恢复](../evidence/swe-paired-checkpoint-v2-20261108.json)。

### 05:59：第三条同类导出恢复与根盘清理

MyPy11567由修复前已在途的旧720运行库结束，第一条assistant消息有模板会trim的外沿空白。复用严格离线恢复工具，两次fresh均满分、required均1/1、canary正常拒绝、原9份证据SHA不变；不重跑模型，原hold/error保留。当前有效CLI604、SWE57，实际16个模型worker、评分容量4、无provider hold；已冻结导出仍CLI604/SWE50，不冒称全部实时数据均已打包。

依用户清理授权，核对无进程引用且不在当前扩展选择后，删除4个VSCode明确标记obsolete的旧插件及重复安装包缓存，回收2.04GiB；当前6个已选择扩展完整保留，无实验文件/镜像删除或进程信号。根盘清理后约9.3GiB、数据盘约101GiB，RAM可用约452GiB。[恢复与清理证据](../evidence/export-trim-recovery-mypy11567-20261108.json)。

### 07:55：SWE75对完整冻结导出，上游短暂500留证

CLI604、SWE75，共679对有效方法/专家数据；两条1000目标分别保留。新SWE checkpoint-v3在manifest与源数据一致时冻结，方法/专家各75条、配对hold为0，全部完整tokenizer重编码和mask校验通过；监督token分别315,427与590,343。复用原270文件SHA验证的冻结导出运行库，仅导出SWE，CLI604选择文件SHA不变，旧SWE50快照保留。两源选择指针已分别更新，未训练、未请求模型、未重跑轨迹。

期间教师3条HTTP500的原响应一致为INTERNAL_ERROR / Failed to validate API key，分别在请求72、33、1出现，不能据此认定凭证无效。既有provider门禁触发后，单独健康探针成功并归档原hold，再恢复新任务；3条原失败不重跑、学生未启动。数条学生6000秒超时仍保留原失败并释放槽位，不计有效数据；不能把这些正常记录的超时说成接口已全部无异常。最新仍16任务/4评分容量，无provider hold。

[数据选择、验证与故障证据](../evidence/swe-paired-checkpoint-v3-20261108.json)。SWE产出持续增加；CLI追加独立学生样本仍待既有用户选择，未派发。

### 08:22：修复生产者扫描进程退出竞态，保留全部在途模型

发现acquisition进度超过两分钟未更新，实际模型协调器健康、16任务仍运行；生产者942280因扫描/proc时目标进程恰好退出，identity只捕获FileNotFoundError而漏掉ProcessLookupError，未捕获异常退出。修复只对明确消失的进程返回空身份，并处理身份复查到SIGTERM之间的同类消失竞态；PermissionError等其他异常仍传播，退出前证据仍保留。

ECS实际SDK5项测试全部通过，包括真实Linux子进程、运行中任务保护、失败收据保留与信号前退出模拟。单独以继承原冻结运行库＋e145656的新生产者身份2403592接续；协调器942279和全部模型运行库不改，1167份旧receipt SHA不变，模型worker信号/重放均0。原生产者崩溃日志保留。

复验acquisition进度年龄7.83秒、模型健康年龄2.01秒，实际16任务、排队16、provider hold空；累计CLI604、SWE78，已冻结导出仍604/75。没有把新源包809数量计作SFT。[修复与恢复证据](../evidence/producer-proc-race-20261108.json)。

### 14:51：评分容量8→32，任务保持16

用户明确批准32，64仅后续考虑。复用248文件SHA核验的既有冻结代码，无方法代码变化；额外真实锁控制证明4个旧4槽位、4个旧8槽位和24个新32槽位可以共存。接续协调器701776、生产器701777（start_ticks均649023016），16个原付费worker保留，1719份原始证据SHA零漂移，无模型worker信号/失败重跑。原8槽位任务保持原环境，32仅对新派发任务生效；初验尚无32槽位worker，不据此声称扩容效果。

前10分钟完成127次逻辑评分（12.7次/分钟），排队中位数228.1秒/P90 323.7秒，请求中位数9.3秒/P90 94.2秒。评分API尝试127成功、2超时，异常率2/129=1.55%；该口径不同于episode异常率。累计CLI604、SWE99，已配对导出仍604+97。保存前窗及上下文长度，待32实际使用后比较；不将不同负载直接当因果实验。[32槽位交接与基线证据](../evidence/score-capacity32-20261108.json)。

### 14:04：新增评分槽位实际使用

已在有限只读观测中看到score-0至score-7均被持有；随后独立/proc/locks单次快照绑定7个实际评分持有者，其中MyPy10174、10582的新8槽位worker实际使用4–6号新增槽位，旧4槽位worker继续共存。生产仍16任务、无provider hold；累计CLI604、SWE99。该证据确认扩容开始实际使用，不代表吞吐或有效样本率已提升。未发额外模型请求、未重跑，详见[交接证据中的实际观测](../evidence/score-capacity8-20261108.json)。

### 13:38：用户批准评分4→8，实际任务保持16

用户明确覆盖此前4评分槽位配置。修复生产者把环境配置强制重置为4、进度硬编码为4的问题；交接入口只接受显式正整数容量，保留原评分锁池和FIFO。实际ECS SDK15项回归通过，包括4个旧槽位持有者与4个新增槽位共存的真实锁检查。248文件冻结副本接续，协调器237371、生产器237372（start_ticks均648583280），16个原付费worker全部接管，1680份原始证据SHA零漂移，无模型worker信号、无失败重跑。

新派发MyPy17182实际环境已继承8和新冻结库；15个原worker仍保留4，随任务周转逐步生效。同一个锁池保证新旧worker共存时不超出8；尚未宣称实际同时8路生产评分或吞吐已提升。8候选、公开前缀评分、最高mean logprob、原/fresh评分和训练准入均不变；未通过校准的后缀评分继续关闭。累计701对已导出数据不变。[交接与首个实际worker证据](../evidence/score-capacity8-20261108.json)。

### 13:04：实际评分复用命中，但排队瓶颈仍在

新配置MyPy14064已出现1次完全相同输入评分复用，有独立收据及原评分文本散列匹配；该任务最终仍超时。14个有评分记录的轮次中，共109次实际评分；每轮最慢已完成评分路径的排队累计4352秒、请求累计502秒。该统计不包含完整episode所有开销，复用命中也不等于吞吐已改善。原错误保留、未重跑、未计有效SFT。4评分槽位此前均核实由活进程持有且FIFO票据持续离队，无失效占位；保持16任务/4评分。见[原证据新增观察](../evidence/exact-score-reuse-20261108.json)。

### 12:25：SWE配对导出更新到97条

复用270文件SHA校验通过的固定导出器，将SWE方法/专家配对从75条更新到97条，0配对hold；完整tokenizer重编码、角色顺序及loss-mask检查通过。有监督token分别为425294和780552。CLI604条选择器散列未变，合计701条已准入且已配对导出；两条1000目标均未完成。新checkpoint-v4和分来源/总选择器已绑定，旧版原件保留；未发模型请求、未开始训练，在途16任务/4评分未改。[导出证据](../evidence/swe-paired-checkpoint-v4-20261108.json)。

### 11:59：后缀评分校准未通过，保持生产评分模式

两组既有八候选池均保留完整无参考历史，只将返回logprob范围限定为候选后缀。23k输入组通过；40k输入组最佳候选仍为5、全部token边界对齐，但一个候选mean logprob差异0.001455超过预设0.001容差，整体不通过。没有放宽门禁；candidate_logprob_slice继续关闭，16任务/4评分不变。两组共15次新零生成评分，另复用一份先前单候选探针；无新动作生成、无付费solver重放。当前比较尚不能分离服务批处理数值波动与评分模式差异，不据此宣称后缀模式错误或等价。原结果散列见[校准证据](../evidence/candidate-logprob-slice-20261108.json)。

### 10:50后：确认评分排队耗时，准备完全相同输入的评分复用

5条保留的学生超时均触及6000秒；每轮最慢已完成评分候选的累计FIFO等待约3958–4778秒，评分服务请求本身约325–658秒。该统计不含最后未完成轮次，不能当完整wall-time分解；足以说明本地4评分槽位排队是主要耗时来源之一，不能统一归因于上游断流。

131个完整八候选块共有1048次评分、927个完全不同的评分输入，121次（11.55%）可避免。新增显式`exact_score_reuse`开关，默认关闭：仅同一块的完整RenderedCandidate相等时共享一次评分；八次生成、无参考评分、选取规则与4槽位不变。逐候选保存复用源及评分hash，不重复计评分token；空白、token边界、历史或template差异不得复用，不跨块缓存，失败不得触发新生成。真实ECS Harbor SDK的8项blockwise和4项评分容量/FIFO回归通过，未发模型请求。

初始准备阶段未改生产；随后以显式冻结副本接入未来任务。真实ECS SDK另5项lifecycle回归通过（合计17项）；同一交接机制接管16个原worker，不发信号给模型worker、不重放付费尝试，871份原始receipt/error散列保持不变。新coordinator3578448、producer3578449（start_ticks均647635815）选定同一247文件冻结副本，保留lifecycle-e145656修复；新学生配置仅加exact_score_reuse=true，模型/端点、8候选、6000秒、16任务/4评分/FIFO不变。postcheck时实际16worker，均仍用原配置；未来首次派发才生效。11.55%是该样本的请求节省上界，不是已证明的生产吞吐提升。见[证据](../evidence/exact-score-reuse-20261108.json)。

## 2026-11-07：规模与专家多样性消融、CLI-Gym留出集

### 23:20：502/学生超时修复，目标明确为CLI-Gym1k＋SWE-Gym1k

用户明确两条独立目标，各1000有效方法/专家配对SFT，共2000；禁止拿SWE填CLI缺口。已设置持续目标，并上线分来源计数、导出和配额准入。当前CLI604、SWE1；原531、原失败/费用与100道CLI留出集保留。SWE另冻结2438官方train任务并排除既有SWE300评测题；每题先验初态0/gold1，未通过继续hold。

37条新专家端点502均为上游`upstream_error`；保留原尝试，不自动重跑。30条学生超时均撞到3000秒整段期限，模型/网络/队列等待共享此期限；HTTP客户端488–509秒而模型端2.85–15.8秒的探针显示传输/前端等待，不能据此唯一归因SSH。新派发改成原生HTTP JSON＋真正异步取消，评分仍剥离专家、8候选、完整input logprob排序。新1144次候选HTTP均200，P50 6.81秒/P95 13.86秒/max183.98秒；这是新请求的传输观察，不代表所有历史异常已恢复或全部可训练。

新增provider短时故障准入门禁；磁盘改为可恢复暂停新派发；保留付费在途任务、修复接续任务在磁盘hold时被漏计的问题。未付费69个环境候选中20个修复通过、49个继续hold，明确保留WorldReset、真实gold失败、缺外部依赖等。未放宽测试/skip/权限要求。SWE首条实际学生数据已通过原与独立恢复评分及训练格式门禁。

生产选择cc7c7e6/`support/dual-source-adoption-20261107`；制造802262d/`support/dual-source-goal-20261107`。7项生产与12项源契约检查在ECS SDK通过。共享容量仍16任务/4评分，23:20实际3个在途，不冒称满16；数据盘~39.5GiB触发40GiB门禁。关闭日志已按解压SHA无损归档，镜像、评分、轨迹与SFT保留；新增镜像缓存删除尚未获准。CLI剩余供给另做无模型全池核对，SWE不混计。

### CLI-Gym1000优先级与实际恢复

供给与吞吐复查（2026-11-07 14:52 CST）：有效数据578（新增47）；已发布包581→595，其中本轮5个pytest-relaxed环境完成初态0/健康1/篡改测试负控制，另9个测试收集修复包进入生产预检。余下4个mutation校准未通过、2个初态已通过及5个gold收集失败继续隔离。没有将包数当SFT。另启动2个无模型依赖镜像修复，生产16任务/4评分槽位继续运行。

45条成功新样本的教师均耗时2.12分钟、学生25.06分钟、学生均6.78块。2440个候选生成平均39.3秒，2437次评分平均9.0秒，生成完成至首次评分POST（含渲染及等槽）平均47.2秒；成功样本统计不代表仍未结束的长尾。实际活跃记录中单候选等待19–27分钟且仅数百至1280个token，16任务槽位持续满。模型主机只读检查：8张H20全100%利用率，TP4/DP2、持续prefill/decode；不能只增加任务并发来推断吞吐会提升。

发现并纠正配置回退：扩量bootstrap沿用旧canary的`127.0.0.1:18131`学生配置，该端口实为SSH隧道，未继承此前HTTP直连授权。新私有配置选择已授权的`http://123.57.26.97:8000/generate`，模型、tokenizer、模板、候选数和评分算法不变。一次既有候选的零生成评分完整token对齐，平均logprob与原值完全相同。选定coordinator3689919/producer3689920；接续保留16在途unit，新派发才用HTTP；在途配置不改、不重放。随后速度变化待实际新HTTP任务验证。维护源码be47cf7使bootstrap优先使用显式route selection，缺失则报错，不回退旧canary。评分后缀传输实验出现0.0005601差异、未上线。证据：root下`support/supply-throughput-20261107/`及`support/qwen-http-student-20261107/`。

端点接续补记（2026-11-07 13:14 CST）：用户批准后续专家切到`https://mint.macaron.im`的`deepseek-flash`。真实生产参数流式探针1.05秒正常结束，模型名/`end_turn`/`message_stop`一致；9项回归在实际ECS SDK通过。协调器以base3fbaa08+teacher补丁43b16ee冻结接续，收养16个现有unit而不重启它们；原unit继续原路由，新派发使用新路由。producer保留5f808e2，预检与学生配置不变。13:14复核累计561条（新增30），无STOP，接续进程正常。切换前确认239个不同任务遇到`group requests-per-minute limit exceeded`（12:58快照），不再用进程存活替代API健康；失败保留且不自动重放。端点是否共享限流、持续吞吐改善尚待实际新请求证据。选择与收据见root下`support/mint-im-switch-20261107/`。

环境供给修复补记（2026-11-07 12:43 CST）：累计558条（本批新增27），主生产16个实际unit进程保持运行，评分容量4。构建/选择器/pytest树状输出适配累计恢复54个包进入预检；另有9个资源控制环境、8个业务fixture边界环境通过独立校准。包、环境与SFT条目分开统计，不相加。

Cantools-580确认旧测试快照把故意损坏的DBC/KCD业务输入也冻结，导致健康世界被污染。修复保留原18个检查：初态14/18→0，健康18/18→1，缺失业务数据→0，篡改测试代码→0；原Python测试源码未变。目录级修复限定原配方声明的数据文件，涉及测试代码变化的455继续hold。静态skip、缺失测试、私有负控制未拒绝等均未放宽。历史142个闭合无模型控制hold被单独复查，额外目录扫描发现0个付费尝试冲突；修复生产者接续保留原coordinator及已运行模型，未重跑失败模型。

工程说明：`agentic/experiments/cli-gym-expand-20261107/ENVIRONMENT-REPAIRS.md`。ECS证据：`environment-repair-live-summary.json`、`remaining-control-blockers.json`、`legacy-unpaid-broad-scan.json`及各修复目录的0/1、mutation receipts。


用户将近期主目标明确为CLI-Gym累计1000条合格方法/专家配对数据，暂停铺开来源/专家消融。原531保持不变；修复后row1517的DeepSeek与Qwen均原评分1/独立评分1，新增1条准入，合计532。16任务槽位/4评分槽位的滚动采集已实际启动；首次核验9个实际unit进程，其余槽位受就绪任务及控制验收影响，不冒称16个学生。

共性修复：制造可联网但solver继续断网；Ubuntu源不可达改为显式可达的华为镜像依赖下载；支持pandas/tests等测试树；不执行损坏的tester.py来抽取选择器，而要求真实gold收集ID的唯一映射；空选择器的原始全套测试任务按全套收集，保留断言。6项契约回归通过，真实canary端到端闭环。

ECS选择root `/mnt/ecs-tb4/cli-gym-expansion-20261107`：producer/preparer5c61542，已有coordinator3fbaa08及付费worker不变，canarybb8409b；身份/接续/散列见active_runtime_selection、unpaid-build-handoff、各launch收据。原失败、临时构建和费用均保留。环境/裁判仍不通过的任务在模型前隔离，历史91个初态即通过者继续排除；100题留出集不参与生产。


- 两组Epoch2均完成68累计更新、1062累计样本曝光；训练/采样权重已保存，未替换当前SWE的Epoch1部署。最后5步NLL：方法0.12619，专家0.38177。
- 内部CLI-Gym留出100题已冻结，19个source images；与863历史派发任务及相同合同隔离，属于官方train池的内部test，不是官方test。去重后680个未派发扩量候选，48个未扫描、632个此前扫描；其中594个能匹配到原准备失败。新增531合格配对是目标而非已满足的源池容量。
- ECS新root `/mnt/ecs-tb4/cli-gym-expansion-20261107`；有限无模型准备worker启动，先100题测试环境再48题新训练候选。首次核验已构建32题、11题准备hold，仍在处理；构建不等于通过初态/healthy裁判控制。保留这些hold，不替换容易测试题凑数。
- 设计v3加入固定任务/token的DS-only、GLM-only、固定比例mix × direct/rewrite六组，以及固定专家的CLI/SWE来源对照。混合专家负迁移与rewrite鲁棒性均待验证。
- 来源小试优先SWE-Gym，备选SWE-smith训练池；当前SWE测试300题禁止进入训练。现有SWE运行不变；本次未发新模型请求、启动训练或重跑历史付费失败。
- 证据：新root `split-v1/summary.json` / `selection.json`、`preparation-launch.json`、`prior-preparation-holds.json`；维护源码 `agentic/experiments/cli-gym-expand-20261107`，源44f7746。


## 2026-11-07：数据盘恢复，保留实验与训练证据

核验时间：00:01，Asia/Shanghai。用户要求清理接近满载的ECS数据盘。

- 操作前可用5.18GiB；本次归档净回收45.18GiB，复核可用50.03GiB。全盘同时有实验写入，不把全盘差值全部归因本次。
- 仅归档已经结束的CLI-Gym rolling acquisition中的123,677份wire/request/response日志，逐文件完整解压核对SHA，0错误；原字节保留为权威gzip归档，ledger保存原路径、SHA、长度、mode、mtime及终态上下文。原目录新增归档入口说明，未来审计可解压或流式读取，不应删除gzip文件作为缓存。
- 轨迹、decision、评分、失败记录、SFT文件和费用记录未删除。415份train.jsonl的SHA逐一与操作前相同，全部终态上下文未改变，另抽12份独立恢复校验通过。
- 全部原镜像仍在，0镜像删除、0Docker/模型重启。约52GiB的CLI-Gym镜像目录确认被dockerd引用后明确排除。全量SWE控制器PID/start不变，采样继续；已有2条1800秒AgentTimeout按unknown保留，另1题NOP环境未产出reward被门禁拦住，均未自动重跑，不归因磁盘也不计有效0分。

审计：ECS `/mnt/ecs-tb4/audits/storage-recovery-20261106-night`；维护源2a106cb，复用ac1eefc压缩原语。原始模型内容不进入Git，只有脱敏统计与校验证据。[复核证据](../evidence/storage-recovery-20261106-night.json)。本次有限清理已结束，未增加定时任务；新SWE批次的独立已结束日志归档继续随该批次生命周期运行。

### 00:47：第二轮扩大夜间存储余量

用户再次要求释放数据盘空间。仅归档5个明确历史评测目录中已终态至少10分钟、日志也静置至少10分钟且无打开FD/符号链接/多硬链接的API wire/request/response文件，明确排除当前SWE300。包含失败/超时尝试的原始流，但不把这些尝试改成有效完成或重跑。

有限worker65b133a、压缩原语ac1eefc；实际SDK3项回归通过。25,349份日志全部完成解压/SHA验证、0错误，本轮净回收88.57GiB；并发写入下数据盘49.02→132.44GiB可用。最大一份旧HTTP流日志59.2GiB压缩为约0.5GiB，原始字节完整保留。与首轮合计净回收约133.75GiB，不把全盘差值冒充本次归因。

1,237份历史result/trajectory的SHA及415份训练文件SHA全部不变；独立抽12份恢复通过，全部原镜像保留，未重启或重跑模型/daemon；SWE300控制器PID/start保持且队列继续。维护只用2个压缩worker，00:38–00:43期间与评测共用主机IO/CPU，耗时分析应保留这个运维窗口，不据此做权重导致速度差的强归因。

各历史根目录新增ARCHIVED_API_JOURNALS_20261107_WAVE2.json指向权威gzip/ledger；原始模型输出不进入Git，压缩包不可当缓存删除。审计ECS `/mnt/ecs-tb4/audits/storage-recovery-20261107-wave2`。[复核证据](../evidence/storage-recovery-20261107-wave2.json)。

## 2026-11-06：轻量SWE开发评测与后续消融路线

核验时间：2026-11-06 23:00，Asia/Shanghai。用户授权更新proposal，并启动base/方法SFT/专家SFT的小规模轻量SWE对照。

- 优先级：P0可靠快速评测；P1补E2直接参考学生SFT；P2随机/较难/混合数据选择；P3recipe；P4domain多样性；P5离线动作改写及候选排序消融。现有531对不是等监督token比较。
- SWE-bench Lite官方dev23题中固定6题：Marshmallow/Pydicom/Astroid各按标识前2，不看模型结果/gold规模。5题NOP0/gold1通过，Pydicom-1139因pytest8未执行旧setup钩子，官方gold有2项P2P失败而hold；不删测试、不算模型0、不换题。
- 初次a1在模型POST前发现官方镜像缺tmux，3组setup失败并逐一按真实进程身份停住；模型请求0，原记录/成本保留。仅为这次零推理启动修复增加离线tmux组件，不动原镜像、Python、repo和评分代码。5/5实际Terminus install-only通过，补验NOP0/gold1通过。
- a2现已进入真实采样：每组5题Pass@1，共15次、每组1并发，epoch1 step34、统一Terminus-2/nonthinking/.6/1800秒/no paid retry；epoch2与TB2.1不变。正式采样已于22:45结束，wall-time53.01分钟：Base3/5、方法5/5、专家3/5；15/15有效，无采样超时/上下文超限/API异常。Agent耗时中位数分别9.43/3.47/3.44分钟；轮次19/14/16；工具调用39/31/35。所有1分均逐项核对全部必需检查通过。5题探索样本不证明稳定优势，服务集群差异仍是延迟混杂。
- 数据revision `b0dde1093fe417d83b7184254edf8199c1f0dff5`、parser commit `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`冻结；5项SDK协议回归通过。新运行显式绑定ECS `/mnt/ecs-tb4/evaluations/qwen38-swe-lite-dev6-20261106-a2`，a1及启动失败不删除。共享库ecb151b、执行入口4483fe8分别冻结。
- 耗时报告分离模型/工具/安装与verifier：已发现Marshmallow-1359官方脚本断网pip重试约6.5分钟，不能算agent能力耗时。正式比较报告原6题与准入5题两种覆盖；小试不是官方300题成绩。

[首批完成指标](../evidence/swe-lite-dev-first-results-20261106.json) · [启动证据与三组绑定](../evidence/swe-lite-dev-pilot-20261106.json) · [完整小试协议](https://github.com/kfq20/finetuning-with-sampling/blob/study/lightweight-swe-eval-20261106/agentic/experiments/swe-lite-dev-20261106/README.md)。

[完整结果](../evidence/swe-lite-dev-final-20261106.json)。原6题中的Pydicom-1139环境hold仍保留；初始零推理启动失败与正式15条分列，未启动额外采样。

### 23:35：用户授权官方test300全量三组对照

范围已明确为官方测试集300题，不是dev23。三组各Pass@1，最多900次新模型尝试，与先导开发集完全分开；继续使用epoch1 step34，不随epoch2完成换权重，不重跑先导已完成尝试。

队列采用4个逐题验收worker，合格即接入三组独立队列、每组最多4并发（合计12模型）。每题实际install-only、NOP0/gold1；门禁失败独立hold，API/捕获/评分异常为unknown、不算正常0。Agent1800秒与先导一致，完整官方测试的verifier放宽到1800秒，必需测试及裁判逻辑不变。Base conda解释器只运行评分包装，官方脚本仍激活原testbed Python。

明确运行身份：ECS `/mnt/ecs-tb4/evaluations/qwen38-swe-lite-test300-20261106-a1`，冻结执行入口183287a、共享推理库ecb151b。首批已有6题准入、17条claim、6条正常完成、0执行异常；此为启动快照，不是900完成或最终得分。控制器在ECS独立运行，不依赖本地SSH会话。源码8项协议回归通过。

数据盘约5.5GiB可用，新增本批已结束请求/流日志的无损压缩worker（ac1eefc，实际SDK2项回归通过）；逐文件完整解压比对SHA后才压缩归档，保留全部原始字节、mtime与证据关系，原result/trajectory/decision/裁判文件不改。压缩包是权威原始记录，不能作为临时缓存删除。源代码和支撑worker各有独立散列及launch收据，不修改在跑的冻结执行代码；没有新增定时自动化或新模型采样器。

[全量启动快照](../evidence/swe-lite-test300-launch-20261106.json) · [运行与报告说明](https://github.com/kfq20/finetuning-with-sampling/blob/study/swe-lite-full-20261106/agentic/experiments/swe-lite-full-20261106/README.md)。正式测试用于这一轮迁移验证；后续recipe与数据筛选仍应使用独立开发材料，不把test300轨迹回流训练。


### 2026-11-08：CLI直接Docker派发，停止逐题校准前置

用户明确覆盖CLI昂贵环境修复/预检口径。选定support/cli-direct-20261108，复用原冻结运行库加e9a529e增量；只对未付费、非留出CLI启用build-only，SWE门禁和最终SFT准入不变。3项实际SDK回归通过；接续16在途worker、1774份已结束证据SHA不变。首次核验8个直接任务已发布且进入主队列，尚无direct模型claim；16活跃、24排队、无provider hold，评分32。新供给不等于新SFT；原CLI604不变。无失败模型重跑、无新自动化。

证据：ECS生产root/support/cli-direct-20261108/postcheck.json、runtime-binding.json、builder-launch.json及cli-direct-build-20261108/plan.json。

### 2026-11-08 21:40 CST：冻结CLI留出100题，启动HTTP Base评测

用户在等待Fleet新凭证期间授权先测Base。选定ECS `/mnt/ecs-tb4/evaluations/qwen38-cli100-base-http-20261108-a1`，同一100题留出SHA不变；无参考Pass@1、Terminus-2、nonthinking/.6/context262144、原题时限、2独立进程并发，无候选评分或SFT导出。首个row1500真实canary已17次请求、17次HTTP200，仍执行中，尚无最终得分；正常闭环后自动进入其余题目。环境复用66包并已新构建1包至67；其余按原配方直接尝试，构建/封装失败单列不替题。3项实际SDK回归及6份Harbor源码pin通过。生产保持16活跃、评分32、无provider hold；评测新增负载共享HTTP服务，耗时比较需区分服务差异。

两组Epoch2均为68步最终state，200次对照配置另存 `/mnt/ecs-tb4/evaluations/qwen38-cli100-epoch2-20261108-a1`；当前Fleet两种鉴权头均返回401 invalid api key，未POST部署、未用Epoch1替代。证据：[Base启动与进程核验](../evidence/cli-heldout100-base-http-20261108.json)。
