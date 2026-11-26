# 输出记录格式

这是[结果交付](result-delivery.md)中 `analysis/output/analysis.json` 的最小可检查格式，可添加实际项目所需信息。它与既有运行和数据共享标识，不替代它们。模板的空数组用于填写，不能作为完成的结果通过检查。只委托讨论或方案时不执行最终输出检查。

所有路径相对于模型工程根目录，引用项目内文件；数据集内部路径、数组名和筛选条件另外填写。为独立交付所需的大型文件使用合适的存储方案，并在项目中实现等价内容检查；不能用一行下载地址代替已保存的必要结果。

原有 `results.status` 表示对应工作与产物是否完成，不等于模型满足生物学要求。最终还需在同一文件的 `completion_review` 分别记录运行、校准、独立评价、科学回答和交付状态，并关联原要求和实际答复，字段与执行入口见 [交付复核](project-checks.md#记录与运行约定)。不新增第二套图表或数据清单。

完整调控的最低筛选问题在 `results` 中标为必需并关联其 Q 编号；同一 `completion_review.regulation` 连接冻结设计、B/D0、实际候选、独立确认、逐项接受及采用决定，图组引用本文件已有 `figures`，不另造一套图件清单。图件至少共同覆盖实际组合、B/D0/选择候选原始比较、搜索及确认过程。任务计划的 `review.regulation` 明确实施或限定范围，检查方式见[调控完成复核](regulation-design.md#执行记录与完成复核)；有阴性结果不等于确认成功，模拟确认也不自动满足生物独立验证。

| 字段 | 规则 |
|---|---|
| `schema_version` | 当前为整数 `2`，增加与任务对应的 `plan_id,model_version`；旧版 `1` 仅保留独立输出检查兼容性，不用于新的联合交付。 |
| `analysis_id, command, statistical_unit` | 非空字符串：分析标识、实际重分析命令与工作目录说明、独立重复单位。 |
| `report` | 已填写的结果报告路径。 |
| `runs` | 非空数组，元素含唯一 `run_id` 与 `record` 路径；对应 JSON 运行记录包含相同 `run_id`，状态 `completed/partial/failed`。完整科学结果不能引用未完成运行冒充完成。 |
| `datasets` | 数据条目数组，见下文。 |
| `figures` | 结果图条目数组。完整研究正文至少 6 幅实算结果图，常用 6–8 幅，模型示意图另计；局部分析按委托范围。 |
| `construction_steps` | 按实际构建顺序排列的非空步骤数组，字段见下文。与构建方法和模块索引使用相同的步骤标识，已有结果直接引用。 |
| `results` | 本轮结果条目数组，每项包含唯一 `id`、非空 `question`、布尔 `required`、`status`、`data_ids`、`figure_ids`；未完成或不适用时写 `reason`。至少有一项必需结果。 |

结果状态为 `complete/pending/failed/not_applicable`。必需项必须为 `complete`；不能把用户必需结果改成不适用绕过交付。完成项必须引用已有数据，有图则引用图标识。某项必须含图时设 `figure_required: true`。非必需的待实测评价可保持 `pending` 并写原因；工具通过只表示所声明的必需交付项齐备，不表示这项科学评价完成。计划来自当前构建方法，不能事后按现有输出缩减。

完整生物建模任务将固定的真实数据验证交付登记为必需结果（例如 `id: biological_validation`、`required: true`、`figure_required: true`），引用实际实验数据、最终采用模型和比较表，以及相应对比图；有迭代时再引用初始模型。状态表示图文比较工作是否完成，是否达标及独立性须在正文和比较表另行说明。真实数据缺失保持 `pending` 并说明原因，不能把该项改成可选；用户原本明确限定的纯理论、软件测试等按原范围记录，不因本规则补造实验。复用现有字段与同一图件，不增加第二套输出格式。

## 构建步骤

每一步含唯一 `id`、`title`、`method_ref`、布尔 `required`、`status`、`depends_on`、`input_refs`、`data_ids`、`figure_ids`、`check_refs`。`method_ref` 指向已有方法文件，可带 `#` 定位；`depends_on` 只能引用列表中已在前面定义的步骤，未依赖其他步骤时为空数组。

完成步骤须给出非空 `observation`（实际结果及必要数值），至少一个存在的实际输入文件、输出数据标识和检查记录路径；图件按需要引用。不能只写计划中的输出名。完成步骤所依赖的步骤也应完成，其输出不能引用失败或部分完成的运行。状态与必需项规则同科学结果；未执行或不适用说明 `reason`。至少有一个必需构建步骤，具体必需步骤是否覆盖完整目标仍要对照构建方法和逐项表。若单独构建产生中间结果，可给该构建操作自己的运行标识和真实完成记录，不伪称已运行完整仿真。

输入引用可带位置说明。完成步骤的检查文件采用[结构化记录](project-checks.md#记录实际检查不手工填写成功标签)，程序读取判定、指标、运行和文件一致性，核对记录实际覆盖本步骤的数据与图件；仍不声称能够证明记录真实。共享数据只登记一次，步骤与科学结果通过 `data_ids` 引用，不重复导出。只读重分析沿用未变的原构建记录，缺失部分如实标记，不补造历史。

## 数据条目

每个条目含 `id,path,kind,run_ids,description,fields`，其中 `kind` 为 `raw` 或 `table`。`origin` 默认为 `model`，表示本项目构建、仿真或分析产生的数据，须有非空的已登记 `run_ids`；`fields` 为字段/数组名到说明的对象。每个字段说明包含非空 `description,unit` 与 `type: text/number`；标识、状态或无量纲数使用单位 `1`。数组再写真实 `shape`、`axes`、对象标识及时间映射，工具不自动读取二进制内容。

外部文献/实验记录设 `origin: external`，允许 `run_ids: []`，另须填写 `source_ref`（项目内来源说明，可带章节定位）、`evidence_type` 和非空 `data_use`。`evidence_type` 区分 `experimental_recording`（原始实测）、`published_summary`（发表汇总）、`digitized_figure`（图中提取值）、`published_simulation`（外部模型结果）或 `synthetic`（测试用数据）。来源说明保留原始网址、版本、协议、图表定位及适用的预处理；图中提取值还须说明原图是实验还是模拟。`data_use` 记录参考、构建、拟合、开发选择或独立评价等真实用途，先前使用历史不能因改写字段而消失。工具只能核对声明，不能确认来源真假和数据独立性。

派生表可用非空 `input_data_ids` 引用已登记数据，不能引用自身或循环引用。文献/实测比较表应引用实际参考、初始和候选模型数据，同时保留自身产生运行与前后模型运行关系。完成状态会检查这些输入对应的运行，不能通过一张新汇总表隐藏未完成的候选仿真。完整的构建步骤或科学结果至少引用一份本项目产生的数据，不能只挂外部文献/实验值就称模型已运行；纯调研任务不使用此最终模型检查。比较是否量纲一致、计算正确仍需复算。

CSV 必须完整声明列，自动检查列名、行宽和数值有限性。`key_columns` 可指定联合主键并检查重复与缺失；不对事件流随意设不成立的唯一键。空事件表只有在 `kind: raw`、`allow_empty: true` 且有 `empty_reason` 时才可接受，例如已核对的全体无尖峰；主要指标表仍应包含对应单位的有效零或状态。脚本和机制源码不能登记为结果数据来代替实际输出。

数值字段可能缺失时声明 `status_column` 和 `missing_statuses`，后者是允许该值留空的状态集合。工具仅接受空字符串作为有说明的缺失，`NaN/Inf` 不可冒充数字。非空值不能同时标成缺失状态。指标是否应为零、无响应或不可估计，仍由指标定义判断。

下面是合成示例中的字段片段，不代表生理设定：

```json
{
  "network_id": {"type": "text", "unit": "1", "description": "独立网络标识"},
  "condition": {"type": "text", "unit": "1", "description": "配对条件"},
  "recovery_ms": {
    "type": "number", "unit": "ms", "description": "刺激结束后的恢复时间",
    "status_column": "recovery_status",
    "missing_statuses": ["not_recovered", "no_detectable_response", "not_recorded"]
  },
  "recovery_status": {"type": "text", "unit": "1", "description": "恢复估计状态"}
}
```

对需要检查条件与重复覆盖的主要指标表，填写 `expected_groups`，例如 `{"network_id":["n1","n2"],"condition":["control","stimulus"]}`，表示这些字段的全部笛卡尔组合都应出现；实际分组应与计划一致。非全因子设计改用 `expected_combinations`，直接列出实际计划的字段组合对象，两种形式不同时使用。期望组合从运行前确定的方案/配置生成，不从待检查表反推。没有声明覆盖规则的 CSV 会列为待人工核对；声明的单位和字段正确性仍要查看产生数据的代码。

## 图件条目

本节的自动记录用于有实际数据依据的图，包括实际构建统计与运行结果。纯架构、机制、流程示意及仅由方法定义绘制的理论曲线，在现有 `docs/research/figure_plan.md` 中记录正式文件、可编辑源文件及对应方法/方程/参数/实现，由方法和结果报告直接引用；不为满足 `data_ids` 编造原始数据或运行。混合图逐面板注明示意、理论与数据用途，真实数据面板仍按本节登记；这不改变模型必须实际运行和保留结果图的要求。

每项包含唯一 `id`、非空 `files` 数组、非空 `data_ids` 数组、`code` 路径、`design_ref` 文件引用，以及非空 `command,caption,selection`。`files` 可以包含同一图的 SVG/PDF 和 PNG；`selection` 说明筛选、聚合与代表样本规则，未筛选时明确写全部。图引用的数据不能超出其所属结果条目引用的数据范围。

`design_ref` 指向[文献图阅读与本模型面板对应](literature-figures.md)的实际记录，可带 `#` 章节定位。没有合适参考图时记录自主设计理由，不能编造引用。工具只验证该文件存在且非空，不判断是否实际看过原图、设计是否适用或图是否准确，仍需人工核对。

程序只检查引用与非空文件，不执行绘图代码，也不推断像素是否与数据一致。打开主要图核对实际显示并从保存数据复算，是独立的必要步骤。非 CSV 数据的 shape、单位、时间映射和二进制可读性需用项目读取器核对。已经有其他格式时可在保持原始数据的同时导出兼容记录，或完成等价检查并说明未运行本工具，不能伪称自动检查已通过。

## 从清洁目录重建读者实际打开的报告

完整新研究的正文至少展示 6 幅有独立科学问题、能定位数据与绘图代码的结果图，通常安排 6–8 幅，复杂研究可增加。模型示意另计。同一幅图的多个面板或导出格式计为一幅。基线、病理、干预、参照与候选、个体差异、机制对照、稳健性和实测比较可按原研究问题组合。重要阴性结果可以独立成图。材料不足时交代已展示哪些结果及缺失原因。

沿用分析记录已登记的图 ID、文件和数据。把读者打开的 Markdown、HTML、主表和主图填入阅读版检查配置。完整字段示意如下。数组中的省略项需要按实际内容补充。`inputs` 逐文件列出重建用的原始数据、配置、代码及包含文字的模板。最终阅读文件、主表、结果 PNG、坐标范围文件和重建记录另列在对应字段。清洁目录只复制声明的输入，重新运行项目出图、排版和导出的可信入口。

```json
{
  "model_version": "v1.2.0",
  "markdown": "docs/results.md",
  "html": "docs/results.html",
  "inputs": ["analysis/render.py", "analysis/results_template.md", "results/observations.csv", "model/config.json"],
  "tables": ["analysis/output/main.csv"],
  "figures": [
    {"id": "F1", "path": "analysis/output/F1_model.png", "role": "overview"},
    {"id": "F4", "path": "analysis/output/F4_search.png", "role": "result",
     "axes": [{"table": "results/observations.csv", "x": "ei", "y": "gamma", "limits": "analysis/output/F4_axes.json"}]}
  ],
  "numbers": [
    {"table": "analysis/output/main.csv", "where": {"condition": "active"}, "column": "gamma",
     "decimals": 3, "label": "固定候选的 gamma/B"}
  ],
  "receipt": "analysis/output/reader_build.json"
}
```

含参数搜索散点的图，在绘图代码中记录最终 `ax.get_xlim()` 和 `ax.get_ylim()`，以 `xlim`、`ylim` 保存；`savefig` 后计算实际 PNG 的 SHA-256，填入同一 JSON 的 `figure_sha256`。每个展示全部候选的坐标轴逐点核对横纵范围。科学上需要局部放大时保留全部候选的总览，再另加放大面板。主要数字用选择条件在表内定位唯一一行，以约定小数位检查读者看到的数值。例如正文或一行表格同时显示“固定候选的 gamma/B ＝ 1.048”。表格需有列名和实际记录。文中 Markdown 的一级标题、HTML 的页面标题注明当前模型版本。

在本人已审核、使用工程相对路径的构建命令上运行下列入口；`--` 后的命令从空输出目录执行。给出的第一个参数为技能内检查脚本的位置。配置既可独立保存，也可由现行交付入口引用；命令行可直接读取含 `completion_review.reader_report` 对象的分析 JSON。数值检验和 PNG 解码使用本地 Python，读取图像时需要 Pillow。

```text
python <skill>/scripts/reader_report.py build --project <工程> --spec <阅读版配置.json> -- python analysis/render.py
python <skill>/scripts/reader_report.py check --project <工程> --spec <阅读版配置.json>
```

`build` 在临时目录运行显式提供的命令，将日期、时间戳等易变元素固定在已登记输入中，有助于文件的确定性重建。构建命令负责生成所有最终文件，包括 HTML 用到的本地图像副本。`check` 只读取证据，比较当前输入、输出与那次重建的记录，并逐图解码。两份阅读版均须实际嵌入登记的 PNG，HTML 可内嵌图像或使用可随目录复制的相对地址。相同像素的重复导出只计一次。推荐的 Markdown 语法为 `![图注](相对路径.png)`。读者应能在离线打开的最终文件中看到坐标轴、单位、图例和所有关键条件。

分别报告两项结论。`numeric_reproduction` 对照从原始输入重建的主表与交付表，按 CSV 的表头、行、字段内容核对。`reader_rebuild` 另外检查命令成功、Markdown、HTML 和 PNG 的重建一致性、图像在两个目录中能否解析、数字与指定单元格是否对应、已登记轴界内的候选覆盖，以及实际结果图数。主表成功而排版或图像失败时分别给出状态。程序比对并解码文件；最终仍需打开实际渲染的页面检查文字遮挡、图例可读性和图意是否重复。[检查入口](../scripts/reader_report.py) · [可运行的完整与失败示例](../evals/test_reader_report.py)
