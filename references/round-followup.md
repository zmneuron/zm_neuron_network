# 上轮决定与本轮复算

上一轮在 `analysis.completion_review.decision` 记录问题和修正。本轮的 `review.previous_analysis_ref` 指向保留的上轮分析，`capture_review` 将其路径和文件摘要写入 `baseline.previous_analysis`。以下为单组参数示例。

```json
{
  "action": "continue",
  "reason": "静默细胞比例低于预定范围。",
  "attribution": ["parameter"],
  "next_action": "降低背景驱动，重新比较静默比例与平均发放率。",
  "correction_ref": "docs/research/drive-rationale.md",
  "affected_comparison_ids": ["rest_calibration"],
  "next_batch": [
    {"component": "baseline", "parameters": {"drive_mV": 24}, "rationale_ref": "docs/research/drive-rationale.md"}
  ]
}
```

`attribution` 是非空列表，可选 `data_comparability`（数据可比性）、`mechanism`（模型机制）、`parameter`（参数）、`observation`（观测方法）、`control`（对照）。仅参数问题用 `set(decision["attribution"]) == {"parameter"}` 判断。下一批沿用原有字段。其他归因可直接指定修正与受影响的比较。是否有外部阻碍由主流程判断。

若偏差只出现在正式时段的机制活动或对照设计，使用 `affected_scientific_check_ids`。它与 `affected_comparison_ids` 至少一项非空。以下决定只需复跑原科学检查。

```json
{
  "action": "continue",
  "reason": "反馈效应在预定晚期时段消失。",
  "attribution": ["mechanism"],
  "next_action": "修正反馈动力学，复测相同的早、晚时段。",
  "correction_ref": "docs/research/feedback-rationale.md",
  "affected_scientific_check_ids": ["feedback_activity"]
}
```

本轮 `review.scientific_checks[]` 和 `completion_review.scientific_checks[]` 沿用原检查 ID。`source` 和适用的 `control` 指向本轮实际仿真的运行记录和原始 CSV。检查按原时段、阈值及匹配规则重算。完整检查仍为阴性时，`verified_scientific` 保留各时段结果或实际设计偏差。只复核科学检查时无需添加校准比较。

当前 `analysis.completion_review.comparisons[]` 条目沿用现有运行、配置、观测及评分字段，加上以下 `recheck` 对应关系。`batch_index` 从 0 开始。上轮没有参数批次时使用 0。

```json
{
  "id": "rest_drive24",
  "run_ref": "results/r2/run.json",
  "recheck": {"previous_comparison_id": "rest_calibration", "batch_index": 0}
}
```

这段仅展示新增字段。当前比较的 `axis, data_role, dataset_ids, targets_ref, measurements_ref, score_ref, config_ref, candidate_id` 按原约定填写。每个计划参数组都要有实际完成的运行及其对应的复算。复算仍可得出未达标的结果。

```python
from round_followup import check_round_followup, prior_selection_sources

selection_sources.extend(prior_selection_sources(root, plan, baseline, analysis))
# 用上述来源调用原有 _compare，得到按比较 ID 索引的 comparisons。
followup = check_round_followup(root, plan, analysis, baseline, comparisons)
```

`prior_selection_sources` 返回与 `review.datasets` 同结构的列表。`check_round_followup` 返回 `status, issues, pending, selection_sources` 等字段。只读检查可以用于恢复。启动及核实已跑参数组的显式入口如下，`PROJECT` 为工程根目录，模型驱动使用 `begin_run` 与 `finish_run` 保存实际配置和输出。

```text
python round_followup.py run PROJECT --batch-index 0 --run-ref results/r2/run.json -- python model/run.py results/r2 data/candidate.json
python round_followup.py verify PROJECT --batch-index 0 --run-ref results/r2/run.json
```

## 恢复时怎样判读

尚无本轮分析文件时，传入 `{"runs": [], "completion_review": {}}` 和空的 `comparisons`。若上轮安排了实际修正，`pending` 指明待运行的批次、原比较或原科学检查。已经得到输出而尚未从数据复算时，这一义务仍待完成。若此前只剩报告、图文整理或资料调研，可以复用同版输出；此项检查返回 `status="passed", applicable=false`。已充分检验且按原目标允许阴性的预测，可以据实写完报告。已有数值失配或未解决的科学检查时，只改 `next_action` 不能消除原义务。

对有实际运行义务的轮次，`incomplete` 表示仍缺运行或结果，`failed` 给出记录矛盾、参数不符或提前宣称完成的原因。`passed` 仅表示已核实所需复算。校准是否达标、预测是否获支持及能否交付，由相应科学判断给出。

## 实际执行与复用

主流程可以调用与命令行相同的 Python 入口。模型驱动从保存的解析配置实例化模型，成功写出数据后调用 `finish_run`。

```python
from round_followup import execute_followup

receipt = execute_followup(root, "results/r2/run.json", batch_index=0,
    command=["python", "model/run.py", "results/r2", "data/candidate.json"])
receipt = execute_followup(root, "results/r2/run.json", batch_index=0)
```

第一种调用逐项传递执行者给出的参数，工作目录为工程根目录。支持工程内的 Python、Rscript、Julia 脚本及本地可执行程序。启用本版 `check_records.py` 的驱动在创建目录前核对本批实际配置、阶段和输出路径。参数名可写顶层配置键，嵌套值也可用 JSON Pointer，如 `/input/gain`。每组可用 `affected_comparison_ids`、`affected_scientific_check_ids` 指定本组复核的子集，所有组共同覆盖原决定所列项目。

第二种调用核对工程已经完成的本批。运行必须晚于保存上轮决定的本轮要求，具有新的运行身份和匹配的实际配置，输出须属于该运行。`/2` 完整建模还须对应本轮运行前保存的要求。返回的 `run_verified` 可用于安排后续取数。比较复核使用 `check_review` 已按原始数据重算的映射，`verified` 保留各比较的判定及分项数值。若修正只涉及观测或可比性，可以提交新的 `stage="analysis"` 记录，以旧仿真为经核实的父运行；用 `analysis_run_ref` 关联新分析，各项数值必须来自新分析的输出。机制、参数及正式时段的科学复核使用新仿真。

同一输出目录的并发启动采用独占文件协调。重复调用已完成的运行会验证原结果。部分运行、失败记录、无完整记录的旧目录以及中断留下的执行锁均保留。先核对原任务是否仍在运行；需要新的尝试时使用新的输出目录。驱动的执行参数只由显式调用提供。

修正说明和参数依据宜使用保留的版本。旧决定可同时保存 `correction_sha256`，参数组可保存 `rationale_sha256`。新版 `begin_run` 也会记录开跑时所用依据的文件摘要。原决定缺少摘要时，可核实的文件版本始于已记录的最早一次绑定。

## 独立观测与正式仿真

失败的独立观测一旦影响模型、协议或观测方法的修正，其原有来源和样本编号随历次保留的记录恢复，返回的条目标记为 `used_for_selection=true`。后续评价需要预留、可比且未参与选择的观测。来自同一来源的留出样本使用稳定的 `source_id` 与互不重叠的 `observation_ids`。新模拟种子可以检验随机稳定性，实测独立性由观测来源和样本划分确定。原独立检查已经充分完成且未用于改模时，可以沿用原评价。历史数据身份缺失或文件已变时，复核会指出需恢复的具体记录。

`prior_selection_sources` 按各轮事前保存的数据登记表解析该轮的 `selection_uses`，包括计划、分析和 `iterations[]` 中用于选择的数值、方向与条件差异。既往校准资料、已标记参与选择的资料以及拒绝候选时引用的比较均保留其当时的用途。候选运行与特征提取的实际输入、输出及评分文件也参与内容比对。具有相同观测内容的复制文件、更名的数据集以及中间轮次重新导出的文件，可按保存的来源、内容和统计单位对应。当前候选搜索完成后，只需在选定模型上进行一次适用的独立确认。

例如，旧记录在候选迭代中写入 `{"dataset_id":"cohort","feature":"contrast","quantity":"组间发放率差","rule_ref":"docs/selection.md","observation_ids":["A","B"]}`，且原登记表预留了同来源的 C。恢复后的来源仅标记已使用的 A、B，C 可按原先的留出安排评价。若整个数据集已登记为校准，或其完整比较已参与淘汰候选，则按该数据集当时登记的全部单位处理。

`/2` 完整建模的正式 `stage="simulation"` 要求事前保存的 `final_plan.status` 为 `passed`。必需要求、`acceptance` 和必需比较标准须与保存的定义相符。尚处于调研或诊断时，可分别使用 `stage="research"`、`stage="diagnostic"` 独立记录计算。最终生产运行按 `simulation` 核实。
