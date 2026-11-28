# 计算神经科学建模文献、电生理结果与公开数据链接索引

从科学问题查论文、具体观测与数据。首轮文献窗口为 **2016-11-26 至 2026-11-26**（含两端），最近检索日期为 **2026-11-28**。近十年建模主文献、实验/技术支持文献、独立数据集、预印本、早期关联来源分别计数。[分批记录与实际规模](batches/README.md)

[按解剖对象](browse/anatomy.md) · [按模型尺度和方法](browse/models.md) · [按信号和记录技术](browse/signals.md) · [按科学问题和状态](browse/topics.md) · [所有记录与原出处](browse/records.md) · [覆盖与空白](browse/coverage.md)

## 从问题查到原始出处

生成的目录可以直接在 GitHub 阅读。已安装技能时，从技能目录运行下列命令。默认返回同时匹配的记录，`--near` 另列只满足部分条件的结果及缺项。`--json` 保留试次、分组、原研究用法、共同来源和关联链接。旧安装先与仓库默认分支核对版本，必要时用当前仓库检索。[两题的实际试查](examples.md) · [公开维护库](https://github.com/zmneuron/zm_neuron_network/tree/main/references/index)

```shell
python scripts/evidence_index.py search "单细胞放电适应" --type results
python scripts/evidence_index.py search --tag awake --tag anesthesia --tag rhythm --type results --json
python scripts/evidence_index.py search --tag awake --tag anesthesia --tag power_spectrum --type resources --near
python scripts/evidence_index.py search --collection window_model --year 2020
```

自然语言查询会显示词表标签和额外的文字条件。作者、题名片段或数字按文字筛选。科学问题中的否定、剂量、时长、动物与记录是否配对，需在结果行和原资料中核对。未被识别的条件须显式补查。若留下多个可能的参数或机制，给出已有资料能约束的量和下一项可区分的测量。[中英文词表](vocabulary.tsv)

## 每一次调研怎样补入共享库

1. 先检索当前索引。返回能定位的论文、图表/数据记录与模型版本，说明符合和有差异的条件、共同来源、可用于构建/校准/比较的量，以及独立检验仍需满足的条件。
2. 对缺少的对象、协议、指标、时间窗、原图、数据入口或失效链接查外部来源。沿论文引用和后续引用、模型编号、数据集、实验室、作者库和正式补充材料交叉寻找。技术博客、综述可指路，观测回到原实验、本体图表或正式记录。[分方向检索与下一批](search-plan.md)
3. 本轮回填所有核实且在范围内的公开资料。条件不合当前课题也按**实际条件**收录。先按规范化 DOI 或其他论文标识、资源编号及版本核对。已有论文补图号或资源关联，已知同批动物/试次、重新切窗、镜像和再分析须登记共同来源。保留旧版本，链接新版本、更正或撤稿状态。只存公开链接、出处、标识和必要科学描述，原始数据、全文和第三方代码留在原平台。
4. 在基于最新默认分支的工作副本改四张表并记录检索，更新词表或待补条件。运行 `build`、`validate` 后**用原问题重查**。记录新增/补全的 ID、此前缺什么、现在查到什么。合并前如果默认分支变化，先重核 DOI、编号和关联，避免多人重复录入。定期检查具体资源页、许可及更正关系，保留旧出处和最近核实日期。
5. 按仓库现有流程提交。有写入权限按维护流程更新并核对远端默认分支。无直接权限，从新分支或 fork 发起合并请求；提交环境不可用时交付同字段的四表新增/修改行、所需词表及批次记录。**已入库**以默认分支能用原查询找到为准。**待合并**附实际 PR。**待提交**附可导入的文件及原因。每个使用者均应报告本轮实际状态。[仓库贡献方式](https://github.com/zmneuron/zm_neuron_network/blob/main/CONTRIBUTING.md)
6. 补查仍无合适资料时，在[待补清单](gaps.jsonl)记录具体缺项、来源、词、日期、下一入口，标记“本次检索尚未定位”。保留已知不公开或申请条件。下次先查未覆盖平台、未查页及新发表或新开放的资源。

```shell
python scripts/evidence_index.py build
python scripts/evidence_index.py validate
```

收到待提交条目时可将四表新增或补充行放入一个 JSON 对象，以 `papers`、`results`、`resources`、`links` 为键。运行 `python scripts/evidence_index.py prepare contribution.json reviewed-index` 会创建可审阅的完整副本。对该副本用 `python scripts/evidence_index.py --root reviewed-index validate` 以及原问题复查，再将相应差异提交默认分支或 PR。[字段及导入约定](schema.md#导入和更新)

[文献表](papers.jsonl) · [结果表](results.jsonl) · [资源表](resources.jsonl) · [关联表](links.jsonl) · [纳入范围与字段](schema.md)
