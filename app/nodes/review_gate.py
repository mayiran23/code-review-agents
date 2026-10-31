"""
review_gate 节点：P1级问题的人工确认闸门

位置：merge->【review——gate】->report

逻辑：
    -auto_approve=True（评估模式）->直接放行，不打断
    -没有P1  ->直接放行
    -有P1   ->interrupt挂起，等人回复

★interrupt的返回值语义：
    第一次跑到interrupt()时，函数不会返回，整个图【冻住】；
    人回复后从这一行继续，answer才是那个回复
    所以interrupt()之后的代码，只是“恢复”时才执行。
"""
from langgraph.types import interrupt

def review_gate_node(state: dict)->dict:
    #1.评估模式：跳过人工确认
    if state.get("auto_approve"):
        return {"human_note": None}

    merged=state.get("merged") or []

    #2.没有P1，不需要打断
    p1=[f for f in merged if f.severity=="P1"]
    if not p1:
        return {"human_note": None}

    #3.有P1->挂起，把问题抛给人
    #注意：这里的payload会被invoke的返回值带出来，人据此做决定
    answer = interrupt({
        "question": f"有{len(p1)}条P1级问题，确认继续吗？",
        "items": [
            {
                "file": f.file,
                "line": f.start_line,
                "message": f.message,
            }
            for f in p1
        ],
    })

    #4.恢复后执行到这里，answer是人的回复
    return {"human_note": str(answer)}