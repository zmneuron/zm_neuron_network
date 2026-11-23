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
| `requirements` | 每项包含唯一 `id`、具体 `description`、方法中的 `source_ref`，以及 `item_ids,module_ids,parameter_ids,step_ids,result_ids` 数组。除不涉及具体参数时的 `parameter_ids` 外均非空。这里登记本轮必需要求。 |

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

旧工程缺少新格式时从实际记录补充可恢复内容。无法恢复的运行或检查明确未完成，不能为通过新工具补写从未发生的检查。独立交付时复制实际使用的检查脚本及 `check_records.py`，清单检查还需同时保存原文副本与 `element-catalog.json`；以 `--checklist` 指向随工程保存的清单。

## 清单更新与固定编号

`element-catalog.json` 保存事项的固定 ID、原文、类别和适用规则；`01.01` 等 ID 现在是永久标识，不由出现位置重新生成。新增事项使用未占用编号，已有事项移动位置不改 ID；拆分或废弃时保留明确迁移关系，不能把旧 ID 分配给不同含义。清单版本更新后同步副本、目录、模板及引用，人工核对事项变化和适用规则。

目录记录所对应原文文件的 SHA256。原文变化而目录未更新时检查失败；仅更新原文摘要并不足以证明事项语义已正确迁移。原文件可访问时继续对照原文件，保留全部通用定义与按需机制的原始含义。
