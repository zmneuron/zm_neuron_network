# 十细胞网络的两轮校准

本例实际积分 8 个兴奋性和 2 个抑制性 LIF 点神经元，使用同一组连接和初始状态。校准参照和留出参照均为合成目标，适用于检验软件流程。

在技能目录运行以下命令。将最后一个参数替换为尚不存在的目录。

```powershell
python -B evals/optimization_round_case.py --workspace E:/experiments/lif_two_rounds
```

| 在演示目录中打开 | 可核对的内容 |
|---|---|
| `docs/round_1_stage.md`、`analysis/round_1/delivery_check.json` | 首轮失配、此前已达标的静默比例，以及下一轮拟改的参数。阶段报告在第二轮开始前由标准入口导出。 |
| `results/round_1/`、`results/round_2/` | 两轮各自的配置、细胞、连接、脉冲、膜电位与积分时实际收到的突触输入。 |
| `analysis/output/rounds.csv`、`analysis/round_2/frozen.json` | 从全部细胞的脉冲复算的两轮结果，以及查看留出电位前已确定的参数。 |
| `docs/results.md`、`analysis/output/delivery_check.json` | 最终报告、图件，以及正常完整建模入口逐项复核后的判断。 |

首轮在 (100, 500] ms 内记录到 150 个脉冲，平均 37.5 Hz。细胞 0 的放电间隔中位数为 27.6 ms。按 50 Hz 对应的 20 ms 间隔和恒驱动膜方程，将有效背景驱动从 20 调整至 23.7 mV。第二轮在同一时窗记录到 199 个脉冲，平均 49.75 Hz，两轮静默比例均为 0。锁定参数后，第二轮细胞 0 在 10 ms 处的电位为 −55.657 mV，落入留出的 −57 至 −54 mV 合成区间。

可分别复核最终模型和待发送的原文。

```powershell
python -B scripts/check_project.py --project E:/experiments/lif_two_rounds --phase delivery
python -B scripts/review_project.py --project E:/experiments/lif_two_rounds --response-file docs/response.md
```

运行 `python -B evals/test_optimization_round_case.py` 可查看配置中启用了突触但实际突触输入为零、留出数据参与选参、必需项待核实等反例的 `final_model_ready`。测试支持 `--workspace <另一个新目录>`，会在其中保留正常样例、反例运行和 `reviews/` 下的原始判定。
