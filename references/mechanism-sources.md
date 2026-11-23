# 机制文献与代码的发现入口

按问题选读，不默认下载或安装。此索引从用户提供的《面向科学问题的神经元模型机制扩展：文献、代码与跨系统建模调研》（2026-11-22）第 2 节及按需扩展部分提炼，配合《未预设科学问题的调研、追问与神经模型构建工作流》的开放检索思路使用。所需操作规则已保存在本技能内，运行不依赖这两份文档在作者电脑上的路径。

它不是全部可用模型的列表，也不是一份已安装、已运行的模型库。缺少条目时按[现象与条件检索](interview.md#调研与追问交替推进)继续查原始研究、作者存档及相关实现；[ModelDB 官方帮助](https://modeldb.science/help)可用于发现完整模型及局部组件。采用前仍需固定实际版本、读取相关方程/代码并按[机制接入规则](mechanism-extension.md)核对适用性。

需要发现不同数学表示或选择软件时，按[方法发现与软件选择](method-discovery.md)从必要过程和观测出发。也可由 [BioModels](https://www.ebi.ac.uk/training/online/courses/biomodels-quick-tour/what-is-biomodels/) 查找相关定量机制模型，由 [NeuroML 官方运行说明](https://docs.neuroml.org/Userdocs/SimulatingNeuroMLModels.html) 了解模型描述、转换和运行后端的区别；所列平台不构成安装清单。新增入口的定向核查范围与日期见方法发现页，原有条目的核查范围仍如下所述。

## 神经元、突触与局部机制

| 研究需求 | 原始模型或实现入口 | 优先核对的最小内容与边界 |
|---|---|---|
| 主动树突、反向传播与 Ca 尖峰 | Hay et al. 2011：[ModelDB 139653](https://modeldb.science/139653)、[模型源码](https://github.com/ModelDBRepository/139653) | 配套形态、通道/钙状态、空间分布、参数组合及目标协议；不能只移植一个机制文件就推定保留原模型目标。 |
| 发放适应、后脉冲电流与动态阈值 | Teeter et al. 2018：[作者仓库](https://github.com/AllenInstitute/GLIF_Teeter_et_al_2018)、[AllenSDK GLIF 文档](https://allensdk.readthedocs.io/en/latest/glif_models.html) | 对应细胞配置及电压、阈值、复位规则；有效状态的解释限于所用表示，不自动提供具体通道药理。 |
| Na/K 动态、泵与离子恢复 | Cressman et al. 2009：[ModelDB 136773](https://modeldb.science/136773)、[降阶源码及版本差异说明](https://github.com/ModelDBRepository/136773/blob/master/Cressman_et_al_JCNS_1_reducedmodel.ode) | 区分完整电学与降阶浓度模型；核对泵、缓冲、储库和电流平均的定义，不能假定已有 ATP 耦合。源码注释区分排印更正与实际出图方程。 |
| 钙阈值可塑性 | Graupner–Brunel：[作者实现](https://github.com/mgraupe/CalciumBasedPlasticityModel) | 钙变量的有效定义、效能状态和诱导协议；与物理浓度或成像信号连接时另作映射。 |
| 形态与局部生理约束的可塑性 | Chindemi et al. 2022：[归档版本 2.1](https://zenodo.org/records/6352774) | 按所需细胞对读取形态、局部通道、突触位置、环境条件和配套参数；取得归档列表不等于已读包内代码。 |
| 多巴胺调节兴奋性及作用时程 | Lindroos et al. 2018：[ModelDB 237653](https://modeldb.science/237653)、[作者模型及勘误](https://github.com/ModelDBRepository/237653) | 静态作用函数、动态级联及通道靶点分开选择；核对接口实际接入的底物，预测与实测约束分别标明。 |
| 光输入到通道电流 | Williams et al. 2013：[作者 MATLAB 模型](https://modeldb.science/151549)、[后续 NEURON 移植](https://modeldb.science/244414) | 通道变体、表达密度、局部光强、电压及条件适配；通道模型与组织光传播分别处理，两种实现不当成独立生理依据。 |
| 胶质 Ca/IP3 响应 | De Pittà 2009 模型的[ModelDB 223269 再实现](https://github.com/ModelDBRepository/223269) | 化学区室、Glu 输入和 Ca/IP3 状态；脉冲到 Glu、胶质到突触的关系需各自定义。 |
| 胶质对释放与网络活动的有效反馈 | De Pittà–Brunel 2022：[作者实现](https://github.com/depitta-lab/eig-classes-pnas-2022) | 反馈作用变量、胶质与突触关联、时程及当前网络工作状态；不与单独的生化响应模型混称。 |
| 共享介质、电扩散与体积关系 | Sætra–Mori：[作者实现](https://github.com/martejulie/electrodiffusive-network-model) | 原模型的空间、区室、边界与共同更新；不是可任意加到任何网络的通用独立插件。 |
| 已有膜电流与化学状态互通 | [NEURON MOD–RxD 官方示例](https://www.neuronsimulator.org/en/latest/rxd-tutorials/combining%20currents%20from%20mod%20files%20with%20rxd.html) | 用于理解接口。该示例没有额外稳态恢复机制，不能据此称已经具备完整泵或能量代谢。 |

## 问题确实涉及跨系统或更换表示时

| 实际缺口 | 进一步发现入口 | 采用前需要解决的关系 |
|---|---|---|
| 生化、反应扩散与复杂几何 | [NEURON RxD](https://www.neuronsimulator.org/en/latest/rxd-tutorials/index.html)、[BhallaLab MOOSE](https://github.com/BhallaLab/moose)、[STEPS](https://steps.sourceforge.net/STEPS/documentation.php.html)、[MCell](https://mcell.org/) | 具体论文模型、物种/反应/几何与膜机制接口；工具名称不替代生理模型。 |
| 群体表示、全脑或局部脉冲网络耦合 | [TVB](https://github.com/the-virtual-brain/tvb-root)、[TVB–NEST](https://github.com/multiscale-cosim/TVB-NEST) | 群体意义、事件/速率转换、交换时间与详细模块替代范围，避免重复计算同一群体作用。 |
| 形态约化、可微拟合或代理 | [Neuron_Reduce](https://github.com/orena1/neuron_reduce)、[Jaxley](https://github.com/jaxleyverse/jaxley)、[neuron_as_deep_net](https://github.com/SelfishGene/neuron_as_deep_net) | 保留量、教师/方程版本、输入范围、误差与参数解释；三种方法不视作等价替换。 |
| 器官与系统生理方程 | [Physiome Model Repository](https://models.cellml.org/welcome)、[OpenCOR](https://opencor.ws/) | 指定论文的区室、物质交换、边界与神经模块映射，不默认增加完整器官系统。 |
| 身体、肌肉与感觉反馈 | [OpenSim](https://github.com/opensim-org/opensim-core)、[FlyGym](https://github.com/NeLy-EPFL/flygym/) | 身体、控制器、感觉与环境的各自职责；行为拟合不直接证明神经机制。 |
| 外场及观测 | [SimNIBS](https://simnibs.github.io/simnibs/build/html/index.html)、[k-Wave](https://www.k-wave.org/)、[LFPy](https://github.com/LFPy/LFPy) | 先区分施加的场与被观测信号，再定义几何、源与细胞作用/观测映射。特定声—膜候选可另查 [PySONIC](https://github.com/tjjlemaire/PySONIC) / [MorphoSONIC](https://github.com/tjjlemaire/MorphoSONIC)，不作为默认刺激或治疗机制。 |

## 本索引的核查范围

2026-11-22 本次技能维护直接读取了 ModelDB 的 Hay、Lindroos 模型页与官方帮助、AllenSDK GLIF 文档、NEURON MOD–RxD 示例，以及 Cressman 降阶源码中的方程/出图差异注释。读取网页或源码均未执行对应模型。其余条目作为用户调研文档提供的候选入口保留，未在本轮逐个重新核查代码、依赖或许可。

这些入口用于启动本次项目的定向研究，不把历史阅读记录写成新项目已完成的检索或验证。仓库的当前主页也不替代项目实际采用的固定版本。关于具体文件、许可、后端接口和数值适用性的结论，以本次实际读取和运行的对应版本为准。
