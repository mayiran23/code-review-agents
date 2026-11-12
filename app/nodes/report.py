"""
report 节点：把意见渲染成 Markdown

结构：
  1. 顶部统计
  2. P0 速览（只列必须改的）
  3. 全部意见：按文件 → 行号 → 严重程度组织
"""
from app.state import Finding

_SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def report_node(state: dict) -> dict:
    findings = state.get("merged") or state.get("findings") or []

    if not findings:
        return {"report": "# 代码评审报告\n\n没有发现问题。\n"}

    # ---------- 1. 全局排序：文件 → 行号 → 严重程度 ----------
    ordered = sorted(
        findings,
        key=lambda f: (f.file, f.start_line, _SEVERITY_ORDER.get(f.severity, 9)),
    )

    lines = ["# 代码评审报告", ""]

    # ---------- 2. 顶部统计 ----------
    counts = {}
    for f in ordered:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    summary = "，".join(f"{k} × {v}" for k, v in sorted(counts.items()))
    lines.append(f"共 {len(ordered)} 条意见：{summary}")
    lines.append("")

    # ---------- 3. P0 速览 ----------
    p0 = [f for f in ordered if f.severity == "P0"]
    if p0:
        lines.append("## P0 · 必须修改")
        lines.append("")
        for f in p0:
            lines.append(f"- `{f.file}:{f.start_line}` {f.message}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ---------- 4. 全部意见：按文件分组 ----------
    lines.append("## 全部意见")
    lines.append("")

    by_file: dict[str, list[Finding]] = {}
    for f in ordered:
        by_file.setdefault(f.file, []).append(f)

    for path, items in by_file.items():
        lines.append(f"### {path}")
        lines.append("")

        # 文件内再按行号分组
        by_line: dict[int, list[Finding]] = {}
        for f in items:
            by_line.setdefault(f.start_line, []).append(f)

        for line_no in sorted(by_line):
            lines.append(f"**第 {line_no} 行**")
            lines.append("")
            for f in by_line[line_no]:
                # 用引用块，渲染后左侧有竖线，像卡片
                lines.append(f"> **[{f.severity}]** `{f.category}` · 置信度 {f.confidence:.2f}")
                lines.append(f"> {f.message}")
                if f.suggestion:
                    lines.append(f"> 建议：{f.suggestion}")
                else:
                    lines.append("> 建议：*（模型未给出具体写法）*")
                lines.append("")
            lines.append("")

    # ---------- 5. 低置信度单独提醒 ----------
    low = [f for f in ordered if f.confidence < 0.6]
    if low:
        lines.append("## 低置信度（建议你自己复核）")
        lines.append("")
        for f in low:
            lines.append(f"- `{f.file}:{f.start_line}` {f.message}")
        lines.append("")

    # ---------- 6. 人工备注 ----------
    human_note = state.get("human_note")
    if human_note:
        lines.append("## 人工确认")
        lines.append("")
        lines.append(f"> {human_note}")
        lines.append("")

    return {"report": "\n".join(lines)}
