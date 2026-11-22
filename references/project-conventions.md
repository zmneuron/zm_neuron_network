# 长期约定与规则分工

本页只保留跨任务约定，不再逐条复制主流程和全部历史补充要求。总体推进由 [SKILL.md](../SKILL.md) 说明，各专项规范负责其字段、方法和检查。

## 持续适用的约定

- 保留技能目录、标识和显示名 `zm_neuron_network`，通过 `$zm_neuron_network` 调用。
- 使用清楚、自然的中文科研表达，先说明结果、依据与必要局限。进度只写影响工作的发现和下一步，不以流程术语、文件数量或图件数量代替实际效果。
- 研究者已选择的互动节奏为：**每轮调研后集中讨论 2–3 个相关问题，附建议及影响**；有依赖时先问上游，已有明确答案和授权不重复确认。完整执行方式见[调研与追问](interview.md)。
- 用户明确的任务范围、资料和决定优先。新建不扫描本地历史工程；只改技能时指定样本只读。科研文字与模型代码按[指定技能接入](skill-integrations.md)使用 anti-defensive-writing 和 Ponytail 的随附文本，不要求另外安装上游插件，也不依赖制作阶段的私人对话或试点项目。
- 默认静息态、完整构建要素、来源到实际参数、实际运行、文献/实测比较、逐步结果及正式数据图件仍是相应建模任务的要求；精简的是重复说明和过早填写，不取消必要研究内容。

## 同一规则放在哪里

| 需要决定或维护的内容 | 主要位置 |
|---|---|
| 总体次序、任务范围、共同要求 | [技能入口](../SKILL.md) |
| 科研文字与模型代码采用哪些辅助技能 | [指定技能接入](skill-integrations.md) |
| 分轮调研、提问、回答后的动作及续接 | [interview.md](interview.md) |
| 文献、代码、数据与参数适配 | [construction-methods.md](construction-methods.md) |
| 原清单与模块内容、项目记录对应 | [element-coverage.md](element-coverage.md)、[project-checks.md](project-checks.md) |
| 机制选择、共享状态与局部接入 | [mechanism-extension.md](mechanism-extension.md) |
| 生物学变化、原因依据、场景映射、参考/历史与对照 | [scenario-adaptation.md](scenario-adaptation.md)；最终文字归 [result-delivery.md](result-delivery.md#生物学变化与模型修改依据) |
| 探索/正式构建、组件与网络检查、工作状态和数据用途 | [workflow-checks.md](workflow-checks.md) |
| 文件职责、记录创建时机与版本 | [project-layout.md](project-layout.md)、[versioning.md](versioning.md) |
| 运行偏差、有限优化、实测比较 | [run-compare-optimize.md](run-compare-optimize.md) |
| 每步结果、科学结论、文献图与数据格式 | [result-delivery.md](result-delivery.md)、[literature-figures.md](literature-figures.md)、[output-manifest.md](output-manifest.md) |

维护时先找现有归属，修改相应规则和受影响引用，不在多处追加同一套流程。案例用于说明选择，不把某个模型、参数、预算或历史入口变成所有任务的默认要求。需要新字段或工具时再检查兼容性；仅改工作方式不自动扩充代码或结构化格式。
