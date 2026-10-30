"""
review节点：调模型审查新增代码
"""
from app.llm import llm
from pathlib import Path
from app.state import Finding

#提示词从外部文件读
_PROMPT_PATH=Path(__file__).parent.parent/"prompts"/"review.md"
_SYSTEM_PROMPT=_PROMPT_PATH.read_text(encoding="utf-8")

def _build_context(files: list[dict],ctx: int=3)->str:
    """
    把结构化改动拼成模型能读懂的文本
    关键：只保留‘+’行，以及它前后ctx行上下文
    其他全部丢弃

    为什么要带上下文，而不是只发‘+’行
        单独一行，看不出问题
        配上前后三行，模型才知道这是在哪一层、什么条件里
    """
    out=[]
    for f in files:
        for h in f.get("hunks", []):
            lines=h.get("lines", [])
            #先算出“哪些行的下标要保留”：每个‘+’行的前后ctx行
            keep=set()
            for i, r in enumerate(lines):
                if r.get("type")=="+":
                    lo=max(0,i-ctx)
                    hi=min(len(lines),i+ctx+1)
                    keep.update(range(lo,hi))
            #这个块里一个新增行都没有（全是删除），整块跳过
            if not keep:
                continue
            out.append(f"### 文件：{f['path']}")
            for i in sorted(keep):
                r=lines[i]
                no=r.get("new_line")
                #删除行没有新行号，用“-”占位，保持列对齐
                no_str=f"{no:>4}" if no else "   -"
                #格式：行号 符号 内容
                out.append(f"{no_str} {r['type']} {r['text']}")
            out.append("")

    return "\n".join(out)
def review_node(state: dict)->dict:
    files=state.get("files") or []

    #没有文件可审，直接返回空列表
    if not files:
        return {"findings": []}

    context=_build_context(files)
    #整个diff只有删除和上下文，没有新写的代码
    if not context.strip():
        return {"findings": []}
    try:
        result=llm.invoke([
            ("system", _SYSTEM_PROMPT),
            ("user", f"请审查以下代码改动：\n\n{context}"),
        ])
    except Exception as e:
        #模型超时/限流/返回格式不合规，不能让整条流水线崩
        print(f"[review]模型调用失败：{e}")
        return {"findings": []}
    #result是ReviewResult对象，取出里面的列表
    return {"findings": result.findings}