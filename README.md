# zm_neuron_network

围绕科学问题开展神经元网络建模的 Codex Skill。从现象或粗略想法出发，结合文献与公开代码逐步明确问题，构建、运行、比较和优化模型，并保存方法、数据与结果图件。

## 能做什么

- 研究过程中分轮讨论目标、观测与建模取舍，保存来源和当前研究状态。
- 比较多篇文献的方法，把来源数值、转换过程、本模型参数及实际对象对应起来。
- 按完整构建要素组织模型，按需补充或简化神经元、突触及局部机制。
- 无特殊要求时构建具有基础发放率的静息态网络；完成实际运行、适用文献与真实数据比较及必要优化。
- 按网络组成组织代码，保留每个构建步骤的结果、原始数据、分析代码和科研图件。

完整工作方式见 [SKILL.md](SKILL.md)。本仓库不包含作者已构建的科研模型、实验数据、账号凭据或模拟器安装程序。

## 安装和更新

将本仓库克隆为 Codex 的一个技能目录。Windows PowerShell 示例：

```powershell
git clone https://github.com/zmneuron/zm_neuron_network.git "$env:USERPROFILE\.agents\skills\zm_neuron_network"
```

也可以下载仓库 ZIP，将其中整个技能目录放到 `~/.agents/skills/zm_neuron_network/`，或某个项目的 `.agents/skills/zm_neuron_network/`。该目录下应直接包含 `SKILL.md`，不要多套一层目录。技能未出现时重启 Codex。安装位置参照 [Codex 官方说明](https://learn.chatgpt.com/docs/build-skills)。私有仓库需要仓库访问权限。

通过 Git 安装后，可获取更新：

```powershell
git -C "$env:USERPROFILE\.agents\skills\zm_neuron_network" pull --ff-only
```

在 Codex 中调用，例如：

```text
$zm_neuron_network
我想研究某脑区静息活动中的一个现象。请先调研相关文献，与我讨论科学问题和模型取舍，再按确定范围构建并运行模型，保存方法、参数对应、逐步结果和数据图件。
```

## 运行环境

需要可使用本地技能的 Codex，以及实际任务所需的资料访问和计算环境。配套检查脚本使用 Python 标准库，建议 Python 3.11 或更高版本；真正的仿真、分析和绘图依赖按选定模型配置。技能不保证不同模型、数据或机器产生完全相同的研究结果。

## 目录与自检

| 目录 | 内容 |
|---|---|
| `references/` | 方法、要素、参数、机制、输出和比较规范 |
| `assets/` | 构建方法、机制说明、参数与结果模板 |
| `scripts/` | 项目与输出的检查工具 |
| `evals/` | 维护用合成软件测试、情境任务与检查记录 |
| `agents/` | 技能显示和调用信息 |

在仓库根目录可执行：

```text
python -B -X utf8 evals/test_check_model.py
python -B -X utf8 evals/test_check_elements.py
python -B -X utf8 evals/test_check_outputs.py
python -B -X utf8 evals/test_workflow.py
```

软件自检会在临时目录生成合成数据，不能代替真实科研模型的生物学验证。发布版省略依赖作者本地工程的少数评测案例，原编号保留，列表见 [publication.json](publication.json)。检查记录中的机器路径使用明确占位符；核心技能、模板与检查实现保留。

更新由维护者的本地发布工具在文件稳定且检查通过后推送。其他使用者通过 Git 更新或重新下载即可取得新版本。
