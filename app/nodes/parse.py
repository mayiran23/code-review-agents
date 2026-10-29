"""
parse节点：把diff纯文本->结构化数据
输入 state["patch"]：一段diff文本
输出 state["files"]：结构化数据

为什么有这一步？
因为模型看不懂“@@ -10，3 +10，5 @@”这种符号
它需要的是“哪个文件，第几行，这一行是新增的还是删除的”
这一步就是把diff翻译成模型能吃的格式
"""
from unidiff import PatchSet, UnidiffParseError




#parse节点，解析diff的节点
def parse_node(state: dict) -> dict:
    patch_text=state.get("patch") or ""

    #情况一：空diff（什么都没有改就跑了命令）
    #直接返回空列表，不要抛异常。下游拿到空列表会直接跳过
    if not patch_text.strip():
        return {"files": []}
    try:
        #把一段diff纯文本变成python里能用代码操作的对象，正好对应diff的三层结构
        patch=PatchSet(patch_text)
    except UnidiffParseError:
        #情况二：不是合法diff（比如误传了整个文件内容）
        #同样不抛异常，交给下游判断
        return {"files": []}

    files=[]
    #遍历每个文件
    for pf in patch:
        if pf.is_binary_file:       #图片，jar包之类，没有“行”的概念
            continue
        if pf.is_removed_file:      #被整个删掉的文件，没有新代码可审
            continue
        hunks=[]
        #遍历每一块
        for hunk in pf:
            lines=[]
            for line in hunk:
                #line.line_type只有三种值
                #“”=没变的上下文行
                #“+”=新增的行
                #“-”=删除的行
                #line.target_line_no=这一行在【新文件】里的行号
                #删除行没有新行号，所以是None
                #这个target_line_no就是Finding.start_line的来源
                lines.append({
                    "type":line.line_type,
                    "text":line.value.rstrip("\n"),
                    "new_line":line.target_line_no,
                })
            hunks.append({
                "new_start": hunk.target_start,
                "lines": lines,
            })
        files.append({
            "path": pf.path,
            "hunks": hunks,
        })
    return {"files": files}