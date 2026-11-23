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

旧工程缺少新格式时从实际记录补充可恢复内容。无法恢复的运行或检查明确未完成，不能为通过新工具补写从未发生的检查。独立交付时复制实际使用的检查脚本及其导入依赖；联合检查需包含 `check_model.py`、`check_elements.py`、`check_outputs.py`、`check_records.py`、`review_project.py`、`check_reuse.py`、`check_regulation.py`、`show_progress.py` 和 `calibration.py`，清单检查还需同时保存原文副本与 `element-catalog.json`；以 `--checklist` 指向随工程保存的清单。采用网页导出时另保留 `build_viewer.py` 及对应的 `assets/progress_viewer.html`，不将网页生成列为普通检查的前置依赖。

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
| 科学问题已回答 | 原问题是否得到有判别能力的比较与合理解释；有效阴性或未能区分可以是答案，缺比较/数据则仍未完成 |
| 交付完整 | 六项适用内容是否由同版实际产物组成，报告和最终答复都包含核心说明、量化结果及图件，而不只有附件链接 |

**报告可诚实交付，不等于原科学目标全部达到。** 例如外部比较已做完但不支持模型，交付仍应呈现实际差异；缺少所需真实数据或比较能力时不能把独立评价/科学问题标为满足。必需目标未达时，记录可执行的下一步及继续/停止依据；剩余授权和预算足以完成必要工作时继续实施。程序只验证记录、数值与关系，来源真实性、目标覆盖、授权与科学论证仍由主 agent 及适用的[独立复核](delegation.md)查看原材料判断。

现有 `--phase plan/implemented` 的软件检查不能替代交付复核。已有可读任务计划但未声明新约定时，返回 `legacy_not_reviewed`；任务计划缺失或不可读则返回 `failed` 并说明原因。按实际返回值报告，不能凭“旧工程”预期改写状态；这些状态说明记录尚不足以复核，不等于生物学结论失败，也不自动写成研究完成。

### 记录与运行约定

本轮开始登记 `review.display_progress: true` 和 `review.model_components`，前者要求最终正文实际包含状态表，后者记录适用的基础/负面影响/调控部分。原要求中启用的展示不能删字段绕过；新增实现关联按实际工作补齐。阶段展示及字段见[用户可见状态](execution-management.md#让用户看见阶段与验证结果)。

复用 [task_plan.json](../assets/task_plan.json) 和 [analysis_manifest.json](../assets/analysis_manifest.json)，均声明 `review_contract: "zm-neuron-review/1"`。不要复制整套空模板后批量填写成功。

- 每项 `requirements` 写明 `id,description,source_kind,source_ref`，继续使用原有模块、步骤、参数和结果关联。来源性质是 `user/document_suggestion/assistant_choice`；来源文件保存必要的目标与决定摘要，不要求复制私人聊天。构建过程中补充实现关联不算缩减范围。
- `review` 保存 `objective`、`questions[{id,text,required}]`、`required_axes`、适用的 `skill_files`、`criteria_refs`、`datasets` 与 `baseline_ref`。接受依据使用 [校准工具](../scripts/calibration.py) 的目标格式，明确数据用途、条件、统计单位及范围。捕获前可以保留待确定问题，正式运行前补齐必要标准并记录变化；不能把运行后才决定的标准说成事前标准。
- 数据条目含 `id,kind,role,available,comparable,used_for_selection,conditions,source_ref`；`kind` 为 `biological/synthetic/model_output`，`role` 为 `calibration/evaluation/reference`。`source_ref` 指向实际来源记录或观测文件，多文件资料另列 `files`；目标的 `source_ref` 必须对应所比较数据的一项已登记来源。捕获时保留这些文件的校验值，更新资料另存版本，数据用途变化则更新条目而不改原始观测。没有数据写 `available:false` 和 `unavailable_reason`；用于新方向或选参的数据在现有工程记录中同步用途，不能只在答复提及，也不能换编号后重新宣称独立。
- 完整模型采用 `delivery_profile: full_model`。原任务只要调研、教学或部分分析时用 `scoped`，在 `delivery_parts` 按原顺序选适用部分，并以 `delivery_scope_reason/ref` 说明原范围。不能事后借此删除原任务必需结果。`independent_evidence: synthetic` 只用于明确的软件试验，真实生物评价默认 `biological`。
- `analysis.completion_review` 保存五项 `axes`、逐要求 `requirements`、实际 `comparisons`、`iterations`、累计 `budget`、继续/停止 `decision` 和 `delivery`。判断均写明 `assessor,reason,evidence_refs`；运行成功、校准满足、独立支持、科学问题已回答、交付完整分别为 `completed/satisfied/supported/answered/complete`，未做、不支持和不适用使用各自状态，不能自动转换。
- 比较条目关联 `axis,data_role,dataset_ids,targets_ref,measurements_ref,score_ref,config_ref,run_ref,candidate_id`。观测值除单位、条件等原有字段外，`source` 指向实际输出 CSV 的 `csv_ref,column,operation,where`；工具从运行绑定的数据复算后再判定。历史比较显式标为 `historical:true`，不能用于宣称当前模型满足要求。
- 迭代条目用 `initial/candidate/final` 角色关联实际运行、配置、比较及取舍理由。预算记录累计 `limit/consumed`；未达标时 `decision.action` 是 `continue` 或有依据的 `stop`，同时写剩余动作。有效阴性或无法区分机制，仍需在问题判断中说明实际比较、`comparison_complete` 和 `adequacy_reason`。
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

## 清单更新与固定编号

`element-catalog.json` 保存事项的固定 ID、原文、类别和适用规则；`01.01` 等 ID 现在是永久标识，不由出现位置重新生成。新增事项使用未占用编号，已有事项移动位置不改 ID；拆分或废弃时保留明确迁移关系，不能把旧 ID 分配给不同含义。清单版本更新后同步副本、目录、模板及引用，人工核对事项变化和适用规则。

目录记录所对应原文文件的 SHA256。原文变化而目录未更新时检查失败；仅更新原文摘要并不足以证明事项语义已正确迁移。原文件可访问时继续对照原文件，保留全部通用定义与按需机制的原始含义。
