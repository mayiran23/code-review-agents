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
        groups.setdefault((f.file,f.start_line,f.category),[]).append(f)

    merged: list[Finding]=[]
    conflicts: list[dict]=[]

    # ---------- 2. 同位置同类别，只留最严重的一条 ----------
    for items in groups.values():
        best = min(items, key=lambda x: _SEVERITY_ORDER.get(x.severity, 9))
        merged.append(best)

    # ---------- 3. 排序：文件 → 行号 → 严重程度 ----------
    merged.sort(key=lambda f: (f.file, f.start_line, _SEVERITY_ORDER.get(f.severity, 9)))

    return {"merged": merged, "conflicts": []}
