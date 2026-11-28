# 事前确定要求，在同一采用模型上逐项核对

在每个必需的 `requirements[]` 条目内写 `acceptance`，与当前范围一起保存后再运行。下例为软件演示，数值和脑区名称只用于说明格式。生物模型的每个必需校准目标须关联原实验数据、发表汇总或有出处的图中提取值，并按登记的条件和时窗复算。

```json
{
  "purpose": "fit",
  "condition": "rest",
  "control": "相同静息条件的合成参考",
  "observable": "逐细胞发放率的均值",
  "window": "0–200 ms",
  "criterion": "mean 目标规定的 29–31 Hz",
  "source": {"ref": "docs/model_spec.md", "locator": "静息目标", "excerpt": "静息目标为 29–31 Hz。"},
  "comparisons": [{
    "id": "calibration",
    "targets_ref": "data/targets.json",
    "target_ids": ["mean"],
    "dataset_ids": ["reference"],
    "selectors": {"mean": {
      "file": "rates.csv", "column": "rate_hz", "column_unit": "Hz", "operation": "mean",
      "where": {"start_ms": "0.0", "stop_ms": "200.0"},
      "where_units": {"start_ms": "ms", "stop_ms": "ms"}
    }},
    "context": {
      "region": "ring", "quantity": "cell firing rate",
      "processing": "count per 200 ms", "statistical_unit": "cell"
    }
  }],
  "result_ids": ["activity"],
  "parts": ["questions"]
}
```

`source.ref` 指向工程内可读取的来源，`locator` 写小节、图表或行号，`excerpt` 写其中可逐字找到的文本。也可用 `sha256` 绑定原始文件字节，适用于 PDF、数据表或完整实验方案。多项依据可写成来源对象列表。实际研究可引用含论文标识、适用条件和引文位置的本地摘录。现有目标文件继续保存数值、单位、统计量及上下界。

比较所用的 `review.datasets[]` 和模型测量条目都填写上述 `context`。原有的 `completion_review.comparisons[]` 继续关联目标、测量、评分、运行及配置。例如模型测量文件中的条目如下。

```json
{
  "measurements": {
    "mean": {
      "metric": "mean_rate", "condition": "rest", "unit": "Hz",
      "statistic": "mean", "data_role": "calibration", "status": "observed", "value": 30,
      "source": {"csv_ref": "results/run/rates.csv", "column": "rate_hz", "operation": "mean",
                 "where": {"start_ms": "0.0", "stop_ms": "200.0"}},
      "context": {
        "region": "ring", "quantity": "cell firing rate",
        "processing": "count per 200 ms", "statistical_unit": "cell"
      }
    }
  }
}
```

每个 `target_ids` 条目在 `selectors` 中各有一个可执行的取数定义。`file` 从实际产出该表的运行目录起算，保留子目录。比较逐项核对实际文件、列、统计运算、行条件及原始单位。比如第 0 号细胞在 10 ms 的单点电位可写为下面的定义。

```json
{"early_voltage": {
  "file": "voltage.csv", "column": "voltage_mV", "column_unit": "mV", "operation": "first",
  "where": {"cell_id": "0", "time_ms": "10.0"}, "where_units": {"time_ms": "ms"}
}}
```

`where` 的各项同时成立，按 CSV 单元格的实际文本匹配，`first` 要求恰有一行。按组取数时写出组别、处理、细胞等识别列。预先按窗口汇总的表可像均值示例一样用起止列定位窗口。使用整张表时显式写 `"where":{}`，实际 `source` 此时可省略 `where`。每个读取列都在该输出路径对应的 `analysis.datasets[].fields` 中登记单位。有量纲的筛选列用 `where_units` 指明单位，如 `ms`。用键确认每个统计单位只占一行时，可写 `"row_key":["animal_id","cell_id"]`。

原始脉冲数的 `column_unit` 可为 `count`，经 `zero_fraction` 得到的结果单位在目标与测量中均为 `1`。逐细胞计数的均值可用 `spikes/cell`，检查同时核对每个 `cell_id` 只计一次。相关系数另填 `other_column` 与 `other_column_unit`。需要换算量纲时，先由登记的运行输出目标单位的列，并在取数定义中指定该列。既有目标可沿用原来的数值标准，在下一次正式运行前把原先文字中的时间和统计对象填入这些字段。缺少逐项取数定义时，事前核对返回 `incomplete`。

留出数据在 `review.datasets[]` 登记稳定的 `source_id` 和实际 `observation_ids`。原表含动物编号时，填 `unit_column:"animal_id"`，让核对直接读取评价目标引用的观测行。省略时读取与 `context.statistical_unit` 同名的列。同一原表含多个预先划分的数据集时，用 `unit_where:{"split":"test"}` 选行。若按行保存的矩阵只有索引，例如原表的 `record_id` 对应样本表的 `entry_id`，可登记如下。

```json
{
  "source_ref": "data/matrix.csv", "files": ["data/samples.csv"],
  "source_id": "cohort", "observation_ids": ["B"], "unit_column": "animal_id",
  "units_ref": "data/samples.csv",
  "unit_join": {"data_column": "record_id", "units_column": "entry_id"}
}
```

原表每个参与评价的索引均须在样本表唯一对应一个单位。重复测量可以共享样本编号。原表也有单位列时，两边须逐行相同。两边单位列异名时，`unit_column` 指定原表列名，`unit_join.unit_column` 指定样本表的列名。对于按原始行号编目的矩阵，可使用 `"unit_join":{"index_base":0,"units_column":"original_row"}`。首条数据行的编号可事前定为 0 或 1，始终在应用 `unit_where` 前编号。

对按列保存样本的矩阵，可用 `"unit_join":{"axis":"columns","index_column":"feature","units_column":"matrix_column"}`。第一列保存特征索引，余下每列的列名都与样本表的 `matrix_column` 对应。参照观测表与样本表支持 CSV 和 TSV。其他格式可在事前导出保留原观测和原索引的表，由目标直接引用并随原始资料一并登记。只有独立样本清单、缺少可读观测或两表对应关系时，留出评价待补。

按研究用途选择现有记录。每项保留来源、条件、对照、观测、时窗、判据及交付段。对于文件、方程等静态要求，可在 `window` 说明适用阶段，在 `control` 说明其参照或为何无配对条件。没有科学依据的阈值应留待补充。

| `purpose` | 本项如何判定 |
|---|---|
| `fit` | 必须关联校准比较。按 `targets_ref`、`target_ids`、`dataset_ids` 对应到既定目标，逐项从采用模型的输出复算，与各自的实测来源比较。一个要求可含多个目标或条件，保留各项达标、未达标或待评价的结果。 |
| `prediction` | 关联事前留出的评价比较。`independent_goal="test_prediction"` 时，完整且有判别力的实测阴性可以完成预测检验，需在对应科学问题中回答。`require_support` 则还要求支持预测。校准失配单列。 |
| `reference` | 使用参考用途的资料及其已登记目标，适用范围由原始数据、方法和研究问题确定。 |
| `mechanism`、`design` | 用 `scientific_check_ids` 关联正式窗口机制检查或比较设计检查。时序、活动方向、阈值、实际条件、处理顺序或单位划分沿用科研检查本身的定义。 |
| `observation` | 可用 `result_ids` 约定须获得的结果，从运行记录中的实际输出和上游数据核对其来源。特定活动水平另用目标或机制检查规定。 |
| `delivery` | 用 `parts` 指明报告和最终答复的相应段落。单独的文字要求可用 `required_text` 指定必须在相应段落中出现的实际内容，例如原定须保留的公式或限制说明。 |

事前复核一并保存已有 `requirements[].result_ids` 与 `acceptance.result_ids`，后续逐项检查这些结果。每个必需目标及正式机制、设计检查都要能回到至少一项必需要求。不同条件可在各条 `comparisons[]` 中各写 `condition`。模型和参照的脑区、观测量、处理及统计单位均须与登记的 `context` 一致，实际 CSV 中出现同名条件列时还会逐行核对。原始表格的列名或处理过程另有约定时，用 `comparison_design` 关联相应的真实记录。

## 区分模型符合实测与完成科学假设检验

新版完整生物模型默认采用 `review.independent_goal="require_support"`。运行前至少登记一项必需校准指标和一项独立实测指标。只有采用版本满足全部原定校准标准，且其冻结预测得到保留实测的支持，方可报告该版本在登记条件下符合实测。原委托明确要检验一个可被推翻的预测时，在第一次运行前选择 `test_prediction` 并写明要回答的科学问题。有判别力的实测阴性可完成该检验，同时报告哪条预测失配。已有记录沿用原先登记的目标和比较方法。

独立评价沿用 `review.datasets[]` 的实验登记。填写 `kind="biological"`、`source_class="measured_record"`、实验来源 `source_id`、预留单位 `observation_ids` 及响应列 `value_column`。直接使用逐单位原表时，目标的 `source_ref` 指向该表。原始文件另附导出的响应表时，在 `files` 中登记导出表，用 `observations_ref` 指向它。响应单位可由表的 `fields`、`context.unit` 或与数据一同保存的 `measurement_ref` 指定。需引用同一论文中不同图表时，写明具体图、表或逐单位数据的出处。刺激幅度、拟合参数、实测响应的用途分别按所引原始记录判断。

若开发实测已齐、独立采集尚未交付，在同一数据登记中写明拟采实验、条件与抽样方法、统计单位、预期响应表和列、单位及用途，填写 `available=false`、`used_for_selection=false` 和 `unavailable_reason`。尚待确认可比性时填 `comparable=false`。独立新采集尚无单位编号时，`observation_ids` 可留空。若与开发数据同源，须事先列明两组互不重叠的单位；来源或分组仍不明确时可先做 `diagnostic`。校准来源和比较方法齐备后可正式运行开发和校准，`final_plan.awaiting_independent_data` 会列出仍待取得的样本与目标。此时两个原始目标的独立评价均为 `not_evaluated`。

收到资料后，核对原定条件、统计单位和来源，登记实际响应文件及全部单位编号并确认可比性。在新一轮填写 `previous_analysis_ref`、`previous_requirements_ref` 并另存本轮要求，保留原问题、阈值、读数和模型选择记录。对尚未编号的新采集，先登记适用的样本和标准，再生成正式预测。配对均值误差可事前写 `precision.expected_ids="registered_observation_ids"`，实际评价按本轮登记的整个队列逐单位配对。

若上一轮已为一个已知对象直接做出冻结预测，可在其响应抵达后复核原输出。最初须在 `final_model.variants` 登记这次正式模拟的具体路径，同一采用配置可填 `{}`。在目标的 `selectors.where` 写明该对象的原始编号与读数条件，例如 `{"sweep":"22","start_ms":"800","stop_ms":"900"}`。新一轮沿用紧接的原要求、相同采用模型、专门保留的运行和该 CSV 的 `first` 或 `mean` 读数。用于开发选择的运行、事后指定的对象或更换过的读数继续按开发记录处理。

直接预测的实测参考区间用原单位核对。先按预定条件和统计单位读取实验值。单点、均值、中位数或极值需能从原表重算，再检验冻结预测是否落入规定范围。这一结果适用于该范围，逐对象精度须另算每个预测与对应实测的误差。预定容差、测量方法和模型参数先行固定，留出的响应只在评价时读取。原始记录包含同一对象的多次测量时，先按预定时间窗汇总每个对象，并保留其编号。对预测误差，已有的 `unit_mean_ci95` 配合 `paired_error` 可按留出单位计算均值和 95% 区间。当前只有单个点预测或比较均值时，用评分分析的 `raw_calculation` 登记预测减实测的两个操作数，例如下列单点电位差。

```json
{
  "operation": "difference",
  "left": {"file": "late.csv", "column": "delta_mV", "column_unit": "mV", "operation": "first",
           "where": {"start_ms": "800", "stop_ms": "900"}, "where_units": {"start_ms": "ms", "stop_ms": "ms"}},
  "right": {"dataset_id": "holdout", "column": "delta_mV", "column_unit": "mV", "operation": "first", "where": {}}
}
```

左项取自采用模拟的原始输出。右项取自登记的留出响应 CSV，列与筛选条件分别对应 `value_column` 和 `unit_where`。测量文件中右项的 `csv_ref` 须指向该实测表，评分分析须在模拟后读取两份输入并产生自己的输出。核对程序重新计算两个操作数与差值，再以事前容许误差判定。由分析表转录直接预测时，还要从模拟原表的相应列、对象和时间窗复算。更复杂的比值、效应差或误差统计量应保留各自的计算定义，缺少可复算的比较时报告待评价。随附的 Allen 历史扫次重放只演示两种原目标的程序判定，其中的容差仅用于软件测试。

最终核对在 `final_evidence.empirical_evaluation` 列出独立目标、数据来源及其支持情况。新版第一次登记完整模型时，研究设计会记录 `independent_observations="measured_record/1"`。旧计划可按原范围完成，其已有结果另注明是否核对过独立实测。

## 采用模型与不同运行条件

在 `analysis.json` 的 `completion_review.final_model` 中登记 `{"run_ref":"results/run/run.json"}`。该运行须已完成，使用当前计划事前保存的要求、当前模型声明的源码和 `current_model.config_ref` 的完整参数。已有唯一的 `iterations[].role="final"` 时可直接用该条的 `run_ref`。比较、机制、结果和交付涉及的模型数据均需能关联到实际记录。

如需更换设计内的种子或条件，运行前登记下例中的 `review.final_model`。键是对应的运行记录，内部按 JSON Pointer 指定允许变化的单个配置值、用途和来源。无差异的运行无需新字段。主流程将整个 `review.final_model` 及 `requirements[].acceptance` 保存到事前范围。

```json
{
  "variants": {
    "results/rest2/run.json": {
      "/seed": {"value": 17, "role": "seed",
                "source": {"ref": "docs/model_spec.md", "locator": "重复", "excerpt": "第二次重复使用种子 17。"}}
    },
    "results/control/run.json": {
      "/protocol/block_feedback": {"value": true, "role": "control", "check_id": "feedback",
                "source": {"ref": "docs/model_spec.md", "locator": "对照", "excerpt": "对照运行阻断反馈输入。"}}
    }
  }
}
```

实验条件用 `role:"condition"`，写明 `condition` 和与其不同的 `reference_condition`，例如 `pulse` 和 `rest`。前者对应要核对的事前要求或比较。机制对照用 `role:"control"`，`check_id` 指向明确登记该运行作为 `control` 的正式检查，`control_change` 说明操纵对象与配对依据。种子填写实际整数。

当前已选定的模型参数在复核中固定，例如调出的背景驱动、耦合强度。检查读取 `changed_parameter_ids` 对应的配置路径、有限选参空间及上一轮决定调整的参数。其他需固定的参数可在 `review.final_model.fixed_parameters` 中以配置路径为键，值填写同样的来源对象。向量参数的各个元素均受此约束。当前方法中登记的核心参数只可按明确的机制对照用途操纵，已选定的系数继续固定。实验协议可单独设置是否阻断该作用。对照运行只为其登记的检查提供对照数据。

机制要求用 `purpose:"mechanism"` 和 `scientific_check_ids:["机制检查ID"]` 复用 `review.scientific_checks[]` 的 `mechanism_activity`。保留该要求的来源、条件、对照、读数、时窗、判据与交付段。检查从对应正式运行的原始输出读取预定列、实例与窗口，并核对控制条件。非数值设计可用 `purpose:"design"` 引用 `comparison_design`，例如核对实际预处理顺序或留出单位。

## 修改后复核与沿用正式模拟

参数或机制修正后，重新核对最终采用模型的每项要求，包括上一轮已经达标的要求。不同模型可作为历史参照出现在同一图中。用于满足要求的数据必须能单独关联到采用模型。需要检查的文件包括当前源码、实际配置、模型输入、上游运行和观测文件。

模型保持同一版本、配置、代码与输入，且只补交付或修正观测时，可继续采用原正式模拟。当前 `previous_requirements` 和 `previous_analysis` 必须能按已保存的文件摘要回到该运行当时的完整事前标准、采用决定及原始记录。中间轮次须持续采用该模型。原目标、逐目标取数定义及必需机制检查保持兼容。只补交付时复核现有原始数据，若引用上一轮分析提取的数值，`source.raw_calculation` 给出能从采用模型原始数据重算该值的已有计算约定。沿用同一取数定义时，其原始文件路径相对父模拟目录解析。若用其他原始列、文件或两组之差，在事前 `selectors[目标ID].raw_calculation` 登记相应取数定义或 `{"operation":"difference","left":取数定义,"right":取数定义}`。核对会读取父模拟的实际表，并验证分析确实将其用作输入。

若上一轮决定修正观测或数据可比性，受影响的比较关联本轮新的 `analysis_run_ref`。该分析须在原模拟完成并保存新一轮要求后启动，以确切的原模拟为直接父运行，在 `input_sha256` 中留下其原始数据，并从新的输出文件读取修正后的测量。已用于修正的独立评价资料按开发资料处理。需要重新检验时，使用预先保留、统计单位独立的观测。

## 检查接口

`check_final_plan(root, plan)` 在运行前检查必需要求及其依据。`check_final_evidence(root, plan, analysis, comparisons, science)` 接收主检查已复算的比较字典和科学检查报告，逐项返回状态、具体缺口、运行路径与目标结果。`preserved_formal_run(root, plan, ref, record)` 仅在先前正式模拟满足上述沿用条件时返回真。这三个接口均只读取文件。

`passed` 表示本项已按事前标准核对。`incomplete` 表示缺少声明、观测、交付内容，或实际测量尚未达到标准。`failed` 表示记录存在冲突，例如用另一套源码产生的数据替代采用模型的结果。科学依据是否适用于所建对象，仍由研究者结合原始资料和实际实现判断。
