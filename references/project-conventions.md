# 长期约定与规则分工

本页只保留跨任务约定，不再逐条复制主流程和全部历史补充要求。总体推进由 [SKILL.md](../SKILL.md) 说明，各专项规范负责其字段、方法和检查。

## 持续适用的约定

- 保留技能目录、标识和显示名 `zm_neuron_network`，通过 `$zm_neuron_network` 调用。
- 使用清楚、自然的中文科研表达，先说明结果、依据与必要局限。进度只写影响工作的发现和下一步，不以流程术语、文件数量或图件数量代替实际效果。正文、表格、图内文字与网页共用[统一表达规范](external-skills/clear-writing.md)，与 anti-defensive-writing 分工，不另建写作流程。
- 按本次委托确定入口。新建或实质重设研究在方向明确后推荐深度，已有档位直接沿用。开放式优化先研究当前结果，再讨论新取舍。按[调研与追问](interview.md)核对用户侧取舍、设计依据与预算，既定工作按原计划接续。
- 用户明确的任务范围、资料和决定优先。新建不扫描本地历史工程；只改技能时指定样本只读。按[指定技能接入](skill-integrations.md)将建模接入 ARS 适配科研流程，并采用 anti-defensive-writing 与 Ponytail 的相关方法；每次调用核对上游版本与规则冲突，不要求另装完整插件，也不依赖制作阶段的私人对话或试点项目。
- 默认静息态、完整构建要素、来源到实际参数、实际运行、文献/实测比较、逐步结果及正式数据图件仍是相应建模任务的要求；精简的是重复说明和过早填写，不取消必要研究内容。

## 同一规则放在哪里

| 需要决定或维护的内容 | 主要位置 |
|---|---|
| 总体次序、任务范围、共同要求 | [技能入口](../SKILL.md) |
| 科研总流程、计算建模、写作与代码技能如何衔接 | [指定技能接入](skill-integrations.md)、[ARS 流程适配](external-skills/academic-research.md) |
| 每次调用的上游更新、采用版本与跨技能冲突 | [更新与冲突检查](skill-update-review.md) |
| 原要求、版本与最终完成复核 | [project-checks.md](project-checks.md) |
| 多 agent 动态分工与独立复核 | [delegation.md](delegation.md) |
| 分轮调研、提问、回答后的动作及续接 | [interview.md](interview.md) |
| 文献、代码、数据与参数适配 | [construction-methods.md](construction-methods.md) |
| 原清单与模块内容、项目记录对应 | [element-coverage.md](element-coverage.md)、[project-checks.md](project-checks.md) |
| 机制选择、共享状态与局部接入 | [mechanism-extension.md](mechanism-extension.md) |
| 生物学变化、原因依据、场景映射、参考/历史与对照 | [scenario-adaptation.md](scenario-adaptation.md)；最终文字归 [result-delivery.md](result-delivery.md#生物学变化与模型修改依据) |
| 探索/正式构建、组件与网络检查、工作状态和数据用途 | [workflow-checks.md](workflow-checks.md) |
| 文件职责、记录创建时机与版本 | [project-layout.md](project-layout.md)、[versioning.md](versioning.md) |
| 运行偏差、迭代校准与实测比较 | [run-compare-optimize.md](run-compare-optimize.md) |
| 每步结果、科学结论、文献图与数据格式 | [result-delivery.md](result-delivery.md)、[literature-figures.md](literature-figures.md)、[output-manifest.md](output-manifest.md) |

维护时先找现有归属，修改相应规则和受影响引用，不在多处追加同一套流程。案例用于说明选择，不把某个模型、参数、预算或历史入口变成所有任务的默认要求。需要新字段或工具时再检查兼容性；仅改工作方式不自动扩充代码或结构化格式。
