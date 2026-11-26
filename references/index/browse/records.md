# 逐条查看资料

由四张表生成。每项结果均可回到原文位置，同一来源组中的条目可能共享动物、细胞或原始记录。

### p_sbi

**[Training deep neural density estimators to identify mechanistic models of neural dynamics](https://doi.org/10.7554/eLife.56261)**　从已知观测推断能重现相同膜活动或环路节律的参数集合。

Gonçalves PJ 等 · 2020-09-17 · published · model, method · 数据 linked。[来源](https://pmc.ncbi.nlm.nih.gov/articles/PMC7581433/)

窗口内建模与理论。

标签　单细胞、局部微环路、生物物理模型、概率与统计生成模型、网络节律

[Figure 5b；原实验 Haddad & Marder 2018](#o_sbi_exp) · cited_measurement · 周期、相位延迟与间隙、簇持续时间

[Figure 5c 与 Appendix 1—figure 11](#o_sbi_params) · inferred · 膜与突触电导的联合后验

[Figure 2g；Appendix 1—figure 5](#o_sbi_negative) · simulation · 感受野与参数后验能否恢复

本条 ← [p_sbi_pre](#p_sbi_pre) · preprint_of · 同一研究的预印本与正式版本，不能当作两次实验。。[出处](https://api.crossref.org/works/10.7554/elife.56261)

本条 → [p_prinz](#p_prinz) · extends_model · 采用经典幽门回路，并在后续推断中加入内在噪声。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC7581433/)

本条 → [p_haddad](#p_haddad) · reuses_observations · Figure 5b 给出原蟹神经实测，5c、5d 以此约束模型。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC7581433/)

本条 ← [r_sbi_implementation](#r_sbi_implementation) · implements · 当前可定位的仓库版本。论文原始运行所用提交需按文中另核。。[出处](https://github.com/mackelab/IdentifyMechanisticModels_2020)

本条 → [p_hh1952](#p_hh1952) · uses_model_family · Fig. 3 的 Hodgkin–Huxley 类模型允许对不同膜参数组合做推断，具体方程和采用参数以该图方法为准。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC7581433/)

### p_sbi_pre

**[Training deep neural density estimators to identify mechanistic models of neural dynamics](https://doi.org/10.1101/838383)**　查看神经动力学参数推断方法的首次公开版本，正式版另有原始结果定位。

Gonçalves PJ 等 · 2019-11-12 · preprint · model, method · 数据 unchecked。[来源](https://www.biorxiv.org/content/10.1101/838383v1)

预印本。

标签　单细胞、局部微环路、概率与统计生成模型

本条 → [p_sbi](#p_sbi) · preprint_of · 同一研究的预印本与正式版本，不能当作两次实验。。[出处](https://api.crossref.org/works/10.7554/elife.56261)

### p_haddad

**[Circuit Robustness to Temperature Perturbation Is Altered by Neuromodulators](https://doi.org/10.1016/j.neuron.2018.08.035)**　区分药理与温度对蟹幽门节律稳定性的影响，后续模型使用其中的记录。

Haddad SA 等 · 2018-09-20 · published · experiment · 数据 unchecked。[来源](https://pubmed.ncbi.nlm.nih.gov/30244886/)

窗口内实验与技术支持。电子首发，原刊/文献登记 ArticleDate

标签　其他无脊椎类、局部微环路、网络节律、药理作用

本条 ← [p_sbi](#p_sbi) · reuses_observations · Figure 5b 给出原蟹神经实测，5c、5d 以此约束模型。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC7581433/)

### p_prinz

**[Similar network activity from disparate circuit parameters](https://doi.org/10.1038/nn1352)**　比较膜与突触参数不同的候选能否产生相似的幽门节律。

Prinz AA 等 · 2004-11-21 · published · model · 数据 unchecked。[来源](https://pubmed.ncbi.nlm.nih.gov/15558066/)

早期关联文献。电子首发，原刊/文献登记 ArticleDate

标签　其他无脊椎类、局部微环路、生物物理模型、网络节律、突触

本条 ← [p_sbi](#p_sbi) · extends_model · 采用经典幽门回路，并在后续推断中加入内在噪声。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC7581433/)

### p_nwb

**[The Neurodata Without Borders ecosystem for neurophysiological data science](https://doi.org/10.7554/elife.78362)**　选择能记录刺激、观测、行为同步与元数据的神经生理交换格式。

Rübel O 等 · 2022-10-04 · published · method, software · 数据 unchecked。[来源](https://pubmed.ncbi.nlm.nih.gov/36193886/)

窗口内实验与技术支持。电子首发，原刊/文献登记 ArticleDate

标签　复现与互操作、细胞内记录、胞外单单位、行为观测

本条 ← [p_nwb_pre](#p_nwb_pre) · preprint_of · 注册元数据明确关联两个公开版本。。[出处](https://api.crossref.org/works/10.1101/2021.03.13.435173)

本条 ← [r_nwb_spec](#r_nwb_spec) · specification_for · 当前可定位的仓库版本。论文原始运行所用提交需按文中另核。。[出处](https://github.com/NeurodataWithoutBorders/nwb-schema)

### p_nwb_pre

**[The Neurodata Without Borders ecosystem for neurophysiological data science](https://doi.org/10.1101/2021.03.13.435173)**　追溯 NWB 数据模型的早期说明与正式版。

Rübel O 等 · 2021-03-15 · preprint · method, software · 数据 unchecked。[来源](https://api.crossref.org/works/10.1101/2021.03.13.435173)

预印本。

标签　复现与互操作、细胞内记录、行为观测

本条 → [p_nwb](#p_nwb) · preprint_of · 注册元数据明确关联两个公开版本。。[出处](https://api.crossref.org/works/10.1101/2021.03.13.435173)

### p_hierarchy

**[Hierarchical Heterogeneity across Human Cortex Shapes Large-Scale Neural Dynamics](https://doi.org/10.1016/j.neuron.2019.01.017)**　比较皮层区域差异对人脑网络动力学的影响，并检查成像读数转换。

Demirtaş M 等 · 2019-02-07 · published · model · 数据 unchecked。[来源](https://pubmed.ncbi.nlm.nih.gov/30744986/)

窗口内建模与理论。电子首发，原刊/文献登记 ArticleDate

标签　人类、大脑皮层、脑区间网络、神经群体、神经群体模型、连接与拓扑、血氧信号

本条 ← [r_hier_code](#r_hier_code) · implements · 当前可定位的仓库版本。论文原始运行所用提交需按文中另核。。[出处](https://github.com/murat-demirtas/heterogeneity)

### p_osb

**[Open Source Brain: A Collaborative Resource for Visualizing, Analyzing, Simulating, and Developing Standardized Models of Neurons and Circuits](https://doi.org/10.1016/j.neuron.2019.05.019)**　寻找可在多个模拟环境复现和比较的标准神经元与回路模型。

Gleeson P 等 · 2019-06-11 · published · method, software · 数据 not_applicable。[来源](https://pubmed.ncbi.nlm.nih.gov/31201122/)

窗口内实验与技术支持。电子首发，原刊/文献登记 ArticleDate

标签　复现与互操作、多区室模型、局部微环路

本条 → [r_granule_osb](#r_granule_osb) · platform_example · 该资源可经 Open Source Brain 的小脑模型专题检索。。[出处](https://v1.opensourcebrain.org/docs/Research_Themes/)

### p_muscle

**[Motoneuron-driven computational muscle modelling with motor unit resolution and subject-specific musculoskeletal anatomy](https://doi.org/10.1371/journal.pcbi.1011606)**　将运动单位放电映射到肌肉力，区分运动单位招募和频率编码。

Caillet AH 等 · 2023-12-07 · published · model, experiment · 数据 linked。[来源](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1011606)

窗口内建模与理论。

标签　人类、神经肌肉系统、脊髓、运动控制、观测信号生成

本条 ← [r_mn_model](#r_mn_model) · implements · 当前可定位的仓库版本。论文原始运行所用提交需按文中另核。。[出处](https://github.com/ArnaultCAILLET/MN-driven-Neuromuscular-Model-with-motor-unit-resolution)

本条 ← [r_muscle_zen](#r_muscle_zen) · provides_geometry · 论文数据声明列出分割影像和肌骨模型。。[出处](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1011606)

### p_myogen

**[MyoGen: unified biophysical modeling of human neuromotor activity and resulting signals](https://doi.org/10.1038/s41467-026-79273-3)**　将脊髓、肌腱及反馈与可比较的肌电及运动单位输出联系起来。

Sîmpetru 等 · 2026-11-16 · published · model, method · 数据 unchecked。[来源](https://www.nature.com/articles/s41467-026-79273-3)

窗口内建模与理论。

标签　脊髓、神经肌肉系统、运动控制、生物物理模型、人类、观测信号生成

### p_senzai

**[Physiological Properties and Behavioral Correlates of Hippocampal Granule Cells and Mossy Cells](https://doi.org/10.1016/j.neuron.2016.12.011)**　在齿状回与 CA3 的记录中区分颗粒细胞、苔藓细胞的放电与行为关联。

Senzai Y 等 · 2017-01-26 · published · experiment · 数据 linked。[来源](https://pubmed.ncbi.nlm.nih.gov/28132824/)

窗口内实验与技术支持。电子首发，原刊/文献登记 ArticleDate

标签　小鼠、海马、在体、尖峰时间、局部场电位记录、行为观测

本条 ← [r_dandi000003](#r_dandi000003) · described_by · 版本记录的 relatedResource 指向采集研究。。[出处](https://api.dandiarchive.org/api/dandisets/000003/versions/0.261122.2143/)

### p_filter

**[Layer 4 fast-spiking interneurons filter thalamocortical signals during active somatosensation](https://doi.org/10.1038/nn.4412)**　约束触须主动感觉任务中丘脑输入与皮层第 4 层快发放中间神经元的响应。

Yu J 等 · 2016-10-17 · published · experiment · 数据 linked。[来源](https://pubmed.ncbi.nlm.nih.gov/27749825/)

早期关联文献。电子首发，原刊/文献登记 ArticleDate

标签　小鼠、大脑皮层、丘脑、感觉编码、细胞内记录、在体

本条 ← [r_dandi000005](#r_dandi000005) · described_by · 版本记录的 relatedResource 指向采集研究。。[出处](https://api.dandiarchive.org/api/dandisets/000005/versions/0.220126.1853/)

### p_economo

**[Distinct descending motor cortex pathways and their roles in movement](https://doi.org/10.1038/s41586-018-0642-9)**　比较不同下行投射的运动皮层细胞在延迟任务中的活动。

Economo MN 等 · 2018-10-31 · published · experiment · 数据 linked。[来源](https://www.nature.com/articles/s41586-018-0642-9)

窗口内实验与技术支持。

标签　小鼠、大脑皮层、运动控制、行为观测、胞外单单位、任务态

本条 ← [r_dandi000006](#r_dandi000006) · described_by · 版本记录的 relatedResource 指向采集研究。。[出处](https://api.dandiarchive.org/api/dandisets/000006/versions/0.220126.1855/)

### p_v1

**[Systematic Integration of Structural and Functional Data into Multi-scale Models of Mouse Primary Visual Cortex](https://doi.org/10.1016/j.neuron.2020.01.040)**　为小鼠 V1 比较多尺度网络表示与实际视觉反应。

Billeh YN 等 · 2020-03-05 · published · model · 数据 unchecked。[来源](https://pubmed.ncbi.nlm.nih.gov/32142648/)

窗口内建模与理论。电子首发，原刊/文献登记 ArticleDate

标签　小鼠、大脑皮层、局部微环路、多区室模型、脉冲网络、感觉编码

### p_bittner

**[Behavioral time scale synaptic plasticity underlies CA1 place fields](https://doi.org/10.1126/science.aan3846)**　将秒级的行为时间尺度可塑性与 CA1 位置场形成对应。

Bittner KC 等 · 未核实 · published · model, experiment · 数据 unchecked。[来源](https://pubmed.ncbi.nlm.nih.gov/28883072/)

首次在线日待核。2017-09-08 为已核实正式刊日，首次在线日未单列。

标签　小鼠、海马、单细胞、突触、突触可塑性、学习记忆

### p_wilson

**[利用双慢变量的快慢变量分离分析新脑皮层神经元Wilson模型的复杂电活动](https://doi.org/10.7498/aps.71.20221416)**　用双慢变量分析区分 Wilson 模型中的簇发机制。

梁艳美、陆博、古华光 · 未核实 · published · theory, model · 数据 not_applicable。[来源](https://wulixb.iphy.ac.cn/article/doi/10.7498/aps.71.20221416?viewType=HTML)

首次在线日待核。2022 年卷期已核实，首次在线日待核

标签　大脑皮层、单细胞、动力系统、离子通道与膜过程

[图 1a–d](#o_wilson_modes) · simulation · 膜电位与放电模式

### p_mainen

**[Influence of dendritic structure on firing pattern in model neocortical neurons](https://doi.org/10.1038/382363a0)**　在相同的离子通道分布下比较不同树突形态能否产生不同发放模式。

Mainen ZF、Sejnowski TJ · 未核实 · published · model · 数据 unchecked。[来源](https://pubmed.ncbi.nlm.nih.gov/8684467/)

早期关联文献。1996 年原刊。首次电子出版日未核实。

标签　多区室模型、树突与轴突、大脑皮层、单细胞、神经元形态

本条 ← [r_modeldb2488](#r_modeldb2488) · implements · 存储库将该 NEURON 模型归于 Mainen 与 Sejnowski 1996。。[出处](https://modeldb.science/2488)

### p_maex

**[Synchronization of Golgi and Granule Cell Firing in a Detailed Network Model of the Cerebellar Granule Cell Layer](https://doi.org/10.1152/jn.1998.80.5.2521)**　复现颗粒层中 Golgi 与颗粒细胞的同步模型并察看后来的空间扩展。

Maex R、De Schutter E · 未核实 · published · model · 数据 unchecked。[来源](https://doi.org/10.1152/jn.1998.80.5.2521)

早期关联文献。1998 年为原刊年份。

标签　小脑、局部微环路、同步、生物物理模型

本条 ← [r_granule_osb](#r_granule_osb) · implements · 当前可定位的仓库版本。论文原始运行所用提交需按文中另核。。[出处](https://github.com/OpenSourceBrain/GranCellLayer)

### p_claar

**[Cortico-thalamo-cortical interactions modulate electrically evoked EEG responses in mice](https://doi.org/10.7554/eLife.84630)**　比较状态和刺激深度对诱发 EEG、皮层及丘脑神经活动的影响。

Claar LD、Rembado I 等 · 2023-06-26 · published · experiment · 数据 linked。[来源](https://elifesciences.org/articles/84630.pdf)

窗口内实验与技术支持。Version of Record，2023-02-09 刊出的是经评阅的预印本。

标签　小鼠、大脑皮层、丘脑、在体、清醒、麻醉、异氟烷、头皮脑电、局部场电位记录、诱发反应

[Figure 7E，左面板](#o_claar_rate_cortex) · measured_here · 基础发放率

[Figure 7E，右面板](#o_claar_rate_thalamus) · measured_here · 基础发放率

本条 ← [p_claar_pre](#p_claar_pre) · preprint_of · 原数据版本指向同研究的 bioRxiv 与 eLife 评阅稿，最终刊期另见正式版。。[出处](https://elifesciences.org/articles/84630.pdf)

本条 ← [r_dandi000458](#r_dandi000458) · archived_observations_for · 同一实验归档，固定版本 24 个文件，包括刺激和状态相关记录。。[出处](https://api.dandiarchive.org/api/dandisets/000458/versions/0.230317.0039/)

### p_claar_pre

**[Cortico-thalamo-cortical interactions modulate electrically evoked EEG responses in mice](https://doi.org/10.1101/2022.07.22.501195)**　查阅同一研究最初预印本及其与正式论文、数据版本的对应。

Claar LD、Rembado I 等 · 2022-07-23 · preprint · experiment · 数据 linked。[来源](https://api.biorxiv.org/details/biorxiv/10.1101/2022.07.22.501195/na/json)

预印本。bioRxiv 第 1 版 2022-07-23，第 3 版是 2022-10-31。

标签　小鼠、大脑皮层、丘脑、诱发反应、头皮脑电

本条 → [p_claar](#p_claar) · preprint_of · 原数据版本指向同研究的 bioRxiv 与 eLife 评阅稿，最终刊期另见正式版。。[出处](https://elifesciences.org/articles/84630.pdf)

### p_hh1952

**[A quantitative description of membrane current and its application to conduction and excitation in nerve](https://doi.org/10.1113/jphysiol.1952.sp004764)**　回查基于电压与离子电导的动作电位和传导模型及其原实验依据。

Hodgkin AL、Huxley AF · 未核实 · published · model, experiment · 数据 unchecked。[来源](https://physoc.onlinelibrary.wiley.com/doi/10.1113/jphysiol.1952.sp004764)

早期关联文献。原刊 1952 年。首次电子发表日未核实。

标签　离子通道与膜过程、霍奇金–赫胥黎模型、生物物理模型、单细胞、树突与轴突、其他无脊椎类

本条 ← [p_sbi](#p_sbi) · uses_model_family · Fig. 3 的 Hodgkin–Huxley 类模型允许对不同膜参数组合做推断，具体方程和采用参数以该图方法为准。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC7581433/)

### p_pmid_28030778

**[Controllability Analysis of the Neural Mass Model with Dynamic Parameters](https://doi.org/10.1162/neco_a_00925)**　用可控性分析判断群体模型哪些动态参数能被外部输入区分。

Liu X 等 · 2016-12-28 · published · theory, model · 数据 unchecked。[来源](https://europepmc.org/article/MED/28030778)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　神经群体、神经群体模型、动力系统

### p_pmid_28380064

**[A neural mass model of cross frequency coupling](https://doi.org/10.1371/journal.pone.0173776)**　为跨频耦合选择神经群体模型及待比较的节律读数。

Chehelcheraghi M 等 · 2017-04-05 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/28380064)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　神经群体、神经群体模型、网络节律、相位耦合

### p_pmid_28987976

**[A new approach to optimal control of conductance-based spiking neurons](https://doi.org/10.1016/j.neunet.2017.08.011)**　比较电导型放电神经元的最优控制目标与可控变量。

Lou X 等 · 2017-09-11 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/28987976)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　单细胞、生物物理模型、动力系统

### p_pmid_28168402

**[Macroscopic neural mass model constructed from a current-based network model of spiking neurons](https://doi.org/10.1007/s00422-017-0710-5)**　检查从电流型脉冲网络推导群体表示时保留哪些动力学。

Umehara H 等 · 2017-02-06 · published · theory, model · 数据 unchecked。[来源](https://europepmc.org/article/MED/28168402)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　神经群体、神经群体模型、脉冲网络

### p_pmid_28101525

**[Untangling Basal Ganglia Network Dynamics and Function: Role of Dopamine Depletion and Inhibition Investigated in a Spiking Network Model](https://doi.org/10.1523/eneuro.0156-16.2016)**　构建基底节多巴胺耗竭与抑制作用的竞争解释。

Lindahl M 等 · 2017-01-12 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/28101525)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　基底节、脉冲网络、疾病扰动、网络节律、局部微环路

### p_pmid_30123121

**[Reproducing Polychronization: A Guide to Maximizing the Reproducibility of Spiking Network Models](https://doi.org/10.3389/fninf.2018.00046)**　检查同一脉冲网络复现时对时序与数值实现的敏感性。

Pauli R 等 · 2018-08-03 · published · method, model · 数据 unchecked。[来源](https://europepmc.org/article/MED/30123121)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　脉冲网络、复现与互操作、局部微环路

### p_pmid_30335761

**[A multi-scale layer-resolved spiking network model of resting-state dynamics in macaque visual cortical areas](https://doi.org/10.1371/journal.pcbi.1006359)**　为猕猴视皮层跨区静息活动选择按层连接的脉冲网络。

Schmidt M 等 · 2018-10-18 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/30335761)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　脑区间网络、大脑皮层、猕猴、脉冲网络、静息

### p_pmid_30211694

**[A neural mass model to predict electrical stimulation evoked responses in human and non-human primate brain](https://doi.org/10.1088/1741-2552/aae136)**　设计电刺激诱发响应与神经群体输出之间的比较。

Basu I 等 · 2018-09-13 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/30211694)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　神经群体、神经群体模型、人类、诱发反应、神经调控

### p_pmid_31323031

**[Propagation of orientation selectivity in a spiking network model of layered primary visual cortex](https://doi.org/10.1371/journal.pcbi.1007080)**　比较层间脉冲传播如何影响视觉皮层的方向选择性。

Merkt B 等 · 2019-07-19 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/31323031)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　局部微环路、大脑皮层、脉冲网络、感觉编码、编码模型

### p_pmid_31396055

**[GABA Regulation of Burst Firing in Hippocampal Astrocyte Neural Circuit: A Biophysical Model](https://doi.org/10.3389/fncel.2019.00335)**　建立海马胶质环路中 GABA 调节与簇发的模型比较。

Liu J 等 · 2019-07-23 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/31396055)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　海马、胶质与神经元、生物物理模型、网络节律

### p_pmid_33320855

**[Exact neural mass model for synaptic-based working memory](https://doi.org/10.1371/journal.pcbi.1008533)**　研究突触状态怎样在群体方程中支持工作记忆。

Taher H 等 · 2020-12-15 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/33320855)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　神经群体、神经群体模型、突触、学习记忆、动力系统

### p_pmid_32559204

**[Spiking network optimized for word recognition in noise predicts auditory system hierarchy](https://doi.org/10.1371/journal.pcbi.1007558)**　用有噪声的词识别任务检验听觉层级脉冲表示。

Khatami F 等 · 2020-06-19 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/32559204)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　脉冲网络、感觉编码、编码模型

### p_pmid_32009922

**[Evaluation of Resting Spatio-Temporal Dynamics of a Neural Mass Model Using Resting fMRI Connectivity and EEG Microstates](https://doi.org/10.3389/fncom.2019.00091)**　设计静息血氧连接和脑电微状态对同一群体模型的不同约束。

Endo H 等 · 2020-01-17 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/32009922)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　神经群体、神经群体模型、血氧信号、头皮脑电、静息、观测信号生成

### p_pmid_34157643

**[A novel density-based neural mass model for simulating neuronal network dynamics with conductance-based synapses and membrane current adaptation](https://doi.org/10.1016/j.neunet.2021.06.009)**　比较电导型突触及膜电流适应如何进入群体动力学。

Huang CH 等 · 2021-06-11 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/34157643)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　神经群体、神经群体模型、放电适应、突触、生物物理模型

### p_pmid_34539355

**[Patient-Specific Network Connectivity Combined With a Next Generation Neural Mass Model to Test Clinical Hypothesis of Seizure Propagation](https://doi.org/10.3389/fnsys.2021.675272)**　检验个体化连接对癫痫传播模型的约束。

Gerster M 等 · 2021-09-01 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/34539355)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　脑区间网络、神经群体模型、连接与拓扑、疾病扰动

### p_pmid_31295136

**[Delayed Feedback-Based Suppression of Pathological Oscillations in a Neural Mass Model](https://doi.org/10.1109/tcyb.2019.2923317)**　评估延迟反馈对模型病理振荡的影响。

Liu C 等 · 2021-10-12 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/31295136)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　神经群体、神经群体模型、网络节律、闭环控制

### p_pmid_36454267

**[Comparison between an exact and a heuristic neural mass model with second-order synapses](https://doi.org/10.1007/s00422-022-00952-7)**　用二阶突触的精确与近似群体模型比较相同输入下的动态。

Clusella P 等 · 2022-12-01 · published · theory, model · 数据 unchecked。[来源](https://europepmc.org/article/MED/36454267)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　神经群体、神经群体模型、突触、动力系统

### p_pmid_35859800

**[Fast Simulation of a Multi-Area Spiking Network Model of Macaque Cortex on an MPI-GPU Cluster](https://doi.org/10.3389/fninf.2022.883333)**　估算猕猴多脑区脉冲网络的并行计算成本。

Tiddia G 等 · 2022-07-04 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/35859800)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　脑区间网络、大脑皮层、猕猴、脉冲网络、数值方法

### p_pmid_35380537

**[Putting the theory into 'burstlet theory' with a biophysical model of burstlets and bursts in the respiratory preBötzinger complex](https://doi.org/10.7554/elife.75713)**　比较前包钦格复合体小簇发与完整簇发的候选生成机制。

Phillips RS 等 · 2022-04-05 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/35380537)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　脑干、局部微环路、生物物理模型、网络节律

### p_pmid_37558704

**[Long- and short-term history effects in a spiking network model of statistical learning](https://doi.org/10.1038/s41598-023-39108-3)**　区分统计学习中长时程与短时程的输入历史效应。

Maes A 等 · 2023-08-09 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/37558704)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　局部微环路、脉冲网络、学习记忆

### p_pmid_38045871

**[A Novel Biophysical Model for the Generation of Sharp Wave Ripples in CA1 Hippocampus](https://doi.org/10.1109/tcsii.2023.3262207)**　为海马 CA1 尖波涟漪的生成提出可比较的回路机制。

Latimer B 等 · 2023-03-27 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/38045871)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　海马、局部微环路、生物物理模型、网络节律

### p_pmid_36775081

**[A physical neural mass model framework for the analysis of oscillatory generators from laminar electrophysiological recordings](https://doi.org/10.1016/j.neuroimage.2023.119938)**　把分层电生理记录对应到产生振荡的群体动力学。

Sanchez-Todo R 等 · 2023-02-11 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/36775081)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　神经群体、神经群体模型、大脑皮层、局部场电位记录、观测信号生成

### p_pmid_39285002

**[Automated customization of large-scale spiking network models to neuronal population activity](https://doi.org/10.1038/s43588-024-00688-3)**　基于群体活动选择大规模脉冲模型待定参数。

Wu S 等 · 2024-09-16 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/39285002)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　脉冲网络、神经群体、数据驱动建模

### p_pmid_38967732

**[Incorporating slow NMDA-type receptors with nonlinear voltage-dependent magnesium block in a next generation neural mass model: derivation and dynamics](https://doi.org/10.1007/s10827-024-00874-2)**　检验 NMDA 电压依赖性和慢时程能否改变群体动力学。

Sheheitli H 等 · 2024-07-05 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/38967732)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　突触、神经群体、神经群体模型、生物物理模型

### p_pmid_39178894

**[Nonlinear model predictive control of a conductance-based neuron model via data-driven forecasting](https://doi.org/10.1088/1741-2552/ad731f)**　设计电导型单细胞的预测控制与反馈比较。

Fehrman C 等 · 2024-09-17 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/39178894)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　单细胞、生物物理模型、闭环控制、数据驱动建模

### p_pmid_39590510

**[Basolateral amygdala oscillations enable fear learning in a biophysical model](https://doi.org/10.7554/elife.89519)**　比较基底外侧杏仁核振荡与恐惧学习的机制假说。

Cattani A 等 · 2024-11-26 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/39590510)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　局部微环路、生物物理模型、学习记忆、网络节律

### p_pmid_40880620

**[The improved thalamo-cortical spiking network model of deep brain stimulation](https://doi.org/10.3389/fncom.2025.1662598)**　设计脑深部刺激时丘脑与皮层脉冲网络的比较。

Farokhniaee A 等 · 2025-08-13 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/40880620)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　丘脑、大脑皮层、脑区间网络、脉冲网络、神经调控

### p_pmid_41142910

**[Linking ion channel gene expression to neuronal firing patterns through a statistical-biophysical model](https://doi.org/10.1016/j.patter.2025.101390)**　检验离子通道表达与发放模式之间的统计和生物物理映射。

Huang W 等 · 2025-10-10 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/41142910)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　离子通道与膜过程、单细胞、混合建模、概率与统计生成模型、发放率

### p_pmid_40694892

**[Kernel-based LFP estimation in detailed large-scale spiking network model of mouse visual cortex](https://doi.org/10.1016/j.neunet.2025.107866)**　比较核函数近似能否从小鼠视皮层脉冲网络生成场电位。

Meneghetti N 等 · 2025-07-12 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/40694892)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　大脑皮层、小鼠、局部场电位记录、观测信号生成、脉冲网络

### p_pmid_40845564

**[A spiking network model of the cerebellum for predicting movements with diverse complex spikes](https://doi.org/10.1016/j.neunet.2025.107962)**　构建小脑复杂尖峰多样性对运动预测影响的比较。

Mitsuhashi T 等 · 2025-08-13 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/40845564)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　小脑、局部微环路、脉冲网络、运动控制

### p_pmid_42939370

**[Decodable Spectral Structure of Input Noise in a Layered Cortical Spiking Network](https://doi.org/10.3390/brainsci16101117)**　检验分层脉冲网络的输出是否保留输入噪声的频谱结构。

Treviño M 等 · 2026-10-16 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/42939370)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　局部微环路、大脑皮层、脉冲网络、解码模型、功率谱

### p_pmid_42572094

**[A spatially discretized convolutional neural mass model for studying meso-scale spatio-temporal transformations in the rat hippocampus](https://doi.org/10.1007/s10827-026-00950-9)**　为大鼠海马时空变换选择空间离散群体模型。

Pham DJ 等 · 2026-08-10 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/42572094)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　海马、大鼠、神经群体模型、神经群体

### p_pmid_43086505

**[A whole-brain neural mass model incorporating astrocyte calcium dynamics for simulating tDCS-induced EEG modulation](https://doi.org/10.1007/s00422-026-01081-1)**　选择含胶质钙状态的全脑模型，核对模拟刺激如何映射到 EEG。

Saidi M 等 · 2026-11-25 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/43086505)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　全脑模型、神经群体模型、胶质与神经元、钙成像、头皮脑电、神经调控

### p_pmid_42371975

**[Neuronal excitability and parameter variability in the Hodgkin-Huxley model](https://doi.org/10.1371/journal.pcbi.1014458)**　检查 Hodgkin–Huxley 参数变化与兴奋性的多解关系。

Korngreen A. 等 · 2026-06-29 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/42371975)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　离子通道与膜过程、单细胞、霍奇金–赫胥黎模型、生物物理模型、兴奋性

### p_pmid_43039696

**[Coincidence detection in aspiny interneuron dendrites](https://doi.org/10.1523/eneuro.0156-26.2026)**　设计无棘中间神经元树突巧合检测的输入时序比较。

Griesius S 等 · 2026-11-16 · published · experiment, model · 数据 unchecked。[来源](https://europepmc.org/article/MED/43039696)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　树突与轴突、单细胞、突触

### p_pmid_42126468

**[A biophysically grounded model of glutamatergic synaptic transmission integrating glutamate transport, receptor kinetics, and electrotonic effects](https://doi.org/10.1007/s10827-026-00935-8)**　区分谷氨酸转运、受体时程及电紧张衰减对突触读数的影响。

Chizhov AV 等 · 2026-05-13 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/42126468)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　树突与轴突、突触、生物物理模型、突触传递

### p_pmid_43057562

**[A microcircuit model of astrocytic potassium buffering and neural synchronization](https://doi.org/10.1016/j.brainres.2026.150630)**　比较星形胶质钾缓冲改变神经元同步的模型预测。

Cafiso M 等 · 2026-11-19 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/43057562)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　局部微环路、胶质与神经元、同步

### p_pmid_42168461

**[Optimization of connectome weights for a neural network model generating both forward and backward locomotion in C. elegans](https://doi.org/10.1038/s41598-026-54384-5)**　查找以线虫连接权重同时约束正向和反向运动的模型。

Chung T 等 · 2026-05-21 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/42168461)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　线虫、连接组、连接与拓扑、运动控制、全中枢神经系统、神经群体

### p_pmid_42380381

**[Computational Model for Synthesizing Auditory Brainstem Responses to Assess Neuronal Alterations in Aging and Autistic Animal Models](https://doi.org/10.1007/s10162-026-01060-0)**　为听觉脑干诱发响应选择从神经活动到记录信号的转换。

Li BZ 等 · 2026-06-30 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/42380381)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　脑干、感觉编码、诱发反应、观测信号生成、衰老

### p_pmid_41306652

**[Ionic mechanisms underlying bistability in spinal motoneurons: insights from a computational model](https://doi.org/10.3389/fncel.2025.1710893)**　用脊髓运动神经元模型区分稳态转换与离子电流假说。

Molkov YI 等 · 2025-11-11 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/41306652)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　脊髓、离子通道与膜过程、单细胞、生物物理模型、运动控制

### p_pmid_42476912

**[Genetic Targeting and Conductance-Based Modeling Reveal Novel Diversity within Mouse Type II Spiral Ganglion Neurons](https://doi.org/10.1523/jneurosci.2254-25.2026)**　核对耳蜗 II 型螺旋神经节细胞的电导模型与细胞亚型。

Nowak N 等 · 2026-08-19 · published · experiment, model · 数据 unchecked。[来源](https://europepmc.org/article/MED/42476912)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　小鼠、耳蜗、单细胞、生物物理模型、兴奋性

### p_pmid_41056431

**[Computational modeling of speed microcircuits in larval zebrafish spinal cord with SiliFish](https://doi.org/10.1152/jn.00393.2024)**　为幼体斑马鱼运动速度选择脊髓微环路与相应读数。

Topcu E 等 · 2025-10-07 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/41056431)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　斑马鱼、鱼类、脊髓、局部微环路、运动控制

### p_pmid_41920737

**[Decoding intended speech with an intracortical brain-computer interface in a person with long-standing anarthria and locked-in syndrome](https://doi.org/10.1016/j.celrep.2026.117162)**　为有明确生物记录的语言解码选择皮层信号与行为输出。

Jude JJ 等 · 2026-03-30 · published · model, experiment · 数据 unchecked。[来源](https://europepmc.org/article/MED/41920737)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　人类、大脑皮层、脑机接口、解码模型

### p_pmid_43022429

**[Connectome analysis reveals brain-wide visual processing in Drosophila](https://doi.org/10.1016/j.isci.2026.118057)**　通过果蝇连接组定位视觉处理模型的候选通路。

Kim SY 等 · 2026-11-02 · published · experiment, data · 数据 unchecked。[来源](https://europepmc.org/article/MED/43022429)

窗口内实验与技术支持。Europe PMC electronicPublicationDate

标签　果蝇、昆虫、全中枢神经系统、连接组、感觉编码

### p_pmid_42875514

**[Symmetries and continuous attractors in disordered neural circuits](https://doi.org/10.1038/s41593-026-02452-4)**　检验连续吸引状态在无序神经回路中的理论条件。

Clark DG 等 · 2026-10-14 · published · theory, model · 数据 unchecked。[来源](https://europepmc.org/article/MED/42875514)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　局部微环路、动力系统、概率与统计生成模型

### p_pmid_41093008

**[Modeling spike frequency adaptation through higher-order fractional leaky integrate and fire model](https://doi.org/10.1016/j.mbs.2025.109548)**　将高阶分数阶漏积分发放模型作为适应动力学的替代解释。

Vats Y 等 · 2025-10-13 · published · model · 数据 unchecked。[来源](https://europepmc.org/article/MED/41093008)

窗口内建模与理论。Europe PMC electronicPublicationDate

标签　单细胞、点神经元、放电适应、发放率

### p_breadth_zheng2018

**[A Complete Electron Microscopy Volume of the Brain of Adult Drosophila melanogaster](https://pmc.ncbi.nlm.nih.gov/articles/PMC6063995/)**　用原始成年雌果蝇脑电镜体数据核对轴树、突触位置与切片覆盖。

Zhihao Zheng, J. Scott Lauritzen, Eric Perlman, Camenzind G. Robinson, Matthew Nichols, Daniel Milkie, Omar Torrens, John Price, Corey B. Fisher, Nadiya Sharifi, Steven A. Calle-Schuler, Lucia Kmecova, Iqbal J. Ali, Bill Karsh, Eric T. Trautman, John A. Bogovic, Philipp Hanslovsky, Gregory S. X. E. Jefferis, Michael Kazhdan, Khaled Khairy, Stephan Saalfeld, Richard D. Fetter, Davi D. Bock · 2018-07-19 · published · experiment, data, method · 数据 linked。[来源](https://pubmed.ncbi.nlm.nih.gov/30033368/)

窗口内实验与技术支持。

标签　果蝇、电子显微成像、全脑模型、神经元形态、昆虫

[Results, Imaging the entire adult fly brain；Figure 1A–C](#o_breadth_fafb_sections) · measured_here · 成功成像的切片比例

本条 → [r_breadth_fafb_image](#r_breadth_fafb_image) · deposited_image_volume · 原始电镜成像组发布的同一成年雌蝇脑；云端 v14 的元数据描述已对齐图像体。。[出处](https://www.janelia.org/open-science/complete-fly-brain-image)

本条 ← [p_breadth_dorkenwald2024](#p_breadth_dorkenwald2024) · reanalyzes_same_specimen · 2024 年工作沿用 2018 年原始电镜体数据，增加分割、校对与突触重建。。[出处](https://www.nature.com/articles/s41586-024-07558-y)

### p_breadth_dorkenwald2024

**[Neuronal wiring diagram of an adult brain](https://www.nature.com/articles/s41586-024-07558-y)**　用人工校对的神经元和化学突触重建约束解剖连边，再另行估计功能权重。

Sven Dorkenwald, Arie Matsliah, Amy R. Sterling, Philipp Schlegel, Szi-chieh Yu, Claire E. McKellar, Albert Lin, Marta Costa, Katharina Eichler, Yijie Yin, Will Silversmith, Casey Schneider-Mizell, Chris S. Jordan, Derrick Brittain, Akhilesh Halageri, Kai Kuehner, Oluwaseun Ogedengbe, Ryan Morey, Jay Gager, Krzysztof Kruk, Eric Perlman, Runzhe Yang, David Deutsch, Doug Bland, Marissa Sorek, Ran Lu, Thomas Macrina, Kisuk Lee, J. Alexander Bae, Shang Mu, Barak Nehoran, Eric Mitchell, Sergiy Popovych, Jingpeng Wu, Zhen Jia, Manuel A. Castro, Nico Kemnitz, Dodam Ih, Alexander Shakeel Bates, Nils Eckstein, Jan Funke, Forrest Collman, Davi D. Bock, Gregory S. X. E. Jefferis, H. Sebastian Seung, Mala Murthy, The FlyWire Consortium · 2024-10-02 · published · experiment, data · 数据 linked。[来源](https://www.nature.com/articles/s41586-024-07558-y)

窗口内实验与技术支持。

标签　果蝇、连接组、突触、全脑模型、昆虫

[Results, The FlyWire connectome；Figure 1a 与 Methods, Synaptic connections](#o_breadth_flywire_synapses) · inferred · 139,255 个重建神经元之间的化学突触数

本条 → [p_breadth_zheng2018](#p_breadth_zheng2018) · reanalyzes_same_specimen · 2024 年工作沿用 2018 年原始电镜体数据，增加分割、校对与突触重建。。[出处](https://www.nature.com/articles/s41586-024-07558-y)

本条 → [r_breadth_flywire783](#r_breadth_flywire783) · provides_processed_data · 数据发布说明指向论文的 Synaptic connections 方法。。[出处](https://zenodo.org/records/10676866)

### p_breadth_palieri2024

**[The preoptic area and dorsal habenula jointly support homeostatic navigation in larval zebrafish](https://pmc.ncbi.nlm.nih.gov/articles/PMC10849091/)**　用有空间对照的脑区消融、温度梯度与转向序列比较两种感觉运动机制。

Virginia Palieri, Emanuele Paoli, You Kure Wu, Martin Haesemeyer, Ilona C. Grunwald Kadow, Ruben Portugues · 2024-01-10 · published · experiment, data · 数据 linked。[来源](https://www.cell.com/article/S096098222301686X/pdf)

窗口内实验与技术支持。

标签　斑马鱼、视前区、缰核、温度刺激或控制、感觉运动整合、实验扰动、鱼类

[Results, Larval zebrafish perform homeostatic navigation；Figure 1A–B，Figure S1D–F](#o_breadth_fish_temp) · measured_here · 占据位置对应的偏好温度

[Results, Figure 5A–C；Figure S6D–E；STAR Methods](#o_breadth_fish_poa) · measured_here · 感觉条件对转向概率调制的方向

本条 → [r_breadth_fish_thermal](#r_breadth_fish_thermal) · provides_processed_data · 存档说明链接同一工作预印本，发表论文说明同一 DOI 的数据可用性。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC10849091/)

### p_breadth_hagen2018

**[Multimodal Modeling of Neural Network Activity: Computing LFP, ECoG, EEG, and MEG Signals With LFPy 2.0](https://www.frontiersin.org/journals/neuroinformatics/articles/10.3389/fninf.2018.00092/full)**　将多区室膜电流经几何与体积传导模型转换成场电位，可比较同一活动在不同电极上的读数。

Espen Hagen, Solveig Næss, Torbjørn V. Ness, Gaute T. Einevoll · 2018-12-18 · published · model, method, software · 数据 not_applicable。[来源](https://www.frontiersin.org/journals/neuroinformatics/articles/10.3389/fninf.2018.00092/full)

窗口内建模与理论。

标签　多区室模型、观测信号生成、头皮脑电、局部场电位记录、磁场或脑磁、软件实现

[Results §3.2.5；Figure 5E–G；Methods §2.5](#o_breadth_lfpy_eeg) · simulation · 偶极正上方的头皮电势波动量级

本条 → [r_breadth_lfpy200](#r_breadth_lfpy200) · provides_model_code · 论文数据可用性段指向这份冻结的软件版本。。[出处](https://www.frontiersin.org/journals/neuroinformatics/articles/10.3389/fninf.2018.00092/full)

### p_breadth_churchland2012

**[Neural population dynamics during reaching](https://www.nature.com/articles/nature11129)**　用运动准备至动作初期的群体轨迹约束运动皮层动力学，也是 DANDI 已保存的两只猕猴部分记录的实验出处。

Mark M. Churchland, John P. Cunningham, Matthew T. Kaufman, Justin D. Foster, Paul Nuyujukian, Stephen I. Ryu, Krishna V. Shenoy · 2012-06-03 · published · experiment, method · 数据 linked。[来源](https://www.nature.com/articles/nature11129)

早期关联文献。

标签　早期关联来源、运动皮层、神经群体、伸手到达任务、大脑皮层

[Figure 3；main text；Methods, Electrophysiological recordings](#o_breadth_rotation_variance) · measured_here · 第一 jPCA 平面解释的总方差

本条 ← [r_breadth_dandi000070](#r_breadth_dandi000070) · is_described_by · DANDI 的 relatedResource 明确给出论文 DOI。文件表有 J 2009-09-18 及 N 2010-09-23，与论文 Methods 的阵列会话日期相符。。[出处](https://api.dandiarchive.org/api/dandisets/000070/versions/0.261122.2046/)

本条 ← [p_breadth_elsayed2017](#p_breadth_elsayed2017) · reanalyzes_published_recordings · 2017 方法节说明沿用原研究 J、N、A、B 的运动皮层记录，构造新的统计对照。。[出处](https://stat.columbia.edu/~cunningham/pdf/ElsayedNN2017.pdf)

### p_breadth_elsayed2017

**[Structure in neural population recordings: an expected byproduct of simpler phenomena?](https://www.nature.com/articles/nn.4617)**　用保持时间、神经元及任务条件协方差的替代数据，检验同批伸手记录中的群体动力学是否超出这些特征所能解释的范围。

Gamaleldin F. Elsayed, John P. Cunningham · 2017-08-07 · published · method, theory · 数据 linked。[来源](https://stat.columbia.edu/~cunningham/pdf/ElsayedNN2017.pdf)

窗口内建模与理论。

标签　神经群体、替代数据分析、零模型、协方差

[Figure 6a；Online Methods, Motor cortex data](#o_breadth_surrogate_rotation) · inferred · 实测与替代数据的模型拟合差异，单尾检验

本条 → [p_breadth_churchland2012](#p_breadth_churchland2012) · reanalyzes_published_recordings · 2017 方法节说明沿用原研究 J、N、A、B 的运动皮层记录，构造新的统计对照。。[出处](https://stat.columbia.edu/~cunningham/pdf/ElsayedNN2017.pdf)

### p_breadth_mizuseki2014

**[Neurosharing: large-scale data sets (spike, LFP) recorded from the hippocampal-entorhinal system in behaving rats](https://f1000research.com/articles/3-98/v1)**　用于解释 CRCNS hc-3 的动物、会话、记录模态与文件构成；期刊 v1 为首次公开版本。

Kenji Mizuseki, Kamran Diba, Eva Pastalkova, Jeff Teeters, Anton Sirota, György Buzsáki · 2014-04-30 · published · experiment, data · 数据 linked。[来源](https://f1000research.com/articles/3-98/v1)

早期关联文献。

标签　早期关联来源、大鼠、海马、内嗅皮层、数据集描述、大脑皮层

[Data description；CRCNS hc-3 About, Overview](#o_breadth_hc3_size) · measured_here · 记录集合内所述神经元数量

本条 → [r_breadth_crcns_hc3](#r_breadth_crcns_hc3) · describes_dataset · 期刊首版正文直接链接同一数据 DOI，数据库亦列该文之后的 v2。。[出处](https://f1000research.com/articles/3-98/v1)

### p_cell_mensi

**[Parameter extraction and classification of three cortical neuron types reveals two distinct adaptation mechanisms](https://infoscience.epfl.ch/bitstreams/6ce42f90-73cc-42b3-a237-70f3bd4688a5/download?download=1)**　用同一细胞的阈下电压和脉冲时序检验含适应电流与动态阈值的点模型，原始图中可分别定位实测和模型曲线。

Skander Mensi 等 · 2011-12-07 · published · model, experiment, method · 数据 not_located。[来源](https://pubmed.ncbi.nlm.nih.gov/22157113/)

早期关联文献。

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、放电间隔、大脑皮层、小鼠、离体、波动电流、有效动力学模型、动作电位阈值

[Fig. 4A 输入；Fig. 4B 黑线为实测胞体电压，黑色点栅为记录的脉冲。](#o_cell_mensi_fig4_record) · measured_here · 实测胞体膜电位、动作电位发生时刻

[Fig. 4B 红线和红色点栅，输入见 Fig. 4A。](#o_cell_mensi_fig4_model) · simulation · 模型膜电位和预测脉冲发生时刻

[Fig. 5A–C 三类模型的初始与稳态频率-电流曲线，Fig. 5D–F 为对应阶跃模拟。](#o_cell_mensi_fig5_steps) · simulation · 初始与稳态放电频率

本条 → [r_cell_mensi_code](#r_cell_mensi_code) · author_model · ModelDB 将该实现归于 Mensi。包内示例使用模型生成的替代数据。。[出处](https://modeldb.science/143148)

### p_cell_velden

**[Altered dendritic complexity affects firing properties of cortical layer 2/3 pyramidal neurons in mice lacking the 5-HT3A receptor](https://journals.physiology.org/doi/full/10.1152/jn.00829.2011)**　用阶跃内的瞬时频率、适应时间和稳态频率比较小鼠体感皮层锥体细胞的基因型差异，可作协议匹配的阶跃实测参照。

Luuk van der Velden 等 · 2012-06-13 · published · experiment, model · 数据 not_located。[来源](https://pubmed.ncbi.nlm.nih.gov/22696545/)

早期关联文献。

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、放电间隔、大脑皮层、小鼠、离体、阶跃电流、锥体细胞、神经元形态

[Fig. 2B 及紧随其后的 Results 段，瞬时频率轨迹和拟合时间常数。](#o_cell_velden_tau) · published_aggregate · 阶跃内放电频率适应时间常数

[Fig. 2C 及正文给出的稳态放电频率。](#o_cell_velden_steady) · published_aggregate · 单指数拟合的稳态放电频率

### p_cell_wang

**[Firing Frequency Maxima of Fast-Spiking Neurons in Human, Monkey, and Mouse Neocortex](https://pmc.ncbi.nlm.nih.gov/articles/PMC5067378/)**　提供人手术皮层快放电细胞对阶跃的实际反应及作者定义的适应比，可检验细胞亚群差异。

Bo Wang 等 · 2016-10-18 · published · experiment · 数据 not_located。[来源](https://pubmed.ncbi.nlm.nih.gov/27803650/)

早期关联文献。

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、放电间隔、大脑皮层、人类、小鼠、离体、阶跃电流、快发放细胞

[Fig. 1A–C 给出样例记录，Fig. 1D 和 Human neocortical FS neurons 结果段给出适应比组间比较。](#o_cell_wang_human_ratio) · published_aggregate · 原作者的适应比（adaptation ratio）

本条 → [r_cell_allen_human_feature](#r_cell_allen_human_feature) · external_comparator · 两者均有人类胞体电流钳记录；组织区域和细胞亚型不同，且已发表适应比须先核实定义，不能合并为同一个量或声称来自同批标本。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC5067378/)

### p_cell_teeter

**[Generalized leaky integrate-and-fire models classify multiple neuron types](https://www.nature.com/articles/s41467-017-02717-4)**　在同一细胞重复的未用于拟合的噪声波形上比较实测和五种广义点模型的放电时序，并提供细胞、刺激和作图实现的对应关系。

Corinne Teeter 等 · 2018-02-19 · published · model, experiment, data, method · 数据 linked。[来源](https://www.nature.com/articles/s41467-017-02717-4)

窗口内建模与理论。

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、大脑皮层、小鼠、离体、波动电流、点神经元、动作电位阈值

[Fig. 4a 黑色实测脉冲点栅；Fig. 1b 生物电压痕迹及作者作图程序可辨示例细胞。](#o_cell_teeter_fig4_record) · measured_here · 重复注流时的实测脉冲发生时刻

[Fig. 4a 彩色 GLIF1–5 脉冲点栅，与黑色实测分开记录。](#o_cell_teeter_fig4_model) · simulation · GLIF1–5 在留出波形上预测的脉冲时刻

本条 → [r_cell_teeter_analysis](#r_cell_teeter_analysis) · author_analysis · Allen Institute 官方仓库存放论文作图与分析实现。。[出处](https://github.com/AllenInstitute/GLIF_Teeter_et_al_2018/tree/dcb232354b1a5c3e348d163cb479ae2ee10c564d)

本条 → [p_cell_gouwens](#p_cell_gouwens) · shares_named_specimens · 已按标本号确认至少两个细胞重叠。跨论文使用前须按 specimen_id 与 donor_id 分组。。[出处](https://github.com/AllenInstitute/GLIF_Teeter_et_al_2018/blob/dcb232354b1a5c3e348d163cb479ae2ee10c564d/MTfig_1b/make_and_save_model_data.py)

### p_cell_gouwens

**[Classification of electrophysiological and morphological neuron types in the mouse visual cortex](https://www.nature.com/articles/s41593-019-0417-0)**　小鼠视觉皮层的细胞分类研究公开单细胞标识，可回到同一标本的长阶跃波形和适应特征，并辨认与建模论文重复使用的细胞。

Nathan W. Gouwens 等 · 2019-06-17 · published · experiment, data, method · 数据 linked。[来源](https://www.nature.com/articles/s41593-019-0417-0)

窗口内实验与技术支持。

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、放电间隔、大脑皮层、小鼠、离体、阶跃电流、细胞类型分类

[Supplementary Dataset 3，Data 表第 7 行，标本 313861794；指标来自关联的 Allen EphysFeature 396463405，并依原始 NWB 的 Sweep_35 脉冲时刻复算。](#o_cell_gouwens_mouse_index) · published_aggregate · Allen adaptation，相邻放电间隔归一化差的均值

本条 → [r_cell_gouwens_table](#r_cell_gouwens_table) · publishes · 补充数据集以 specimen_id 登记电生理标本。。[出处](https://www.nature.com/articles/s41593-019-0417-0)

本条 ← [p_cell_teeter](#p_cell_teeter) · shares_named_specimens · 已按标本号确认至少两个细胞重叠。跨论文使用前须按 specimen_id 与 donor_id 分组。。[出处](https://github.com/AllenInstitute/GLIF_Teeter_et_al_2018/blob/dcb232354b1a5c3e348d163cb479ae2ee10c564d/MTfig_1b/make_and_save_model_data.py)

### p_bajwa2025

**[A repeated awakening study exploring the capacity of complexity measures to capture dreaming during propofol sedation](https://www.nature.com/articles/s41598-025-12695-z)**　给出闭眼/睁眼清醒和丙泊酚深镇静期间的自发 EEG、可唤醒标准及复杂度比较。

['Imad J. Bajwa', 'Andre S. Nilsen', 'René Skukies', 'Arnfinn Aamodt', 'Gernot Ernst', 'Johan F. Storm', 'Bjørn E. Juel'] · 2025-09-24 · published · experiment · 数据 linked。[来源](https://api.crossref.org/works/10.1038/s41598-025-12695-z)

窗口内实验与技术支持。

标签　清醒、镇静、网络节律、头皮脑电、人类、在体、神经群体、大脑皮层、丙泊酚、静息

[Results：Differences in measures between wakefulness and sedation；Table 4；方法及补充 Fig. S3](#o_bajwa_lzc) · measured_here · 单导 Lempel–Ziv 复杂度（LZc）的状态均值与标准差

[Figure 2b 与 Results 中深镇静内报告类别比较，分组见 Table 3。](#o_bajwa_experience) · measured_here · 唤醒前单导 Lempel–Ziv 复杂度与体验报告类别的关联

本条 → [o_bajwa_lzc](#o_bajwa_lzc) · reports_measurement · Table 4 为配对检验，正文列状态均值、标准差及分析单位。。[出处](https://www.nature.com/articles/s41598-025-12695-z)

本条 → [r_bajwa_openneuro](#r_bajwa_openneuro) · deposits_raw_data · 论文 Data availability 明列固定版 DOI。。[出处](https://www.nature.com/articles/s41598-025-12695-z)

### p_purdon2013

**[Electroencephalogram signatures of loss and recovery of consciousness from propofol](https://pmc.ncbi.nlm.nih.gov/articles/PMC3607036/)**　提供人类闭眼听觉反应任务中，渐进丙泊酚诱导与苏醒的个体行为定义及额部频谱参照。

['Patrick L. Purdon', 'Eric T. Pierce', 'Eran A. Mukamel', 'Michael J. Prerau', 'John L. Walsh', 'Kin Foon K. Wong', 'Andres F. Salazar-Gomez', 'Priscilla G. Harrell', 'Aaron L. Sampson', 'Aylin Cimenser', 'ShiNung Ching', 'Nancy J. Kopell', 'Casie Tavares-Stoeckel', 'Kathleen Habeeb', 'Rebecca Merhar', 'Emery N. Brown'] · 2013-03-04 · published · experiment · 数据 linked。[来源](https://api.crossref.org/works/10.1073/pnas.1221180110)

早期关联文献。

标签　清醒、麻醉、网络节律、头皮脑电、功率谱、人类、在体、神经群体、大脑皮层、丙泊酚、失去反应

[Fig. 1及方法的状态判定；Fig. 2B–D 的行为对齐频谱与头皮分布](#o_purdon_frontal) · measured_here · 相对于先前清醒频谱的功率变化及其头皮分布

[Fig. 3A 额部频谱中位数和四分位带宽；Results：time course of the traveling peak](#o_purdon_peak) · measured_here · 2–40 Hz 中位频率；第 75 与第 25 百分位之差

本条 → [o_purdon_frontal](#o_purdon_frontal) · reports_measurement · 原文 Fig. 2B–D。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC3607036/)

本条 → [o_purdon_peak](#o_purdon_peak) · reports_measurement · 原文 Fig. 3A；同批受试者。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC3607036/)

本条 ← [r_purdon_dandi](#r_purdon_dandi) · references_acquisition_protocol · DANDI 引用该论文的十人实验设计；固定版清单只有一份记录，个体对应未独立证实。。[出处](https://api.dandiarchive.org/api/dandisets/001285/versions/0.250110.2125/)

### p_xiong2024

**[Propofol-mediated loss of consciousness disrupts predictive routing and local field phase modulation of neural activity](https://pmc.ncbi.nlm.nih.gov/articles/PMC11494327/)**　提供同一猕猴清醒和丙泊酚反应丧失时，听觉皮层与额叶对意外声音的局部场电位时频比较。

['Yihan (Sophy) Xiong', 'Jacob A. Donoghue', 'Mikael Lundqvist', 'Meredith Mahnke', 'Alex James Major', 'Emery N. Brown', 'Earl K. Miller', 'André M. Bastos'] · 2024-10-07 · published · experiment · 数据 linked。[来源](https://api.crossref.org/works/10.1073/pnas.2315160121)

窗口内实验与技术支持。

标签　清醒、麻醉、网络节律、局部场电位记录、功率谱、猕猴、在体、神经群体、大脑皮层、丙泊酚、听觉任务

[Fig. 3A–C，Results 的 Tpt 局部 oddball 频率峰](#o_xiong_tpt_peak) · measured_here · Tpt 局部 oddball 相对 regular 的功率变化峰之中心频率

本条 → [o_xiong_tpt_peak](#o_xiong_tpt_peak) · reports_measurement · 原文 Fig. 3A–C。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC11494327/)

本条 → [r_xiong_tfr](#r_xiong_tfr) · deposits_processed_data · 原文 Data, Materials, and Software Availability 及参考文献 68 明示 Figshare 标识。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC11494327/)

### p_cecchetto2021

**[Simultaneous Two-Photon Voltage or Calcium Imaging and Multi-Channel Local Field Potential Recordings in Barrel Cortex of Awake and Anesthetized Mice](https://www.frontiersin.org/journals/neuroscience/articles/10.3389/fnins.2021.741279/full)**　区分小鼠桶状皮层清醒静止、跑动及轻度异氟烷麻醉，提供层内电位与皮层表面电位的时域对照。

['Claudia Cecchetto', 'Stefano Vassanelli', 'Bernd Kuhn'] · 2021-11-11 · published · experiment, method · 数据 linked。[来源](https://www.frontiersin.org/journals/neuroscience/articles/10.3389/fnins.2021.741279/full)

窗口内实验与技术支持。

标签　清醒、麻醉、局部场电位记录、皮层电图、小鼠、在体、神经群体、大脑皮层、感觉任务、异氟烷

[Fig. 3D–F、4D–F、5D–F 及其结果段；运行速度见 Fig. 3J–L](#o_cecchetto_lfp) · measured_here · 诱发 LFP 的相序、分量持续时间

本条 → [o_cecchetto_lfp](#o_cecchetto_lfp) · reports_measurement · 分层的头固定鼠吹气诱发反应。。[出处](https://www.frontiersin.org/journals/neuroscience/articles/10.3389/fnins.2021.741279/full#F3)

本条 → [r_cecchetto_dryad](#r_cecchetto_dryad) · deposits_figure_data · 数据库记录 IsCitedBy 实验论文；Dryad 按图组织。。[出处](https://api.datacite.org/dois/10.5061/dryad.dbrv15f23)

### p_yanagawa2013

**[Large-Scale Information Flow in Conscious and Unconscious States: an ECoG Study in Monkeys](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0080845)**　区分皮层表面电位的频率特异定向耦合与局部频谱，并核对药物、睁闭眼和自然睡眠的分层。

['Toru Yanagawa', 'Zenas C. Chao', 'Naomi Hasegawa', 'Naotaka Fujii'] · 2013-11-15 · published · experiment, method · 数据 linked。[来源](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0080845)

早期关联文献。

标签　清醒、麻醉、网络节律、皮层电图、猕猴、在体、神经群体、大脑皮层、睡眠、氯胺酮、美托咪定

[Fig. 2B–C；Results 的频率域分类权重；Methods 的条件样本构造](#o_yanagawa_weights) · inferred · 基于频域 Granger 指标的线性分类器权重随频率分布

本条 → [o_yanagawa_weights](#o_yanagawa_weights) · reports_measurement · 左半球 ECoG 中可分类的定向耦合频带。。[出处](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0080845)

本条 ← [r_neurotycho_protocol](#r_neurotycho_protocol) · documents_protocol · 固定版本的实验室协议引用原始论文，并分列药物、睡眠和恢复。。[出处](https://wiki.neurotycho.org/index.php?title=Anesthesia_and_Sleep_Task_Details&oldid=86113)

### o_sbi_exp

**周期、相位延迟与间隙、簇持续时间**　图示三相节律，不从示意轨迹估读总体均值。[Figure 5b；原实验 Haddad & Marder 2018](https://pmc.ncbi.nlm.nih.gov/articles/PMC7581433/) · [所属论文](#p_sbi)

Cancer borealis（蟹） | 口胃神经节幽门环路的运动神经 | 离体神经记录，见原实验 | 幽门节律。

刺激/对照为 记录 AB/PD、LP、PY 相关运动神经的自发簇发 / 同一节律内各细胞组时序参照。单位 时间或周期归一化相位，按特征定义，时窗 未报告，分组 三类节律单元，独立单位 该面板为示例记录，生物独立样本数未报告。

原研究用途为 作为条件观测用于推断。建模用途为 约束相对时序及另列的摘要特征。同一图用过后不宜充当独立验证。。来源类别 `cited_measurement`，共同来源 `haddad2018_stg_pyloric`。

标签　局部微环路、网络节律、其他无脊椎类、胞外多单位、尖峰时间

本条 → [o_sbi_params](#o_sbi_params) · constrains · 图 5b 的实测摘要约束图 5c 的后验。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC7581433/)

### o_sbi_params

**膜与突触电导的联合后验**　24 个膜电导和 7 个突触电导可有多组相容配置。[Figure 5c 与 Appendix 1—figure 11](https://pmc.ncbi.nlm.nih.gov/articles/PMC7581433/) · [所属论文](#p_sbi)

与蟹幽门节律对应的三单元模型 | AB/PD、LP、PY 模型回路 | 模拟 | 拟合三相节律。

刺激/对照为 以 5b 实测摘要条件化后验 / 比较不同的高后验概率参数组合。单位 依各电导参数定义，时窗 未报告，分组 参数后验样本，独立单位 参数样本不等同于动物。

原研究用途为 定位可重现观测的参数集合。建模用途为 单一节律不足以唯一标定各电导。需以新扰动或直接电流记录区分候选。。来源类别 `inferred`，共同来源 `haddad2018_stg_pyloric`。

标签　局部微环路、网络节律、概率与统计生成模型、生物物理模型、离子通道与膜过程、突触

本条 ← [o_sbi_exp](#o_sbi_exp) · constrains · 图 5b 的实测摘要约束图 5c 的后验。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC7581433/)

### o_sbi_negative

**感受野与参数后验能否恢复**　同一模拟预算下，文中 SMC-ABC 对照未恢复正确的感受野和后验。[Figure 2g；Appendix 1—figure 5](https://pmc.ncbi.nlm.nih.gov/articles/PMC7581433/) · [所属论文](#p_sbi)

不适用 | 感受野基准模型 | 合成数据 | 不适用。

刺激/对照为 相同模拟预算下估计感受野 / 已知生成参数及另一推断方法。单位 依参数坐标，时窗 不适用，分组 算法及其预设预算，独立单位 模拟基准，非生物重复。

原研究用途为 用已知生成过程检查算法恢复能力。建模用途为 该失败界定所测预算和实现的表现，不能外推到所有 SMC-ABC 或真实神经元。。来源类别 `simulation`，共同来源 `sbi_synthetic_receptive_field`。

标签　单细胞、概率与统计生成模型、编码模型、数值方法

### o_wilson_modes

**膜电位与放电模式**　模型呈现规则/快速峰放电以及连续型/内源性簇放电。[图 1a–d](https://wulixb.iphy.ac.cn/article/doi/10.7498/aps.71.20221416?viewType=HTML) · [所属论文](#p_wilson)

模型，无指定样本 | 新皮层单细胞模型 | 数值模型 | 模拟放电。

刺激/对照为 按图 1a–d 改变参数组 / 四组参数对应的膜电位轨迹。单位 mV，分类按图中 RS、FS、CB、IB，时窗 各图示轨迹，分组 四组模型参数，独立单位 模型条件。

原研究用途为 为双慢变量的分岔分析提供轨迹。建模用途为 可比较模型动力学分类，不能用作离体生物记录。。来源类别 `simulation`，共同来源 `wilson_aps2022_model`。

标签　大脑皮层、单细胞、动力系统、膜电位

### o_claar_rate_cortex

**基础发放率**　安静清醒 3.3±0.2、跑动 5.0±0.5、麻醉 1.1±0.2。[Figure 7E，左面板](https://elifesciences.org/articles/84630/figures) · [所属论文](#p_claar)

小鼠 | 皮层 | 在体头固定 | 安静清醒、跑动与异氟烷麻醉。

刺激/对照为 电刺激实验中的状态比较 / 同研究清醒不跑动阶段。单位 Hz，时窗 基线，具体取窗按原方法，分组 皮层按状态，独立单位 作者该面板按受试小鼠报告 N=16。

原研究用途为 描述状态与兴奋性变化。建模用途为 可约束该制备的基础活动；诱发实验的基础率并非静息功率谱。。来源类别 `measured_here`，共同来源 `claar_eeg_np`。

标签　小鼠、在体、清醒、麻醉、异氟烷、发放率、胞外单单位、大脑皮层

本条 ← [r_dandi000458](#r_dandi000458) · supports · 归档原试验，面板指标仍须依作者纳入和窗口重算。。[出处](https://api.dandiarchive.org/api/dandisets/000458/versions/0.230317.0039/)

### o_claar_rate_thalamus

**基础发放率**　安静清醒 9.4±1.5、跑动 16.8±1.6、麻醉 0.8±0.4。[Figure 7E，右面板](https://elifesciences.org/articles/84630/figures) · [所属论文](#p_claar)

小鼠 | 躯体运动相关丘脑 | 在体头固定 | 安静清醒、跑动与异氟烷麻醉。

刺激/对照为 电刺激实验中的状态比较 / 同研究清醒不跑动阶段。单位 Hz，时窗 基线，具体取窗按原方法，分组 躯体运动相关丘脑按状态，独立单位 作者该面板按受试小鼠报告 N=13。

原研究用途为 描述状态与兴奋性变化。建模用途为 可约束该制备的基础活动；诱发实验的基础率并非静息功率谱。。来源类别 `measured_here`，共同来源 `claar_eeg_np`。

标签　小鼠、在体、清醒、麻醉、异氟烷、发放率、胞外单单位、丘脑

本条 ← [r_dandi000458](#r_dandi000458) · supports · 归档原试验，面板指标仍须依作者纳入和窗口重算。。[出处](https://api.dandiarchive.org/api/dandisets/000458/versions/0.230317.0039/)

### o_breadth_fafb_sections

**成功成像的切片比例**　99.8。[Results, Imaging the entire adult fly brain；Figure 1A–C](https://pmc.ncbi.nlm.nih.gov/articles/PMC6063995/) · [所属论文](#p_breadth_zheng2018)

Drosophila melanogaster | 全脑 | 固定的一只成年雌蝇脑，连续透射电镜薄切片 | 离体结构成像。

刺激/对照为 切出 7,062 张约 40 nm 的连续切片，核对实际完成成像的张数。 / 分母为同一标本切出的全部切片。。单位 %，时窗 一次连续采集，空间切片指标，分组 7,050 / 7,062 张切片，独立单位 标本为一只雌蝇，切片为同一标本内重复。。

原研究用途为 说明该体数据的完整度，便于核对跨切片重建。。建模用途为 切片完整度不等于突触检出灵敏度，个体间变异需另取标本。。来源类别 `measured_here`，共同来源 `fafb_single_female_2018`。

标签　电子显微成像、收录覆盖范围、结构测量、成年

### o_breadth_flywire_synapses

**139,255 个重建神经元之间的化学突触数**　约 54,500,000。[Results, The FlyWire connectome；Figure 1a 与 Methods, Synaptic connections](https://www.nature.com/articles/s41586-024-07558-y) · [所属论文](#p_breadth_dorkenwald2024)

Drosophila melanogaster | 全脑 | 重复利用 Zheng 等的同一只成年雌蝇脑的连续电镜图像，自动识别突触并经人工校对神经元分割。 | 固定组织。

刺激/对照为 计数 FlyWire 第 783 版已重建神经元之间的化学突触。 / 以发表版本及神经元端点均归入该重建集合为计数口径。。单位 个突触，时窗 固定标本的空间总数，分组 每个突触按突触前与突触后端点归入神经元，连接对可含多个突触。，独立单位 一个原始脑，历次发布及再分析仍是同一只动物。。

原研究用途为 为连边和突触数提供解剖结构约束。。建模用途为 突触数由图像判读得出，单条突触的传导强度和时延还需生理测量；下载表中范围更大的全部检测点不能直接复现此计数。。来源类别 `inferred`，共同来源 `fafb_single_female_2018`。

标签　连接组、化学突触、连接推断

### o_breadth_fish_temp

**占据位置对应的偏好温度**　约 25.3。[Results, Larval zebrafish perform homeostatic navigation；Figure 1A–B，Figure S1D–F](https://pmc.ncbi.nlm.nih.gov/articles/PMC10849091/) · [所属论文](#p_breadth_palieri2024)

Danio rerio | 整体动物的游泳行为 | 受精后 5–7 天幼鱼自由游动，位置与实测水温做对应。 | 浅温度梯度下的寻温行为。

刺激/对照为 每尾鱼在约 24–33 °C、沿长轴约 0.04 °C/mm 的梯度内游动 15 min。 / 本条描述原组随位置和时间选择水温，未比较消融组。。单位 °C，时窗 单尾 15 min，最初约 260 s 探索后出现偏好。，分组 Figure 1A 共 26 尾，按个体轨迹和群体位置分布汇总。，独立单位 鱼，游动回合嵌套于鱼内。。

原研究用途为 给闭环导航模型设置可检验的行为目标。。建模用途为 此值描述给定场地的占位偏好；把它解释为神经控制器的设定值尚需比较控制策略。。来源类别 `measured_here`，共同来源 `palieri_thermal_navigation`。

标签　行为观测、温度刺激或控制、闭环控制、幼体

### o_breadth_fish_poa

**感觉条件对转向概率调制的方向**　视前区消融削弱恶化与改善条件之间的转向调制；未为此条摘录效应量。。[Results, Figure 5A–C；Figure S6D–E；STAR Methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC10849091/) · [所属论文](#p_breadth_palieri2024)

Danio rerio | 双侧视前区与内侧视顶盖 | 5 dpf 做定位激光消融，恢复 40–48 h 后在 7 dpf 自由游动。 | 趋向或远离偏好温度的连续游泳回合。

刺激/对照为 同样的温度梯度与运动测量下比较视前区消融和视顶盖消融，对照病变位置；比较温度条件恶化与改善时的转向。 / 内侧视顶盖接受同类消融，另记录同一实验中的游泳速率。。单位 定性（概率差的方向），时窗 消融后 40–48 h 的行为测试，按相邻游泳回合判定感觉条件。，分组 视前区消融与视顶盖消融各 20 尾。，独立单位 鱼，回合和方向条件为鱼内重复。。

原研究用途为 比较依赖感觉变化的转向策略和广泛运动受损这两种解释。。建模用途为 可限制这项任务与干预条件下的视前区作用，不能由该读数单独确定环路的突触实现。。来源类别 `measured_here`，共同来源 `palieri_thermal_navigation`。

标签　视前区、消融实验、匹配对照、感觉运动整合、幼体

### o_breadth_lfpy_eeg

**偶极正上方的头皮电势波动量级**　约 0.1。[Results §3.2.5；Figure 5E–G；Methods §2.5](https://www.frontiersin.org/journals/neuroinformatics/articles/10.3389/fninf.2018.00092/full) · [所属论文](#p_breadth_hagen2018)

基于大鼠皮层细胞和连接模型，配合理想化的四层球形头模型 | 局部皮层柱到头皮电极 | NEURON 多区室网络与 LFPy 四层导体正向计算 | 模拟自发波动，径向排列的等效电流偶极子。

刺激/对照为 5,594 个神经元的跨膜电流合成为电流偶极矩，计算位于偶极上方的头皮电势。 / 同一网络不同头皮位置，以及文内引用的人体 EEG 量级仅供背景比较。。单位 µV，时窗 0–1,500 ms 模拟，舍去起始 500 ms。，分组 同一模拟网络，各头皮位置共享同一源。，独立单位 该条为一个网络算例，无独立生物受试者。。

原研究用途为 检验传感器几何、源方向、导电率和源规模是否足以生成目标量级。。建模用途为 模型输出不能作为人体独立验证；论文引述的实测 EEG 典型幅度来自其他研究。。来源类别 `simulation`，共同来源 `hagen_lfpy_demo`。

标签　观测信号生成、模拟结果、头皮脑电

### o_breadth_rotation_variance

**第一 jPCA 平面解释的总方差**　平均 28。[Figure 3；main text；Methods, Electrophysiological recordings](https://stat.columbia.edu/~cunningham/pdf/ChurchlandNature2012.pdf) · [所属论文](#p_breadth_churchland2012)

Macaca mulatta | 初级运动皮层及背侧前运动皮层 | 在体胞外放电，单电极或电极阵列；不同实验有直线或弯曲伸手。 | 指示延迟后从运动准备转入执行。

刺激/对照为 对各动作条件的群体反应做 jPCA 投影，统计第一二维旋转平面解释的方差。 / 论文比较打乱数据、运动学和肌电投影；第一平面只代表一部分总变异。。单位 %，时窗 从准备相关活动过渡到运动相关活动的前 200 ms，分组 原研究 4 只猕猴、9 组记录；图 3 展示所选多组。，独立单位 动物；同只动物的不同记录组、条件和神经元不能作独立个体。。

原研究用途为 为群体轨迹形状与方差建立数据参照。。建模用途为 低维旋转现象也可兼容外部反馈；现有 DANDI 条目只覆盖部分原研究。。来源类别 `measured_here`，共同来源 `churchland_reaching_original`。

标签　运动皮层、旋转群体动力学分析、群体轨迹旋转、大脑皮层

### o_breadth_surrogate_rotation

**实测与替代数据的模型拟合差异，单尾检验**　<0.001（作者报告）。[Figure 6a；Online Methods, Motor cortex data](https://stat.columbia.edu/~cunningham/pdf/ElsayedNN2017.pdf) · [所属论文](#p_breadth_elsayed2017)

Macaca mulatta | 初级运动皮层及背侧前运动皮层 | 重新分析 Churchland 等已发表的多只猕猴运动期记录。 | 延迟伸手任务的动作期。

刺激/对照为 用同一低维线性动力系统分别拟合实测放电和保持不同边缘统计特征的替代数据，比较 R²。 / 比较时间、神经元和条件三个维度的均值与协方差组合；每类对照 100 份，另用留一条件交叉验证。。单位 P 值，时窗 Figure 6 为 400 ms 运动相关活动，原始放电用 24 ms 高斯核平滑后每 10 ms 采样。，分组 同一批运动皮层数据按动物及条件组织；100 份替代数据是计算重复。，独立单位 生物单位为原研究的动物，替代数据集不增加动物数。。

原研究用途为 检验特定边缘均值与协方差能否解释群体动力学的拟合质量。。建模用途为 该再分析只排除了被检验的替代解释；没有获得一组新的独立生物记录。。来源类别 `inferred`，共同来源 `churchland_reaching_original`。

标签　替代数据分析、协方差、零模型

### o_breadth_hc3_size

**记录集合内所述神经元数量**　7,737。[Data description；CRCNS hc-3 About, Overview](https://crcns.org/data-sets/hc/hc-3/about-hc-3) · [所属论文](#p_breadth_mizuseki2014)

Rattus norvegicus，Long-Evans | 海马 CA1、CA3、齿状回及内嗅皮层 | 在体多通道胞外记录配合行为任务。 | 多个行为条件。

刺激/对照为 跨会话采集并整理单元时间、波形、LFP 和可用的头部位置。 / 此数为整个公开集合的描述；单个状态、动物及脑区须按元数据另行筛选。。单位 个神经元，时窗 全体实验累计 204.5 h，无共同单一分析窗。，分组 11 只大鼠，442 次会话，14 类行为。，独立单位 动物；单元和会话嵌套于动物。。

原研究用途为 确定能否按动物划分校准和留出，并在同一任务状态下比较时序。。建模用途为 整库神经元数不能充当独立样本数，也不代表所有单元在同一时刻记录。。来源类别 `measured_here`，共同来源 `crcns_hc3_original`。

标签　归档样本范围、电生理记录、海马

### o_cell_velden_tau

**阶跃内放电频率适应时间常数**　野生型 0.178 ± 0.024，敲除型 0.132 ± 0.027（均值 ± SE）。。[Fig. 2B 及紧随其后的 Results 段，瞬时频率轨迹和拟合时间常数。](https://journals.physiology.org/doi/full/10.1152/jn.00829.2011) · [所属论文](#p_cell_velden)

Mus musculus | 体感皮层 L2/3 锥体细胞 | 急性脑片，胞体全细胞电流钳 | 离体，去极化阶跃诱发重复放电。

刺激/对照为 1 s 阶跃，对 200–450 pA 刺激的瞬时频率轨迹叠合后拟合单指数衰减。 / 相同刺激下比较野生型与 5-HT3A 受体敲除小鼠。。单位 s，时窗 自 1 s 阶跃起始，对脉冲间隔倒数随时间的变化作拟合。，分组 按基因型汇总，野生型 21 个细胞，敲除型 24 个细胞。，独立单位 原文以细胞计数。未从该比较定位各动物贡献的细胞数，动物间推断需有隶属资料。。

原研究用途为 比较两组达到稳态的速率，作者报告两个时间常数相近。。建模用途为 可约束同条件模型的有效渐近时间尺度。区分两种候选机制还应保持同样的放电定义，并检验新的刺激历史。。来源类别 `published_aggregate`，共同来源 `velden_mouse_l23`。

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、放电间隔、大脑皮层、小鼠、离体、阶跃电流、锥体细胞

本条 ← [o_cell_mensi_fig5_steps](#o_cell_mensi_fig5_steps) · candidate_external_step_check · 两者分别提供模型阶跃预测和独立研究的阶跃实测时间尺度。年龄、细胞类型和刺激条件须匹配才可数值比较。。[出处](https://journals.physiology.org/doi/full/10.1152/jn.00829.2011)

本条 → [o_cell_velden_steady](#o_cell_velden_steady) · same_experimental_cohort · 同一研究细胞的互补读数，不能计为独立生物批次。。[出处](https://journals.physiology.org/doi/full/10.1152/jn.00829.2011)

### o_cell_velden_steady

**单指数拟合的稳态放电频率**　野生型 11.9 ± 0.9，敲除型 17.8 ± 1.5（均值 ± SE；原文 P < 0.01）。。[Fig. 2C 及正文给出的稳态放电频率。](https://journals.physiology.org/doi/full/10.1152/jn.00829.2011) · [所属论文](#p_cell_velden)

Mus musculus | 体感皮层 L2/3 锥体细胞 | 急性脑片，胞体全细胞电流钳 | 离体，去极化阶跃诱发重复放电。

刺激/对照为 1 s 阶跃，对 200–450 pA 刺激的瞬时频率轨迹叠合后拟合单指数衰减。 / 相同刺激下比较野生型与 5-HT3A 受体敲除小鼠。。单位 Hz，时窗 自 1 s 阶跃起始，对脉冲间隔倒数随时间的变化作拟合。，分组 按基因型汇总，野生型 21 个细胞，敲除型 24 个细胞。，独立单位 原文以细胞计数。未从该比较定位各动物贡献的细胞数，动物间推断需有隶属资料。。

原研究用途为 与适应时间常数和初始频率合看，区分到达稳态所需时间及稳态高度。。建模用途为 在相同刺激和细胞条件下约束稳态响应。拟合单一高低差不能单独给出离子通道或树突形态的因果解释。。来源类别 `published_aggregate`，共同来源 `velden_mouse_l23`。

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、放电间隔、大脑皮层、小鼠、离体、阶跃电流、锥体细胞

本条 ← [o_cell_velden_tau](#o_cell_velden_tau) · same_experimental_cohort · 同一研究细胞的互补读数，不能计为独立生物批次。。[出处](https://journals.physiology.org/doi/full/10.1152/jn.00829.2011)

### o_cell_wang_human_ratio

**原作者的适应比（adaptation ratio）**　经典型 0.89 ± 0.02（71 细胞），爆发型 0.44 ± 0.06（11 细胞），延迟型 1.15 ± 0.10（10 细胞）。。[Fig. 1A–C 给出样例记录，Fig. 1D 和 Human neocortical FS neurons 结果段给出适应比组间比较。](https://pmc.ncbi.nlm.nih.gov/articles/PMC5067378/) · [所属论文](#p_cell_wang)

Homo sapiens | 切除的新皮层快放电细胞，脑叶混合 | 手术组织急性切片，全细胞电流钳，来源以癫痫患者为主 | 离体，超阈值阶跃诱发放电。

刺激/对照为 500 ms 去极化阶跃，按电流增加直至高频放电，记录同一细胞的动作电位序列。 / 同一实验按起始放电模式分为经典、爆发和延迟型。。单位 无量纲，时窗 阶跃内 500 ms，Fig. 1D 单一电流幅度及适应比精确取值窗未从已查资料定位。，分组 92 个快放电细胞，全文人组织来自 24 名患者。各亚型对应患者数未单列。，独立单位 文中亚型比较单位为细胞。患者级推断需逐细胞回连患者。。

原研究用途为 比较人皮层三类快放电细胞的时序表型。。建模用途为 适用于该手术组织的快放电子群。未核实适应比的完整公式时可保留组内比较方向，不可将数值直接换作 Allen 的相邻间隔指数。。来源类别 `published_aggregate`，共同来源 `wang_human_fs`。

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、放电间隔、大脑皮层、人类、离体、阶跃电流、快发放细胞

### o_cell_mensi_fig4_record

**实测胞体膜电位、动作电位发生时刻**　图中 11 次重复记录呈时序点栅；未数字化单点电压。。[Fig. 4A 输入；Fig. 4B 黑线为实测胞体电压，黑色点栅为记录的脉冲。](https://infoscience.epfl.ch/bitstreams/6ce42f90-73cc-42b3-a237-70f3bd4688a5/download?download=1) · [所属论文](#p_cell_mensi)

Mus musculus | 新皮层 L2/3，Fig. 4B 为 GABA 能快放电细胞 | 出生后 17–22 天 GAD67-GFP 小鼠急性脑片，胞体全细胞电流钳 | 离体，注入类突触波动电流。

刺激/对照为 对同一细胞重复注入相同波形；各细胞调整幅度使 30 s 平均放电约 5–15 Hz。 / 配对比较同一细胞相同输入下的记录和适配该细胞的模型。。单位 mV，s，时窗 30 s 指平均放电的调幅窗，图示电压轨迹取该记录的片段。，分组 Fig. 4B 是一例快放电细胞的 11 次重复，Fig. 4C、D 分别另示非快放电抑制性与兴奋性细胞。，独立单位 细胞；该图中重复注流来自同一细胞，不能增加生物样本数。。

原研究用途为 检验相同波形可引出的尖峰时序和阈下膜电位轨迹。。建模用途为 对平均率相同的候选模型可比较阈下电压及时序。电压记录并未直接测得慢适应电流或阈值状态。。来源类别 `measured_here`，共同来源 `mensipatch_l23`。

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、大脑皮层、小鼠、离体、波动电流

本条 → [o_cell_mensi_fig4_model](#o_cell_mensi_fig4_model) · paired_prediction · 同一细胞、同一电流波形与绘图时间坐标，黑色记录和红色模型来自不同过程。。[出处](https://infoscience.epfl.ch/bitstreams/6ce42f90-73cc-42b3-a237-70f3bd4688a5/download?download=1)

### o_cell_mensi_fig4_model

**模型膜电位和预测脉冲发生时刻**　图示红色电压及点栅，未从图片估计数值。。[Fig. 4B 红线和红色点栅，输入见 Fig. 4A。](https://infoscience.epfl.ch/bitstreams/6ce42f90-73cc-42b3-a237-70f3bd4688a5/download?download=1) · [所属论文](#p_cell_mensi)

Mus musculus | 新皮层 L2/3，Fig. 4B 为 GABA 能快放电细胞 | 适配同一脑片细胞的广义积分发放模型。 | 仿真，输入为实验使用的波动电流。

刺激/对照为 对同一细胞重复注入相同波形；各细胞调整幅度使 30 s 平均放电约 5–15 Hz。 / 配对比较同一细胞相同输入下的记录和适配该细胞的模型。。单位 mV，s，时窗 30 s 指平均放电的调幅窗，图示电压轨迹取该记录的片段。，分组 Fig. 4B 是一例快放电细胞的 11 次重复，Fig. 4C、D 分别另示非快放电抑制性与兴奋性细胞。，独立单位 细胞；该图中重复注流来自同一细胞，不能增加生物样本数。。

原研究用途为 与同一图中黑色实测比较，检查模型对电压及放电时序的预测。。建模用途为 支持对等效适应电流和动态阈值的预测能力比较，二者的生物实现仍需独立测量。。来源类别 `simulation`，共同来源 `mensipatch_l23`。

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、大脑皮层、小鼠、离体、波动电流

本条 ← [o_cell_mensi_fig4_record](#o_cell_mensi_fig4_record) · paired_prediction · 同一细胞、同一电流波形与绘图时间坐标，黑色记录和红色模型来自不同过程。。[出处](https://infoscience.epfl.ch/bitstreams/6ce42f90-73cc-42b3-a237-70f3bd4688a5/download?download=1)

### o_cell_mensi_fig5_steps

**初始与稳态放电频率**　Fig. 5D–F 各示三个刺激强度；未数字化曲线。。[Fig. 5A–C 三类模型的初始与稳态频率-电流曲线，Fig. 5D–F 为对应阶跃模拟。](https://infoscience.epfl.ch/bitstreams/6ce42f90-73cc-42b3-a237-70f3bd4688a5/download?download=1) · [所属论文](#p_cell_mensi)

Mus musculus | 按 L2/3 快放电、非快放电及兴奋性细胞拟合的模型 | 不同细胞类型的积分发放模型 | 仿真，恒定阶跃电流。

刺激/对照为 在模型中施加方波电流，比较初始与稳态的频率-电流关系。 / 同一模型的初始和稳态响应，并横向参照另外两类模型。。单位 Hz，时窗 初始频率按首个放电间隔倒数；稳态按原图，具体时间窗未单列。，分组 按模型所对应的细胞类型分组。，独立单位 模型或所对应的生物细胞；不同阶跃幅度为同一模型条件。。

原研究用途为 说明拟合得到的适应成分将怎样改变方波响应。。建模用途为 可用于复现候选模型的定性预测。实测阶跃适应应另取记录与预测对比。。来源类别 `simulation`，共同来源 `mensipatch_l23`。

标签　放电适应、单细胞、发放率、放电间隔、大脑皮层、小鼠、阶跃电流、点神经元

本条 → [o_cell_velden_tau](#o_cell_velden_tau) · candidate_external_step_check · 两者分别提供模型阶跃预测和独立研究的阶跃实测时间尺度。年龄、细胞类型和刺激条件须匹配才可数值比较。。[出处](https://journals.physiology.org/doi/full/10.1152/jn.00829.2011)

### o_cell_teeter_fig4_record

**重复注流时的实测脉冲发生时刻**　图示同一细胞多次记录的点栅，未从图像提取时刻；例示细胞可在 Allen 数据库按标本号获取。。[Fig. 4a 黑色实测脉冲点栅；Fig. 1b 生物电压痕迹及作者作图程序可辨示例细胞。](https://www.nature.com/articles/s41467-017-02717-4/figures/4) · [所属论文](#p_cell_teeter)

Mus musculus | 示例为小鼠初级视觉皮层；Fig. 1b 实现指定 Htr3a 标本 474637203 与 Ctgf 标本 512322162。 | 急性小鼠脑片全细胞电流钳 | 离体，以变化的胞体电流诱发放电。

刺激/对照为 对同一细胞重复输入同一条 3 s Noise 2 波形，拟合使用 Noise 1，评估用未参与拟合的 Noise 2。 / 同一输入、同一细胞内，对比记录的重复响应与五种广义积分发放模型。。单位 s，时窗 Noise 2 的 3 s 输入段。，分组 按细胞分组，图内各次重复和五种模型均配对。，独立单位 本细胞内的留出波形检验新输入的预测；跨细胞、跨动物推断需另行留出样本。。

原研究用途为 估计同细胞刺激重放时序的可重复程度，并评价模型时间预测。。建模用途为 可约束同一细胞在新刺激波形下的尖峰预测；不能作为来自新动物的独立确认。。来源类别 `measured_here`，共同来源 `allen_ctdb_mouse`。

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、大脑皮层、小鼠、离体、波动电流、点神经元

本条 → [o_cell_teeter_fig4_model](#o_cell_teeter_fig4_model) · paired_prediction · 同一 Noise 2 输入上的实验与模型点栅；同一细胞重复刺激。。[出处](https://www.nature.com/articles/s41467-017-02717-4/figures/4)

### o_cell_teeter_fig4_model

**GLIF1–5 在留出波形上预测的脉冲时刻**　图内为确定性模型脉冲，未数字化；拟合数据和预测波形在原文有明示。。[Fig. 4a 彩色 GLIF1–5 脉冲点栅，与黑色实测分开记录。](https://www.nature.com/articles/s41467-017-02717-4/figures/4) · [所属论文](#p_cell_teeter)

Mus musculus | 示例为小鼠初级视觉皮层；Fig. 1b 实现指定 Htr3a 标本 474637203 与 Ctgf 标本 512322162。 | 五种 GLIF 点神经元模型，按同一实测细胞分别拟合 | 仿真，重放同一 Noise 2 电流。

刺激/对照为 对同一细胞重复输入同一条 3 s Noise 2 波形，拟合使用 Noise 1，评估用未参与拟合的 Noise 2。 / 同一输入、同一细胞内，对比记录的重复响应与五种广义积分发放模型。。单位 s，时窗 Noise 2 的 3 s 输入段。，分组 按细胞分组，图内各次重复和五种模型均配对。，独立单位 本细胞内的留出波形检验新输入的预测；跨细胞、跨动物推断需另行留出样本。。

原研究用途为 比较模型层级增加阈值和脉冲后电流后，留出时序预测如何改变。。建模用途为 提供模型间样本内协议泛化比较。有效脉冲后电流或阈值参数尚不能指定真实通道。。来源类别 `simulation`，共同来源 `allen_ctdb_mouse`。

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、大脑皮层、小鼠、离体、波动电流、点神经元

本条 ← [o_cell_teeter_fig4_record](#o_cell_teeter_fig4_record) · paired_prediction · 同一 Noise 2 输入上的实验与模型点栅；同一细胞重复刺激。。[出处](https://www.nature.com/articles/s41467-017-02717-4/figures/4)

### o_cell_gouwens_mouse_index

**Allen adaptation，相邻放电间隔归一化差的均值**　门户预计算 0.299873232107749；公开 NWB 的 4 个脉冲产生 3 个 ISI，复算 0.2998732321077493。。[Supplementary Dataset 3，Data 表第 7 行，标本 313861794；指标来自关联的 Allen EphysFeature 396463405，并依原始 NWB 的 Sweep_35 脉冲时刻复算。](https://api.brain-map.org/api/v2/data/EphysFeature/396463405.json) · [所属论文](#p_cell_gouwens)

Mus musculus | 外侧视觉区 VISl 第 4 层，有棘细胞 | 急性脑片，胞体全细胞电流钳，Scnn1a-Tg3-Cre;Ai14 | 离体，Long Square 诱发放电。

刺激/对照为 代表性扫次 #35，约 +150 pA，阈电流 110 pA。相邻 ISI 按 (后 − 前)/(后 + 前) 计算，再对同一阶跃平均。 / 同一长阶跃内部相邻脉冲间期逐对比较。。单位 无量纲，时窗 从扫次内 1.02 s 起，报告脉宽 0.999995 s，以刺激段内脉冲计算。，分组 一只供体 313401484 的一个标本及其一个代表性长阶跃。，独立单位 细胞；外推至动物需若干独立供体。。

原研究用途为 原研究用电生理表征进行细胞分类。该具体数字为关联公开数据产品中的每细胞特征，论文补表提供标本身份。。建模用途为 可用作有出处的算法核对与单细胞协议比较；不能把选出的高适应样本当作总体分布。。来源类别 `published_aggregate`，共同来源 `allen_ctdb_mouse`。

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、放电间隔、大脑皮层、小鼠、离体、阶跃电流、皮层第四层

本条 → [r_cell_allen_mouse_feature](#r_cell_allen_mouse_feature) · derived_feature · 该特征从同一细胞的代表性长阶跃计算；门户数值归于数据产品。。[出处](https://api.brain-map.org/api/v2/data/EphysFeature/396463405.json)

### o_bajwa_lzc

**单导 Lempel–Ziv 复杂度（LZc）的状态均值与标准差**　睁眼 0.325±0.020，闭眼 0.309±0.018，镇静 0.274±0.012；三项配对 Wilcoxon 比较在 Table 4 均为 p<0.001。。[Results：Differences in measures between wakefulness and sedation；Table 4；方法及补充 Fig. S3](https://www.nature.com/articles/s41598-025-12695-z) · [所属论文](#p_bajwa2025)

人，健康志愿者 | 多通道头皮 EEG，逐导估计复杂度 | 在体自发 EEG；清醒睁眼与闭眼分开；镇静闭眼 | 清醒睁眼、清醒闭眼、丙泊酚深镇静（目标 RASS −4）。

刺激/对照为 逐步滴定至强刺激可唤醒，最多三次苏醒访谈；选每次唤醒前静息 EEG，与 TMS 时段分别处理 / 同一参加者睁眼与闭眼清醒静息；闭眼清醒是镇静闭眼的眼态匹配对照。单位 无量纲，时窗 清醒各 5 min；镇静取唤醒前 1 min，个人最多三次取均值，分组 20 人完成，40 段清醒自发 EEG，52 次镇静自发记录；分析按人配对。TMS-EEG 属其他分析。，独立单位 人 n=20；每次唤醒、时间片和通道嵌套于人。。

原研究用途为 比较清醒与深镇静的复杂度，并评估同一镇静条件内主观报告可否区分。。建模用途为 复杂度不能作为功率谱数值；原始 EEG 可以另算同窗频谱。可强刺激唤醒的深镇静不等同于其他协议的全麻无反应，也不说明个人没有体验。。来源类别 `measured_here`，共同来源 `bajwa_oslo_propofol_sedation_2025`。

标签　清醒、镇静、网络节律、头皮脑电、人类、在体、神经群体、大脑皮层、丙泊酚、静息

本条 ← [p_bajwa2025](#p_bajwa2025) · reports_measurement · Table 4 为配对检验，正文列状态均值、标准差及分析单位。。[出处](https://www.nature.com/articles/s41598-025-12695-z)

### o_purdon_frontal

**相对于先前清醒频谱的功率变化及其头皮分布**　LOC 时额部 0.1–1 Hz 与 8–12 Hz 功率均升高；LOC 后 15 min，alpha 增强集中于额部，低频增强广及颞顶头皮；未从色彩图摘取个体幅值。。[Fig. 1及方法的状态判定；Fig. 2B–D 的行为对齐频谱与头皮分布](https://pmc.ncbi.nlm.nih.gov/articles/PMC3607036/) · [所属论文](#p_purdon2013)

人，10 名健康成人 | 头皮 64 导；额中附近 Fz 与全头皮电极 | 在体头皮 EEG；闭眼；最近邻拉普拉斯参考 | 本人清醒用药前 → 渐进丙泊酚 → 言语无反应 → 恢复。

刺激/对照为 持续听觉提示，每 4 s 一次；按言语反应概率低于 0.05 并持续至少 5 min 界定 LOC / 同一人的用药前清醒频谱；逐人对齐 LOC/ROC。单位 频率 Hz；基线归一化功率（图示 dB），时窗 个体 LOC/ROC对齐；空间比较取 LOC 后 15 min，分组 个体内相对基线后作组水平汇总；电极、时间窗在个体内重复，独立单位 受试者 n=10。

原研究用途为 表征丙泊酚诱导与恢复过程中的行为及 EEG 频带标志。。建模用途为 可限定人类该协议下变化方向、频带与头皮分布。无任务静息、单一突触机制或跨药剂推广需另外检验。。来源类别 `measured_here`，共同来源 `purdon_mgh_gradual_propofol_2013`。

标签　清醒、麻醉、网络节律、头皮脑电、功率谱、人类、在体、神经群体、大脑皮层、丙泊酚

本条 ← [r_bajwa_openneuro](#r_bajwa_openneuro) · alternative_with_different_depth · 相同药物、人类和头皮 EEG，但这里明确为静息与目标 RASS −4 深镇静，可以外检协议依赖性；两文的状态终点与任务不同。。[出处](https://www.nature.com/articles/s41598-025-12695-z)

本条 ← [p_purdon2013](#p_purdon2013) · reports_measurement · 原文 Fig. 2B–D。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC3607036/)

本条 ← [r_openneuro_clinical](#r_openneuro_clinical) · candidate_external_comparison · 独立机构临床队列可从同人事件表重算指定窗；用药/睁闭眼/任务不同或未知，独立的丙泊酚复验资格仍待核。。[出处](https://raw.githubusercontent.com/OpenNeuroDatasets/ds004541/1.0.0/sub-02/ses-01/eeg/sub-02_ses-01_task-anesthesia_events.tsv)

本条 ← [r_zenodo_rest](#r_zenodo_rest) · candidate_resting_control · 登记有闭眼清醒与丙泊酚静息记录，访问须申请；未确认原始样本独立性。。[出处](https://zenodo.org/api/records/806176)

### o_purdon_peak

**2–40 Hz 中位频率；第 75 与第 25 百分位之差**　诱导过渡期中位频率 23.1→12.0，带宽 17.4→9.1；恢复过渡期中位频率 11.8→21.9，带宽 9.9→12.8。。[Fig. 3A 额部频谱中位数和四分位带宽；Results：time course of the traveling peak](https://pmc.ncbi.nlm.nih.gov/articles/PMC3607036/) · [所属论文](#p_purdon2013)

人，同一批 10 名健康成人 | 额中附近头皮 EEG，约 Fz | 闭眼，拉普拉斯参考；2–40 Hz 内按基线归一化功率计算中位频率 | 丙泊酚诱导时首次行为改变至持续言语无反应前，及恢复言语反应之后。

刺激/对照为 渐进输注；重复同一听觉按键任务 / 受试者自身诱导和恢复过渡期，分别与其清醒基准对齐。单位 Hz，时窗 诱导取 LOC 前过渡期；恢复取 ROC 后过渡期，端点依行为定义，分组 组水平额部频谱；与 Fig. 2 属同批受试者，独立单位 受试者 n=10。

原研究用途为 量化移行峰随行为反应改变的时间进程。。建模用途为 这是给定带宽中功率的中位频率；不能把两端当作任意静息和稳态深麻醉的谱峰。。来源类别 `measured_here`，共同来源 `purdon_mgh_gradual_propofol_2013`。

标签　清醒、麻醉、网络节律、头皮脑电、功率谱、人类、在体、神经群体、大脑皮层、丙泊酚

本条 ← [p_purdon2013](#p_purdon2013) · reports_measurement · 原文 Fig. 3A；同批受试者。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC3607036/)

### o_xiong_tpt_peak

**Tpt 局部 oddball 相对 regular 的功率变化峰之中心频率**　在第 5 音之后 200 ms 内，中心频率由清醒的 82 Hz 降至 LOC 的 40 Hz；正文另报告清醒时两区局部 regular 的 15–30 Hz 功率较高。。[Fig. 3A–C，Results 的 Tpt 局部 oddball 频率峰](https://pmc.ncbi.nlm.nih.gov/articles/PMC11494327/) · [所属论文](#p_xiong2024)

猕猴，两只 | 颞顶过渡听觉区 Tpt，另记录额叶眼区 FEF | 在体颅内 LFP，多电极；只纳入主动筛得的听觉应答通道 | 同一猴清醒与丙泊酚所致行为反应丧失。

刺激/对照为 被动聆听五个音组成的序列；以第 5 音是否违反局部规律作对照 / 每个状态内将局部 oddball 与相同结构的 regular 试次比较，再比较两个状态。单位 Hz；诱发功率为相对差，时窗 第 5 音起算，前 200 ms；保留图 3C 的时段分类，分组 两只动物；总计 207 FEF/170 Tpt 通道，选听觉应答 99 FEF/128 Tpt；通道嵌套于动物，独立单位 动物 n=2；区域、通道与试次为重复测量。

原研究用途为 用频率与区域依赖的意外声音应答检验预测性路由。。建模用途为 可对照同种药物、相同任务、Tpt 局部电位的变化。自发头皮 EEG 和单动物外推需要相应记录。。来源类别 `measured_here`，共同来源 `xiong_monkeys_oddball_2024`。

标签　清醒、麻醉、网络节律、局部场电位记录、功率谱、猕猴、在体、神经群体、大脑皮层、丙泊酚、听觉任务

本条 ← [p_xiong2024](#p_xiong2024) · reports_measurement · 原文 Fig. 3A–C。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC11494327/)

本条 ← [r_xiong_tfr](#r_xiong_tfr) · supports_condition_comparison · 公开归档分列清醒与丙泊酚的时频数组，使用与图匹配的 area、局部 oddball 和 regular；本次核读文件结构，尚未重算峰值。。[出处](https://api.figshare.com/v2/file/download/49295326)

### o_cecchetto_lfp

**诱发 LFP 的相序、分量持续时间**　麻醉时先负后正，两分量持续 33.8 ± 0.3 ms 和 406 ± 13 ms；清醒静止的响应先负、后正、再负。。[Fig. 3D–F、4D–F、5D–F 及其结果段；运行速度见 Fig. 3J–L](https://www.frontiersin.org/journals/neuroscience/articles/10.3389/fnins.2021.741279/full#F3) · [所属论文](#p_cecchetto2021)

成年雄性小鼠，电压成像同期 cohort 为 6 只 | 桶状皮层不同深度的 LFP；ECoG 与光学信号另列 | 头固定在体小鼠，同次记录多深度电极、成像与运行速度 | 1% 异氟烷轻度麻醉；恢复 30–40 min 后清醒静止或跑动。

刺激/对照为 面颊和阵列对侧触须吹气 100 ms、20 psi；试次间隔平均 10 s；刺激前 500 ms 平均速度 >5 mm/s 判跑动 / 同一只小鼠、同一刺激的麻醉/清醒静止/清醒跑动；两种清醒状态分开。单位 持续时间 ms；相序为分类读数，时窗 吹气开始对齐；分量持续时间按原文报告；选择试次采用刺激前 500 ms，分组 每鼠先按行为和记录深度汇总，再比较 6 鼠；4 鼠钙成像实验另计，独立单位 小鼠 n=6。

原研究用途为 表征层位、行为和麻醉状态对触须诱发电位的影响。。建模用途为 可约束小鼠浅麻醉下的感觉诱发动力学；吹气试次的时域波形不能直接约束无刺激丙泊酚人脑功率谱。。来源类别 `measured_here`，共同来源 `cecchetto_mouse_vsd_2021`。

标签　清醒、麻醉、局部场电位记录、皮层电图、小鼠、在体、神经群体、大脑皮层、异氟烷、感觉任务

本条 ← [p_cecchetto2021](#p_cecchetto2021) · reports_measurement · 分层的头固定鼠吹气诱发反应。。[出处](https://www.frontiersin.org/journals/neuroscience/articles/10.3389/fnins.2021.741279/full#F3)

### o_yanagawa_weights

**基于频域 Granger 指标的线性分类器权重随频率分布**　12–32 Hz 权重更偏向清醒类别，6–10 Hz 与 34–100 Hz 权重更偏向麻醉类别。。[Fig. 2B–C；Results 的频率域分类权重；Methods 的条件样本构造](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0080845) · [所属论文](#p_yanagawa2013)

猕猴；M1–M3 为 Macaca fuscata，M4 为 Macaca mulatta | 左半球额、顶、颞、枕叶皮层表面，128 导 | 慢性硬膜下 ECoG 阵列，在体双极导联 | 清醒与氯胺酮–美托咪定麻醉；丙泊酚与自然睡眠另行验证。

刺激/对照为 在频域估计成对 Granger 因果，以同一动物的实验日数据区分两种状态；清醒含睁/闭眼条件，须保留标签 / 同一动物的清醒和氯胺酮–美托咪定麻醉。单位 频率 Hz；分类权重经归一化，时窗 每个条件样本 120 s，由 600 个 200 ms 段汇集；分析频率 6–100 Hz，步长 2 Hz，分组 4 猴分别计算，跨实验日构造条件样本；按协议药剂分层，独立单位 猕猴 n=4；导联对、切片和交叉验证折不增加动物数。

原研究用途为 识别可区分状态的大范围频率特异定向耦合。。建模用途为 权重不同于单通道功率谱。原研究另行比较丙泊酚、自然睡眠，不能把这些条件当同一麻醉重复。。来源类别 `inferred`，共同来源 `yanagawa_neurotycho_2013`。

标签　清醒、麻醉、网络节律、皮层电图、猕猴、在体、神经群体、大脑皮层、功能连接、氯胺酮、美托咪定

本条 ← [p_yanagawa2013](#p_yanagawa2013) · reports_measurement · 左半球 ECoG 中可分类的定向耦合频带。。[出处](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0080845)

### o_allen_human_s39

**相邻放电间隔归一化差的均值（Allen adaptation）**　归档特征 0.187288525642607。按原始脉冲时间复算为 0.1872885256426067。。[Allen 标本 486940963，EphysSweep 486941688（Sweep_39），NWB /analysis/spike_times/Sweep_39，EphysFeature 486943542。](https://api.brain-map.org/api/v2/data/EphysFeature/486943542.json) · 采集论文尚待核实 · [数据记录](#r_cell_allen_human_raw)

人 | 额下回第 3 层有棘细胞 | 离体脑片、胞体全细胞电流钳 | 离体阶跃诱发。

刺激/对照为 约 1 s 的 +190 pA 长方波，阈电流 150 pA。 / 同一细胞同一电流阶跃，逐对比较相邻脉冲间隔。。单位 无量纲，时窗 起点 1.02 s，约 1 s。，分组 1 个供体、1 个细胞、1 个代表性阶跃中的 9 个脉冲，形成 8 个间隔。，独立单位 细胞；供体 486909083。。

原研究用途为 原平台由实验记录计算逐细胞特征。该样本对应的原始建模或采集论文尚未指定。。建模用途为 可检验给定细胞的尖峰提取与同协议适应读数。单个样本不能界定物种差异。。来源类别 `published_aggregate`，共同来源 `allen_ctdb_human_486940963`。

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、放电间隔、大脑皮层、人类、离体、阶跃电流、皮层第三层

本条 ← [r_cell_allen_human_feature](#r_cell_allen_human_feature) · reports_feature · 同一标本的预计算特征，原始阶跃脉冲时间可复算。。[出处](https://api.brain-map.org/api/v2/data/EphysFeature/486943542.json)

### o_bajwa_experience

**唤醒前单导 Lempel–Ziv 复杂度与体验报告类别的关联**　体验类别的线性混合模型固定效应 F=0.727，p=0.489。。[Figure 2b 与 Results 中深镇静内报告类别比较，分组见 Table 3。](https://pmc.ncbi.nlm.nih.gov/articles/PMC12460656/) · [所属论文](#p_bajwa2025)

人，健康志愿者 | 多通道头皮 EEG，逐导估计复杂度 | 在体自发 EEG；清醒睁眼与闭眼分开；镇静闭眼 | 丙泊酚深镇静（RASS −4），唤醒前。

刺激/对照为 取每次唤醒前一段自发 EEG，按随后的体验报告分组。 / 同一镇静水平下比较报告有体验、无体验及无有效信息三类。。单位 无量纲，时窗 每次唤醒前 1 min，分组 52 次唤醒，24 次有体验、5 次无体验、23 次无可用信息，合计 20 名参与者。，独立单位 人；多次唤醒嵌套于受试者，受试者设随机截距。。

原研究用途为 检验同一深镇静状态中，自发 EEG 复杂度能否区分随后报告的体验。。建模用途为 本样本未检出类别效应。无体验报告次数少，且体验依赖回顾性报告，不能据此排除小效应或认定三个状态等效。。来源类别 `measured_here`，共同来源 `bajwa_oslo_propofol_sedation_2025`。

标签　镇静、头皮脑电、神经群体、人类、在体、丙泊酚、行为观测、静息

本条 ← [r_bajwa_openneuro](#r_bajwa_openneuro) · archives_study · 同一深镇静实验归档；按原文报告类别和唤醒前的时间窗解释。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC12460656/)

### r_modeldb2488

**[Mainen–Sejnowski 的四种重建新皮层神经元](https://modeldb.science/2488)**　用四种形态和共同通道分布比较放电模式，查看模型对应论文与具体文件。

model_code · ModelDB:2488 · 版本 未核实 · public · 许可 未核实 · 核实于 2026-11-26 · 共同来源 `mainen1996_geometry`。[依据](https://modeldb.science/2488)

标签　大脑皮层、单细胞、多区室模型、树突与轴突、神经元形态

本条 → [p_mainen](#p_mainen) · implements · 存储库将该 NEURON 模型归于 Mainen 与 Sejnowski 1996。。[出处](https://modeldb.science/2488)

### r_sbi_implementation

**[作者的生物物理参数推断实现](https://github.com/mackelab/IdentifyMechanisticModels_2020/tree/b93c90ec6156ae5f8afee6aaac7317373e9caf5e)**　定位模型、观测特征和推断实验的实现。

model_code · GitHub:mackelab/IdentifyMechanisticModels_2020 · 版本 b93c90ec6156ae5f8afee6aaac7317373e9caf5e · public · 许可 MIT · 核实于 2026-11-26 · 共同来源 `mackelab_IdentifyMechanisticModels_2020`。[依据](https://github.com/mackelab/IdentifyMechanisticModels_2020)

https://github.com/mackelab/IdentifyMechanisticModels_2020/blob/b93c90ec6156ae5f8afee6aaac7317373e9caf5e/LICENSE

标签　生物物理模型、概率与统计生成模型、数值方法

本条 → [p_sbi](#p_sbi) · implements · 当前可定位的仓库版本。论文原始运行所用提交需按文中另核。。[出处](https://github.com/mackelab/IdentifyMechanisticModels_2020)

### r_hier_code

**[层级异质性脑网络模型](https://github.com/murat-demirtas/heterogeneity/tree/2ac00d730ce5f3cf8256165066a203c7a519025b)**　核对区域异质性的参数化及成像功能连接的模拟方法。

model_code · GitHub:murat-demirtas/heterogeneity · 版本 2ac00d730ce5f3cf8256165066a203c7a519025b · public · 许可 未核实 · 核实于 2026-11-26 · 共同来源 `murat-demirtas_heterogeneity`。[依据](https://github.com/murat-demirtas/heterogeneity)

https://github.com/murat-demirtas/heterogeneity

标签　人类、大脑皮层、脑区间网络、神经群体模型

本条 → [p_hierarchy](#p_hierarchy) · implements · 当前可定位的仓库版本。论文原始运行所用提交需按文中另核。。[出处](https://github.com/murat-demirtas/heterogeneity)

### r_nwb_spec

**[Neurodata Without Borders 格式规范](https://github.com/NeurodataWithoutBorders/nwb-schema/tree/3ada52e0152847c937e168fd9565d95b37582112)**　统一表示记录、刺激、细胞/试次元数据，帮助复算。

format · GitHub:NeurodataWithoutBorders/nwb-schema · 版本 3ada52e0152847c937e168fd9565d95b37582112 · public · 许可 以固定版本 license.txt 的再分发条款为准 · 核实于 2026-11-26 · 共同来源 `NeurodataWithoutBorders_nwb-schema`。[依据](https://github.com/NeurodataWithoutBorders/nwb-schema)

https://github.com/NeurodataWithoutBorders/nwb-schema/blob/3ada52e0152847c937e168fd9565d95b37582112/license.txt

标签　复现与互操作、细胞内记录、行为观测

本条 → [p_nwb](#p_nwb) · specification_for · 当前可定位的仓库版本。论文原始运行所用提交需按文中另核。。[出处](https://github.com/NeurodataWithoutBorders/nwb-schema)

### r_mn_model

**[作者的运动单位驱动肌肉模型](https://github.com/ArnaultCAILLET/MN-driven-Neuromuscular-Model-with-motor-unit-resolution/tree/688a8d94a817d3312892182b4d9b03f180bf0610)**　从运动单位活动生成肌肉力，核对实际实现。

model_code · GitHub:ArnaultCAILLET/MN-driven-Neuromuscular-Model-with-motor-unit-resolution · 版本 688a8d94a817d3312892182b4d9b03f180bf0610 · public · 许可 未核实 · 核实于 2026-11-26 · 共同来源 `ArnaultCAILLET_MN-driven-Neuromuscular-Model-with-motor-unit-resolution`。[依据](https://github.com/ArnaultCAILLET/MN-driven-Neuromuscular-Model-with-motor-unit-resolution)

https://github.com/ArnaultCAILLET/MN-driven-Neuromuscular-Model-with-motor-unit-resolution

标签　人类、神经肌肉系统、运动控制、观测信号生成

本条 → [p_muscle](#p_muscle) · implements · 当前可定位的仓库版本。论文原始运行所用提交需按文中另核。。[出处](https://github.com/ArnaultCAILLET/MN-driven-Neuromuscular-Model-with-motor-unit-resolution)

### r_granule_osb

**[Open Source Brain 小脑颗粒层网络](https://github.com/OpenSourceBrain/GranCellLayer/tree/cee8604721c8654c24d3c69cedc07edb9679d935)**　可检查经典小脑颗粒层网络的三维移植与原模型差异。

model_code · GitHub:OpenSourceBrain/GranCellLayer · 版本 cee8604721c8654c24d3c69cedc07edb9679d935 · public · 许可 MIT · 核实于 2026-11-26 · 共同来源 `OpenSourceBrain_GranCellLayer`。[依据](https://github.com/OpenSourceBrain/GranCellLayer)

https://raw.githubusercontent.com/OpenSourceBrain/GranCellLayer/cee8604721c8654c24d3c69cedc07edb9679d935/LICENSE

标签　局部微环路、小脑、脉冲网络

本条 → [p_maex](#p_maex) · implements · 当前可定位的仓库版本。论文原始运行所用提交需按文中另核。。[出处](https://github.com/OpenSourceBrain/GranCellLayer)

本条 ← [p_osb](#p_osb) · platform_example · 该资源可经 Open Source Brain 的小脑模型专题检索。。[出处](https://v1.opensourcebrain.org/docs/Research_Themes/)

### r_dandi000003

**[Physiological Properties and Behavioral Correlates of Hippocampal Granule Cells and Mossy Cells](https://dandiarchive.org/dandiset/000003/0.261122.2143)**　按细胞标签与脑状态重算齿状回/CA3 发放与 LFP；101 次会话来自 16 只小鼠。

processed · DANDI:000003 · 版本 0.261122.2143 · public · 许可 CC BY 4.0 · 核实于 2026-11-26 · 共同来源 `dandi_000003`。[依据](https://api.dandiarchive.org/api/dandisets/000003/versions/0.261122.2143/)

具体数据形态见条目说明及档案清单，000003 为分选单位、LFP 等归档输出。

本批已核对采集论文，尚未核实使用这批记录拟合的建模论文

标签　小鼠、海马、在体、局部场电位记录、尖峰时间、行为观测

本条 → [p_senzai](#p_senzai) · described_by · 版本记录的 relatedResource 指向采集研究。。[出处](https://api.dandiarchive.org/api/dandisets/000003/versions/0.261122.2143/)

### r_dandi000005

**[Electrophysiology data from thalamic and cortical neurons during somatosensation](https://dandiarchive.org/dandiset/000005/0.220126.1853)**　在触须定位任务中将细胞内/外电生理与触觉协议对应，用于约束丘脑皮层输入。

raw · DANDI:000005 · 版本 0.220126.1853 · public · 许可 CC BY 4.0 · 核实于 2026-11-26 · 共同来源 `dandi_000005`。[依据](https://api.dandiarchive.org/api/dandisets/000005/versions/0.220126.1853/)

NWB 归档，原始与已转换/加工字段需按文件核对。

本批已核对采集论文，尚未核实使用这批记录拟合的建模论文

标签　小鼠、大脑皮层、丘脑、细胞内记录、在体、任务态、感觉编码

本条 → [p_filter](#p_filter) · described_by · 版本记录的 relatedResource 指向采集研究。。[出处](https://api.dandiarchive.org/api/dandisets/000005/versions/0.220126.1853/)

### r_dandi000006

**[Mouse anterior lateral motor cortex (ALM) in delay response task](https://dandiarchive.org/dandiset/000006/0.220126.1855)**　读取延迟反应任务中小鼠前外侧运动皮层细胞的活动，比较不同投射群。

raw · DANDI:000006 · 版本 0.220126.1855 · public · 许可 CC BY 4.0 · 核实于 2026-11-26 · 共同来源 `dandi_000006`。[依据](https://api.dandiarchive.org/api/dandisets/000006/versions/0.220126.1855/)

NWB 归档，原始与已转换/加工字段需按文件核对。

本批已核对采集论文，尚未核实使用这批记录拟合的建模论文

标签　小鼠、大脑皮层、胞外单单位、任务态、运动控制

本条 → [p_economo](#p_economo) · described_by · 版本记录的 relatedResource 指向采集研究。。[出处](https://api.dandiarchive.org/api/dandisets/000006/versions/0.220126.1855/)

### r_muscle_zen

**[分割影像与个体化肌骨模型](https://zenodo.org/records/10069266)**　约束个体结构；此条目不是受试者完整原始肌电。

processed · Zenodo:10069266 · 版本 10069266 · public · 许可 CC BY 4.0 · 核实于 2026-11-26 · 共同来源 `caillet_subject_geometry`。[依据](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1011606)

https://zenodo.org/records/10069266

标签　人类、神经肌肉系统、神经元形态

本条 → [p_muscle](#p_muscle) · provides_geometry · 论文数据声明列出分割影像和肌骨模型。。[出处](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1011606)

### r_dandi000458

**[Simultaneous electroencephalography, extracellular electrophysiology, and cortical electrical stimulation in head-fixed mice](https://dandiarchive.org/dandiset/000458/0.230317.0039)**　读取同一实验在清醒与异氟烷麻醉阶段的 EEG、可用 Neuropixels 记录和刺激事件，核实各会话实际电极与阶段。

raw · DANDI:000458 · 版本 0.230317.0039 · public · 许可 CC BY 4.0 · 核实于 2026-11-26 · 共同来源 `claar_eeg_np`。[依据](https://api.dandiarchive.org/api/dandisets/000458/versions/0.230317.0039/)

标签　大脑皮层、丘脑、小鼠、在体、清醒、麻醉、异氟烷、头皮脑电、局部场电位记录、诱发反应、尖峰时间

本条 → [p_claar](#p_claar) · archived_observations_for · 同一实验归档，固定版本 24 个文件，包括刺激和状态相关记录。。[出处](https://api.dandiarchive.org/api/dandisets/000458/versions/0.230317.0039/)

本条 → [o_claar_rate_cortex](#o_claar_rate_cortex) · supports · 归档原试验，面板指标仍须依作者纳入和窗口重算。。[出处](https://api.dandiarchive.org/api/dandisets/000458/versions/0.230317.0039/)

本条 → [o_claar_rate_thalamus](#o_claar_rate_thalamus) · supports · 归档原试验，面板指标仍须依作者纳入和窗口重算。。[出处](https://api.dandiarchive.org/api/dandisets/000458/versions/0.230317.0039/)

### r_dandi001622_registry

**[In vivo electrophysiology recordings from the ventral hippocampus of anesthetized rats](https://dandiarchive.org/dandiset/001622/draft)**　记录麻醉成年大鼠海马的具体数据集登记；核实时资产数为 0，等待原始信号开放。

portal · DANDI:001622 · 版本 draft · not_located · 许可 spdx:CC-BY-4.0 · 核实于 2026-11-26 · 共同来源 `dandi_001622`。[依据](https://api.dandiarchive.org/api/dandisets/001622/versions/draft/)

登记元数据可公开阅读，draft 的 assetsSummary.numberOfFiles=0。不能据标题宣称可下载原始记录。

本批未定位使用该草稿进行建模的论文

标签　大鼠、海马、麻醉、在体、自发活动

### r_breadth_fafb_image

**[Full Adult Fly Brain (FAFB) EM image volume](https://storage.googleapis.com/neuroglancer-fafb-data/fafb_v14/fafb_v14_orig/info)**　云端元数据公开列出 4×4×40 nm 的图像体素和数据层。可回看超微结构，区别于派生的神经元连接表。

raw · FAFB v14, fafb_v14_orig · 版本 v14；已对齐的图像体版本 · public · 许可 Janelia 数据下载页注明 CC BY-NC 4.0。 · 核实于 2026-11-26 · 共同来源 `fafb_single_female_2018`。[依据](https://www.janelia.org/open-science/complete-fly-brain-image)

标签　电子显微成像、体积成像、果蝇、成年、昆虫

本条 ← [p_breadth_zheng2018](#p_breadth_zheng2018) · deposited_image_volume · 原始电镜成像组发布的同一成年雌蝇脑；云端 v14 的元数据描述已对齐图像体。。[出处](https://www.janelia.org/open-science/complete-fly-brain-image)

本条 ← [r_breadth_flywire783](#r_breadth_flywire783) · derived_from · 连接表与电镜图像共享原始标本，不能当作两只动物评估独立重复。。[出处](https://www.nature.com/articles/s41586-024-07558-y)

### r_breadth_flywire783

**[FlyWire Whole-brain Connectome Connectivity Data](https://zenodo.org/records/10676866)**　公开文件表含已校对神经元、连接和全部检测点，按具体端点与版本筛选。

processed · 10.5281/zenodo.10676866 · 版本 783.0 · public · 许可 CC BY 4.0 · 核实于 2026-11-26 · 共同来源 `fafb_single_female_2018`。[依据](https://zenodo.org/records/10676866)

标签　连接组、处理后资料、果蝇、昆虫

本条 ← [p_breadth_dorkenwald2024](#p_breadth_dorkenwald2024) · provides_processed_data · 数据发布说明指向论文的 Synaptic connections 方法。。[出处](https://zenodo.org/records/10676866)

本条 → [r_breadth_fafb_image](#r_breadth_fafb_image) · derived_from · 连接表与电镜图像共享原始标本，不能当作两只动物评估独立重复。。[出处](https://www.nature.com/articles/s41586-024-07558-y)

### r_breadth_fish_thermal

**[Data accompanying The preoptic area and dorsal habenula jointly support homeostatic navigation in larval zebrafish](https://zenodo.org/records/10281421)**　公开 Data.zip 目录说明列出逐鱼的荧光轨迹、坐标和行为，以及消融与对照；可按鱼划分建模和检验数据。

processed · 10.5281/zenodo.10281421 · 版本 版本 DOI 所指的 2023-12-07 存档，作者未另设版本号 · public · 许可 CC BY 4.0 · 核实于 2026-11-26 · 共同来源 `palieri_thermal_navigation`。[依据](https://zenodo.org/records/10281421)

标签　钙成像、行为观测、温度刺激或控制、斑马鱼、幼体、鱼类

本条 ← [p_breadth_palieri2024](#p_breadth_palieri2024) · provides_processed_data · 存档说明链接同一工作预印本，发表论文说明同一 DOI 的数据可用性。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC10849091/)

### r_breadth_lfpy200

**[LFPy v2.0.0 archived release](https://zenodo.org/records/1401088)**　采用论文指定的模型代码和示例复算多区室网络至各类传感器的转换。

model_code · 10.5281/zenodo.1401088 · 版本 v2.0.0 · public · 许可 GPL-3.0，按该版本仓库 LICENSE 核对。 · 核实于 2026-11-26 · 共同来源 `hagen_lfpy_demo`。[依据](https://raw.githubusercontent.com/LFPy/LFPy/v2.0.0/LICENSE)

标签　LFPy 场信号计算、观测信号生成、资源发行版

本条 ← [p_breadth_hagen2018](#p_breadth_hagen2018) · provides_model_code · 论文数据可用性段指向这份冻结的软件版本。。[出处](https://www.frontiersin.org/journals/neuroinformatics/articles/10.3389/fninf.2018.00092/full)

### r_breadth_crcns_hc3

**[CRCNS hc-3: rat hippocampal and entorhinal multi-unit recordings](https://crcns.org/data-sets/hc/hc-3)**　下载清单含已检测的尖峰时间和波形、单元分组、LFP、部分会话头部位置及元数据。需依据动物、脑区与行为筛选。

processed · 10.6080/K09G5JRZ · 版本 CRCNS hc-3，2013 年条目，未单列版本号 · registration · 许可 DataCite 未列标准许可证。CRCNS 下载需免费账户，发布页要求引用数据集和相关论文。 · 核实于 2026-11-26 · 共同来源 `crcns_hc3_original`。[依据](https://crcns.org/data-sets/hc/hc-3/about-hc-3)

标签　CRCNS 数据库、大鼠、胞外记录、海马、内嗅皮层、大脑皮层

本条 ← [p_breadth_mizuseki2014](#p_breadth_mizuseki2014) · describes_dataset · 期刊首版正文直接链接同一数据 DOI，数据库亦列该文之后的 v2。。[出处](https://f1000research.com/articles/3-98/v1)

### r_breadth_dandi000070

**[Neural population dynamics during reaching](https://dandiarchive.org/dandiset/000070/0.261122.2046)**　该版本 DOI 为 10.48324/dandi.000070/0.261122.2046，公开列出 2 只猕猴的 10 个 NWB 文件，含电生理与运动信息。原论文两次阵列记录的日期能在文件表内定位。

raw · DANDI:000070 · 版本 0.261122.2046 · public · 许可 CC BY 4.0 · 核实于 2026-11-26 · 共同来源 `churchland_reaching_original`。[依据](https://api.dandiarchive.org/api/dandisets/000070/versions/0.261122.2046/)

标签　DANDI 档案、运动皮层、伸手到达任务、神经生理数据格式、胞外记录、大脑皮层

本条 → [p_breadth_churchland2012](#p_breadth_churchland2012) · is_described_by · DANDI 的 relatedResource 明确给出论文 DOI。文件表有 J 2009-09-18 及 N 2010-09-23，与论文 Methods 的阵列会话日期相符。。[出处](https://api.dandiarchive.org/api/dandisets/000070/versions/0.261122.2046/)

### r_cell_mensi_code

**[Mensi 等作者提交的 MATLAB 参数拟合和放电模型](https://modeldb.science/143148)**　作者说明示范 fit_IF 对同一模型生成的替代数据拟合；可作参数回收与模型运行示例。未在此包中定位到 Fig. 4 的原始脑片记录。

model_code · ModelDB 143148 · 版本 ModelDB 镜像提交 62e7dba0a1ce5cfa7ff421331a02916990d5f1e4 · public · 许可 归档和作者说明中未核实独立许可。 · 核实于 2026-11-26 · 共同来源 `mensipatch_l23`。[依据](https://github.com/ModelDBRepository/143148/tree/62e7dba0a1ce5cfa7ff421331a02916990d5f1e4)

标签　放电适应、单细胞、点神经元、大脑皮层、小鼠、有效动力学模型、替代数据分析

本条 ← [p_cell_mensi](#p_cell_mensi) · author_model · ModelDB 将该实现归于 Mensi。包内示例使用模型生成的替代数据。。[出处](https://modeldb.science/143148)

### r_cell_teeter_analysis

**[Allen Institute 的 Teeter 等论文章节、主图脚本和拟合配置](https://github.com/AllenInstitute/GLIF_Teeter_et_al_2018/tree/dcb232354b1a5c3e348d163cb479ae2ee10c564d)**　作图脚本关联示例细胞与模型，可重建论文比较的输入输出关系；原环境注明 Python 2.7，数值复现需另核对依赖。

analysis_code · AllenInstitute/GLIF_Teeter_et_al_2018 · 版本 dcb232354b1a5c3e348d163cb479ae2ee10c564d · public · 许可 Allen Institute Software License，二条款 BSD 加商业再分发须另行许可条款。 · 核实于 2026-11-26 · 共同来源 `allen_ctdb_mouse`。[依据](https://github.com/AllenInstitute/GLIF_Teeter_et_al_2018/blob/dcb232354b1a5c3e348d163cb479ae2ee10c564d/MTfig_1b/make_and_save_model_data.py)

标签　放电适应、单细胞、点神经元、大脑皮层、小鼠、波动电流

本条 ← [p_cell_teeter](#p_cell_teeter) · author_analysis · Allen Institute 官方仓库存放论文作图与分析实现。。[出处](https://github.com/AllenInstitute/GLIF_Teeter_et_al_2018/tree/dcb232354b1a5c3e348d163cb479ae2ee10c564d)

本条 → [r_cell_allen_glif](#r_cell_allen_glif) · uses_solver · 作图实现调用 AllenSDK 的 GLIF 神经元；索引的 SDK 标签用于查实现，未据此认定论文使用该版本。。[出处](https://github.com/AllenInstitute/GLIF_Teeter_et_al_2018/blob/dcb232354b1a5c3e348d163cb479ae2ee10c564d/MTfig_1b/make_and_save_model_data.py)

本条 → [r_cell_allen_ctgf](#r_cell_allen_ctgf) · illustrates_specimen · Fig. 1b 作图脚本显式使用 Ctgf 标本 512322162。。[出处](https://github.com/AllenInstitute/GLIF_Teeter_et_al_2018/blob/dcb232354b1a5c3e348d163cb479ae2ee10c564d/MTfig_1b/make_and_save_model_data.py)

### r_cell_allen_glif

**[AllenSDK 的 GLIF 单细胞仿真实现](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/model/glif/glif_neuron.py)**　使用模型配置与规定的电流波形重放放电预测；与论文本身的绘图实现相连。

model_code · AllenInstitute/AllenSDK, glif_neuron.py · 版本 v2.16.2；此次核对的可固定版本，未作为论文使用版本核实。 · public · 许可 Allen Institute Software License，二条款 BSD 加商业再分发须另行许可条款。 · 核实于 2026-11-26 · 共同来源 `allen_sdk`。[依据](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/LICENSE.txt)

标签　放电适应、单细胞、点神经元、动作电位阈值、波动电流

本条 ← [r_cell_teeter_analysis](#r_cell_teeter_analysis) · uses_solver · 作图实现调用 AllenSDK 的 GLIF 神经元；索引的 SDK 标签用于查实现，未据此认定论文使用该版本。。[出处](https://github.com/AllenInstitute/GLIF_Teeter_et_al_2018/blob/dcb232354b1a5c3e348d163cb479ae2ee10c564d/MTfig_1b/make_and_save_model_data.py)

### r_cell_allen_isi

**[AllenSDK 的相邻放电间隔适应指数](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/ephys/ephys_features.py#L756-L770)**　以代码运算符为准，(后一个 ISI − 前一个 ISI)/(两者和) 的均值；间隔不足 2 个记为缺失。被引用版本的 docstring 和实际实现的差值方向不一致。

analysis_code · AllenInstitute/AllenSDK，adaptation_index/norm_diff · 版本 v2.16.2 · public · 许可 Allen Institute Software License，二条款 BSD 加商业再分发须另行许可条款。 · 核实于 2026-11-26 · 共同来源 `allen_sdk`。[依据](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/ephys/ephys_features.py#L756-L770)

标签　放电适应、单细胞、细胞内记录、发放率、放电间隔、阶跃电流

本条 ← [r_cell_allen_mouse_feature](#r_cell_allen_mouse_feature) · uses_metric · 可用相邻 ISI 的后减前归一化差重算。。[出处](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/ephys/ephys_features.py#L756-L770)

本条 ← [r_cell_allen_human_feature](#r_cell_allen_human_feature) · uses_metric · 使用相同的实际运行公式，可以跨样本检查程序；两物种单细胞样本的差值不足以判断物种效应。。[出处](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/ephys/ephys_features.py#L756-L770)

### r_cell_allen_hero

**[AllenSDK 代表性长阶跃的选取与每细胞特征回连](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/ephys/extract_cell_features.py#L126-L140)**　将每个细胞的 adaptation 和 thumbnail_sweep_id 回连同一代表性长阶跃；作者实现通常在阈电流以上约 40–60 pA 的候选中选取。

analysis_code · AllenInstitute/AllenSDK，extract_cell_features 与 core_feature_extract · 版本 v2.16.2 · public · 许可 Allen Institute Software License，二条款 BSD 加商业再分发须另行许可条款。 · 核实于 2026-11-26 · 共同来源 `allen_sdk`。[依据](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/internal/ephys/core_feature_extract.py#L145-L159)

标签　放电适应、单细胞、膜片钳、放电间隔、阶跃电流

本条 ← [r_cell_allen_mouse_feature](#r_cell_allen_mouse_feature) · sweep_selection · 每细胞的适应来自指定代表性长阶跃。。[出处](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/internal/ephys/core_feature_extract.py#L145-L159)

### r_cell_allen_nwb_reader

**[AllenSDK 早期 IVSCC 记录的电流单位与版本转换](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/core/nwb_data_set.py#L87-L109)**　读取 general/generated_by 的分析管线版本。IVSCC 1.0 的电流样本已经是安培，转 pA 乘 10¹²；盲乘早期文件的 conversion 属性会误读人样本幅度。

analysis_code · AllenInstitute/AllenSDK，NwbDataSet.get_sweep · 版本 v2.16.2 · public · 许可 Allen Institute Software License，二条款 BSD 加商业再分发须另行许可条款。 · 核实于 2026-11-26 · 共同来源 `allen_sdk`。[依据](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/core/nwb_data_set.py#L203-L230)

标签　单细胞、细胞内记录、阶跃电流、神经生理数据格式、计量单位

本条 ← [r_cell_allen_human_raw](#r_cell_allen_human_raw) · uses_unit_convention · 早期生成管线采用已按 SI 单位储存的输入。。[出处](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/core/nwb_data_set.py#L87-L109)

### r_cell_gouwens_table

**[Gouwens 等 Supplementary Dataset 3 电生理样本名单与分类](https://static-content.springer.com/esm/art%3A10.1038%2Fs41593-019-0417-0/MediaObjects/41593_2019_417_MOESM5_ESM.xlsx)**　用 specimen_id 联回标本；Data 表第 7、272、946 行分别为 313861794、474637203、512322162，后两例也用于 Teeter 的绘图。

processed · 41593_2019_417_MOESM5_ESM.xlsx，工作表 Data · 版本 2019 年正式论文附件，未单独编号 · public · 许可 出版商论文补充资料，未单独核实电子表的再分发许可。 · 核实于 2026-11-26 · 共同来源 `allen_ctdb_mouse`。[依据](https://www.nature.com/articles/s41593-019-0417-0)

标签　单细胞、膜片钳、细胞内记录、大脑皮层、小鼠、离体、细胞类型分类

本条 ← [p_cell_gouwens](#p_cell_gouwens) · publishes · 补充数据集以 specimen_id 登记电生理标本。。[出处](https://www.nature.com/articles/s41593-019-0417-0)

本条 → [r_cell_allen_mouse_raw](#r_cell_allen_mouse_raw) · lists_specimen · Data 表第 7 行登记小鼠标本 313861794，使用标本号映射到原始记录。。[出处](https://static-content.springer.com/esm/art%3A10.1038%2Fs41593-019-0417-0/MediaObjects/41593_2019_417_MOESM5_ESM.xlsx)

本条 → [r_cell_allen_ctgf](#r_cell_allen_ctgf) · lists_same_specimen · Data 表第 946 行为 512322162，表内第 272 行为也出现在 Teeter 脚本的 474637203。。[出处](https://static-content.springer.com/esm/art%3A10.1038%2Fs41593-019-0417-0/MediaObjects/41593_2019_417_MOESM5_ESM.xlsx)

### r_cell_allen_mouse_raw

**[小鼠 VISl4 有棘细胞 313861794 的胞体电压、电流和脉冲时刻](https://api.brain-map.org/api/v2/well_known_file_download/491200821)**　首条可以复算的单细胞阶跃。60 个扫次内有 20 个 Long Square；Sweep_35 以 200 kHz 采样，输入在阶跃内约 150 pA，刺激前后为 0 pA。读 /analysis/spike_times/Sweep_35 可重算指标。

raw · specimen 313861794；well-known file 491200821；donor 313401484 · 版本 NWB-1.0.5，IVSCC 1.0 · public · 许可 Allen Institute Terms of Use 与 Citation Policy；学术/非商业使用按条款，其他使用须审查。未核实独立 CC 许可。 · 核实于 2026-11-26 · 共同来源 `allen_ctdb_mouse`。[依据](https://api.brain-map.org/api/v2/data/Specimen/313861794.json?include=donor,structure)

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、放电间隔、大脑皮层、小鼠、离体、阶跃电流、神经生理数据格式、皮层第四层

本条 ← [r_cell_gouwens_table](#r_cell_gouwens_table) · lists_specimen · Data 表第 7 行登记小鼠标本 313861794，使用标本号映射到原始记录。。[出处](https://static-content.springer.com/esm/art%3A10.1038%2Fs41593-019-0417-0/MediaObjects/41593_2019_417_MOESM5_ESM.xlsx)

本条 ← [r_cell_allen_mouse_feature](#r_cell_allen_mouse_feature) · derived_from · 扫次 ID 396301642 连到标本 313861794 的 #35。公开脉冲时间重算的结果与特征表一致。。[出处](https://api.brain-map.org/api/v2/data/EphysSweep/396301642.json)

本条 → [r_cell_allen_terms](#r_cell_allen_terms) · access_terms · 原始数据按 Allen Institute 的数据使用和引用条件访问。。[出处](https://alleninstitute.org/legal/terms-use/)

本条 → [r_cell_allen_protocol](#r_cell_allen_protocol) · uses_protocol · 用官方电生理技术白皮书核对长阶跃与代表性扫次的选择，并以具名扫次的实际记录核对幅度和时间。。[出处](https://s3.amazonaws.com/webflow-prod-assets/689cfbd308fa7373b604d290/68ee796e6df1cc984c3ab432_Documentation_Cell_Types_Database-Electrophysiology_Overview.pdf)

### r_cell_allen_mouse_feature

**[Allen 小鼠标本 313861794 的每细胞特征和代表性扫次](https://api.brain-map.org/api/v2/data/EphysFeature/396463405.json)**　从 thumbnail_sweep_id 找到 1.02 s 起、约 1 s 的 150 pA 阶跃；标准化 ISI 适应指数为 0.299873232107749，4 个脉冲。该数来自一个细胞。

processed · EphysFeature 396463405；EphysSweep 396301642 (#35) · 版本 具名 RMA 记录，未单独编号 · public · 许可 Allen Institute Terms of Use 与 Citation Policy；学术/非商业使用按条款，其他使用须审查。未核实独立 CC 许可。 · 核实于 2026-11-26 · 共同来源 `allen_ctdb_mouse`。[依据](https://api.brain-map.org/api/v2/data/EphysSweep/396301642.json)

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、放电间隔、大脑皮层、小鼠、离体、阶跃电流、皮层第四层

本条 ← [o_cell_gouwens_mouse_index](#o_cell_gouwens_mouse_index) · derived_feature · 该特征从同一细胞的代表性长阶跃计算；门户数值归于数据产品。。[出处](https://api.brain-map.org/api/v2/data/EphysFeature/396463405.json)

本条 → [r_cell_allen_mouse_raw](#r_cell_allen_mouse_raw) · derived_from · 扫次 ID 396301642 连到标本 313861794 的 #35。公开脉冲时间重算的结果与特征表一致。。[出处](https://api.brain-map.org/api/v2/data/EphysSweep/396301642.json)

本条 → [r_cell_allen_isi](#r_cell_allen_isi) · uses_metric · 可用相邻 ISI 的后减前归一化差重算。。[出处](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/ephys/ephys_features.py#L756-L770)

本条 → [r_cell_allen_hero](#r_cell_allen_hero) · sweep_selection · 每细胞的适应来自指定代表性长阶跃。。[出处](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/internal/ephys/core_feature_extract.py#L145-L159)

### r_cell_allen_human_raw

**[人额下回 L3 有棘细胞 486940963 的胞体电压、电流和脉冲时刻](https://api.brain-map.org/api/v2/well_known_file_download/664222041)**　71 个扫次内有 23 个 Long Square。Sweep_39 的 200 kHz 刺激记录在阶跃中为 1.9×10⁻¹⁰ A（190 pA）；该 1.0 文件使用已按 SI 储存的值。读 /analysis/spike_times/Sweep_39 可独立复算。

raw · specimen 486940963；well-known file 664222041；donor 486909083 · 版本 NWB-1.0.5，IVSCC 1.0 · public · 许可 Allen Institute Terms of Use 与 Citation Policy；学术/非商业使用按条款，其他使用须审查。未核实独立 CC 许可。 · 核实于 2026-11-26 · 共同来源 `allen_ctdb_human_486940963`。[依据](https://api.brain-map.org/api/v2/data/Specimen/486940963.json?include=donor,structure)

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、放电间隔、大脑皮层、人类、离体、阶跃电流、神经生理数据格式、皮层第三层

[Allen 标本 486940963，EphysSweep 486941688（Sweep_39），NWB /analysis/spike_times/Sweep_39，EphysFeature 486943542。](#o_allen_human_s39) · published_aggregate · 相邻放电间隔归一化差的均值（Allen adaptation）

本条 ← [r_cell_allen_human_feature](#r_cell_allen_human_feature) · derived_from · 扫次 ID 486941688 连到人标本 486940963 的 #39。公开脉冲时间重算的结果与特征表一致。。[出处](https://api.brain-map.org/api/v2/data/EphysSweep/486941688.json)

本条 → [r_cell_allen_nwb_reader](#r_cell_allen_nwb_reader) · uses_unit_convention · 早期生成管线采用已按 SI 单位储存的输入。。[出处](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/core/nwb_data_set.py#L87-L109)

本条 → [r_cell_allen_terms](#r_cell_allen_terms) · access_terms · 原始数据按 Allen Institute 的数据使用和引用条件访问。。[出处](https://alleninstitute.org/legal/terms-use/)

本条 → [r_cell_allen_protocol](#r_cell_allen_protocol) · uses_protocol · 用官方电生理技术白皮书核对长阶跃与代表性扫次的选择，并以具名扫次的实际记录核对幅度和时间。。[出处](https://s3.amazonaws.com/webflow-prod-assets/689cfbd308fa7373b604d290/68ee796e6df1cc984c3ab432_Documentation_Cell_Types_Database-Electrophysiology_Overview.pdf)

### r_cell_allen_human_feature

**[Allen 人额下回标本 486940963 的适应特征与代表性阶跃](https://api.brain-map.org/api/v2/data/EphysFeature/486943542.json)**　阈电流 150 pA；Sweep_39 自 1.02 s 起约 1 s，190 pA，9 个脉冲、8 个 ISI。RMA 预计算指数 0.187288525642607，依 NWB 时刻复算 0.1872885256426067。单供体、单细胞。

processed · EphysFeature 486943542；EphysSweep 486941688 (#39) · 版本 具名 RMA 记录，未单独编号 · public · 许可 Allen Institute Terms of Use 与 Citation Policy；学术/非商业使用按条款，其他使用须审查。未核实独立 CC 许可。 · 核实于 2026-11-26 · 共同来源 `allen_ctdb_human_486940963`。[依据](https://api.brain-map.org/api/v2/data/EphysSweep/486941688.json)

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、放电间隔、大脑皮层、人类、离体、阶跃电流、皮层第三层

本条 → [r_cell_allen_human_raw](#r_cell_allen_human_raw) · derived_from · 扫次 ID 486941688 连到人标本 486940963 的 #39。公开脉冲时间重算的结果与特征表一致。。[出处](https://api.brain-map.org/api/v2/data/EphysSweep/486941688.json)

本条 → [r_cell_allen_isi](#r_cell_allen_isi) · uses_metric · 使用相同的实际运行公式，可以跨样本检查程序；两物种单细胞样本的差值不足以判断物种效应。。[出处](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/ephys/ephys_features.py#L756-L770)

本条 ← [p_cell_wang](#p_cell_wang) · external_comparator · 两者均有人类胞体电流钳记录；组织区域和细胞亚型不同，且已发表适应比须先核实定义，不能合并为同一个量或声称来自同批标本。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC5067378/)

本条 → [o_allen_human_s39](#o_allen_human_s39) · reports_feature · 同一标本的预计算特征，原始阶跃脉冲时间可复算。。[出处](https://api.brain-map.org/api/v2/data/EphysFeature/486943542.json)

### r_cell_allen_ctgf

**[Teeter 和 Gouwens 共用的 Ctgf 小鼠细胞 512322162](https://api.brain-map.org/api/v2/data/EphysFeature/512323887.json)**　VISp6b 有棘细胞。与 Fig. 1b 代码及分类补表回连；另一个同细胞长阶跃 #38 有 13 个脉冲，公开指数 0.0246543952304564。Noise 2 重复用于时序测试。

processed · specimen 512322162；donor 511856495；EphysFeature 512323887；EphysSweep 512322448 (#38) · 版本 RMA 具名记录，未单独编号 · public · 许可 Allen Institute Terms of Use 与 Citation Policy；学术/非商业使用按条款，其他使用须审查。未核实独立 CC 许可。 · 核实于 2026-11-26 · 共同来源 `allen_ctdb_mouse`。[依据](https://api.brain-map.org/api/v2/data/EphysSweep/512322448.json)

标签　放电适应、单细胞、细胞内记录、发放率、放电间隔、大脑皮层、小鼠、离体、阶跃电流、波动电流

本条 ← [r_cell_teeter_analysis](#r_cell_teeter_analysis) · illustrates_specimen · Fig. 1b 作图脚本显式使用 Ctgf 标本 512322162。。[出处](https://github.com/AllenInstitute/GLIF_Teeter_et_al_2018/blob/dcb232354b1a5c3e348d163cb479ae2ee10c564d/MTfig_1b/make_and_save_model_data.py)

本条 ← [r_cell_gouwens_table](#r_cell_gouwens_table) · lists_same_specimen · Data 表第 946 行为 512322162，表内第 272 行为也出现在 Teeter 脚本的 474637203。。[出处](https://static-content.springer.com/esm/art%3A10.1038%2Fs41593-019-0417-0/MediaObjects/41593_2019_417_MOESM5_ESM.xlsx)

### r_cell_allen_terms

**[Allen Institute 数据访问许可与引用条件](https://alleninstitute.org/legal/terms-use/)**　申请重新分发、商业用途或获取更新版本时以链接条件为准；数据条款和软件许可证分别记录。

portal · Allen Institute Terms of Use; Citation Policy · 版本 核对日条款，未单独编号 · public · 许可 网页列明使用及引用条件。 · 核实于 2026-11-26 · 共同来源 `allen_terms`。[依据](https://alleninstitute.org/legal/citation-policy/)

标签　资源访问条件、资源许可

本条 ← [r_cell_allen_mouse_raw](#r_cell_allen_mouse_raw) · access_terms · 原始数据按 Allen Institute 的数据使用和引用条件访问。。[出处](https://alleninstitute.org/legal/terms-use/)

本条 ← [r_cell_allen_human_raw](#r_cell_allen_human_raw) · access_terms · 原始数据按 Allen Institute 的数据使用和引用条件访问。。[出处](https://alleninstitute.org/legal/terms-use/)

### r_cell_allen_protocol

**[Allen Cell Types Database 技术白皮书：Electrophysiology](https://s3.amazonaws.com/webflow-prod-assets/689cfbd308fa7373b604d290/68ee796e6df1cc984c3ab432_Documentation_Cell_Types_Database-Electrophysiology_Overview.pdf)**　原作者说明鼠和人切片的全细胞方案、长阶跃与特征选择。文中说明代表性长阶跃在阈电流上方 40–60 pA 的候选中取最低合适幅度；复算须使用相应扫次的实际输入与时窗。

protocol · Allen Cell Types Database Technical White Paper · 版本 October 2017 v.5 · public · 许可 PDF 公开，独立再分发条款未在本文中另行核实。 · 核实于 2026-11-26 · 共同来源 `allen_ctdb_protocol`。[依据](https://s3.amazonaws.com/webflow-prod-assets/689cfbd308fa7373b604d290/68ee796e6df1cc984c3ab432_Documentation_Cell_Types_Database-Electrophysiology_Overview.pdf)

标签　放电适应、单细胞、膜片钳、细胞内记录、发放率、放电间隔、大脑皮层、小鼠、人类、离体、阶跃电流

本条 ← [r_cell_allen_mouse_raw](#r_cell_allen_mouse_raw) · uses_protocol · 用官方电生理技术白皮书核对长阶跃与代表性扫次的选择，并以具名扫次的实际记录核对幅度和时间。。[出处](https://s3.amazonaws.com/webflow-prod-assets/689cfbd308fa7373b604d290/68ee796e6df1cc984c3ab432_Documentation_Cell_Types_Database-Electrophysiology_Overview.pdf)

本条 ← [r_cell_allen_human_raw](#r_cell_allen_human_raw) · uses_protocol · 用官方电生理技术白皮书核对长阶跃与代表性扫次的选择，并以具名扫次的实际记录核对幅度和时间。。[出处](https://s3.amazonaws.com/webflow-prod-assets/689cfbd308fa7373b604d290/68ee796e6df1cc984c3ab432_Documentation_Cell_Types_Database-Electrophysiology_Overview.pdf)

### r_bajwa_openneuro

**[A repeated awakening study exploring the capacity of complexity measures to capture dreaming during propofol sedation](https://openneuro.org/datasets/ds005620/versions/1.0.0)**　已在公开对象存储实际读取 sub-1016 的 task-awake_acq-EC_eeg.eeg 和 task-sed_acq-rest_run-1_eeg.eeg，两者均返回 206 并读到不同信号字节；同人另有睁眼、TMS、其他镇静静息文件。可对清醒及丙泊酚深镇静的静息频谱订同窗重算。participants.tsv 有 21 条，须按 excluded/质量及原文 20 名完成者筛选并核对受试者编号写法。

raw · OpenNeuro:ds005620；10.18112/openneuro.ds005620.v1.0.0 · 版本 1.0.0 · public · 许可 CC0（固定版数据说明） · 核实于 2026-11-26 · 共同来源 `bajwa_oslo_propofol_sedation_2025`。[依据](https://raw.githubusercontent.com/OpenNeuroDatasets/ds005620/1.0.0/dataset_description.json)

标签　清醒、镇静、网络节律、头皮脑电、人类、在体、神经群体、大脑皮层、丙泊酚、静息、功率谱

本条 ← [p_bajwa2025](#p_bajwa2025) · deposits_raw_data · 论文 Data availability 明列固定版 DOI。。[出处](https://www.nature.com/articles/s41598-025-12695-z)

本条 → [o_purdon_frontal](#o_purdon_frontal) · alternative_with_different_depth · 相同药物、人类和头皮 EEG，但这里明确为静息与目标 RASS −4 深镇静，可以外检协议依赖性；两文的状态终点与任务不同。。[出处](https://www.nature.com/articles/s41598-025-12695-z)

本条 → [o_bajwa_experience](#o_bajwa_experience) · archives_study · 同一深镇静实验归档；按原文报告类别和唤醒前的时间窗解释。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC12460656/)

### r_purdon_dandi

**[EEG Anesthesia Dataset（单一被试的归档电位矩阵）](https://dandiarchive.org/dandiset/001285/0.250110.2125)**　固定版只含 sub-Subject001 的 1 个 NWB；远程读得 acquisition/example_timeseries/data，形状 64×2316950，标称 µV，标称 250 Hz。intervals、stimulus/presentation、processing 和 scratch 为空；文件说明为 EEG Session Example。可检查读取与频谱流程，研究方案引用 Purdon，不足以证明文件对应论文哪个受试者、分期区间或未经处理。

raw · DANDI:001285；10.48324/dandi.001285/0.250110.2125 · 版本 0.250110.2125 · public · 许可 CC BY 4.0 · 核实于 2026-11-26 · 共同来源 `purdon_mgh_gradual_propofol_2013`。[依据](https://api.dandiarchive.org/api/dandisets/001285/versions/0.250110.2125/)

标签　清醒、麻醉、头皮脑电、网络节律、功率谱、人类、神经群体、丙泊酚、部分样本归档

本条 → [p_purdon2013](#p_purdon2013) · references_acquisition_protocol · DANDI 引用该论文的十人实验设计；固定版清单只有一份记录，个体对应未独立证实。。[出处](https://api.dandiarchive.org/api/dandisets/001285/versions/0.250110.2125/)

### r_xiong_tfr

**[Local/global propofol oddball](https://figshare.com/articles/dataset/Local_global_propofol_oddball/26980630/1)**　实际打开 TFR_all.mat（590850519 字节）。TFR_awk_all 与 TFR_ans_all 均含 area、global、nonglobal、local、nonlocal，并含 freq_label、time_label。可用相同时间、频率、区域与控制条件复算已处理的时频比较；动物标识、预处理与通道选择仍应核对。

processed · 10.6084/m9.figshare.26980630.v1 · 版本 v1；文件 49295326 · public · 许可 CC BY 4.0 · 核实于 2026-11-26 · 共同来源 `xiong_monkeys_oddball_2024`。[依据](https://api.figshare.com/v2/articles/26980630/versions/1)

标签　清醒、麻醉、局部场电位记录、网络节律、功率谱、猕猴、大脑皮层、神经群体、丙泊酚、听觉任务

本条 ← [p_xiong2024](#p_xiong2024) · deposits_processed_data · 原文 Data, Materials, and Software Availability 及参考文献 68 明示 Figshare 标识。。[出处](https://pmc.ncbi.nlm.nih.gov/articles/PMC11494327/)

本条 → [o_xiong_tpt_peak](#o_xiong_tpt_peak) · supports_condition_comparison · 公开归档分列清醒与丙泊酚的时频数组，使用与图匹配的 area、局部 oddball 和 regular；本次核读文件结构，尚未重算峰值。。[出处](https://api.figshare.com/v2/file/download/49295326)

### r_openneuro_clinical

**[Multimodal EEG-fNIRS data from patients undergoing general anesthesia](https://openneuro.org/datasets/ds004541/versions/1.0.0)**　8 位患者，9 个 EDF、9 个 SNIRF；sub-11 有两次会话。已读 sub-02 EDF 头和 1.0.0 事件表，基准 82.188 s、start 385.205 s、loc 895.848 s、roc 1970.693 s；若干被试少一个或多个标签。可预先分出有有效记录者按状态求谱，避开语言与强直刺激。用药、剂量、睁闭眼、行为判定规则在已查元数据中未确认。

raw · OpenNeuro:ds004541；10.18112/openneuro.ds004541.v1.0.0 · 版本 1.0.0 · public · 许可 CC0（数据说明的 License 字段） · 核实于 2026-11-26 · 共同来源 `openneuro_ds004541_patients`。[依据](https://raw.githubusercontent.com/OpenNeuroDatasets/ds004541/1.0.0/dataset_description.json)

标签　清醒、麻醉、头皮脑电、网络节律、功率谱、人类、在体、神经群体、大脑皮层、临床记录、连续记录

本条 → [o_purdon_frontal](#o_purdon_frontal) · candidate_external_comparison · 独立机构临床队列可从同人事件表重算指定窗；用药/睁闭眼/任务不同或未知，独立的丙泊酚复验资格仍待核。。[出处](https://raw.githubusercontent.com/OpenNeuroDatasets/ds004541/1.0.0/sub-02/ses-01/eeg/sub-02_ses-01_task-anesthesia_events.tsv)

### r_cecchetto_dryad

**[Data from: Simultaneous two-photon voltage or calcium imaging and multi-channel LFP recordings in barrel cortex of awake and anesthetized mice](https://datadryad.org/dataset/doi:10.5061/dryad.dbrv15f23)**　仓库公开列出 Cecchetto_et_al_data.zip（160944293 字节）并说明按论文图组织。本次匿名访问文件 API 返回 401、站点文件链接返回 403，未验证 ZIP 内容；能查到记录和许可，无法判断是否含完整连续逐试次 LFP。

figure_data · 10.5061/dryad.dbrv15f23 · 版本 第 5 版；API version 148502；ZIP 文件 1146287 · unchecked · 许可 CC0 1.0 · 核实于 2026-11-26 · 共同来源 `cecchetto_mouse_vsd_2021`。[依据](https://datadryad.org/api/v2/versions/148502)

标签　清醒、麻醉、局部场电位记录、皮层电图、小鼠、在体、大脑皮层、异氟烷、感觉任务、图表源数据

本条 ← [p_cecchetto2021](#p_cecchetto2021) · deposits_figure_data · 数据库记录 IsCitedBy 实验论文；Dryad 按图组织。。[出处](https://api.datacite.org/dois/10.5061/dryad.dbrv15f23)

### r_neurotycho_protocol

**[NeuroTycho Anesthesia and Sleep Task Details](https://wiki.neurotycho.org/index.php?title=Anesthesia_and_Sleep_Task_Details&oldid=86113)**　列出清醒睁眼/遮眼、给药种类、无反应判定、苏醒、自然睡眠和事件文件格式。四只参加混合药剂，丙泊酚方案只列 M1、M2。官网可核协议；本次未验证所列会话压缩包，不能充作已读取的原始数据。

protocol · NeuroTycho Wiki 86113 · 版本 oldid=86113；2014-07-30 · public · 许可 协议页面文字许可未核实；项目对可下载数据另行声明放弃版权及相关权利。 · 核实于 2026-11-26 · 共同来源 `yanagawa_neurotycho_2013`。[依据](https://wiki.neurotycho.org/index.php?title=Anesthesia_and_Sleep_Task_Details&oldid=86113)

标签　清醒、麻醉、网络节律、皮层电图、猕猴、在体、神经群体、大脑皮层、睡眠、丙泊酚、氯胺酮、美托咪定

本条 → [p_yanagawa2013](#p_yanagawa2013) · documents_protocol · 固定版本的实验室协议引用原始论文，并分列药物、睡眠和恢复。。[出处](https://wiki.neurotycho.org/index.php?title=Anesthesia_and_Sleep_Task_Details&oldid=86113)

### r_zenodo_rest

**[Rest EEG recordings in healthy subjects during wakefulness, sleep and anesthesia with ketamine, propofol, and xenon](https://zenodo.org/records/806176)**　目录列每种药 5 人，氯胺酮对照为睁眼，丙泊酚及氙气为闭眼，另有 4 人 N3 睡眠。访问受限且未取到文件，可定向申请药剂特异的静息对照；个别受试者与其他研究的独立性仍需核实。

raw · 10.5281/zenodo.806176 · 版本 record 806176，2017-06-12 · application · 许可 未报告；官方元数据 access_right=restricted。 · 核实于 2026-11-26 · 共同来源 `zenodo_806176_rest_eeg`。[依据](https://zenodo.org/api/records/806176)

标签　清醒、麻醉、网络节律、头皮脑电、功率谱、人类、在体、神经群体、大脑皮层、睡眠、丙泊酚、氯胺酮、氙气、静息

本条 → [o_purdon_frontal](#o_purdon_frontal) · candidate_resting_control · 登记有闭眼清醒与丙泊酚静息记录，访问须申请；未确认原始样本独立性。。[出处](https://zenodo.org/api/records/806176)
