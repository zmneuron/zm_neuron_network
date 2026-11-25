"""Check the labels and scientific context of the figure files actually embedded in a delivery."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from check_records import fingerprint, local, require


HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+[A-Za-zÀ-ÖØ-öø-ÿ0-9]*")
PANEL = re.compile(r"(?:fig(?:ure)?\.?|图)\s*(?:S(?:upp(?:lementary)?)?\.?\s*)?\d+[A-Za-z]?", re.I)
UNITS = set(("ms s min h Hz kHz MHz mV V pA nA mA A nS pS mS Ω mmHg bpm Pa kPa mm cm km nm ng mg "
             "ml mL μL uL mM nM m mol mmol sec kg g um umol rad dB a.u. arb SD SEM CI ppm spk "
             "Na Ca K Cl Mg mOsm mEq preBötC BötC sin cos tan log ln exp lim max sqrt erf Re Im").split())
ENGLISH_LABEL = set(("time firing rate rates frequency input output response results data baseline control "
                     "condition group model test training signal stimulus peak mean error difference voltage "
                     "spikes trials trial pressure activity amplitude panel results axis legend figure").split())
GENERIC = {"图", "组", "输入", "数据", "模型", "模块", "关键模块", "关键步骤", "创新", "创新点", "研究创新",
           "本研究", "模型构建", "数据输入", "输入数据", "数据处理", "模型输出", "模拟", "运行", "分析", "研究结果",
           "结果输出", "研究流程", "过程", "处理", "构建", "输出", "结果", "改进", "改进模型", "优化", "模型创新",
           "方法", "核心模块", "状态", "贡献", "本研究贡献", "模型复现", "复现", "复现原模型", "复现模型",
           "当前", "本次", "条件", "比较", "对照", "实验", "课题", "研究", "采用", "观察", "以及"}
SKIP = {"defs", "symbol", "clipPath", "mask", "metadata", "title", "desc", "style", "script", "marker", "pattern"}
DRAWING = {"path", "circle", "ellipse", "rect", "line", "polyline", "polygon", "image", "use", "foreignObject"}
RASTER = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _str(value, message):
    require(isinstance(value, str) and value.strip(), message)
    return value.strip()


def _fold(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def _specific(text):
    words = re.sub(r"[\s\d\W_]", "", text, flags=re.UNICODE)
    words = re.sub(r"^(?:(?:本研究|本模型|本次)?(?:创新点|关键模块|特色|贡献|复现点))", "", words)
    return bool(words) and words not in GENERIC and not re.fullmatch(r"(?:模块|流程|步骤|阶段)[甲乙丙丁一二三四五六七八九十a-zA-Z]?", words)


def _linked(left, right):
    """Allow short scientific names inside longer Chinese figure labels or method descriptions."""
    left, right = _fold(left), _fold(right)
    if left and left in right and _specific(left):
        return True
    for block in re.findall(r"[\u3400-\u9fff]{2,}|[a-z][a-z\d-]{2,}", left):
        if block in right and _specific(block):
            return True
        if HAN.search(block):
            for width in (3, 2):
                if any("的" not in block[i:i + width] and _specific(block[i:i + width]) and block[i:i + width] in right
                       for i in range(len(block) - width + 1)):
                    return True
    return False


def _scientific_token(word):
    if word in UNITS or len(word) == 1:
        return True
    english_parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+", re.sub(r"\d+$", "", word))
    if english_parts and all(s.casefold() in ENGLISH_LABEL for s in english_parts):
        return False
    return (bool(re.fullmatch(r"[A-Z]{2,8}\d*|[A-Za-z]+\d+[A-Za-z\d]*", word))
            or bool(re.search(r"[a-z][A-Z]", word)))


def _check_labels(labels, name):
    require(labels and any(HAN.search(s) for s in labels), f"{name} 缺少可核对的图内中文标注")
    for label in labels:
        # Each label is checked separately. Scientific symbols and standard abbreviations
        # need no translation, but an English axis cannot borrow a different label's Chinese.
        text = unicodedata.normalize("NFKC", label)
        text = re.sub(r"\bspikes?(?:\s*/\s*s\b|\s*[·⋅]\s*s[-−]?1)|\bpre-BötC\b", "", text, flags=re.I)
        words = WORD.findall(text)
        prose = [word for word in words if not _scientific_token(word)]
        if not prose:
            continue
        chinese = "".join(HAN.findall(label))
        # A named model (e.g. Hodgkin–Huxley) can appear with its Chinese description.
        # An ordinary English axis or condition still needs translating on the same label.
        proper_names = all(word.istitle() and word.casefold() not in ENGLISH_LABEL for word in prose)
        require(proper_names and chinese and chinese not in {"图", "组", "轴", "表", "示意", "图例", "横轴", "纵轴", "标题"},
                f"{name} 有待中文说明的图内标注：{label}")


def _style(declarations):
    return {k.strip(): v.strip().removesuffix("!important").strip()
            for part in declarations.split(";") if ":" in part for k, v in [part.split(":", 1)]}


def _svg(path):
    """Read displayed SVG text nodes, including local use targets; glyphs and pixels need review."""
    try:
        svg = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise ValueError(f"SVG 无法读取：{path.name}") from error
    tag = lambda e: e.tag.rsplit("}", 1)[-1]
    require(tag(svg) == "svg", f"缺少 SVG 根元素：{path.name}")
    ids = {e.get("id"): e for e in svg.iter() if e.get("id")}
    css = []
    for element in svg.iter():
        if tag(element) == "style":
            for selectors, code in re.findall(r"([^{}]+)\{([^{}]+)\}", element.text or ""):
                for selector in selectors.split(","):
                    css.append((selector.strip(), _style(code)))

    def properties(e):
        result = dict(e.attrib)
        for selector, styles in css:
            classes = e.get("class", "").split()
            if (selector in {"*", tag(e)} or selector == "#" + e.get("id", " ")
                    or any(selector in {"." + cls, tag(e) + "." + cls} for cls in classes)):
                result.update(styles)
        result.update(_style(e.get("style", "")))
        return result

    def hidden(props):
        def zero(key):
            try:
                return float(props.get(key, "1").rstrip("%")) == 0
            except ValueError:
                return False
        return (props.get("display") == "none" or props.get("visibility") in {"hidden", "collapse"}
                or zero("opacity") or re.fullmatch(r"0(?:\.0+)?(?:px|pt)?", props.get("font-size", "")) is not None
                or bool(re.search(r"scale\(\s*0(?:\.0+)?(?:\s*[, ]\s*0(?:\.0+)?)?\s*\)", props.get("transform", ""))))

    labels, has_drawing, opaque = [], False, False

    def visit(e, ancestors=(), inherited=None, active_text=None, referenced=False):
        nonlocal has_drawing, opaque
        name = tag(e)
        if name in SKIP and not (referenced and name == "symbol"):
            return
        props = dict(inherited or {})
        own = properties(e)
        props.update(own)
        if hidden(props):
            return
        painted = (props.get("fill", "black") not in {"none", "transparent"} and props.get("fill-opacity") not in {"0", "0.0"}
                   or props.get("stroke", "none") not in {"none", "transparent"} and props.get("stroke-opacity") not in {"0", "0.0"})
        if name in DRAWING:
            has_drawing = True
            if name in {"image", "foreignObject"} or (name == "path" and (
                    own.get("aria-label") or own.get("font-family") or "glyph" in own.get("id", "").lower())):
                opaque = True
        if name == "use":
            target = e.get("href") or e.get("{http://www.w3.org/1999/xlink}href", "")
            ref = target[1:] if target.startswith("#") else ""
            if ref in ids and ref not in ancestors:
                if re.search(r"(?:[\w.-]+-[0-9a-f]{2,6}$|glyph)", ref, re.I):
                    opaque = True
                visit(ids[ref], (*ancestors, ref), props, active_text, True)
            else:
                opaque = True
            return
        if name == "g" and re.search(r"(?:^|[_-])(?:text|glyph)(?:s|[_-]?\d+)?$", e.get("id", ""), re.I):
            if any(tag(c) in {"use", "path"} for c in e.iter()) and not any(tag(c) == "text" for c in e.iter()):
                opaque = True
        starts = name == "text" or (name == "tspan" and active_text is not None and any(k in own for k in ("x", "y", "dy")))
        if starts:
            active_text = []
        if active_text is not None and painted and e.text:
            active_text.append(e.text)
        # Non-inherited CSS presentation and geometry cannot become child properties.
        child_props = {k: v for k, v in props.items() if k in ("visibility", "fill", "fill-opacity", "stroke",
                                                                  "stroke-opacity", "font-size")}
        for child in e:
            visit(child, ancestors, child_props, active_text)
            if active_text is not None and painted and child.tail:
                active_text.append(child.tail)
        if starts:
            label = " ".join("".join(active_text).split())
            if label:
                labels.append(label)

    visit(svg)
    require(labels or has_drawing, f"SVG 没有可见图形或图中文字：{path.name}")
    return labels, opaque or not labels


def _visual_labels(root, figure, path):
    reviews = figure.get("visual_review", [])
    require(isinstance(reviews, list), f"{path.name} 的成图查看记录应按文件填写")
    rows = [r for r in reviews if isinstance(r, dict) and isinstance(r.get("file"), str)
            and (root / r["file"]).resolve() == path]
    require(len(rows) == 1, f"{path.name} 缺少适用于该成图的唯一视觉核查记录")
    row = rows[0]
    require(row.get("sha256") == fingerprint(path), f"{path.name} 的视觉核查记录与当前成图不符")
    labels = row.get("labels")
    require(isinstance(labels, list) and labels and all(isinstance(s, str) and s.strip() for s in labels),
            f"{path.name} 需记录实际看到的图内中文、坐标、图例或面板标注")
    _check_labels(labels, path.name)
    caption = _fold(figure.get("caption", ""))
    require(any(_fold(label) != caption for label in labels if HAN.search(label)), f"{path.name} 视觉记录仅复述图注，缺少图内标注")
    observation = _str(row.get("observation"), f"{path.name} 缺少查看实际导出图的具体观察")
    require(not re.fullmatch(r"已?(?:查看|核查|检查|审阅|完成|通过|正常|清楚|可读|无误|无问题|无错误)[。.!！]?", observation)
            and (any(_fold(label) in _fold(observation) for label in labels if HAN.search(label)) or
                 bool(re.search(r"字号|图例|标注|标尺|坐标|刻度|颜色|箭头|线型|重叠|遮挡|裁切|正常尺寸|label|axis|legend",
                                observation, re.I))), f"{path.name} 请记录正常阅读尺寸下实际看到的标注或显示情况")
    return labels


def _model(overview, labels, methods, name):
    require(isinstance(overview, dict), f"{name} 缺少本研究的方法图流程、关键模块与贡献说明")
    for key, minimum in (("flow", 2), ("modules", 1)):
        values = overview.get(key)
        require(isinstance(values, list) and all(isinstance(v, str) and v.strip() for v in values)
                and len({_fold(v) for v in values}) >= minimum, f"{name} 需列出图中的流程环节或关键模块：{key}")
    contribution = _str(overview.get("contribution"), f"{name} 缺少具体的研究贡献或复现内容")
    named = [*overview["flow"], *overview["modules"], contribution]
    for item in named:
        require(any(_fold(item) in _fold(label) for label in labels), f"{name} 的方法说明未出现在图内：{item}")
    require(any(_specific(s) for s in overview["flow"]) and any(_specific(s) for s in overview["modules"])
            and _specific(contribution), f"{name} 的通用流程或创新占位词没有指出本研究实际构建的内容")
    require(any(_linked(s, methods) for s in overview["modules"]) and _linked(contribution, methods),
            f"{name} 的关键模块或贡献与所交付的研究方法缺少对应")


def _design_text(root, figure, name):
    ref = _str(figure.get("design_ref"), f"{name} 缺少参考图阅读记录 design_ref")
    document = local(root, ref).read_text(encoding="utf-8-sig")
    document = re.sub(r"<!--.*?-->|(?ms:^\s*\x60{3}[^\n]*\n.*?^\s*\x60{3}[^\n]*$)", "", document, flags=re.S)
    if "#" in ref:
        anchor = _fold(unquote(ref.split("#", 1)[1])).replace("-", "")
        headings = list(re.finditer(r"(?m)^(#{1,6})[ \t]+(.+)$", document))
        selected = next((h for h in headings if anchor == _fold(h[2]).replace("-", "")), None)
        require(selected, f"{name} 的 design_ref 未找到指定的阅读记录段落")
        end = next((h.start() for h in headings if h.start() > selected.start() and len(h[1]) <= len(selected[1])),
                   len(document))
        document = document[selected.start():end]
    return ref, document


def _named_paper(value):
    return (bool(value) and not re.fullmatch(r"(?:某|相关|一篇|原始|参考|已有|同类|新)?(?:论文|研究|文献)(?:[A-Z\d])?", value)
            and (re.search(r"\b(?:19|20)\d{2}\b|10\.\d{4,9}/|PMID\s*:?\s*\d+|《[^》]+》", value, re.I)
                 or len(WORD.findall(value)) >= 3 or len(HAN.findall(value)) >= 6))


def _paper_record(root, figure, name, labels, context):
    ref, document = _design_text(root, figure, name)
    # Keep separate table rows and paragraphs separate so two papers cannot be spliced together.
    blocks = re.split(r"\n[ \t]*\n|\n(?=[ \t]*\|)", document)
    table_rows = [line for line in document.splitlines() if line.lstrip().startswith("|")]
    if not table_rows and "#" in ref:
        blocks.append(document)
    source = figure.get("literature_figure")
    if source is None:
        # A design_ref pointing to a single reading in the existing figure-plan table is sufficient.
        candidates = []
        for line in table_rows:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 4 and _named_paper(cells[0]) and PANEL.search(cells[1]):
                candidates.append(cells[:4])
            elif len(cells) == 3:
                panel_match = PANEL.search(cells[0])
                if panel_match:
                    paper = cells[0][:panel_match.start()].strip(" ,，;；:：")
                    if _named_paper(paper):
                        candidates.append([paper, panel_match[0], cells[1], cells[2]])
        require(len(candidates) == 1, f"{name} 的 design_ref 需指明一条结果图参考记录，可选择对应段落或填写 literature_figure")
        paper, panel, comparison, reason = candidates[0]
    else:
        require(isinstance(source, dict), f"{name} 缺少本结果图实际参考的原始研究图与设计理由")
        paper, panel, comparison, reason = [_str(source.get(k), f"{name} 的参考图缺少 {k}")
                                            for k in ("paper", "panel", "comparison", "reason")]
    require(_named_paper(paper), f"{name} 请指明参考论文的作者年份、题名或文献标识")
    require(PANEL.search(panel) or re.fullmatch(r"S?\d+[A-Za-z]?", panel, re.I), f"{name} 请指明原论文图号或具体图版")
    require(comparison and reason, f"{name} 的阅读记录缺少采用的比较或适用理由")
    require(any(all(_fold(v) in _fold(block) for v in (paper, panel, comparison, reason)) for block in blocks),
            f"{name} 的论文、图号、采用的比较和理由未对应到 design_ref 中同一条阅读记录")
    require(_fold(comparison) != _fold(reason) and not re.fullmatch(r"借鉴|美观|好看|参考|同上|适用|合理|方便|更清楚|与本研究有关", reason)
            and _linked(comparison, " ".join([*labels, context])),
            f"{name} 的原图比较或采用理由与本研究的图文未形成具体对应")


def check_figure_reading(root, delivery, figures, embedded_paths, model_figure_id):
    """Validate every displayed rendition; raster/outlined labels are human observations, not OCR."""
    root = Path(root).resolve()
    parts = delivery.get("parts", [])
    require(model_figure_id in figures and model_figure_id in embedded_paths, "主要模型图没有实际嵌入正文")
    require(set(embedded_paths) <= set(figures), "正文嵌入了未登记的图件")
    declared = {fid for p in parts for fid in p.get("figure_ids", [])}
    require(declared <= set(embedded_paths), "部分已登记的正文图件缺少实际嵌入文件")
    visual_files = set()
    for fid, paths in embedded_paths.items():
        figure = figures[fid]
        require(isinstance(paths, (list, tuple, set, frozenset)) and paths, f"{fid} 缺少实际嵌入的成图文件")
        registered = {local(root, f) for f in figure.get("files", [])}
        own_parts = [p for p in parts if fid in p.get("figure_ids", [])]
        methods = " ".join(p.get("report_excerpt", "") for p in own_parts if p.get("kind") == "methods")
        result_parts = [p for p in own_parts if p.get("kind") in {"questions", "validation", "comparison", "evaluation"}]
        result_figure = bool(result_parts) or (fid != model_figure_id and (figure.get("depiction") == "data_result" or
                           any(p.get("depiction") == "data_result" for p in figure.get("panels", []))))
        context = " ".join([figure.get("caption", ""), *(p.get("report_excerpt", "") for p in result_parts)])
        for ref in paths:
            path = local(root, str(ref))
            require(path in registered, f"{fid} 实际嵌入的文件与登记的图件不符：{path.name}")
            if path.suffix.lower() == ".svg":
                labels, needs_visual = _svg(path)
            else:
                require(path.suffix.lower() in RASTER, f"{fid} 无法核对该嵌入图的格式：{path.name}")
                labels, needs_visual = [], True
            if needs_visual:
                labels = [*labels, *_visual_labels(root, figure, path)]
                visual_files.add(path.relative_to(root).as_posix())
            _check_labels(labels, path.name)
            if fid == model_figure_id:
                _model(figure.get("model_overview"), labels, methods, path.name)
            if result_figure:
                _paper_record(root, figure, path.name, labels, context)
    return dict(model_figure_id=model_figure_id, checked_figures=sorted(embedded_paths), visual_review_files=sorted(visual_files))
