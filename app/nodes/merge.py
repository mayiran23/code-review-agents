"""
merge节点：把三路并行产出的意见归并成一份

三路并行时，同一行代码可能被两个甚至三个审查员同时提到。
本节点负责：
    1.按（文件，行号）分组
    2.每组只保留最严重的一条
    3.同一位置出现多个类型->记一条冲突提示
"""
from app.state import Finding
#排序权重：P0排最前
_SEVERITY_ORDER={"P0": 0, "P1": 1, "P2": 2, "P3": 3}

def merge_node(state: dict)->dict:
    findings=state.get("findings") or []

    #没有意见可归并
    if not findings:
        return {"merged": [],"conflicts": []}

    #---------------1.按（文件，行号）分组---------------
    #键用精确的（file,start_line）,不做模糊匹配：
    #行号差1就合并会把两个不同问题揉在一起，得不偿失
    groups: dict[tuple,list[Finding]]={}
    for f in findings:
        groups.setdefault((f.file,f.start_line),[]).append(f)

    merged: list[Finding]=[]
    conflicts: list[dict]=[]

    for (file,line),items in groups.items():
        #---------2.同位置只留最严重的一条------------
        best=min(items,key=lambda x: _SEVERITY_ORDER.get(x.severity,9))
        merged.append(best)

        #---------3.同一位置出现多个类别->冲突--------
        #不判断“结论是否真的矛盾”（模型判断不了）
        #只提示“这一行有多个维度的意见”，让人自己取舍
        cats={x.category for x in items}
        if len(cats)>=2:
            conflicts.append({
                "file":file,
                "line":line,
                "category":sorted(cats),
                "note": " / ".join(sorted(cats)) + " 都指向这一行，建议合并考虑",
            })
    #--------------------4.排序，保证每次输出顺序一致--------------
    merged.sort(key=lambda f:(_SEVERITY_ORDER.get(f.severity,9),f.file,f.start_line))

    return {"merged":merged,"conflicts":conflicts}