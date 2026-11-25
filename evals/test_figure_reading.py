"""Exercise reading a project's actual SVG and raster renditions without a renderer or OCR."""
import base64
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_records import fingerprint
from figure_reading import check_figure_reading


def svg(*labels, extra=""):
    nodes = "".join(f'<text x="2" y="{15 + i * 13}">{label}</text>' for i, label in enumerate(labels))
    return '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">' + extra + nodes + '</svg>'


class FigureReadingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.design = self.root / "figure_plan.md"
        self.model = self.root / "model.svg"
        self.result = self.root / "comparison.svg"
        self.flow = ["鼻部刺激", "延髓中继", "心率读数"]
        self.contribution = "迷走支路短时抑制"
        self.model_labels = [*self.flow, self.contribution]
        self.model.write_text(svg(*self.model_labels), encoding="utf-8")
        self.result_labels = ["刺激条件", "心率（bpm）", "恢复时间（s）"]
        self.result.write_text(svg(*self.result_labels), encoding="utf-8")
        self.paper = dict(paper="Mooney 等（2019）", panel="Fig. 5A", comparison="刺激前后的心率",
                          reason="同一刺激条件可对照心率恢复过程")
        self.plan()
        self.figures = {
            "model": dict(id="model", files=["model.svg"], depiction="schematic",
                          model_overview=dict(flow=self.flow, modules=["延髓中继"], contribution=self.contribution)),
            "comparison": dict(id="comparison", files=["comparison.svg"], depiction="data_result", caption="刺激条件与心率变化",
                               design_ref="figure_plan.md#参考设计", literature_figure=self.paper),
        }
        self.embedded = {"model": {self.model}, "comparison": {self.result}}
        self.delivery = dict(parts=[
            dict(kind="methods", figure_ids=["model"], report_excerpt="鼻部刺激经延髓中继，记录迷走支路短时抑制后的心率。"),
            dict(kind="questions", figure_ids=["comparison"], report_excerpt="对照各刺激条件的心率。"),
        ])

    def plan(self):
        self.design.write_text("# 参考设计\n\n| " + " | ".join(self.paper.values()) + " |\n", encoding="utf-8")

    def check(self):
        return check_figure_reading(self.root, self.delivery, self.figures, self.embedded, "model")

    def review(self, path, labels):
        return dict(file=path.name, sha256=fingerprint(path), labels=labels,
                    observation=f"打开导出图后可辨认{labels[0]}，坐标下方的小字和面板边框没有重叠。")

    def test_svg_chinese_labels_allow_units_math_and_acronyms(self):
        self.result.write_text(svg(*self.result_labels, "mV", "Hz", "CA1", "GABA", "A/B", "ΔF/F", "spikes/s", "exp(−t/τ)"), encoding="utf-8")
        result = self.check()
        self.assertEqual(result, dict(model_figure_id="model", checked_figures=["comparison", "model"], visual_review_files=[]))

    def test_chinese_caption_or_another_label_cannot_cover_english_title_axis_or_legend(self):
        for label in ("Stimulus condition", "TIME", "Firing rate (Hz)", "Baseline", "Group1", "FiringRate"):
            with self.subTest(label=label):
                self.result.write_text(svg("中文图名", label), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, label.split()[0]):
                    self.check()
        self.result.write_text(svg(extra='<text><tspan x="5">心率</tspan><tspan x="5" dy="14">Baseline</tspan></text>'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Baseline"):
            self.check()

    def test_only_displayed_svg_text_counts_including_local_symbols(self):
        self.result.write_text(svg(extra='<style>.hide {display:none}</style><title>心率</title>'
                                  '<g class="hide"><text>中文图名</text></g><defs><text id="a">刺激条件</text></defs>'
                                  '<text fill="none">另一条中文</text><text>Hz</text>'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "图内中文"):
            self.check()
        self.result.write_text(svg(extra='<defs><symbol id="bar"><text>刺激心率</text></symbol></defs>'
                                  '<use href="#bar"/><g opacity="0"><text>Baseline</text></g>'), encoding="utf-8")
        self.assertEqual(self.check()["visual_review_files"], [])

    def test_every_displayed_rendition_requires_its_own_check(self):
        path = self.root / "comparison.png"
        # Monochrome synthetic curve actually labelled 心率 (bpm) and 时间 (s).
        path.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAIAAAAA0AQAAAABqHg0FAAABUUlEQVR42r2SvU4CURCFz4UlogX4"
            "E0NhIsTaxk4LxQfAV1DfBB7EwkfByhIxJiYmuhgTSQwKhGKXsPd+FrLLLoWxcrr5cmbmzNxrUDZy"
            "WgZOd+qliYvUvICAecjRcT7MYpCbnvezTR6/Vm23e38cKzyZhmYy17HAU3CmTS3c5Bsrl+MDSRu"
            "JYu2h5MssFFfjHbc9KUVbMRnVhw5/4UMATT/lFACfJIxd2jdHawmY2tJB7FtSfgMgG8W5OzGAL"
            "NU5eMUZkKU/B1VwBlmmP3kI4Mo5qXAqSepIkhnJQgcgqs+tWxgDxNNlwTUhrCY3lcy6xpUwcQp"
            "MRuXEriwQlX9bX/oH4GEyed7w9x4ExQygVhhFoaTkEdr7lWAGSVN65Y+a56V6HErhXrrkaVD5spA"
            "aa9pqpcd6kqmlS3YHleFz/KUA9/IZvB+lAOHwNuNDkqKoqG/A/mHtvVJEPgAAAABJRU5ErkJggg=="))
        self.figures["comparison"]["files"].append(path.name)
        self.embedded["comparison"].add(path)
        with self.assertRaisesRegex(ValueError, "视觉核查记录"):
            self.check()
        review = self.review(path, ["心率 (bpm)", "时间 (s)"])
        self.figures["comparison"]["visual_review"] = [review]
        self.assertEqual(self.check()["visual_review_files"], [path.name])
        review["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "当前成图"):
            self.check()
        review["sha256"] = fingerprint(path)
        review["observation"] = "已检查"
        with self.assertRaisesRegex(ValueError, "具体观察|实际看到"):
            self.check()
        self.figures["comparison"]["visual_review"] = [self.review(path, [self.figures["comparison"]["caption"]])]
        with self.assertRaisesRegex(ValueError, "仅复述图注"):
            self.check()

    def test_outlined_or_raster_labels_need_a_review_but_the_record_cannot_overwrite_svg_text(self):
        outline = '<g id="text_2"><path d="M0 0 L2 0 L2 3 Z"/></g>'
        self.result.write_text(svg(*self.result_labels, extra=outline), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "视觉核查记录"):
            self.check()
        self.figures["comparison"]["visual_review"] = [self.review(self.result, self.result_labels)]
        self.assertEqual(self.check()["visual_review_files"], [self.result.name])
        self.result.write_text(svg("横坐标", "Control", extra=outline), encoding="utf-8")
        self.figures["comparison"]["visual_review"] = [self.review(self.result, self.result_labels)]
        with self.assertRaisesRegex(ValueError, "Control"):
            self.check()
        self.result.write_text(svg(extra=outline), encoding="utf-8")
        self.figures["comparison"]["visual_review"] = [self.review(self.result, ["Control", "Hz"])]
        with self.assertRaisesRegex(ValueError, "图内中文"):
            self.check()

    def test_method_contribution_must_appear_in_figure_and_correspond_to_project_method(self):
        self.model.write_text(svg(*self.flow), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "未出现在图内"):
            self.check()
        self.model.write_text(svg(*self.model_labels), encoding="utf-8")
        self.delivery["parts"][0]["report_excerpt"] = "用相机采集斑马鱼游动速度。"
        with self.assertRaisesRegex(ValueError, "研究方法"):
            self.check()

    def test_generic_model_figure_does_not_substitute_for_study_and_replication_can_be_specific(self):
        self.figures["model"]["model_overview"] = dict(flow=["输入", "输出"], modules=["模块一"], contribution="创新点")
        self.model.write_text(svg("输入", "输出", "模块一", "创新点"), encoding="utf-8")
        self.delivery["parts"][0]["report_excerpt"] = "输入、模块一、输出、创新点。"
        with self.assertRaisesRegex(ValueError, "通用流程"):
            self.check()
        replica = "复现延髓至疑核的传入投射"
        self.model.write_text(svg(*self.flow, replica), encoding="utf-8")
        self.figures["model"]["model_overview"] = dict(flow=self.flow, modules=["延髓中继"], contribution=replica)
        self.delivery["parts"][0]["report_excerpt"] = "按原论文设置延髓中继并复现延髓至疑核的传入投射。"
        self.assertEqual(self.check()["model_figure_id"], "model")

    def test_result_reference_must_identify_paper_figure_comparison_and_reason_in_one_reading_record(self):
        self.paper["panel"] = "某个面板"
        self.plan()
        with self.assertRaisesRegex(ValueError, "原论文图号"):
            self.check()
        self.paper["panel"] = "Fig. 5A"
        self.paper["paper"] = "相关论文"
        self.plan()
        with self.assertRaisesRegex(ValueError, "作者年份"):
            self.check()
        self.paper["paper"] = "Mooney 等（2019）"
        self.design.write_text("# 参考设计\n\n| Mooney 等（2019） | Fig. 5A |\n| 另一篇论文 | 刺激前后的心率 | 同一刺激条件可对照心率恢复过程 |\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "同一条阅读记录"):
            self.check()
        self.plan()
        self.figures["comparison"]["design_ref"] = "figure_plan.md#缺失段落"
        with self.assertRaisesRegex(ValueError, "指定的阅读记录"):
            self.check()

    def test_result_reference_must_relatively_match_current_question(self):
        self.paper["comparison"] = "降雨季节的土壤湿度"
        self.plan()
        with self.assertRaisesRegex(ValueError, "研究的图文"):
            self.check()

    def test_existing_figure_plan_row_can_supply_the_result_reference_without_copying_it(self):
        self.figures["comparison"].pop("literature_figure")
        self.assertEqual(self.check()["checked_figures"], ["comparison", "model"])
        self.design.write_text("# 参考设计\n\n| Mooney 等（2019），Fig. 5A | 刺激前后的心率 | 同一刺激条件可对照心率恢复过程 |",
                               encoding="utf-8")
        self.assertEqual(self.check()["checked_figures"], ["comparison", "model"])
        with self.design.open("a", encoding="utf-8") as stream:
            stream.write("\n| Panneton 等（2012），图2 | 各条件的平均动脉压 | 另一问题比较血压变化 |")
        with self.assertRaisesRegex(ValueError, "一条结果图参考记录"):
            self.check()


if __name__ == "__main__":
    unittest.main()
