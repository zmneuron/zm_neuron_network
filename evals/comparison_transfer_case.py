"""Make a small synthetic slice-recording exercise for independent skill evaluation.

Run with --workspace NEW_DIRECTORY. Give the executor only that directory and
the task in study.md. Keep this generator and reviewer expectations separate.
"""

import argparse
import csv
from pathlib import Path
import random


STUDY = """# 切片诱发电位的连续预测

本材料由模拟生成，用于评价分析方法。工作组想知道，在相同刺激和记录成本下，方法 B 能否比 A 更准确地实时预测新动物切片的下一个时点。请从现有记录回答，给出实际比较和支持范围，并为下一轮构建一个可执行的最小方案。本次授权仅限这个小型方法比较。

origin.csv 保存导出的每份记录及其来源动物。开发与评价按 role 标出。
delivered_A.csv、delivered_B.csv 分别是在记录入口实际送达的刺激，单位为 pA。
trace.csv 的 field_mV 是两种方法共用的另一条已采集参考观测，按记录和 sweep 初始化，每个 tick 间隔 5 ms。
outputs.csv 中的数值预测与其行上 field_mV 属于同一时刻。在线系统每次仅可使用此时刻之前的观测，表内 online_mV 为实际在线输出，archive_mV 为归档分析输出。请用相同的目标时间窗和原始来源比较。
cost.csv 为实际标定和选择所用的带标签 sweep 数。工程参考指标是预测误差绝对值不超过 0.18 mV 的比例。
"""


def write_csv(root, name, fields, rows):
    with (root / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        writer.writerows(rows)


def generate(root):
    root.mkdir(parents=True, exist_ok=False)
    (root / "study.md").write_text(STUDY, encoding="utf-8")
    animals = [1, 2, 3, 4, 2, 5, 6, 7]
    origins, traces, outputs, stimulus_a, stimulus_b = [], [], [], [], []
    for record, animal in enumerate(animals, 1):
        export = f"record-{record:02d}"
        role = "development" if record <= 4 else "evaluation"
        origins.append((export, role, f"animal-{animal:02d}"))
        for sweep in range(1, 5):
            rng = random.Random(2020 + 100 * record + sweep)
            ticks = (3, 6)
            for pulse, tick in enumerate(ticks, 1):
                amplitude = 20 + rng.randrange(4)
                stimulus_a.append((export, sweep, pulse, tick, amplitude))
                changed = record == 6 and sweep == 2 and pulse == 1
                stimulus_b.append((export, sweep, pulse, tick, amplitude + 4 * changed))
            previous, older = 0.0, 0.0
            for tick in range(10):
                target = round(0.55 * previous + (0.8 + 0.04 * animal) * (tick in ticks)
                               + rng.uniform(-0.16, 0.16), 6)
                traces.append((export, sweep, tick, target))
                for method, prediction in (("A", previous), ("B", (previous + older) / 2)):
                    archived = target if method == "B" and tick in (0, 1) else prediction
                    outputs.append((export, sweep, tick, method, round(prediction, 6),
                                    round(archived, 6)))
                older, previous = previous, target
    write_csv(root, "origin.csv", ["record", "role", "animal"], origins)
    event_fields = ["record", "sweep", "pulse", "tick", "amplitude_pA"]
    write_csv(root, "delivered_A.csv", event_fields, stimulus_a)
    write_csv(root, "delivered_B.csv", event_fields, reversed(stimulus_b))
    write_csv(root, "trace.csv", ["record", "sweep", "tick", "field_mV"], traces)
    write_csv(root, "outputs.csv", ["record", "sweep", "tick", "method", "online_mV",
                                    "archive_mV"], outputs)
    write_csv(root, "cost.csv", ["method", "fit_labelled_sweeps", "select_labelled_sweeps"],
              [("A", 12, 0), ("B", 12, 4)])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    generate(parser.parse_args().workspace)
