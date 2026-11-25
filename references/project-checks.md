# 本轮要求、实际检查与联合核对

用于完整构建方案和模型交付。讨论阶段不要求建立全部文件；仅调研不执行实施检查。原有要素、参数与输出工具继续负责各自内容，`check_project.py` 核对它们是否对应同一任务与当前模型。脚本均默认只读，不执行模型、公式字符串或来源代码。

用于选型的[探索小运行](workflow-checks.md#探索小运行与正式构建)先保存其真实范围、设置和产物，不要求先让最终网络通过联合检查。现有脚本没有“跳过完整性但仍通过”的探索模式，不新增这种标记。探索纳入正式模型时补齐实际对应及适用检查；正式方案与交付的要求保持不变。

## 在构建前登记本轮要求

将[任务模板](../assets/task_plan.json)填写为 `docs/task_plan.json`。它是对当前构建方法的结构化引用，不另写一份科学方案。先人工核对用户目标、主要输出及必需机制，再登记；工具不会从一段自然语言自动推导完整研究要求。

| 字段 | 含义 |
|---|---|
| `schema_version` | 当前整数 `1`。 |
| `plan_id, model_version, catalog_version` | 当前方案、模型及清单版本。模块索引和当前分析使用相同标识；历史运行保留自己的来源。 |
| `mode` | `research/build/modify/reanalyze/audit`。只讨论无需完整任务文件；研究方案只用 `--phase plan`。 |
| `run_record_contract` | 新工程采用 `zm-neuron-run/1`，按[运行记录约定](versioning.md#运行记录与阶段衔接)生成解析配置与父/子运行记录；联合检查逐份核实。旧记录未声明时单列 `legacy_not_verified`，不冒充已验证，也不伪造历史补齐。 |
| `dynamics, state, state_reason` | `spiking/rate/static`；`resting/other/static`。选择默认静息态以外的状态时说明授权范围与理由。静态结构不填写虚构动力学。 |
| `features` | 已选择的 `spatial/lfp/plasticity/resting_spiking/resting_rate`；它们在清单目录中关联必须覆盖的事项。其他机制通过明确的事项登记，必要时扩充有版本的规则。 |
| `spec_ref, spec_sha256` | 当前完整构建方法及文件 SHA256（用于检查文件是否改变）。方法改动后核对要求，更新记录，不能只改校验值绕过审阅。 |
| `files` | 逐项表、模块索引、参数表、实际配置、实际实例导出、分析记录；`network` 可指向网络数值检查说明。不使用的可选路径删除字段，不能填写空路径后声称完成。 |
| `runtime_parameter_ids` | 本轮必须从实际对象核对的关键参数标识，在运行前确定。动态构建至少有一项；参数数量、适用对象及覆盖范围按研究需要确定，不能只挑已通过的参数。 |
| `requirements` | 每项包含唯一 `id`、具体 `description`、原要求或决定的 `source_ref`，以及 `item_ids,module_ids,parameter_ids,step_ids,result_ids` 数组。除不涉及具体参数时的 `parameter_ids` 外均非空。用简短出处和 `source_kind` 区分 `user`、`document_suggestion`、`assistant_choice`；文档建议说明是否采纳及理由，后来明确取舍优先，不复制整段私人聊天。这里登记本轮必需要求。 |
| `review_contract, review` | 新任务采用 `zm-neuron-review/1`，在同一计划中保存原目标、科学问题、必需完成项、数据用途、接受依据和适用技能文件；开始记录与恢复/交付核对见下节。不能只登记实现者容易完成的事项。 |

例如，要求计算 LFP 时将 `lfp` 加入 `features`，把相关详细事项与观测模块、参数、步骤和结果关联。不能遗漏该特征后称工具已自动确认用户目标；方案阶段的人工核对仍是必要工作。模块表中 `required_items` 保留这些事项及原因，联合检查确认没有漏登记或被改为不适用。各模块的 `parameter_ids,step_ids` 指向本项目实际条目，不生成独立的一套数值。

`analysis.json` 当前使用 `schema_version: 2`，增加 `plan_id,model_version`。旧格式仍可用于范围有限的输出检查；联合交付检查需要版本 2。修改任务保留完整清单，只重做受影响的检查；未受影响的记录要能证明其输入与代码未变。重分析保留模型方案及仿真来源，分析标识单独更新，原始数据不能因更新分析而重写。

## 记录实际检查，不手工填写成功标签

模块和完成步骤的 `check_refs` 指向 JSON 检查记录。记录由本次实际执行的检查代码产生，包含：

```json
{
  "schema_version": 1,
  "check_id": "cell_response",
  "status": "passed",
  "command": "python tests/check_cell.py --run results/r1",
  "run_ref": "results/r1/run.json",
  "run_id": "r1",
  "model_version": "m1",
  "module_ids": ["cells"],
  "step_ids": ["cell_response"],
  "config_ref": "results/r1/config_used.json",
  "config_sha256": "由实际文件计算",
  "code_sha256": {"model/cells/dynamics.py": "由实际文件计算"},
  "data_sha256": {"results/r1/raw/voltage.csv": "由实际文件计算"},
  "metrics": [
    {"name": "response_error", "actual": 0.0, "expected": 0.0, "atol": 0.01, "unit": "mV"}
  ]
}
```

示例只说明字段，不提供通用生理阈值；实际值、容差与判定根据本轮协议填写。指标可用有限数值的 `actual/expected/rtol/atol`，或 `actual/bounds`；离散检查可用布尔 `actual/expected`。至少有一项实际指标。不能把有失败项的报告改写为 `passed`，工具也会根据保存值重新核对判定。

运行记录的 `run_id` 必须相同且 `status: completed`；构建或分析操作可有自己的真实运行记录，不冒充完整仿真。`code_sha256` 覆盖模块源码及依赖的自定义机制/导出代码，`data_sha256` 覆盖用于该检查的数据。一个模块的多份检查共同覆盖它声明的代码和结果。文件改变、配置不匹配、报告属于其他模块/步骤或判定失败时，原完成记录失效。

采用新运行约定时，检查脚本还会核对真实解析配置、已归档源码、输入、父记录及已完成输出；输出检查同样读取这些绑定。检查记录中 `config_ref` 是该次检查实际采用的配置，与被检查运行的产生配置各司其职；比较多个条件时不把它们都改成主配置的校验值。工具只验证所声明的关系，未登记的科学要求或实际依赖仍须按[科学约束](scientific-constraints.md)审查，`passed` 不证明机制成立。

校验值用于发现改变，不能替代可恢复源码，也不能证明记录真实。仍需检查命令、入口和数据来源；通用工具不会判断所有后端的函数是否真正被调用。按模块安排能体现实际作用的检查，如受控输入、机制关闭或方向/延迟响应；静态模块检查实际生成结构，不伪造时间轨迹。

## 联合检查与缺口报告

```text
python <skill_dir>/scripts/check_project.py --project <project> --phase plan
python <skill_dir>/scripts/check_project.py --project <project> --phase implemented
```

需要保存时加 `--output results/<run_id>/project_check.json`，只在已有目录中新建文件，不覆盖原记录。报告分开列出要素、参数/实例与输出检查，实测验证另行报告。计划阶段检查方法、要求和计划中的模块关系，不要求源码已存在；实施阶段读取实际记录、参数与输出。不因没有全文、原始数据或预算就将本轮必需要求改为可选。

旧工程缺少新格式时从实际记录补充可恢复内容。无法恢复的运行或检查明确未完成，不能为通过新工具补写从未发生的检查。独立交付时复制实际使用的检查脚本及其导入依赖；联合检查需包含 `check_model.py`、`check_elements.py`、`check_outputs.py`、`check_records.py`、`review_project.py`、`check_reuse.py`、`check_regulation.py`、`show_progress.py` 和 `calibration.py`，清单检查还需同时保存原文副本与 `element-catalog.json`；以 `--checklist` 指向随工程保存的清单。采用网页导出时另保留 `build_viewer.py` 及对应的 `assets/progress_viewer.html`；自动打开还保留 `preview_viewer.py`。网页服务不作为科学检查通过的前置条件。

## 在阶段转换恢复和交付前执行复核

使用现有 `docs/task_plan.json` 保存当前适用要求，`analysis.json` 保存实际完成判断，`docs/progress.md` 只写关键决定与下一动作。开始时用 [review_project.py](../scripts/review_project.py) 留存一次原要求记录；它是不可覆盖的历史副本，不是第二份当前方案。初期仅明确需求时登记已知目标和待决定范围，不先填一套虚构完整网络；进入正式构建后补齐原有要素、参数和模块关联。

| 时点 | 实际读取与处理 | 不允许的替代 |
|---|---|---|
| 开始一轮任务 | 恢复原目标、来源性质、已确认取舍和范围；登记必须完成的比较与产物，说明不适用事项；保存实际采用的规则版本 | 将助手的建议自动算作用户要求，或只把已经容易完成的内容登记为必需 |
| 从方法进入构建、从局部检查进入正式运行 | 读当前要求和本阶段规则，确认机制/参数、来源转换、数据用途、观测及接受依据已具体化，预算仍足够 | 每一步通读全部技能，或仅因阶段标签改变就机械要求用户批准 |
| 中断或新会话恢复 | 对照原要求和当前规则版本，核实实际任务、有效配置、已有结果、未解决项和累计预算；规则变化先判断影响，必要时重读受影响章节 | 用旧进度猜测进程仍在运行，重新启动已完成计算，或用新版规则悄悄改旧指标 |
| 比较后及最终交付前 | 从用户目标顺着问题、机制/参数、运行、真实数据、迭代决定到图文结论逐项核对；复算关键数值，实看图件，并检查实际将发送的核心正文 | 检查文件存在、六个标题或实现者自评后自动把全部状态填成 complete |

采用规则变化与科学范围变化分别记录。常规规则修复可以在既有授权内应用，但须说明哪些结论/记录受影响；删除或降低用户原必需要求须有真实的用户决定来源，不能只更新文件摘要以绕过核对。旧工程只读审查时输出未复核或无法恢复项，不补造历史登记、原始运行和事前标准。

五项状态独立报告：

| 判断 | 看什么实际内容 |
|---|---|
| 运行完成 | 本轮必要运行与分析是否实际结束，是否对应采用的配置、代码、输入和时间范围 |
| 校准满足 | 预定可比条件与统计单位下，各项必需接受规则是否满足；均值合格不能抵消分布或其他约束失败 |
| 独立评价支持 | 冻结后的模型是否得到未参与选择且条件可比的相应数据支持；新种子或合成参考不冒充生物数据 |
| 科学问题已回答 | 原问题是否得到有判别能力的比较与合理解释；**主要拟合指标未满足文献与真实数据要求时不属于有效阴性，须继续优化**；有效阴性或未能区分可以是答案，缺比较/数据则仍未完成 |
| 交付完整 | 六项适用内容是否由同版实际产物组成，报告和最终答复都包含核心说明、量化结果及图件，而不只有附件链接 |

校准与假设检验在第一次运行前分别登记。全模型维持五项判断，`goal_complete` 反映本轮科研目标，`ready_to_deliver`、`ready_to_send` 分别反映交付材料和实际待发送文件。每次检查须读取问题和各项状态。模型、模块、参数、结果或正文检查已经报错时，先定位并修复，再从原入口复核。若当下受阻，可交付标明错误、影响和恢复条件的阶段说明。成功退出、报告排版完整或某次仿真结束均不足以宣布研究完成。

完整建模采用或修改模型时，检查自动启用。其他任务若确实交付一个最终模型，可以声明 `review.final_model_requested=true` 并使用完整交付。每个必需的 `requirements[].acceptance` 在正式运行前写入依据、条件、时段、对照、判据与结果对应关系，见[同一采用模型的逐项核对](final-model.md)。补查遗漏时保留原记录，在 `review.scope_changes` 保存来源和理由。补入必需要求时用 `change=add:requirement:<id>`，补入必需判据时用 `change=add:criterion:<目标文件>#<id>`。新一轮捕获识别上轮运行对应的要求文件；有多份候选文件或尚未正式运行时，通过 `review.previous_requirements_ref` 指定并保留上一轮。每一轮都重查早先的必需标准。事后放宽范围不能作为已达到原标准的依据。

跨轮沿用研究方案时，原先分别检验的比较和独立队列仍要分别核对。通常保留已有的比较和资料编号。若多个比较或队列均改名，且无法从条件和观测单位确定原先的对应关系，在新比较中用 `replaces_comparison_ids`、在新资料中用 `replaces_dataset_ids` 标明前身。一项必需比较须有自己对应的结果，直接比对原定的两批独立观测也须保留两个独立来源或事先划分的统计单位。

只有当前最终交付检查的 `final_model_ready=true` 才表示最终采用版本满足完整建模要求。发送六项正文还须检查实际文件，核对 `ready_to_send_final_model`。用户需要阶段结果时，可用 `review_project.py --project <工程目录> --stage-report-output docs/stage.md` 输出当下已经核实的数据、缺口及后续工作，发送前以 `--stage-report-file docs/stage.md` 复核。此时依据 `stage_report_ready_to_send` 发送该进展说明，科研检查的退出状态仍反映原任务。处于 `continue_required` 或 `repair_required` 时继续执行。

- 在 `review.component_calibration` 为本轮各部分登记 `mode: targets`，并在必需校准目标写明 `component`。仅承担预测、对照等职责的部分可登记 `outside_calibration`，写明 `reason,source_ref`。已有目标缺少合格数据时保留原目标和缺口。程序逐部分从当前运行的逐项比较汇总；多个部分不能共用一个未归属的达标结论。
- 以检验预测为目的时在 `review.independent_goal` 登记 `test_prediction`。若已约定必须证明支持才达到用途要求，登记 `require_support`；旧计划未声明时沿用后者。前者得到阴性结果仍可完成：预先留出的观测和判据均已核对，所有必需结果均有有效测量，独立评价保留 `not_supported`，注明 `evaluation_completed,adequacy_reason`；对应问题引用实际比较并解释效应范围和精度。设计不足、测量缺失和运行失败须保留为未评价或无法判定。主张效应可忽略，还须在原始单位上与预定的实质差异界限比较。 对检验本身可以得出阴性回答。原目标还要求正向支持时，该用途目标继续保留为未达到；重新建模后使用新的独立观测。
- 在 `review.selection_uses` 登记事前筛选规则，在 `completion_review.selection_uses` 或 `iterations[].selection_uses` 补记实际用过的资料。每条写 `dataset_id,feature,quantity,rule_ref`，`feature` 为 `value/direction/contrast`；只用了部分观测时列出真实 `observation_ids`。相同来源的不同文件可共享稳定的 `source_id`。候选轮将比较列入 `comparison_ids` 即表示其参与决策。逐条核对真实筛选代码、表格、淘汰记录及全部试过的方向，包括没有出现在标准比较文件中的条件。使用后的数据可以报告为开发结果；新种子可检查计算稳定性，生物独立评价需要预先保留且未参与选择的观测。
- 各适用模块的失配先按数据可比性、机制、参数、观测方法或对照设计定位。在 `decision.attribution,correction_ref,affected_comparison_ids,next_action` 中记录判断。参数问题写入 `next_batch` 并实际运行；机制或观测问题回查文献、公开代码和实测，修正后重跑受影响的条件。复查已达标项目。运行与恢复见[上轮决定与本轮复算](round-followup.md)。
- 完整建模只在用户明确要求现在停止，或授权范围内的可行工作均已完成、余项确受外部条件阻断时暂停。`decision.action=stop` 保留 `source_ref,gap,recovery_condition,next_action`。`attempts` 记录已试方法及其 `evidence_ref`。外部受阻时，逐项说明备选方法的 `method,feasible:false,blocked_by,evidence_ref`，将原始回复关联到受影响的尝试或备选方法。
  - `user_decision` 使用 `source_kind=user`，`source_excerpt` 引用用户当前的完整停令。可指向保存的单条消息，或含 `role,content` 的原始消息记录。消息列表按最近一条用户消息判读。核对整句及上下文，区分立即停工、要求继续、否定停止和约定将来满足条件再停。
  - `budget_exhausted` 核对用户或资源方给出的总授权、计量单位和累计实际消耗。可引用写明额度的原话，也可使用资源方原记录中的 `scope:"total",limit,unit`，如有 `remaining` 必须为零。首轮模拟调用数须有对应的实际运行记录。
  - `resources_unavailable` 和 `missing_data` 引用资源方、资料提供方或实际访问日志，`source_kind` 分别可填 `resource_provider`、`data_provider`、`access_log`。可直接核对带请求地址的 HTTP 拒绝或服务故障响应，也可核对提供方保存的 `url` 或 `resource,request_id` 及实际状态。例如，计算队列返回 HTTP 503 或明确记录 `available:false` 时，即使仍有模拟额度，也可能需要等待队列恢复。资料缺失还须将回复与相应资料条目关联。一批运行结束、手写的故障解释和仅注明备选方法不可行，都不足以判定暂停。
  - 自动检查能识别部分中英文直接停令和常见的外部状态记录。其他语言、复杂条件或来源归属不清时，保留原文供人工核实，同时继续可做的工作。尚未核实的 `stop` 会得到 `repair_required`，科研目标保持未完成。

交付复核还需按[文字、表格与图件检查](external-skills/clear-writing.md#输出前如何检查)实际查看当前输出：名称/单位是否一致、术语和条件是否能理解、图内文字是否显示完整、改写是否保留数据与结论强度。图件的查看与修订记录复用 `figure_plan.md`，其他问题写入原复核说明；不新建另一套完成状态。未看的图件保持待检查，已发现且影响理解的文字问题先修正，不能凭软件检查通过宣称文字检查也通过。

现有 `--phase plan/implemented` 的软件检查不能替代交付复核。已有可读任务计划但未声明新约定时，返回 `legacy_not_reviewed`；任务计划缺失或不可读则返回 `failed` 并说明原因。按实际返回值报告，不能凭“旧工程”预期改写状态；这些状态说明记录尚不足以复核，不等于生物学结论失败，也不自动写成研究完成。

### 记录与运行约定

本轮开始登记 `review.display_progress: true` 和 `review.model_components`，前者要求最终正文实际包含状态表，后者记录适用的基础/负面影响/调控部分。`review.viewer.auto_open` 默认 `true`，工程与计划建立后立即按[当前对话打开](execution-management.md#在-codex-内查看)执行；继续优化/调参时在恢复工程后、研究讨论前重新打开或刷新，阶段转换、恢复和交付时同时更新相应页面，查看器可访问不能替代浏览器已打开或科研完成判断。原要求中启用的展示不能删字段绕过；新增实现关联按实际工作补齐。阶段展示及字段见[用户可见状态](execution-management.md#让用户看见阶段与验证结果)。

复用 [task_plan.json](../assets/task_plan.json) 和 [analysis_manifest.json](../assets/analysis_manifest.json)，新建任务均声明 `review_contract: "zm-neuron-review/2"`。不要复制整套空模板后批量填写成功。

- 每项 `requirements` 写明 `id,description,source_kind,source_ref`，继续使用原有模块、步骤、参数和结果关联。来源性质是 `user/document_suggestion/assistant_choice`；来源文件保存必要的目标与决定摘要，不要求复制私人聊天。构建过程中补充实现关联不算缩减范围。
- `review` 保存 `objective`、`questions[{id,text,required}]`、`required_axes`、适用的 `skill_files`、`criteria_refs`、`datasets` 与 `baseline_ref`。接受依据使用 [校准工具](../scripts/calibration.py) 的目标格式，明确数据用途、条件、统计单位及范围。捕获前可以保留待确定问题，正式运行前补齐必要标准并记录变化；不能把运行后才决定的标准说成事前标准。
- 数据条目含 `id,kind,role,available,comparable,used_for_selection,conditions,source_ref`；`kind` 为 `biological/synthetic/model_output`，`role` 为 `calibration/evaluation/reference`。`source_ref` 指向实际来源记录或观测文件，多文件资料另列 `files`；目标的 `source_ref` 必须对应所比较数据的一项已登记来源。捕获时保留这些文件的校验值，更新资料另存版本，数据用途变化则更新条目而不改原始观测。没有数据写 `available:false` 和 `unavailable_reason`；用于新方向或选参的数据在现有工程记录中同步用途，不能只在答复提及，也不能换编号后重新宣称独立。
- 完整模型采用 `delivery_profile: full_model`。原任务只要调研、教学或部分分析时用 `scoped`，在 `delivery_parts` 按原顺序选适用部分，并以 `delivery_scope_reason/ref` 说明原范围。不能事后借此删除原任务必需结果。`independent_evidence: synthetic` 只用于明确的软件试验，真实生物评价默认 `biological`。
- `analysis.completion_review` 保存五项 `axes`、逐要求 `requirements`、实际 `comparisons`、`iterations`、累计 `budget`、继续/停止 `decision` 和 `delivery`。判断均写明 `assessor,reason,evidence_refs`；运行成功、校准满足、独立支持、科学问题已回答、交付完整分别为 `completed/satisfied/supported/answered/complete`，未做、不支持和不适用使用各自状态，不能自动转换。
- 比较条目关联 `axis,data_role,dataset_ids,targets_ref,measurements_ref,score_ref,config_ref,run_ref,candidate_id`。观测值除单位、条件等原有字段外，`source` 指向实际输出 CSV 的 `csv_ref,column,operation,where`；工具从运行绑定的数据复算后再判定。历史比较显式标为 `historical:true`，不能用于宣称当前模型满足要求。
- 正文中的关键数值应从已登记的原始记录计算。若正文引用派生结果表，在相应的 `delivery.claims[]` 写入 `raw_calculation`，重新计算并比对表值与正文。均值等使用原始列和条件；配对相关使用 `operation: pearson` 和同一行的 `column,other_column`；组间差用 `operation: difference` 和两个原始选择 `left,right`。更复杂的变换保留原分析代码、输入、逐层输出及复算过程，人工核对统计单位和变换含义。
- 迭代条目用 `initial/candidate/final` 关联实际运行、配置、比较和取舍理由。预算记录累计 `limit/consumed`。完整研究有未满足项且仍有可行工作时，登记 `continue` 并执行。参数偏差对应下一批有依据的配置，机制、观测方法或对照偏差对应受影响条件的修正和重跑。只有用户明确叫停或有当前授权内无法解决的外部阻碍才可暂停。充分的阴性检验在科学回答中记录实际比较、`comparison_complete` 和 `adequacy_reason`。
- `delivery` 引用实际 `report_ref` 并保存准备发送的 `response_text`。`parts` 以 `abstract,methods,equations,questions,biological_comparison,limitation` 顺序保存完整分节正文（含本节图与公式）、关联已有图件、量化 `claims` 和问题图组。数值只能来自已登记完成运行的输出（派生表需实际分析运行），或所声明的参考文件；任意 CSV 与文字自洽不算有效。图件明确 `depiction: schematic/actual_model/data_result`，最终答复使用可显示的绝对本地图片路径。公式关联 `methods_ref` 指向的构建方法正文、实际公式、符号单位、参数文件、源码及对应代码段；不能只列六个标题。发送前确认实际答复与已检查内容相同。

```text
python <skill_dir>/scripts/review_project.py --project <project> --capture --skill <采用的skill目录>
python <skill_dir>/scripts/review_project.py --project <project> --checkpoint start
python <skill_dir>/scripts/review_project.py --project <project> --checkpoint transition
python <skill_dir>/scripts/review_project.py --project <project> --checkpoint resume
python <skill_dir>/scripts/check_project.py --project <project> --phase delivery
```

捕获只执行一次且不覆盖原记录；之后的检查只读。若使用的规则不在执行脚本同目录下，检查也传相同的 `--skill`。`scope_changes` 保存真实来源、原因、原范围标识及影响；`skill_changes` 保存变动文件的前后版本、复核人、依据和是否改变科学标准。原目标不变的下一轮继续引用原要求，并补充本轮目标，不重置历史规避原失配。

复核结果分别给出 `consistent`（记录与数值一致）、`ready_to_deliver`（可交付如实报告）、`goal_complete`（所登记的必需目标均满足）；退出码 `0/2/1` 分别表示满足、尚未满足或旧格式未复核、记录不一致。初期读取建议 `read_next` 仅指导下一步，不能证明实际已读。使用可执行例子了解完整嵌套字段：`python <skill_dir>/evals/review_fixture.py --help`；软件失败用例见 [test_review_project.py](../evals/test_review_project.py)，已并入现有工作流测试。

最终检查返回的 `progress.table_markdown` 须放入报告与答复第5项，再次核对并以 `--response-output <新文本路径>` 导出发送稿。中途问题不取消六项交付，追加答复只能在科研交付块之后；详见[完整正文组装](result-delivery.md#中途补充不取消完整交付)。首次检查未放表会明确报告缺项；用 `required_progress_table` 补稿后重新检查，`progress` 仍显示当前真实状态，不把补稿模板当作已完成；不能因缺表直接取消展示要求。

阶段性开源复用同时读取任务计划中的 `reuse`：当前阶段是否比较已有能力，实际采用版本/本次更新检查与交接是否明确，软件运行是否关联对应版本的真实记录。规则及最小结构见[阶段性接入](open-source-reuse.md#在现有记录中落实采用)。结构通过只表示记录对应，不证明来源可靠、已经阅读或科研方法有效；旧工程缺记录时明确未审查，不自动补写历史。

完整调控实施还核对 `review.regulation` 与 `completion_review.regulation`。已登记的实施范围不得删除后规避多组合搜索和确认；初期设计未齐可登记 `pending`，但不能标为研究完成。检查器从保存配置与实际 CSV 重算 B/D0/候选/确认，检查搜索设计、固定模型、独立条件、分项约束、真实调用与预算及三类结果关联。阴性且比较充分可完成研究过程，缺搜索/确认则未完成；两者都不能自动变成“恢复”或生物学独立评价支持。记录方式和计算范围见[调控执行与复核](regulation-design.md#执行记录与完成复核)。程序之外仍须查看原委托、作用实现、完整文献协议、原始分布/轨迹和图件，判断可比性、搜索充分性与科学结论。

## 当前模型与实际发送的检查

新任务使用`zm-neuron-review/2`，以下内容仍保存在原任务计划、分析记录和方法正文，不增加第二套流程。AI从当前方法、配置和实际分析生成这些字段，不要求用户填写程序表格。旧`/1`可按原约定读取，但返回提示说明未接受这些新增检查；升级时保存原记录，逐项判断影响，不把回顾补记说成运行前已经核对。

**当前模型。** `docs/task_plan.json`是当前入口。`current_model`包含`name,spec_ref,config_ref,changed_parameter_ids,parameter_bindings`；方法及配置引用须与计划原字段一致，具体模型名出现在当前方法及两份摘要。每个绑定含`parameter_id,config_pointer,value,unit,spec_excerpt`，把本轮变更和关键参数对应到配置、原参数CSV及方法中的实际说明。检查整张参数表的配置值；`modify`还需`previous_config_ref`，据前后配置识别漏报的变更。旧配置确实不可得时写`previous_config_unavailable_reason`，保留尚未完成状态，不能靠只绑定一个未变参数通过。数字与短文本对应并不证明自然语言解释正确，仍须科学复核。

**主要效应和偏差。** `review.scientific_checks`在计算前按问题登记必需的比较及重要方法取舍，`completion_review.scientific_checks`保存同ID的实算结果和处置。不用一个通用“模型合理”项目替代各题的主要比较。

对会影响主结论的比较，填写具体可检验的 `description`，需要指向上层主张时可另写 `conclusion`。报告所涉主张、实际读数和仍可保留的观察。`outcome_scope` 说明 `outcome` 针对哪项判据。数值稳定性只回答精度问题，统计单位或实验顺序的核对只回答比较设计问题。完整且有判别力的比较可支持假设（`supported`）或不支持假设（`not_supported`）。多个解释仍相容时用 `inconclusive`，条件、数据归属或必要配对有缺口时用 `not_evaluated`。只有[原主张仍需判别](scientific-questions.md#判断补充实验是否必要)时才在 `minimum_comparison` 说明最小补充比较。完整的参照误差可以直接报告，该字段可留空。

一项参数错误可能只影响部分问题。错误报告标出参数表文件、CSV 行、参数 ID、配置文件和字段路径。要保留能独立完成的科学比较，在运行前用 `parameter_ids` 列出该比较实际依赖的参数。明确独立于模型参数的读数可填空数组；没有填写时，参数异常期间依赖关系仍未知。核对原计划与本轮分析、原始运行或留存的实测记录后，正常审查入口会分别重算可归属的项目。依赖错误参数、事后改变依赖、无法确定统计单位或原始对照归属的结论保持未评价。已核实的单侧读数和已有时间窗可作为描述性观察保存，整体交付仍须处理参数错误。

| 类型 | 开始时登记 | 从实际结果记录与检查 |
|---|---|---|
| `reference_change` | `id,question_id,kind,required,basis_ref,description,unit,tolerance,tolerance_basis` | `before,after,reference`引用实际CSV选择；参考可为数值或`lower/upper`区间。分别重算初始及最终距离；误差增大须说明取舍或尚未解决，不能用均值改善抵消。分布和时程先用适合问题的分析生成指标及图，不能以此标量接口取代完整比较。 |
| `numerical_effect` | 同上；按每个主要条件差单列，精度依据来自问题；必要时加`direction_floor` | `before/after`为配对效应及可用区间，记录`pairing_ref/pairing_reason`说明实际网络和输入对应。超出精度、重要变号或区间明显变化分别处置；一组稳定不能替代另一组。小幅过零本身不证明有作用或无作用。 |
| `method_assumption` | `id,question_id,kind,required,basis_ref,description` | `original_method,implemented_method,choice_reason,consequence`说明最近邻方法、关键输入/突触/观测假设及选择后果。按实际资料写已采用、条件性采用或尚未解决，不强制统一受体、三维表示或输入配平。 |
| `mechanism_activity` | 问题列出 `required_mechanisms`。各机制登记 `mechanism_id`、运行来源、正式时窗、观测量、作用方向与判据。 | 从该次运行输出读取量值，逐窗区分短暂出现与持续作用。必要时在共同时间点核对只改变该机制的匹配对照。 |
| `comparison_design` | 问题列出 `required_design_dimensions`。按适用维度登记 `dimension_id`、预定处理或统计单位、范围、水平或重复数。 | 从实际比较使用的逐行数据核对各组。偏离方案时说明偏差及其限制；原问题仍无法判断时保留未完成。 |

当分母声称为独立动物或细胞时，可在 `comparison_design` 用 `rule: one_row_per_unit`、`expected: true` 和现有 `source.column` 指定单位 ID。`where` 选择实际纳入分母的记录。程序返回纳入行数、不同 ID 数和超过每单位一行的重复行数。同一细胞可有多次刺激，原刺激记录仍可用于刺激层面的分析。细胞比例要对照真正进入计算的逐细胞汇总行；这些细胞是否来自独立动物，另按实验设计核对。

这两类检查的取数方法和判读见[科学约束](scientific-constraints.md)。明确本轮可用的模拟预算时，把 `limit,unit` 写入事前 `review.simulation_budget`；用尽的调用需与实际运行记录相符。完整建模交付还核对 `delivery.reproduction.commands` 中发表的命令、默认或显式配置和采用版本，沿用[结果交付](result-delivery.md)中的说明。实现检查与复现材料的缺口须进入当前判断。

CSV选择使用已有的`csv_ref,column,where,operation`；数值效应需要区间时用`{estimate,lower,upper}`三个选择。文件必须属于登记的真实运行/分析输出或参考资料，不能随手造一张表自证正确。新增分析注明探索性质；运行后增加的检查使用`timing: exploratory_after_run`，保留原定义，不改容差制造通过。

完整结果行含`id,status,reason,support_scope,evidence_refs,disposition`。有变差、数值敏感或条件性假设时，补`next_action,report_excerpt`，并在`decision.scientific_check_ids`逐项交代采用、继续或停止的依据；`report_excerpt`必须实际进入报告和发送正文。`reference_change`的处置为`accepted/tradeoff/unresolved`，`numerical_effect`为`accepted/resolved/unresolved`，`method_assumption`为`adopted/conditional/unresolved`。数值问题称已解决时，`confirmation`引用新的实际比较并仍按原精度核对；尚未完成的必需比较对应问题不能标为已回答。合理的条件性结论或阴性结果可交付，缺数据和未完成工作如实保留，不自动要求扩大模拟。

**运行前与续接。** 首先登记原目标；方案尚未确定时检查可返回`incomplete`，继续调研讨论。进入计算前补齐模型、适用比较和接受依据，再检查当前阶段。`begin_run`为新约定保存当时的要求引用与比较定义，不能在运行后补一份记录就声称完成过事前检查。`review.previous_analysis_ref`指向保留的上轮分析，预算记录`previous_consumed,round_consumed,consumed,limit,unit`，累计量为前两项之和；历史成本不全时保留已知下界并写`history_incomplete/history_reason`，不重置成零。更换计划不能删除原开源复用决定，复用或调整理由写回原`reuse`。

旧运行可在`review.reused_runs`中记录`run_ref,run_sha256,preparation_status: retrospective_review,assessor,reason,evidence_refs`，核对原输出、配置及适用性后复用。它必须早于本轮要求记录，不能让新运行借历史名义跳过准备。回顾复核既不补造事前判据，也不因升级规则重跑所有计算。真实运行、各项检查及是否能支持科学结论仍分开判断。

**独立比较与图件。** 已经进行描述性评价、但可比性或判据不足时，独立评价用`inconclusive`，记录`evaluation_completed:true`及实际`comparison_ids/result_ids`；显示“已评价，尚不能判断是否支持”，不打勾。没有计算仍用`not_evaluated`，有明确不支持依据才用`not_supported`。混合方法图用`depiction: mixed`和`panels[{id,depiction,label}]`；逐面板区分`schematic/actual_model/data_result`，完整标签在所属图注或正文可见。程序检查声明及文本，不能自动鉴定图片是否来自所称数据，实际看图仍是必要工作。

**最后发送。** 先完成原交付复核，把当前状态表放入第5项；用`--response-output`导出正文时会再检查该文件。已有或修改后的文件用以下入口重新检查，不能只复用上一次成功记录：

```text
python <skill_dir>/scripts/review_project.py --project <project> --checkpoint delivery --response-file docs/response.md
```

只有`ready_to_send:true`才说明这次准备发送的文件与当前方法、数据和完整正文一致；直接使用其内容，补充问答已由原组装规则置于六项之后。脚本没有宿主发送权，`host_send_verified`不会因文件通过而变成真。`--sent-response-file`只复核由宿主读取或用户提供的实际消息文本，不自动取得聊天，也不把文件本身视为消息来源证明。`--historical`仅用于只读历史检查，不能导出当前交付。

要检查首次失配能否触发实际计算，可在技能目录运行下面的程序，指定一个尚不存在的工程目录。它保留首轮阶段报告、两轮配置和原始时序、第二轮交付检查，以及各项不满足时的判定。校准范围和模拟规模均来自演示自己的方案。

```text
python -B -X utf8 evals/test_optimization_round_case.py --workspace <新目录>
```

[两轮网络算例](../evals/optimization_round_case.py) 与[对应检验](../evals/test_optimization_round_case.py)通过常规建模入口运行。另见[逐项采用判断](../evals/test_final_model.py)、[跨轮复算](../evals/test_round_followup.py)、[分项科学判断](../evals/test_scientific_review.py)与[发送正文](../evals/test_delivery_response.py)。

## 清单更新与固定编号

`element-catalog.json` 保存事项的固定 ID、原文、类别和适用规则；`01.01` 等 ID 现在是永久标识，不由出现位置重新生成。新增事项使用未占用编号，已有事项移动位置不改 ID；拆分或废弃时保留明确迁移关系，不能把旧 ID 分配给不同含义。清单版本更新后同步副本、目录、模板及引用，人工核对事项变化和适用规则。

目录记录所对应原文文件的 SHA256。原文变化而目录未更新时检查失败；仅更新原文摘要并不足以证明事项语义已正确迁移。原文件可访问时继续对照原文件，保留全部通用定义与按需机制的原始含义。
