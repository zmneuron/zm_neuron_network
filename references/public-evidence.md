# 公开论文、实验与实现怎样共同决定模型

以“感觉皮层各层的自发放电率为何不同”为例。要查的是细胞怎样分层、投射概率和接触数怎样定义、突触参数怎样进入后端、何种记录可以检验预测。下列对应关系来自公开资料的数值与源码核对。该例包含来源比较、参数换算和局部连接的构建检查。完整网络的放电动力学尚未在此运行。

本文件示范如何比较来源；新任务仍需按[调研记录与模型构建方法](construction-methods.md)保存该次真实检索、方法比较及来源到参数的转换，并形成完整构建步骤。下述历史参数和局部检查不自动成为新模型的默认值，也不代替该次模型的实际构建记录。

## 从十四项要素出发

| 要素 | 查到的依据与本轮处置 |
|---|---|
| 01 目标、02 生物学条件 | Potjans 与 Diesmann（PD14）研究通用早期感觉皮层的层间放电差异。Binzegger 等以猫 V1 形态重建估算接触数，Lefort 等在 P18–21 小鼠 C2 桶状皮层脑片测兴奋性细胞对的连接。两项实验约束不同的量。若目标改变为某一物种的特定区域，须重审来源。[PD14 方法与表 4–5][pd] · [猫 V1 解剖研究][binzegger] · [小鼠配对记录，图 3、表 2][lefort] |
| 03 细胞群、04 空间 | 为比较各层，保留 L2/3、L4、L5、L6 各自的兴奋与抑制群。原模型以 1 mm² 皮层表面下组织为范围，细胞以点单元表示。表 5 的八群数量在参考代码的 `full_num_neurons` 中逐群给出。缩小规模要说明保留什么量。[PD14 表 4–5][pd] · [群体与参数][pd-params] |
| 05 动力学、06 参数 | 参考实现采用 `iaf_psc_exp`。原模型的膜电容 250 pF、膜时间常数 10 ms 和突触时间常数 0.5 ms 可直接用于相同方程。Brunel 的两群体简化路线可作兴奋–抑制平衡对照，本身没有层别输出。[PD14 表 5][pd] · [参考参数][pd-params] · [Brunel 原研究][brunel] |
| 07 投射、08 突触 | PD14 定义的是有向细胞对至少有一个接触的概率。群间接触总数、每个来源的出度和单接触强度分别记录。两份同源代码的概率表相同，具体连线实现及单位转换见下文。[PD14 方法与表 5][pd] · [连接数与权重换算][helpers] |
| 09 输入、10 耦合 | 明确背景是独立泊松输入还是等效直流。参考版本的参数字典默认 `dc`，同时给出 8 Hz 的背景源率；复现规定为泊松背景的条件时显式选该模式。兴奋和抑制通过突触电流耦合，本题先不引入额外生理模块。[参考输入配置][pd-params] · [PD14 对背景输入的比较][pd] |
| 11 初值、12 数值设置 | 参考实现提供原始和分群优化的膜电位初值。运行方案选择其一并写清预运行、记录期和步长。改变网络规模或后端时保存相同条件，用独立种子评估波动。[初始分布][pd-params] · [参考时间设置][sim] · [缩模研究][port-paper] |
| 13 实验观测、14 分析验证 | 从逐细胞尖峰按实际记录时长计算 Hz，含无尖峰的已记录细胞。PD14 图 6B 是模拟的自发放电率。de Kock 等有大鼠桶状皮层分层、逐细胞放电及胡须刺激协议。只能将可比的层、细胞类别和行为或刺激时段相配。独立实验检验还需取得未参与选参且条件匹配的记录。同步若为终点，须另验时间分箱和缩模效应。[PD14 图 6B、D][pd] · [原始放电研究][dekock] · [缩模研究][port-paper] |

## 三个会改变实现的比较

1. **采用哪一个连接概率。** PD14 表 5 以行为目标、列为来源，L4E→L2/3E 报为 0.044。公开实现保留 0.0437，反向为 0.0077。Lefort 等在其脑片样本中分别测到 L4→L2 为 12%、L4→L3 为 14.5%。研究对象、细胞分层与取样范围各异。复现通用模型时采用 0.0437，写入方向与分母。若要解释小鼠 C2 配对数据，则区分 L2 和 L3，按实验取样条件重新约束。解剖接触数用于检验数量级，换成细胞对概率还需要接触在细胞对之间如何分配的假设。[原模型表 5][pd] · [参数矩阵][pd-params] · [配对实验][lefort] · [解剖估计][binzegger]
2. **怎样画出实际的连接。** 对照 INM-6 参考 PyNEST（提交 `849185b3`）与 Romaro 等发布的 NetPyNE/NEURON 移植（`a6e39c19`），两份 8×8 概率表的 64 项逐值相同。前者由 `num_synapses_from_conn_probs` 换算群间接触总数，在建网函数中用 `fixed_total_number` 抽样。后者的皮层间连接用 `divergence` 按每个突触前细胞分配出度。若第一版旨在复现 PD14 的连线统计，首选前者的抽样语义，并输出群间总接触数、不同细胞对数和出入度分布。两个实现是同一模型的两种实现。独立的 Brunel 两群体示例（NEST v3.8，`6dca9500`）用 `fixed_indegree` 固定每个目标的输入数，适合回答群体平衡问题。若用它作简化对照，应重新定义能比较的量。[PyNEST 建网函数][pd-connect] · [NetPyNE 连接规则][port-code] · [移植论文][port-paper] · [Brunel 实现][brunel-code]
3. **哪种权重和指标能跨实现比较。** PD14 的常规兴奋性突触后电位峰值为 0.15 mV，L4E→L2/3E 的均值加倍。在上述膜和突触参数下，用被动膜对单个指数衰减电流脉冲的响应核算突触后电位。电位约在 1.577 ms 达峰，0.15 和 0.30 mV 分别对应约 87.81 和 175.62 pA 的电流峰值。该换算用于全规模、未做突触缩放的参数。Brunel 的 `iaf_psc_delta` 示例把 `J=0.1` 定义为 mV 电压跃变，换后端应重新核对方程。Romaro 等评估了缩模对同步性的影响，所以自发率通过只支持该指标。若用户改选同步，另设预处理、样本数、独立种子和同步指标的判据；复现 PD14 图 6D 时采用 3 ms 分箱计算群体尖峰数的方差与均值之比。[PSP 至 PSC 的函数][helpers] · [加倍的投射][pd-params] · [移植与缩模][port-paper] · [Brunel 实现][brunel-code] · [原模型图 6D][pd]

本次查的是感觉皮层分层、细胞对连接、控制性模型比较与放电读数。上述实验证据尚不足以给任一特定动物填满含抑制亚型的 8×8 矩阵。遇到这种缺口，要记录已查到哪些物种、制备和测量，保留合理范围或明确模型假设，再按实际问题选取新的实测材料。这个比较方法可用于 CA1 等其他脑区，具体参数需另查。

### 把细胞对、突触接触和伙伴数分别算一次

为检查第 07 项，从公开概率表取出两个相反方向的值，在内存中分别建立 32 个 L4E 和 32 个 L2/3E 测试细胞。对每个方向，以 `round(log(1-p) / log(1-1/1024))` 得到接触总数，再用 Python 3.13.5 的 `random.Random(42)` 均匀有放回抽取有向细胞对。先算 L4E→L2/3E，再算反向，每个接触调用一次 `randrange(1024)`，除以 32 的商为来源编号，余数为目标编号。每个目标的不同来源数按全部 32 个目标汇总，包括没有输入的目标。[概率定义][pd] · [接触数换算][helpers]

| 投射 | 细胞对连接概率 | 生成的接触数 | 不同的有向细胞对数 | 每目标平均不同来源数 |
|---|---:|---:|---:|---:|
| L4E → L2/3E | 0.0437 | 46 | 44 | 1.375 |
| L2/3E → L4E | 0.0077 | 8 | 8 | 0.25 |

同一种子再运行一次得到相同的连接。第一行中有重复接触，若将接触数直接当成不同的来源数，会把伙伴总数从 44 写成 46。32 个细胞是这次软件检查选定的规模，上表的数值描述这一组生成结果。

## 当目标改成小鼠 V1 的局部连接

用户若问“对相似图像有响应的细胞，彼此更容易连上，还是已经连上的突触更强”，要素 07 和 08 对应两种测量。Ko 等在小鼠 V1 第 2/3 层比较了相邻锥体细胞的视觉反应和连接概率。同一研究团队的发育研究发现，刚睁眼时已经出现视觉选择性，当时尚未观察到相似细胞间的优先连接。Cossell 等进一步测量连接强度，少数强连接集中于视觉反应高度相关的细胞对。此时应查明动物年龄，分别保留检测过的全部细胞对、其中的已连接细胞对及其突触后电位幅度。这决定了概率的分母、强度的单位和所需记录。这几篇论文有共同作者，使用实验数据前还应核对样本是否重叠。[连接概率研究](https://pubmed.ncbi.nlm.nih.gov/21478872/) · [发育条件](https://pubmed.ncbi.nlm.nih.gov/23552948/) · [连接强度研究](https://pubmed.ncbi.nlm.nih.gov/25652823/)

换一条独立的模型路线进行比较。Billeh 等发布的小鼠 V1 模型有 17 类细胞，点神经元和生物物理版本共享连接图，可在控制连接图的条件下比较细胞表示。Allen 后续公开实现中的 `connect_cells` 使用平面胞体距离，并在启用取向依赖的投射上依据细胞的偏好取向差调整连接概率。该后续版本单列来源。若实测量是两个细胞对一组视觉刺激的反应相关系数，先从模型用同一刺激计算这个量，再与实验比较。取向差和反应相关系数须分别定义。这会影响要素 04 的位置变量、07 的连接生成以及 13–14 的观测和检验。[Billeh 等原研究](https://pubmed.ncbi.nlm.nih.gov/32142648/) · [2020 模型发布页](https://brain-map.org/our-research/computational-modeling/models-of-the-mouse-primary-visual-cortex) · [后续实现的连接函数](https://github.com/AllenInstitute/biorealistic-v1-model/blob/8f3159ca8574b5e3cc090705be507e2cb60b1523/edge_funcs.py#L90-L190)

[pd]: https://juser.fz-juelich.de/record/127963/files/FZJ-2012-00909.pdf
[binzegger]: https://pubmed.ncbi.nlm.nih.gov/15456817/
[lefort]: https://www.hms.harvard.edu/bss/neuro/bornlab/nb204/papers/lefort-etal-petersen-network-neuron2009.pdf
[dekock]: https://doi.org/10.1113/jphysiol.2006.124321
[brunel]: https://doi.org/10.1023/A:1008925309027
[port-paper]: https://doi.org/10.1162/neco_a_01400
[pd-params]: https://github.com/INM-6/microcircuit-PD14-model/blob/849185b3f989dfd5d5c693415808830221b99910/PyNEST/src/microcircuit/network_params.py#L64-L149
[pd-connect]: https://github.com/INM-6/microcircuit-PD14-model/blob/849185b3f989dfd5d5c693415808830221b99910/PyNEST/src/microcircuit/network.py#L473-L501
[helpers]: https://github.com/INM-6/microcircuit-PD14-model/blob/849185b3f989dfd5d5c693415808830221b99910/PyNEST/src/microcircuit/helpers.py#L46-L120
[sim]: https://github.com/INM-6/microcircuit-PD14-model/blob/849185b3f989dfd5d5c693415808830221b99910/PyNEST/src/microcircuit/sim_params.py#L33-L43
[port-code]: https://github.com/suny-downstate-medical-center/PDCM_NetPyNE/blob/a6e39c19a0d85e0e907acac33791363591a88f45/netParams.py#L195-L221
[brunel-code]: https://github.com/nest/nest-simulator/blob/6dca9500e512da50fa730a7b62ce4b05c77e2bfd/pynest/examples/brunel_delta_nest.py#L64-L206
