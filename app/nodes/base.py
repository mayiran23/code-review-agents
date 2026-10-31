"""
三个审查员共用的骨架

security/performance/style 除了【看哪类问题】不同，其余完全一样
拼上下文->调模型->兜异常->返回findings
所以抽成工厂函数，避免重复代码
"""
from app.llm import llm
from pathlib import Path
from app.state import Finding

#提示词从外部文件读
_PROMPT_DIR =Path(__file__).parent.parent/"prompts"
#拼接上下文
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
def make_reviewer(category: str,prompt_file: str):
    """
    造一个审查员节点：
    Args:
        category: 这个节点产出Finding的类别
        prompt_file: prompts/下的文件名

    Returns:返回一个符合LangGraph节点签名的函数：state->dict

    """
    #提示词在造节点时读一次，不是每次调用都读
    prompt_path=_PROMPT_DIR/f"{prompt_file}.md"
    system_prompt=prompt_path.read_text(encoding="utf-8")

    def node(state: dict)->dict:
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
                ("system", system_prompt),
                ("user", f"请审查以下代码改动：\n\n{context}"),
            ])
        except Exception as e:
            #模型超时/限流/返回格式不合规，不能让整条流水线崩
            print(f"[{category}]模型调用失败：{e}")
            return {"findings": []}

        #*强制改写category*
        #模型可能返回别的分类（比如给security节点返回performance）
        #那merge归并时就全乱了。这里不信任模型，直接覆盖
        for f in result.findings:
            f.category=category
        #result是ReviewResult对象，取出里面的列表
        return {"findings": result.findings}
    return node