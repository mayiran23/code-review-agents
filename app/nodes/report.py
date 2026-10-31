"""
report节点：把所有意见渲染成Markdown

这一步是纯字符串处理，不调模型、不联网
"""
from app.state import Finding

#排序权重：P0必须排最前面
_SEVERITY_ORDER={"P0": 0,"P1": 1,"P2": 2,"P3": 3}

#每一级的标题和含义
_SEVERITY_LABEL={
    "P0": "必须修改",
    "P1":"需要你判断",
    "P2":"建议修改",
    "P3":"可以不管",
}

def _render_one(f: Finding)->str:
    """
    渲染单条意见
    输入一个Finding对象，输出一段Markdown文字
    """
    #“###”是三级标题
    head=f"### `{f.file}:{f.start_line}`"
    #“**···**”是加粗
    meta=f"**{f.message}**（{f.category}·置信度{f.confidence:.2f}）"

    parts=[head,meta]
    if f.suggestion:
        parts.append(f"建议： {f.suggestion}")
    else:
        parts.append("建议：*（模型未给出具体写法）*")
    return "\n\n".join(parts)

def report_node(state: dict)->dict:
    # 优先用merge（merge跑过），否则退回findings（merge没加的时候）
    findings=state.get("merged") or state.get("findings") or []
    conflicts=state.get("conflicts") or []
    human_note=state.get("human_note")
    #情况一：什么都没有发现
    if not findings:
        return {"report": "# 代码评审报告\n\n没有发现问题。\n"}

    #按严重级别->文件->行号排序，保证每一次输出顺序一致
    ordered=sorted(
        findings,
        key=lambda f: (_SEVERITY_ORDER.get(f.severity,9),f.file,f.start_line),
    )

    lines=["# 代码评审报告",""]

    #------顶部统计--------
    counts={}
    for f in ordered:
        counts[f.severity]=counts.get(f.severity,0)+1
    summary="，".join(f"{k} × {v}"for k,v in sorted(counts.items()))
    lines.append(f"共{len(ordered)}条意见：{summary}")
    lines.append("")
    #---------按级别分组--------
    for sev in ("P0","P1","P2","P3"):
        group=[f for f in ordered if f.severity==sev]
        if not group:
            continue
        lines.append(f"## {sev}·{_SEVERITY_LABEL[sev]}({len(group)}条)")
        lines.append("")
        for f in group:
            lines.append(_render_one(f))
            lines.append("")

    #-------低置信度单独提醒---------
    #这是产品设计：模型自己都没把握的判断，不该和确定的判断混在一起
    low=[f for f in ordered if f.confidence<0.6]
    if low:
        lines.append("## 低置信度（建议你自己复核）")
        lines.append("")
        for f in low:
            lines.append(f"- `{f.file}:{f.start_line}` {f.message}")
        lines.append("")

    #-------冲突提示------
    #两个审查员吵架了，工具不替你决定
    if conflicts:
        lines.append("## 冲突提示")
        lines.append("")
        for c in conflicts:
            lines.append(f"- `{c.get('file')}:{c.get('line')}` {c.get('note', '')}")
        lines.append("")
    #----人工备注----
    #注意这里明确标了“人工确认”
    #否则读者会以为这是AI的结论
    if human_note:
        lines.append("## 人工确认")
        lines.append("")
        lines.append(f"> {human_note}")
        lines.append("")

    return {"report": "\n".join(lines)}
