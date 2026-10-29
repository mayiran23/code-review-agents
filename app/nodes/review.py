"""
review节点：出审查意见
"""

from app.state import Finding

def review_node(state: dict)->dict:
    files=state.get("files") or []

    #没有文件可审，直接返回空列表
    if not files:
        return {"findings": []}
    #假数据也要“贴着真实数据”造，否则报告会指向不存在的行
    #你会一位是report写错了，其实是这里造的假
    first=files[0]
    path=first["path"]

    #取第一个改动块的新文件起始行。没有hunk就退回第一行
    line=first["hunks"][0]["new_start"] if first["hunks"] else 1

    findings=[
        Finding(
            file=path,
            start_line=line,
            end_line=line,
            category="security",
            severity="P0",
            message="【假数据】这里可能有注入风险",
            suggestion="改成参数化查询",
            confidence=0.9,
        ),
        Finding(
            file=path,
            start_line=line,
            end_line=line,
            category="performance",
            severity="P2",
            message="【假数据】这里可能有N+1查询",
            suggestion=None,
            confidence=0.5,
        ),
    ]

    return {"findings": findings}