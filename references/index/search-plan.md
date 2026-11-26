# 分方向检索、筛选与下一批

本批的[完整检索式和实际页次](batches/2026-11-26-searches.jsonl)包含可直接执行的 API 或检索页链接。首轮候选按数据库自身排序保存[实际返回的标识和名次](batches/2026-11-26-candidates.tsv)。命中总数、已看页数、核实收录数分别统计。同一论文可跨多个检索式。平台相关性排名会变化，复跑时新建批次并保存检索时间。

## 可执行的专题入口

| 方向 | 可直接复制的检索式（按所在平台语法） | 交叉追查 |
|---|---|---|
| 离子通道、膜动力学、单细胞 | Europe PMC `(TITLE_ABS:"Hodgkin-Huxley" OR TITLE_ABS:"conductance-based model") AND (neuron OR neuronal) AND E_PDATE:[2016-11-26 TO 2026-11-26]` | 从模型、激活/失活曲线、电流钳与电压钳追到具体温度、细胞和刺激。 |
| 树突、轴突与区室 | Europe PMC `(TITLE_ABS:dendritic OR TITLE_ABS:axon) AND (TITLE_ABS:"compartmental model" OR TITLE_ABS:"cable equation") AND E_PDATE:[2016-11-26 TO 2026-11-26]` | 从形态编号和作用位置反查原始重建与电生理。 |
| 放电适应 | Europe PMC `(TITLE_ABS:"spike-frequency adaptation" OR TITLE_ABS:"after-spike currents" OR TITLE_ABS:"generalized leaky integrate-and-fire") AND E_PDATE:[2016-11-26 TO 2026-11-26]`。Allen Cell Types 以 `long square`、`adaptation`、细胞号和 sweep 号检索。 | 追查特征的具体实现、有效试次、尖峰数及额外刺激能否提供独立检验。 |
| 突触、可塑性、胶质 | Europe PMC `(TITLE_ABS:"short-term plasticity" OR TITLE_ABS:"spike-timing-dependent plasticity") AND (model OR simulation)`。另查 `astrocyte AND ("potassium buffering" OR "calcium dynamics")`。 | 对照 paired recording、细胞类型、短时刺激、模型连接的方向；钙信号单标。 |
| 局部微环路、跨区网络、群体与全脑 | Europe PMC `(TITLE_ABS:"spiking network" OR TITLE_ABS:"neural mass" OR TITLE_ABS:"neural field model" OR TITLE_ABS:"whole-brain model")`。Crossref 用 `neural mass whole brain resting state functional connectivity`。 | 未写 model 的论文另从端点、原型方程、连接组或神经动力学词检索，检查 LFP/血氧等观测转换。 |
| 麻醉、觉醒与节律 | PubMed `(awake OR wakefulness OR consciousness) AND (anesthesia OR anaesthesia OR propofol) AND (oscillations OR spectrum OR electroencephalography)`。DANDI/开放数据另以 `anesthesia`、药物名或动物单查。 | 用个体编号、状态标签、同一会话、事件时间、原始信号及图号确认。睡眠、镇静、诱发反应单列。 |
| 感觉、运动、疾病与神经调控 | PubMed `(cochlea OR retina OR brainstem OR spinal OR autonomic OR neuromuscular) AND (biophysical OR conductance OR model)`。工程文献查 `("brain-computer interface" OR "motor decoder") AND ("closed loop" OR feedback)`。 | 追到使用的刺激、记录、控制器延迟和数据来源，在 IEEE 检索同义词与会议版。 |
| 理论、算法、基准与神经信息学 | arXiv `(cat:q-bio.NC OR cat:physics.bio-ph) AND (abs:spiking OR abs:electrophysiology OR abs:connectome)`。另用 `"simulation-based inference" neuron`、`NWB electrophysiology`。 | 核对算法解决的具体方程或估计问题、论文/预印本关系、作者软件发布版本与可比较性能。 |
| 物种与解剖空白 | PubMed `(songbird OR zebrafish OR Drosophila OR "C. elegans" OR retina OR cochlea) AND (recording OR reconstruction OR connectome OR "encoding model")`。 | 补小脑、丘脑、基底节、脑干、脊髓、自主与神经肌肉。只取得物种或状态相近记录时，按实际对象收录。 |
| 中文与其他语种 | 中文主题检索 `(神经元 OR 脑电) AND (放电适应 OR 脑节律 OR 神经场 OR 快慢变量)`，另查旧称“脑电图、植物神经、皮质”。法语尝试 `oscillations corticales anesthésie éveil`，日语尝试 `神経細胞 発火順応 電流クランプ`。 | 先检区域数据库和学位/会议目录，沿作者或 DOI 核对出版史。记录界面是否实际返回了结果。 |

期刊领域和物种决定选用哪些入口。身处不同地区时，网页的访问条件可不同。登录/申请资源先保存公开记录，并记录可见层级。

| 路线 | 可启动检索的正式入口 | 补查范围 |
|---|---|---|
| 综合与医学 | [PubMed](https://pubmed.ncbi.nlm.nih.gov/) · [Europe PMC](https://europepmc.org/advancedsearch) · [Crossref](https://search.crossref.org/) · [OpenAlex](https://openalex.org/works) | 组合题名/摘要/标识词；查被引与后续引用、勘误、协议、配套数据和未开放说明。 |
| 工程、物理、预印本 | [IEEE Xplore](https://ieeexplore.ieee.org/search/advanced) · [arXiv](https://arxiv.org/search/advanced) · [bioRxiv](https://www.biorxiv.org/search) · [HAL](https://hal.science/search/index) | 查算法名、方程、会议与期刊版本。检索初稿与正式版差异。 |
| 区域、学位与机构 | [知网](https://kns.cnki.net/kns8s/AdvSearch) · [万方](https://s.wanfangdata.com.cn/) · [J-STAGE](https://www.jstage.jst.go.jp/) · [物理学报](https://wulixb.iphy.ac.cn/) | 本批检索了中文关键词及公开期刊页面。受访问限制的结果页与尚待直接检索的平台分别记录，外部站点限定检索不能算做已筛完数据库。 |
| 数据先行 | [DANDI](https://dandiarchive.org/dandiset) · [CRCNS](https://crcns.org/data-sets) · [Allen Cell Types](https://celltypes.brain-map.org/) · [OpenNeuro](https://openneuro.org/search) · [EBRAINS](https://search.kg.ebrains.eu/) | 用实验协议、脑区、细胞类别、样本/试次号找记录，反查采集论文、再用论文、同源镜像与未参与建模的资料。 |
| 通用归档、补充和实验室 | [Zenodo](https://zenodo.org/search) · [Dryad](https://datadryad.org/search) · [Figshare](https://figshare.com/search) · [OSF](https://osf.io/search/) · [DataCite](https://commons.datacite.org/) | 追 DOI、版本、图表源数据、实验室主页、机构归档和学会链接。图表数据、举例文件、完整原始信号分开识别。 |
| 模型与代码先行 | [ModelDB](https://modeldb.science/) · [Open Source Brain](https://v1.opensourcebrain.org/projects) · [GitHub](https://github.com/search) · [Software Heritage](https://archive.softwareheritage.org/) | 以模型编号、方程、作者、README 和引用文件追原文、采用的参数和数据，每次固定版本。门户只作发现入口。 |

## 分年和分专题扩展

1. 首轮把时间窗切成 11 个自然年片段，2016 年从 11 月 26 日开始，2026 年截至 11 月 26 日。逐年运行同一组明确的建模词以补偿相关性首页偏重近期文章，再运行跨年的专题词和数据/模型查询。本首轮的题名限定年度支路是补充样本，不能据此宣称各年已穷尽。
2. 下一批先处理已保存候选中的未核实论文、已收录论文中缺数据入口的条目和读者的具体缺口。对覆盖表稀疏格开专门检索，注明年份、物种、解剖、方法、语种和实际页次。例如用鸟类听觉/发声、耳蜗突触、脑干与自主环路的名称搜论文，再反查对应公开记录。没有命中时复查数据库用词、旧称和补充材料索引。
3. 每批增加一组与检索设计者独立的已知资料。先冻结测试名单和日期，再检索。以实际返回列表中的稳定标识计算原始召回，相关论文、数据库镜像和同名但不同对象分别记录。针对漏项开展一般性专题补检后，另外报告找回数与原因。
4. 期满后保留既有批次及原窗口，新增滚动十年/新增年度的检索记录。论文出版勘误、预印本正式发表、资源开放和链接失效可触发单条更新。
