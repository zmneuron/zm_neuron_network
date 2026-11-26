# 两个建模问题的实际试查

在技能目录运行下列命令。`--json` 返回原始出处、测量协议、同源条目和相关资源。`--near` 列出部分匹配的条目，未匹配的标签和文字分别见 `missing` 和 `missing_text`。药剂、取窗和生物样本是否独立，仍须核对原文和文件。

## 单细胞在持续注流时逐渐减慢放电，什么资料能约束模型？

```shell
python scripts/evidence_index.py search "单细胞放电适应" --type results
python scripts/evidence_index.py search --tag mouse --tag adaptation --tag isi --tag step_current --type resources --access public --json
python scripts/evidence_index.py search --tag adaptation --tag fluctuating_current --type results --origin measured_here --json
```

**先对齐同一细胞、刺激和算法。** 第一条查询返回 `o_cell_gouwens_mouse_index`，第二条可找到对应的 `r_cell_allen_mouse_raw`。小鼠外侧视觉区第 4 层有棘细胞 313861794 的第 35 次扫查，从 1.02 s 起注入约 1 s、150 pA 的方波，记录到 4 个脉冲。依原始脉冲时刻得到 3 个放电间隔，计算每对相邻间隔的（后−前）/（后＋前），再取平均为 **0.2998732321077493**，与数据库的 0.299873232107749 一致。正值表示间隔总体延长。模型应在同一注流窗用相同算法产生可比读数。原始文件、数据库特征和论文补表中的这行只代表一只鼠的一个细胞。[原始 NWB](https://api.brain-map.org/api/v2/well_known_file_download/491200821) · [数据库特征](https://api.brain-map.org/api/v2/data/EphysFeature/396463405.json) · [作者的计算代码](https://github.com/AllenInstitute/AllenSDK/blob/v2.16.2/allensdk/ephys/ephys_features.py#L756-L770) · [Gouwens 等的逐细胞补表](https://static-content.springer.com/esm/art%3A10.1038%2Fs41593-019-0417-0/MediaObjects/41593_2019_417_MOESM5_ESM.xlsx)

用完整问题 `寻找可约束单细胞放电适应的实测记录` 查询，结果会排除模拟曲线。人额下回第 3 层标本 486940963 的第 39 次扫查在 190 pA 阶跃中产生 9 个脉冲，归档适应指数为 0.18729。它提供另一个可复算的协议，具体采集论文尚待查明。比较人鼠差异还需匹配细胞类型和注流，并增加独立供体。[人类标本和供体记录](https://api.brain-map.org/api/v2/data/Specimen/486940963.json?include=donor,structure) · [适应特征](https://api.brain-map.org/api/v2/data/EphysFeature/486943542.json)

**再找能分开机制的输入。** 候选点模型可以让每次放电引起一个逐渐衰减的外向电流，或让放电后阈值短暂升高。调节强度和时间常数，两者都可能拟合阶跃内的平均率和适应指数。第三条查询可找到 Mensi 等 Fig. 4B 中同一快放电细胞在相同波动输入下的 11 次实测。黑色电压和脉冲点栅为记录，红色为模拟。Teeter 等 Fig. 4a 也将同一细胞对留出噪声波形的实测与模型脉冲并列。可以冻结阶跃拟合参数，再比较新波形下放电后的阈下电压、下一脉冲的时间及对先前放电间隔的依赖。快放电细胞与上述有棘细胞分属不同类型，所举论文示范的是判别协议。若目标细胞缺少这些波形，仍应保留两种解释。要推广到动物，须再留出供体。同一细胞换波形只能检验新输入。[Mensi 等 Fig. 4，作者存档全文](https://infoscience.epfl.ch/bitstreams/6ce42f90-73cc-42b3-a237-70f3bd4688a5/download?download=1) · [Teeter 等 Fig. 4](https://www.nature.com/articles/s41467-017-02717-4/figures/4)

## 清醒与麻醉的网络节律如何变化，哪个数据集可以实际比较？

```shell
python scripts/evidence_index.py search "清醒与麻醉网络节律" --type results
python scripts/evidence_index.py search --tag awake --tag anesthesia --tag propofol --tag power_spectrum --type resources --access public --json
python scripts/evidence_index.py search --tag human --tag awake --tag anesthesia --tag propofol --tag eeg --tag power_spectrum --type resources --near --json
```

**先写明所问的节律。** 第一条查询中的 `o_purdon_frontal` 来自 10 名健康成人的头皮 EEG。闭眼听觉任务中，丙泊酚渐进诱导至言语无反应时，额部 0.1–1 Hz 和 8–12 Hz 功率均升高；15 min 后，alpha 增强集中在额部，低频增强广及颞顶头皮。Fig. 3A 的 23.1→12.0 Hz 是**同批人诱导过渡期 2–40 Hz 内的中位频率**。这两个图可共同约束头皮分布与时间进程。第二条查询中的 `r_purdon_dandi` 虽引用十人协议，固定版只有一个被试文件，文件内未见行为分期。用这份矩阵可以检查读取和频谱算法，原文的十人组效应仍需相应受试者和行为时间戳才能复算。[Purdon 等 Fig. 2–3](https://pmc.ncbi.nlm.nih.gov/articles/PMC3607036/) · [DANDI 固定版文件清单](https://api.dandiarchive.org/api/dandisets/001285/versions/0.250110.2125/assets/)

|研究目标|可采用的资料与范围|
|---|---|
|同药剂、同刺激比较局部节律|两只猕猴在清醒及丙泊酚所致反应丧失期间，均听到由五个音组成的序列。颞顶听觉区最后一音违反规律相对符合规律的局部场电位功率峰，在其后 200 ms 内由 82 Hz 降至 40 Hz。公开的 `r_xiong_tfr` 内有清醒和麻醉两套时频数组及局部意外/规则条件，可重新作图比较。82 与 40 Hz 是原文数值；该资料用于听觉诱发 LFP，以动物为生物单位。相同记录产生的论文图和时频数组共享来源。[Xiong 等 Fig. 3](https://pmc.ncbi.nlm.nih.gov/articles/PMC11494327/) · [Figshare v1](https://doi.org/10.6084/m9.figshare.26980630.v1) · [版本及文件直链清单](https://api.figshare.com/v2/articles/26980630/versions/1)|
|同药剂、同人闭眼比较自发 EEG|第三条查询中的 `r_bajwa_openneuro` 缺少 `anesthesia` 标签。实验将丙泊酚滴定至强刺激可唤醒的深镇静（目标 RASS −4），固定版有同一人的闭眼清醒和镇静静息原始 EEG。按人取等长、无刺激窗口可重新估计功率谱。原文报告的单导复杂度是闭眼 0.309±0.018、镇静 0.274±0.012；这个数值不能填入功率谱。该队列可检验变化是否延伸到深镇静，不能直接确证持续无反应全麻的效应。[实验方法与表 4](https://www.nature.com/articles/s41598-025-12695-z) · [OpenNeuro ds005620 v1.0.0](https://openneuro.org/datasets/ds005620/versions/1.0.0)|

**留下可以补查的缺口。** 若目标是人类同药剂、闭眼、无任务、按行为确认全麻的原始 EEG，当前仍缺同时核实这些条件、且未参与选参的独立记录。临床队列 ds004541 的 sub-02 有原始 EEG 及 `baseline`、`loc`、`roc` 时标，并记录言语及强直刺激；须另核给药和眼态，逐人排除刺激窗口。另有按闭眼清醒及丙泊酚登记的静息数据，需要向保管方申请。若改问小鼠，Claar 等 Fig. 7E 的清醒静止与异氟烷麻醉皮层基础发放率为 3.3±0.2 和 1.1±0.2 Hz。这里的 Hz 是每秒放电数；判定节律仍要读取该研究的 EEG/LFP，计算预定频带的功率。[临床队列与状态时标](https://raw.githubusercontent.com/OpenNeuroDatasets/ds004541/1.0.0/sub-02/ses-01/eeg/sub-02_ses-01_task-anesthesia_events.tsv) · [受限静息记录](https://zenodo.org/records/806176) · [Claar 等 Fig. 7](https://elifesciences.org/articles/84630/figures) · [小鼠原始记录固定版](https://dandiarchive.org/dandiset/000458/0.230317.0039)
