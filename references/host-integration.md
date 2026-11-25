# 宿主接入与能力边界

在更换宿主、由多代理平台编排任务，或首次核对「这个技能到底需要什么」时阅读。本页说明用途边界、触发条件、参数配置、执行流程与依赖关系；它**不改变** [SKILL.md](../SKILL.md) 的科研标准、六步主线、六项交付和完成判断，也不新建第二套记录体系。

## 一、用途与边界

| 这份仓库是 | 这份仓库不是 |
|---|---|
| 用自然语言规则、结构化契约与只读检查脚本约束建模过程的研究 Skill | 已经构建好的神经元网络模型 |
| 供支持本地技能的宿主加载的方法与交付规范 | 实验数据、账号凭据或模拟器安装程序 |
| 可由多代理平台导入并分配给多个角色共享 | 多代理平台的团队、岗位或任务配置文件 |
| 一组零第三方依赖的 Python 检查脚本 | 仿真器、优化器或实验特征提取器 |

导入技能后仍需让代理找到**实际模型工程**；把工作目录指向本仓库只适用于「开发和修改技能」的任务。

## 二、触发条件

| 触发方式 | 技能做什么 |
|---|---|
| 宿主中调用 `$zm_neuron_network`，或按 [agents/openai.yaml](../agents/openai.yaml) 的默认提示发起 | 恢复原目标与实际状态，首轮询问三档；目标未定时先按[需求探索与方向选择](research-direction.md) 调研方向 |
| 「继续优化模型」「继续调参数」等开放式改进 | 先恢复当前工程与实际结果、补查资料，再进入总计 5–7 问的新一轮 |
| 明确点名复用、续接、检查或重分析某工程 | 读取该工程，只重查受影响部分 |
| 只调研、检查、维护技能或泛泛讨论 | 按实际范围交付，不自动新建科研工程、不自动打开查看页、不启动仿真 |

`agents/openai.yaml` 只提供显示名、简短说明与默认提示；它不会创建负责人、实施者、复核者岗位，也不会设置工作目录或预算。

## 三、参数配置

技能本身没有安装参数。可配置的是「档位与契约」和「检查脚本命令行参数」。

| 配置项 | 位置 | 说明 |
|---|---|---|
| 三档建模与题数 | [interview.md](interview.md) | 探索 2–3 问、规范 5–6 问、精确不设总题数；另加 2–3 个科学讨论问题；继续优化总计 5–7 问 |
| 当前任务与要求 | `docs/task_plan.json`，模板 [task_plan.json](../assets/task_plan.json) | 当前入口；原要求有不可覆盖的初始快照 |
| 模块与参数映射 | `docs/model_spec.md`、`docs/research/parameter_mapping.csv`，模板 [module_contracts.json](../assets/module_contracts.json)、[parameter_mapping.csv](../assets/parameter_mapping.csv) | 模块七项定义与来源到采用值的对应 |
| 分析与五轴完成判断 | `analysis.json`、模板 [analysis_manifest.json](../assets/analysis_manifest.json) | 运行、校准、独立评价、科学回答、交付分别判断 |
| 检查脚本 | `scripts/` 下的 `.py` | 以只读为主；`--output` 必须指向项目内尚不存在的新文件 |

常用命令行形式，`<skill_dir>` 为技能目录、`<project>` 为实际模型工程：

```text
python <skill_dir>/scripts/check_project.py --project <project> --phase plan|implemented|delivery
python <skill_dir>/scripts/review_project.py --project <project> --capture --skill <采用的技能目录>
python <skill_dir>/scripts/review_project.py --project <project> --checkpoint start|resume|transition|delivery
python <skill_dir>/scripts/review_project.py --project <project> --checkpoint delivery --response-output <项目内新文件>
python <skill_dir>/scripts/review_project.py --project <project> --stage-report-output <项目内新文件.md>
python <skill_dir>/scripts/show_progress.py --project <project>
python <skill_dir>/scripts/build_viewer.py --project <project> --output <新HTML>
python <skill_dir>/scripts/preview_viewer.py --project <project> --checkpoint start|resume|transition|delivery
python <skill_dir>/scripts/check_skill_sources.py
```

参数与退出码的权威说明见 [project-checks.md](project-checks.md) 和 [automatic-checks.md](automatic-checks.md)；命令示例不构成新的验收标准。

## 四、执行流程

**六步主线：**确定问题 → 调研并讨论取舍 → 形成可执行方法 → 检查输入与小规模运行 → 正式运行、比较与逐模块优化 → 回答问题并交付。调研贯穿全程。完整建模按用户原始要求在同一最终采用版本上复核。未达项按原因返回构建、计算或比较，重跑受影响条件并复查旧项。分批计算与任务暂停按[迭代规则](run-compare-optimize.md#根据偏差执行迭代优化)执行。

**五轴独立完成判断：**运行完成、校准满足、独立评价支持、科学问题回答、交付完整分别判断；程序通过不等于研究完成。

**六项交付：**摘要式首段 → 模型与方法图 → 主要公式 → 逐题图文结果 → 真实生物数据对比、验证与迭代说明 → 一句话局限。

阶段表、检查点与发送稿复核见 [execution-management.md](execution-management.md) 与 [result-delivery.md](result-delivery.md)。

## 五、依赖关系

| 层 | 需要什么 | 谁提供 |
|---|---|---|
| 宿主 / 编排平台 | 支持加载本地技能；任务读取、命令执行、文件读写、文献检索、绘图等能力 | Codex、Claude Code、Paperclip 等；能力逐项核实 |
| Skill 自身 | Python 3.11 及以上**标准库**，零第三方依赖；`SKILL.md`、`references/`、`assets/`、`scripts/`、`evals/` 完整 | 本仓库 |
| 实际科研工程 | 模型源码、配置、实验数据、结果目录，以及按选定模型安装的数值与仿真依赖 | 使用者自己的工程 |
| 外部平台与作业管理 | 多代理编排、长时仿真作业管理、预算与用量记录 | 平台或调度器；短任务不需要 |

导入技能**不会**安装模拟器、赋予浏览器或文献数据库权限，也不自动获得任务状态接口。外部平台自身的版本要求（例如编排平台的 Node 版本、AI CLI 登录）属于平台依赖，不是本技能的依赖，两者不要混写。

## 六、宿主能力差异与降级

| 能力 | 不具备时如何处理 |
|---|---|
| 侧栏打开工具（如 `open_in_codex`） | 用 `build_viewer.py` 生成实际 HTML 并在任务中引用其路径；如实说明未执行侧栏打开动作，不编造工具调用或界面结果 |
| 本地网页预览服务 | 单独管理预览服务并核对浏览器可访问地址；页面生成成功不等于模型验证通过 |
| 平台任务状态与复核交接接口 | 按当前适配器提供的协议报告状态；不机械套用旧版接口，也不把「运行成功」当成任务完成 |
| 长时间仿真保活 | 交给外部作业管理并登记作业身份；一次 AI 运行结束可能停止其启动的子进程，续接先查已有作业再决定是否重试 |
| 文献检索、绘图、外部数据访问 | 列入接入能力检查；技能提出工作要求，不会自动安装这些工具 |

完整查看页规则见 [execution-management.md](execution-management.md#在-codex-内查看)。

## 七、版本固定与记录位置

- 在科研阶段内固定技能版本，更新前查看差异，在阶段边界统一更新所有角色；不在同一轮参数比较中改变验收规范。
- 手工安装目录与平台管理的运行时注入目录不是同一件事；选定一个作为本项目的权威来源，首个接入任务应报告实际加载的路径与版本。
- 平台任务保存派单、讨论、状态和证据入口；科学目标、方法与参数依据、运行身份、预算和结果仍按 [project-layout.md](project-layout.md) 保留在工程记录中，不另建第二套科研标准。

多代理分工与独立复核按 [delegation.md](delegation.md) 执行；平台完成一次审核交接不代表结论已获科学验证。
