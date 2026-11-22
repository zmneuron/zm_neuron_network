# 科研总流程与建模技能的分工

按用户要求，将 `zm_neuron_network` 作为 **Academic Research Skills（ARS）科研流程中的计算建模与实验环节**。ARS 的领域适配流程承接研究设计、写作、审阅与修改；本技能深入调研神经科学构建方法、持续追问科学取舍，并实际构建、运行和比较模型。科研文字采用 **anti-defensive-writing**，模型代码实现可采用 **Ponytail**。每次调用先完成[版本与冲突检查](skill-update-review.md)，再按任务读取下表文本。

| 工作 | 读取的技能文本 | 本模型工作中如何使用 |
|---|---|---|
| 从研究问题到模型实验、论文表达和审阅反馈的衔接 | [ARS 科研流程适配](external-skills/academic-research.md) | 采用 deep-research、academic-paper、academic-paper-reviewer 和 academic-pipeline 的相关方法；在研究设计与写作之间接入实际建模，并将补充实验返回本技能。 |
| 构建方法说明、结果解释、论文段落和科学结论的撰写或修改 | [anti-defensive-writing](external-skills/anti-defensive-writing.md) | 先明确实际成立的结论及依据，再组织问题、方法、结果与意义；减少流水账和无依据的自我削弱。 |
| 模型构建代码、运行入口、分析代码的实现、修改或整理 | [Ponytail](external-skills/ponytail.md) | 先读现有调用关系和实际需要，优先复用适用实现与已有依赖，用容易理解的最小完整改动完成任务。 |

这些材料是给 AI 使用的工作指令，不是仿真后端。ARS 不能替代领域构建研究，Ponytail 负责软件实现取舍；神经元方程、网络结构、参数与仿真器选择仍依据科学问题、原始文献及适用性比较。上游提出问题后，仍按[调研与追问](interview.md)详细比较方法，每轮围绕实质发现讨论 2–3 个相关问题。

## 科研文字怎样衔接

1. 先取得当前构建方法、来源与参数对应、实际运行记录及结果表图；只委托文字工作时使用用户给定材料，不为润色额外运行模型。
2. 应用 anti-defensive-writing 时，将核心问题、实际贡献和支持它的结果放在前面。方法说明保留复现所需细节，结果解释明确效应、条件和科学含义；日常进度说明保持简短，不套用整篇论文结构。
3. 精简的是重复背景、与当前主张无关的叙述和夸大的负面措辞。保留影响判断的偏差、阴性结果、失败运行、必要局限及替代解释；不能为突出优势删除原始结果、隐去必要对照或改写数值。
4. 论文主线可以围绕真实发现重新组织，但不得事后挑选主要指标、将探索结果改称预设检验，或把拟合数据改称独立验证。需要新比较时按原有研究范围与记录规则处理。
5. 修改后核对每个结论与来源、数据和图表是否一致。写作技能不把“代码能运行”提升为“模型机制已证实”，也不把尚未运行的方案写成结果。

## 模型代码怎样衔接

1. 按已明确的科学目标和完整构建要素确定必需实现，再读取 Ponytail。先检查本项目的模块、配置、已有后端能力与相关调用位置。
2. 在已比较的实现中优先复用能满足方程、单位、状态、随机过程和输出要求的代码；新增依赖或复用公开模型时，核对版本、接口与许可。复用理由及必要适配进入现有方法和参数记录。
3. 用最小完整实现完成目标，不为未来可能性增加空模块、通用框架或重复配置。代码仍按细胞、空间、连接、突触、输入、求解、记录和分析等实际职责组织；少写代码不等于将全部实现合成一个文件。
4. 用户要求、目标依赖机制、单位与数值检查、基础发放率、真实运行、比较和数据图件保存均属于完整任务。不能为减少代码省略它们，也不能未经科学论证约化模型或替换神经元动力学。
5. 修改后运行与改动有关的组件或网络比较，核对实际生成对象和输出。新增非平凡逻辑用能发现实际错误的测试检查；只改文字不新增匹配措辞的测试。整理代码时保留适用检查、错误处理和防止数据损失的逻辑。

## 读取方式与作用范围

- 本仓库随附 anti-defensive-writing、Ponytail 的原版核心文本，以及 ARS 的明确署名适配文本。未单独安装它们的使用者，也可读取这些材料完成这里定义的流程，不需要作者电脑上的路径。
- 默认采用随附、已核对版本。若任务明确采用环境中的其他版本，先核对来源、版本与差异；同名不代表同一项目，尤其不能把其他作者的 `deep-research` 当成 ARS。记录本次实际读取的路径与版本，不只记录仓库最新版本。
- 原技能的用户意图、科学完整性和结果真实性要求持续适用。上游的全会话常驻、强力简化或论证重排等默认行为，只在当前任务授权范围内解释，不因此扩大范围或取消既定工作。
- 本接入只携带原版或适配的流程文本与许可，不安装上游插件、会话钩子、外部模型服务或自动发布功能，不声称具备其全部命令。首次采用时简短说明本轮分工；版本与差异按[检查规则](skill-update-review.md)保存，每个阶段不重复创建记录。
- 每次调用查询上游是否更新；检查相关变化和跨技能影响后再决定是否采用。运行中的同一项科学比较保持技能、模型与指标版本一致；技能更新本身不改变已确定的科学目标。

## 来源与随附许可

本次于 **2026-11-23** 读取下列固定版本。前两项核心文本按原样保存，ARS 为另行标注修改的适配文本；本页定义各自在神经元网络研究中的作用范围。

| 项目 | 核对的版本与原文 | 随附许可 |
|---|---|---|
| Adkid-Zephyr / anti-defensive-writing-Skill | [`e65bd9d8bf8e` 的中文 SKILL.md](https://github.com/Adkid-Zephyr/anti-defensive-writing-Skill/blob/e65bd9d8bf8ed8b9af809e5aff8237d76370876d/skills/anti-defensive-writing/SKILL.md) | [MIT，Copyright 2026 Adkid-Zephyr](external-skills/anti-defensive-writing.LICENSE) |
| DietrichGebert / ponytail | [`ebd8654c2c62` 的 SKILL.md](https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/skills/ponytail/SKILL.md) | [MIT，Copyright 2026 DietrichGebert](external-skills/ponytail.LICENSE) |
| Imbad0202 / academic-research-skills | [`ae243ac2ad6e` 的科研流程](https://github.com/Imbad0202/academic-research-skills/tree/ae243ac2ad6ef2deeb46e35b636e6a2d137e50ec)；采用范围见[适配说明](external-skills/academic-research.md) | [CC BY-NC 4.0，Copyright 2026 Cheng-I Wu](external-skills/academic-research.LICENSE)，包含署名及非商业使用条件；未改标为 MIT |

精确来源、版本及文件一致性信息见 [sources.json](external-skills/sources.json)。这些文本的检查不代表已经验证某个生物学模型，也不保证所有宿主都提供上游插件的交互命令。
