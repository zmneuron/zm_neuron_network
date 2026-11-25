# zm_neuron_network

面向计算神经科学的 AI 建模技能，用于构建、复现或优化神经元网络模型，并用实验数据检验预测。

在自己的研究工程中使用。先确定要解释的现象和关键对照，再运行模型。报告用全貌图说明模型怎样建成，用各条件的结果图回答科学问题。

![从明确问题、设计比较，到构建模型和解释结果](assets/workflow/overview.png)

**一个例子。** 十个模拟神经元的平均放电率经校准从 37.5 Hz 升至 49.75 Hz。固定参数后，一个细胞的膜电位为 −55.657 mV，落在预留区间内。两项参照均为合成数据。[查看结果与复算方法](evals/optimization-round-example.md)

## 快速开始

在模型工程根目录运行以下命令，将技能安装到当前工程的 Codex 环境。此方式需要 Git 和带 npm 的 Node.js 22.20 或更高版本。

```sh
npx skills add zmneuron/zm_neuron_network -a codex -y
```

新开 Codex 对话，说出你想解释的现象。已有模型时也可以直接提供工程路径，请助手复核结果。

> $zm_neuron_network 刺激后放电减少。怎样区分传入减弱和局部抑制增强？请先查文献，再和我确定模型需要哪些对照。

<a name="安装和更新"></a>
<details>
<summary>手动安装和更新</summary>

Windows 用户也可用 Git 安装到个人技能目录。以下两条 PowerShell 命令分别用于首次安装和之后更新。

```powershell
git clone https://github.com/zmneuron/zm_neuron_network.git "$env:USERPROFILE\.agents\skills\zm_neuron_network"
git -C "$env:USERPROFILE\.agents\skills\zm_neuron_network" pull --ff-only
```

使用 ZIP 安装时，将包含 `SKILL.md` 的目录放入当前工程的 `.agents/skills/zm_neuron_network/`。若技能未显示，可重启 Codex。[安装位置说明](https://learn.chatgpt.com/docs/build-skills)

</details>

## 目录与自检

[建模方法](SKILL.md) · [报告模板](assets/results_report.md) · [运行环境与参数](references/host-integration.md) · [更新记录](CHANGELOG.md)

在仓库根目录运行 `python -B -X utf8 evals/test_workflow.py` 可检查软件流程，需要 Python 3.11 或更高版本。[最近一次测试结果](evals/latest-workflow-results.json)
