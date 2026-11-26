#!/usr/bin/env python3
"""Search and publish the shared neuroscience link index. Uses only the Python standard library."""
import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT = Path(__file__).resolve().parents[1] / "references" / "index"
TABLES = {
    "papers": "id title authors doi date status kinds url source use data_status tags",
    "results": "id paper locator source origin species anatomy preparation state protocol control metric unit value window grouping independent_unit use constraint family tags",
    "resources": "id kind title accession version url source access license checked use family tags",
    "links": "from to relation detail source",
}
ACCESS = {"public", "registration", "application", "not_public", "not_located", "broken", "unchecked"}
ORIGINS = {"measured_here", "cited_measurement", "published_aggregate", "simulation", "inferred", "theory"}
KINDS = {"model", "theory", "experiment", "data", "method", "software", "review"}
RESOURCES = {
    "raw",
    "processed",
    "figure_data",
    "protocol",
    "model_code",
    "analysis_code",
    "portal",
    "tool",
    "atlas",
    "format",
    "benchmark",
    "parameter",
    "reproduction",
    "waveform",
}
MISSING = {"未报告", "未核实", "不适用", "未知", ""}
DIMENSIONS = {
    "scale": "尺度",
    "method": "模型与方法",
    "anatomy": "解剖",
    "species": "物种",
    "state": "状态",
    "topic": "生理问题",
    "recording": "记录方式",
    "signal": "电生理指标",
    "related": "相关观测",
    "preparation": "制备",
    "protocol": "协议",
    "cell": "细胞类型",
    "layer": "组织层",
    "stage": "发育阶段",
    "metadata": "资源说明",
}
TITLES = {"papers": "文献", "results": "观测与模拟结果", "resources": "资源", "links": "关联"}
COLLECTIONS = {
    "window_model": "窗口内建模与理论",
    "window_support": "窗口内实验与技术支持",
    "preprint": "预印本",
    "early": "早期关联文献",
    "pending": "首次在线日待核",
    "later": "本期截止后出版",
}


def paper_collection(row, period):
    if row["status"] == "preprint":
        return "preprint"
    start, end = period["start"], period["end"]
    published = row["date"]
    if published in MISSING:
        reported = str(row.get("reported_year", ""))
        return "early" if reported.isdigit() and int(reported) < int(start[:4]) else "pending"
    if published < start:
        return "early"
    if published > end:
        return "later"
    return "window_model" if set(row["kinds"]) & {"model", "theory"} else "window_support"


def read_lines(path):
    with path.open(encoding="utf-8-sig") as f:
        rows = []
        for n, line in enumerate(f, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError as exc:
                    raise ValueError(f"{path.name}:{n} {exc}") from exc
        return rows


def read_catalog(root):
    with (root / "vocabulary.tsv").open(encoding="utf-8-sig", newline="") as f:
        vocab = list(csv.DictReader(f, delimiter="\t"))
    data = {name: read_lines(root / (name + ".jsonl")) for name in TABLES}
    return data, vocab


def audit_searches(root):
    period = json.loads((root / "period.json").read_text(encoding="utf-8-sig"))
    start, end, last = (date.fromisoformat(period[k]) for k in ("start", "end", "last_search"))
    if start > end or last < end:
        raise ValueError("检索窗口或最近检索日期无效")
    query_ids = set()
    for path in (root / "batches").glob("*-searches.jsonl"):
        for row in read_lines(path):
            if not all(
                row.get(k)
                for k in (
                    "id",
                    "platform",
                    "query",
                    "url",
                    "date",
                    "years",
                    "language",
                    "scope",
                    "outcome",
                    "status",
                )
            ):
                raise ValueError(f"{path.name} 缺少检索范围、出处或结果")
            if row["id"] in query_ids or not valid_url(row["url"]) or date.fromisoformat(row["date"]) > last:
                raise ValueError(f"检索标识重复、日期或链接无效 {row['id']}")
            query_ids.add(row["id"])
    gap_ids = set()
    for gap in read_lines(root / "gaps.jsonl"):
        if not all(gap.get(k) for k in ("id", "status", "conditions", "keywords", "date", "next")):
            raise ValueError("待补条件缺少字段")
        if (
            gap["id"] in gap_ids
            or set(gap.get("search_ids", [])) - query_ids
            or date.fromisoformat(gap["date"]) > last
        ):
            raise ValueError(f"待补条件的标识或检索来源有误 {gap['id']}")
        gap_ids.add(gap["id"])


def norm(s):
    return unicodedata.normalize("NFKC", str(s)).casefold().replace("–", "-").replace("—", "-").strip()


def doi_key(s):
    s = norm(s)
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", s)


def valid_url(s):
    p = urlsplit(str(s))
    return p.scheme in ("http", "https") and bool(p.netloc) and not p.username and not p.password


def identifiers(table, row):
    def known(key):
        value = row.get(key)
        return value if isinstance(value, str) and value not in MISSING else None

    if table == "papers":
        keys = []
        if known("doi"):
            keys.append(("doi", doi_key(row["doi"])))
        values = row.get("identifiers", [])
        if isinstance(values, dict):
            values = [f"{k}:{v}" for k, v in values.items()]
        elif isinstance(values, str):
            values = [values]
        fields = [*values, *(f"{k}:{row[k]}" for k in ("pmid", "arxiv") if row.get(k))]
        for v in [*fields, row.get("url", ""), row.get("source", "")]:
            v = norm(v)
            m = re.search(
                r"(?:pubmed\.ncbi\.nlm\.nih\.gov/|europepmc\.org/article/med/|\bpmid\s*:?\s*)(\d+)", v
            )
            if m:
                keys.append(("pmid", m.group(1)))
            m = re.search(
                r"(?:arxiv\.org/(?:abs|pdf)/|\barxiv\s*:\s*)([a-z.-]+/\d+|\d{4}\.\d{4,5})(?:v\d+)?", v
            )
            if m:
                keys.append(("arxiv", m.group(1)))
        for v in fields:
            if ":" in str(v):
                keys.append(("paper_id", norm(v)))
        return list(dict.fromkeys(keys))
    if table == "resources" and known("version"):
        accession = known("accession") or known("url")
        if accession:
            return [("resource", norm(accession).rstrip("/"), norm(row["version"]))]
    if table == "results":
        parent = known("paper") or known("resource")
        fields = (
            "locator",
            "origin",
            "species",
            "anatomy",
            "protocol",
            "control",
            "metric",
            "grouping",
            "window",
        )
        if parent and all(row.get(k) for k in fields):
            return [("observation", parent, *(norm(row[k]) for k in fields))]
    return []


def validate(data, vocab):
    defs = {r["id"]: r for r in vocab}
    if len(defs) != len(vocab) or any(
        r["dimension"] not in DIMENSIONS or not all(r.get(k) for k in ("id", "zh", "en")) for r in vocab
    ):
        raise ValueError("词表 ID 重复、维度未知或缺少中英文名称")
    ids = {}
    papers = set()
    identities = {}
    edges = set()
    for table, fields in TABLES.items():
        for row in data[table]:
            key = row.get("id") or str((row.get("from"), row.get("to"), row.get("relation")))
            for col in fields.split():
                if col not in row or row[col] is None or (isinstance(row[col], str) and not row[col].strip()):
                    raise ValueError(f"{table}/{key} 缺 {col}")
            if not valid_url(row["source"]) or ("url" in row and not valid_url(row["url"])):
                raise ValueError(f"{key} 需要公开的来源页")
            if table == "links":
                edge = (row["from"], row["to"], row["relation"])
                if edge in edges or edge[0] == edge[1]:
                    raise ValueError(f"重复或自指的关联 {edge}")
                edges.add(edge)
                continue
            if (
                not re.fullmatch(
                    {"papers": "p_", "results": "o_", "resources": "r_"}[table] + r"[a-z0-9_]+", key
                )
                or key in ids
            ):
                raise ValueError(f"记录 ID 无效或重复 {key}")
            ids[key] = row
            if (
                not isinstance(row["tags"], list)
                or not row["tags"]
                or len(set(row["tags"])) != len(row["tags"])
                or set(row["tags"]) - set(defs)
            ):
                raise ValueError(f"{key} 标签缺失、重复或未定义 {set(row['tags'])-set(defs)}")
            if table == "papers":
                papers.add(key)
                if (
                    row["status"] not in {"published", "preprint", "correction", "thesis", "conference"}
                    or not set(row["kinds"]) <= KINDS
                    or not row["kinds"]
                ):
                    raise ValueError(f"{key} 文献类型或发表状态无效")
                if row["data_status"] not in {
                    "linked",
                    "not_located",
                    "not_public",
                    "unchecked",
                    "not_applicable",
                }:
                    raise ValueError(f"{key} 数据状态无效")
                if row["date"] not in MISSING:
                    date.fromisoformat(row["date"])
                if row["doi"] not in MISSING:
                    doi = doi_key(row["doi"])
                    if not doi.startswith("10.") or "/" not in doi:
                        raise ValueError(f"{key} DOI 无效")
            elif table == "results":
                if row["origin"] not in ORIGINS:
                    raise ValueError(f"{key} 结果来源无效")
            else:
                if row["kind"] not in RESOURCES or row["access"] not in ACCESS:
                    raise ValueError(f"{key} 资源类型或访问条件无效")
                date.fromisoformat(row["checked"])
            for identity in identifiers(table, row):
                if identity in identities:
                    raise ValueError(f"同一标识和版本重复 {key} / {identities[identity]}")
                identities[identity] = key
    for a, b, _ in edges:
        if a not in ids or b not in ids:
            raise ValueError(f"未找到关联对象 {a} / {b}")
    for r in data["results"]:
        if r["paper"] not in papers and (r["paper"] not in MISSING or not r.get("resource")):
            raise ValueError(f"{r['id']} 未找到原文献或直接实测的数据资源")
        if r.get("resource") and (r["resource"] not in ids or not r["resource"].startswith("r_")):
            raise ValueError(f"{r['id']} 未找到原始资源")
    return ids


def aliases(row):
    return {norm(s) for s in [row["id"], row["zh"], row["en"], *row["aliases"].split(";")] if s}


def parse_question(text, vocab):
    text = norm(text)
    found = set()
    covered = [False] * len(text)
    for row in vocab:
        for a in aliases(row):
            pattern = re.escape(a)
            if not re.search(r"[\u3400-\u9fff]", a):
                pattern = r"(?<![a-z0-9_])" + pattern + r"(?![a-z0-9_])"
            for match in re.finditer(pattern, text):
                found.add(row["id"])
                covered[match.start() : match.end()] = [True] * len(match.group())
    remainder = "".join(" " if used else char for char, used in zip(text, covered))
    filler = r"寻找|查找|搜索|请问|比较|可用于|约束|条件下|状态下|状态|实测数据|实测记录|实验记录|相关记录|的记录|实测|记录|是否|哪些|可|与|及|和|的|、|，|。|[？?]"
    remainder = re.sub(filler, " ", remainder)
    quantity = r"\d+(?:\.\d+)?\s*(?:小时|分钟|毫秒|秒钟|秒|khz|hz|ms|pa|na|mv|min|s)\b"
    terms = [
        t
        for t in re.findall(quantity + r"|[a-z0-9][a-z0-9./:_-]*|[\u3400-\u9fff]+", remainder)
        if t
        not in {
            "find",
            "the",
            "and",
            "of",
            "for",
            "in",
            "under",
            "records",
            "recordings",
            "compare",
            "empirical",
            "measured",
        }
    ]
    return found, terms


def infer(text, vocab):
    return parse_question(text, vocab)[0]


def related(row, data, ids):
    key = row["id"]
    items = []
    for e in data["links"]:
        if key not in (e["from"], e["to"]):
            continue
        other = ids[e["to"] if e["from"] == key else e["from"]]
        items.append(
            {
                "id": other["id"],
                "relation": e["relation"],
                "from": e["from"],
                "to": e["to"],
                "detail": e["detail"],
                "url": other.get("url", other["source"]),
            }
        )
    if key.startswith(("p_", "r_")):
        for result in data["results"]:
            if key in (result["paper"], result.get("resource")):
                items.append(
                    {
                        "id": result["id"],
                        "relation": "reports_result",
                        "from": key,
                        "to": result["id"],
                        "detail": result["locator"],
                        "origin": result["origin"],
                        "metric": result["metric"],
                        "url": result["source"],
                    }
                )
    return items


def query(data, vocab, ids, question, tags, table, near):
    wanted = set()
    for token in tags:
        matches = {r["id"] for r in vocab if norm(token) in aliases(r)}
        if len(matches) != 1:
            raise ValueError(f"标签不存在或有歧义 {token}，请使用 vocabulary.tsv 中的 id")
        wanted.update(matches)
    inferred, terms = parse_question(question, vocab) if question else (set(), [])
    wanted.update(inferred)
    measured_only = bool(re.search(r"实测|实验记录|\b(?:empirical|measured) recordings?\b", norm(question)))
    empirical = {"measured_here", "cited_measurement", "published_aggregate"}
    empirical_papers = {r["paper"] for r in data["results"] if r["origin"] in empirical}
    output = []
    for name in ("papers", "results", "resources") if table == "all" else (table,):
        for row in data[name]:
            if measured_only:
                if name == "results" and row["origin"] not in empirical:
                    continue
                if name == "papers" and not (
                    {"experiment", "data"} & set(row["kinds"]) or row["id"] in empirical_papers
                ):
                    continue
                if name == "resources" and (
                    row["kind"] not in {"raw", "processed", "figure_data"} or "simulation" in row["tags"]
                ):
                    continue
            have = set(row["tags"])
            missing = wanted - have
            hit = wanted & have
            parent = ids.get(row.get("paper"), {}) if name == "results" else {}
            searchable = norm(
                " ".join(
                    str(v)
                    for v in [
                        *row.values(),
                        parent.get("title", ""),
                        parent.get("authors", ""),
                        parent.get("doi", ""),
                    ]
                )
            )

            def present(term):
                if re.match(r"^\d+(?:\.\d+)?\s*[a-z\u3400-\u9fff]", term):
                    pattern = re.sub(
                        r"(?<=\d)\s*(?=[a-z\u3400-\u9fff])", lambda _: r"\s*", term.replace(".", r"\.")
                    )
                    return bool(re.search(r"(?<![\d.])" + pattern + r"(?![a-z0-9])", searchable))
                if re.fullmatch(r"[a-z0-9]+", term):
                    return bool(re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", searchable))
                return term in searchable

            missing_text = [term for term in terms if not present(term)]
            if not near and (missing or missing_text):
                continue
            if near and not hit and len(missing_text) == len(terms):
                continue
            if question and not wanted and not terms and not measured_only:
                continue
            family = row.get("family")
            same = [
                r["id"]
                for k in ("results", "resources")
                for r in data[k]
                if family not in MISSING and family == r.get("family") and r["id"] != row["id"]
            ]
            output.append(
                {
                    "type": name,
                    "record": row,
                    "matched": sorted(hit),
                    "missing": sorted(missing),
                    "missing_text": missing_text,
                    "paper_url": parent.get("url"),
                    "resource_url": ids[row["resource"]]["url"] if row.get("resource") else None,
                    "related": related(row, data, ids),
                    "same_family": same,
                }
            )
    output.sort(key=lambda r: (len(r["missing"]) + len(r["missing_text"]), r["record"]["id"]))
    return {
        "filters": sorted(wanted),
        "text_filters": terms,
        "measured_only": measured_only,
        "matches": output,
    }


def md(s):
    return str(s).replace("|", r"\|").replace("\r", " ").replace("\n", " ")


def render(root, data, vocab):
    dest = "browse/"
    out = {}
    rows = [(n, r) for n in ("papers", "results", "resources") for r in data[n]]
    defs = {r["id"]: r for r in vocab}
    period = json.loads((root / "period.json").read_text(encoding="utf-8-sig"))
    lines = [
        "# 逐条查看资料",
        "",
        "由四张表生成。每项结果均可回到原文位置，同一来源组中的条目可能共享动物、细胞或原始记录。",
        "",
    ]
    adj = {}
    for e in data["links"]:
        for start, end in [(e["from"], e["to"]), (e["to"], e["from"])]:
            direction = "→" if start == e["from"] else "←"
            adj.setdefault(start, []).append((end, direction, e["relation"], e["detail"], e["source"]))
    for name, r in rows:
        k = r["id"]
        lines += ["### " + k, ""]
        if name == "results":
            owner = f"[所属论文](#{r['paper']})" if r["paper"] not in MISSING else "采集论文尚待核实"
            if r.get("resource"):
                owner += f" · [数据记录](#{r['resource']})"
            lines += [
                f"**{md(r['metric'])}**　{md(r['value'])}。[{md(r['locator'])}]({r['source']}) · {owner}",
                "",
                " | ".join(md(r[x]) for x in ("species", "anatomy", "preparation", "state")) + "。",
                "",
                f"刺激/对照为 {md(r['protocol'])} / {md(r['control'])}。单位 {md(r['unit'])}，时窗 {md(r['window'])}，分组 {md(r['grouping'])}，独立单位 {md(r['independent_unit'])}。",
                "",
                f"原研究用途为 {md(r['use'])}。建模用途为 {md(r['constraint'])}。来源类别 `{r['origin']}`，共同来源 `{md(r['family'])}`。",
            ]
        else:
            lines += [f"**[{md(r['title'])}]({r['url']})**　{md(r['use'])}", ""]
            if name == "papers":
                lines.append(
                    f"{md(r['authors'])} · {r['date']} · {r['status']} · {', '.join(r['kinds'])} · 数据 {r['data_status']}。[来源]({r['source']})"
                )
                lines += ["", COLLECTIONS[paper_collection(r, period)] + "。" + md(r.get("date_note", ""))]
            else:
                lines.append(
                    f"{r['kind']} · {md(r['accession'])} · 版本 {md(r['version'])} · {r['access']} · 许可 {md(r['license'])} · 核实于 {r['checked']} · 共同来源 `{md(r['family'])}`。[依据]({r['source']})"
                )
                for field in ("access_note", "model_use_status", "license_source"):
                    if r.get(field):
                        lines += ["", md(r[field])]
        lines += ["", "标签　" + "、".join(defs[t]["zh"] for t in r["tags"])]
        if name in ("papers", "resources"):
            for obs in data["results"]:
                if k in (obs["paper"], obs.get("resource")):
                    lines += [
                        "",
                        f"[{md(obs['locator'])}](#{obs['id']}) · {obs['origin']} · {md(obs['metric'])}",
                    ]
        for other, direction, rel, detail, source in adj.get(k, []):
            lines += ["", f"本条 {direction} [{other}](#{other}) · {rel} · {md(detail)}。[出处]({source})"]
        lines.append("")
    out[dest + "records.md"] = "\n".join(lines)
    facets = {
        "anatomy": ("按解剖对象", ["anatomy"]),
        "models": ("按模型尺度和方法", ["scale", "method"]),
        "signals": ("按记录方式和可比指标", ["recording", "signal", "related"]),
        "topics": ("按研究问题与状态", ["topic", "state", "protocol"]),
    }
    for filename, (heading, dims) in facets.items():
        lines = ["# " + heading, "", "同一资料可以出现在多个主题下。空白主题见[覆盖表](coverage.md)。", ""]
        for t in vocab:
            if t["dimension"] not in dims:
                continue
            matches = [(n, r) for n, r in rows if t["id"] in r["tags"]]
            if not matches:
                continue
            lines += [f"## {t['zh']} · {t['en']}", ""]
            for n, r in matches:
                title = r.get("title") or (r["metric"] + " · " + r["locator"])
                lines.append(f"- [{md(title)}](records.md#{r['id']})　{TITLES[n]}")
            lines.append("")
        out[dest + filename + ".md"] = "\n".join(lines)
    batch_paths = sorted((root / "batches").glob("*-searches.jsonl"))
    logs = [r for p in batch_paths for r in read_lines(p)]
    claims = {}
    for log in logs:
        for pair in log.get("cells", []):
            claims.setdefault(tuple(pair), []).append(log)
    start, end = period["start"], period["end"]
    years = [str(i) for i in range(int(start[:4]), int(end[:4]) + 1)]
    coverage = [
        "# 已收录与待查范围",
        "",
        f"窗口 {start} 至 {end}，最近检索 {period['last_search']}。第一张表只计窗口内正式发表的 model/theory 文献。其余两表以具体结果或资源自身明确标注的条件计数。一项可出现于多格。",
        "",
        "每格组成是记录数和状态。空格“待查”表示尚无专门筛查记录。限定查询返回零、或在记录的范围内确实筛查无匹配时才记“本次未定位”。“查过部分”保留分页和筛选限制。“缺数据入口”仅用于已标记检索未定位的文献，明确未公开单列。",
        "",
        "[检索批次与候选标识](../batches/README.md) · [具体待补条件](../gaps.jsonl)",
        "",
    ]
    for label, xs, ys, subset in [
        (
            "年份 × 建模尺度",
            years,
            [t["id"] for t in vocab if t["dimension"] == "scale"],
            [(n, r) for n, r in rows if n == "papers" and paper_collection(r, period) == "window_model"],
        ),
        (
            "解剖系统 × 记录方式",
            [t["id"] for t in vocab if t["dimension"] == "anatomy"],
            [t["id"] for t in vocab if t["dimension"] == "recording"],
            [(n, r) for n, r in rows if n != "papers"],
        ),
        (
            "物种 × 生理状态",
            [t["id"] for t in vocab if t["dimension"] == "species"],
            [t["id"] for t in vocab if t["dimension"] == "state"],
            [(n, r) for n, r in rows if n != "papers"],
        ),
    ]:
        name = lambda t: defs[t]["zh"] if t in defs else t
        coverage += [
            "## " + label,
            "",
            "|类别|" + "|".join(name(y) for y in ys) + "|",
            "|---|" + "---|" * len(ys),
        ]
        for x in xs:
            values = []
            for y in ys:
                matched = [
                    r for n, r in subset if (x in r["tags"] or x == r.get("date", "")[:4]) and y in r["tags"]
                ]
                investigations = claims.get((x, y), [])
                if matched:
                    flags = Counter(r.get("data_status") for r in matched)
                    v = str(len(matched))
                    if flags["not_located"]:
                        v += f" 缺数据入口{flags['not_located']}"
                    if flags["not_public"]:
                        v += f" 明确未公开{flags['not_public']}"
                    if flags["unchecked"]:
                        v += f" 数据待核{flags['unchecked']}"
                else:
                    v = "待查"
                    if any(z.get("cell_status") == "not_located" for z in investigations):
                        v = "本次未定位"
                    elif investigations:
                        v = "查过部分"
                values.append(v)
            coverage.append("|" + name(x) + "|" + "|".join(values) + "|")
        coverage.append("")
    out[dest + "coverage.md"] = "\n".join(coverage)
    return {p: s.rstrip() + "\n" for p, s in out.items()}


def prepare(root, data, vocab, patch, output):
    """Build a complete import in a new sibling directory; the input index is read-only."""
    import shutil
    import tempfile
    from copy import deepcopy

    extra = set(patch) - set(TABLES) - {"vocabulary", "searches", "gaps"}
    if extra:
        raise ValueError("未识别的导入字段 " + ", ".join(sorted(extra)))
    updated = deepcopy(data)
    terms = {r["id"]: dict(r) for r in vocab}
    aliases_by_id = {}
    for term in patch.get("vocabulary", []):
        key = term["id"]
        if key in terms and terms[key] != term:
            raise ValueError(f"词表已有不同定义 {key}，请先合并词义")
        terms[key] = term
    for table in ("papers", "resources", "results"):
        by_id = {r["id"]: r for r in updated[table]}
        by_identity = {key: r for r in updated[table] for key in identifiers(table, r)}
        for item in patch.get(table, []):
            item = dict(item)
            submitted = item["id"]
            if "paper" in item:
                item["paper"] = aliases_by_id.get(item["paper"], item["paper"])
            if "resource" in item:
                item["resource"] = aliases_by_id.get(item["resource"], item["resource"])
            previous_by_id = by_id.get(submitted)
            known_keys = identifiers(table, {**(previous_by_id or {}), **item})
            matches = {by_identity[k]["id"] for k in known_keys if k in by_identity}
            if previous_by_id:
                matches.add(submitted)
            if len(matches) > 1:
                raise ValueError(f"ID 和来源标识分别指向不同记录 {submitted}")
            old = by_id[next(iter(matches))] if matches else None
            if old:
                protected = (
                    ("doi",)
                    if table == "papers"
                    else ("accession", "version") if table == "resources" else ()
                )
                for field in protected:
                    if field not in item or field not in old or old[field] in MISSING:
                        continue
                    canonical = doi_key if field == "doi" else norm
                    if canonical(item[field]) != canonical(old[field]):
                        raise ValueError(f"已发布 ID 的来源或版本改变 {submitted}/{field}，新版本请另建条目")
                    item[field] = old[field]
            if old:
                aliases_by_id[submitted] = old["id"]
            changes = set(item.pop("replace_fields", []))
            note = item.pop("change_note", None)
            if changes and (not note or not valid_url(item.get("source", ""))):
                raise ValueError(f"{submitted} 修改既有事实须给 change_note 和 source")
            if old is None:
                updated[table].append(item)
                by_id[submitted] = item
                for key in identifiers(table, item):
                    by_identity[key] = item
                continue
            for field, value in item.items():
                if field in {"id", "doi"} and field in old and old[field] not in MISSING:
                    continue
                if field in {"tags", "kinds"}:
                    old[field] = list(dict.fromkeys([*old.get(field, []), *value]))
                    continue
                previous = old.get(field)
                if previous == value:
                    continue
                unknown = not previous or (
                    isinstance(previous, str) and previous in MISSING | {"unchecked", "not_located"}
                )
                if not unknown and field not in changes:
                    raise ValueError(f"{submitted}/{field} 已有不同内容。核对后在 replace_fields 中指定")
                old[field] = value
            if note:
                amendment = {"note": note, "source": item["source"]}
                if amendment not in old.setdefault("amendments", []):
                    old["amendments"].append(amendment)
            for key in identifiers(table, old):
                by_identity[key] = old
    by_edge = {(e["from"], e["to"], e["relation"]): e for e in updated["links"]}
    for incoming in patch.get("links", []):
        e = dict(incoming)
        for k in ("from", "to"):
            e[k] = aliases_by_id.get(e[k], e[k])
        key = (e["from"], e["to"], e["relation"])
        if key in by_edge:
            if e != by_edge[key]:
                raise ValueError(f"请核对已有关系并显式编辑其说明 {key}")
        else:
            updated["links"].append(e)
            by_edge[key] = e
    vocab = list(terms.values())
    validate(updated, vocab)
    output = output.resolve()
    root = root.resolve()
    if output.exists() or output.is_relative_to(root):
        raise ValueError("输出须为原索引之外的全新目录")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="catalog-import-", dir=output.parent) as tmp:
        work = Path(tmp) / "index"
        shutil.copytree(root, work)
        for k, rows in updated.items():
            (work / (k + ".jsonl")).write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
            )
        with (work / "vocabulary.tsv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=["id", "dimension", "zh", "en", "aliases"],
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(vocab)
        if patch.get("searches") or patch.get("gaps"):
            stored = {}
            for path in (work / "batches").glob("*-searches.jsonl"):
                stored.update({r["id"]: r for r in read_lines(path)})
            dates = []
            for row in patch.get("searches", []):
                day = date.fromisoformat(row["date"]).isoformat()
                dates.append(day)
                if row["id"] in stored:
                    if stored[row["id"]] != row:
                        raise ValueError(f"检索 {row['id']} 已存在，请为新检索指定新 ID")
                    continue
                path = work / "batches" / (day + "-searches.jsonl")
                path.parent.mkdir(exist_ok=True)
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                stored[row["id"]] = row
            gap_path = work / "gaps.jsonl"
            gaps = {r["id"]: r for r in read_lines(gap_path)}
            for row in patch.get("gaps", []):
                day = date.fromisoformat(row["date"]).isoformat()
                dates.append(day)
                if row["id"] in gaps and gaps[row["id"]] != row:
                    raise ValueError(f"保留既有待补记录，以新 ID 登记后续跟进 {row['id']}")
                gaps[row["id"]] = row
            gap_path.write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in gaps.values()), encoding="utf-8"
            )
            period_path = work / "period.json"
            period = json.loads(period_path.read_text(encoding="utf-8"))
            period["last_search"] = max([period["last_search"], *dates])
            period_path.write_text(json.dumps(period, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            audit_searches(work)
        for path, s in render(work, updated, vocab).items():
            (work / path).parent.mkdir(parents=True, exist_ok=True)
            (work / path).write_text(s, encoding="utf-8")
        if output.exists():
            raise ValueError("输出目录已存在")
        work.rename(output)
    print(f"已准备合并副本 {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT)
    subs = parser.add_subparsers(dest="cmd", required=True)
    subs.add_parser("validate")
    subs.add_parser("build")
    m = subs.add_parser("prepare")
    m.add_argument("patch", type=Path)
    m.add_argument("output", type=Path)
    p = subs.add_parser("search")
    p.add_argument("question", nargs="?", default="")
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--type", choices=["all", "papers", "results", "resources"], default="all")
    p.add_argument("--near", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--limit", type=int)
    p.add_argument("--origin", choices=sorted(ORIGINS))
    p.add_argument("--access", choices=sorted(ACCESS))
    p.add_argument("--collection", choices=sorted(COLLECTIONS), help="按本期首次在线日与文献用途筛选")
    p.add_argument("--year", type=int, help="仅查有确定发表日期的文献")
    args = parser.parse_args()
    root = args.root
    data, vocab = read_catalog(root)
    ids = validate(data, vocab)
    if args.cmd == "prepare":
        prepare(root, data, vocab, json.loads(args.patch.read_text(encoding="utf-8-sig")), args.output)
        return
    if args.cmd in ("build", "validate"):
        audit_searches(root)
        generated = render(root, data, vocab)
        for rel, content in generated.items():
            path = root / rel
            if args.cmd == "build":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            elif not path.is_file() or path.read_text(encoding="utf-8") != content:
                raise ValueError(f"目录过期，请先 build 再 validate: {rel}")
        print(json.dumps({k: len(v) for k, v in data.items()}, ensure_ascii=False))
        return
    if not args.question and not args.tag and not args.collection and args.year is None:
        parser.error("请提供问题、标签或文献范围")
    result = query(data, vocab, ids, args.question, args.tag, args.type, args.near)
    if args.origin:
        result["matches"] = [m for m in result["matches"] if m["record"].get("origin") == args.origin]
    if args.access:
        result["matches"] = [m for m in result["matches"] if m["record"].get("access") == args.access]
    if args.collection or args.year is not None:
        period = json.loads((root / "period.json").read_text(encoding="utf-8-sig"))
        result["matches"] = [
            m
            for m in result["matches"]
            if m["type"] == "papers"
            and (not args.collection or paper_collection(m["record"], period) == args.collection)
            and (args.year is None or m["record"]["date"][:4] == str(args.year))
        ]
    total = len(result["matches"])
    if args.limit is not None:
        if args.limit < 0:
            parser.error("--limit 不能为负")
        result["matches"] = result["matches"][: args.limit]
    result["total"] = total
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(
        "标签",
        ", ".join(result["filters"]),
        "其余文字条件",
        " ".join(result["text_filters"]) or "无",
        "资料来源",
        "实测" if result["measured_only"] else args.origin or "全部",
        "命中",
        total,
    )
    for match in result["matches"]:
        r = match["record"]
        print("\n", r["id"], r.get("title") or r.get("locator"), r.get("url", r["source"]))
        if match["type"] == "results":
            print(
                r["origin"],
                r["value"],
                r["unit"],
                r["protocol"],
                "/",
                r["control"],
                r["window"],
                r["independent_unit"],
            )
            print(r["constraint"], match["paper_url"] or match["resource_url"])
        else:
            print(r["use"])
        print(
            "同源",
            r.get("family", "见关联"),
            "未满足条件",
            ",".join([*match["missing"], *match["missing_text"]]) or "无",
        )
        for item in match["related"]:
            print(" ", item["relation"], item["id"], item["detail"], item["url"])


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
