"""
mcp_server.py —— MCP 层

职责只有一个：把 MCP 的工具调用，翻译成对 app.graph 的一次 invoke。
业务逻辑（怎么解析 diff、怎么并行、怎么归并）一行都不写在这里。

在 Agent 环境里，取数据和处理数据应该分开：
git diff 是取数据，Agent 自己有终端能做；审查是处理数据，交给 server。
让 server 去猜「我在哪个仓库」，是把不确定性塞进了工具内部——猜错的代价是
它默默审了另外一个仓库，还不报错。所以 review_workspace 必须收到明确路径。

两个工具：
    review_diff      主工具：拿到一段 diff 文本就审，返回分级报告
    review_workspace 省一步：自己跑 git diff，再交给 review_diff

超长 diff 的策略（方案一：拒绝并给出可行动的下一步）：
    不截断、不静默丢弃，直接返回「超了多少行、都有哪些文件、建议怎么分批」。
    行级截断会让 parse 拿到残缺的 hunk 而解析失败，最终输出「未发现问题」——那是静默撒谎。
"""

#起子进程跑外部命令，让python去启动别的程序（git等），在这个项目中就是要跑git diff
import subprocess
#访问解释器状态：模块搜索路径、命令行参数、标准输入输出、退出
import sys
import time
#路径对象
from pathlib import Path
#顺序有语义：这两步必须在import app之前
# （1）宿主启动subprocess时cwd不确定，把本文件所在目录塞进模块搜索路径，app才找得到
# （2）app/llm.py在模块级读DEEPSEEK_API_KEY,所以.env必须在这之前加载完
sys.path.insert(0, str(Path(__file__).resolve().parent))
#读.env文件
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

from mcp.server.mcpserver import MCPServer

from app.graph import graph

server = MCPServer("code-review")

#一次审查最多喂多少行diff
#1500行≈3-5万token，三路并行就是3倍的量，已经到成本和延迟的甜点区上限
MAX_DIFF_LINES = 1500

#超长时最多列几个文件；再多就折叠成一行，别把上下文塞满
MAX_FILES_LISTED = 10

#git子进程超时（秒）：大仓库或网络盘卡住时，stdio是串行，整个server都会被拖死
GIT_TIMEOUT=30


def _split_files(diff: str) -> list[tuple[str, int]]:
    """按 "diff --git" 边界把 diff 切成文件块，返回 [(文件名, 该块行数), ...]。

    只用于「超长时生成建议」，不参与审查逻辑，所以不需要精确到 hunk。
    """
    lines = diff.splitlines()
    total = len(lines)

    #每个 "diff --git " 开头就是一个文件块的起点
    starts = [i for i, ln in enumerate(lines) if ln.startswith("diff --git ")]
    if not starts:
        return []

    blocks: list[tuple[str, int]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else total

        #文件名优先从 "+++ b/..." 取：
        #"diff --git a/x y b/x y" 这行里路径可能含空格，split() 会切错；"+++ " 后面是整体路径
        name = ""
        for ln in lines[start:end]:
            if ln.startswith("+++ "):
                raw = ln[4:].strip()
                if raw.startswith('"') and raw.endswith('"'):
                    raw = raw[1:-1]
                if raw == "/dev/null":
                    break
                name = raw[2:] if raw.startswith("b/") else raw
                break

        #删除文件没有 "+++" 行，退回去从 "diff --git" 里粗取一个名字
        if not name:
            name = lines[start][len("diff --git "):].split(" b/")[-1].strip('"')

        blocks.append((name, end - start))

    return blocks


def _too_long(diff: str, line_count: int) -> str:
    """把「审不了」翻译成「怎么审」。

    三类情况给三种不同的建议，混在一起会误导：
      1. 根本不是完整 diff    → 让它先确认输入格式
      2. 单个文件就超上限    → 分批救不了，只能缩小范围
      3. 多文件但总量超限    → 给文件行数清单，让它自己组合
    """
    head = f"这个 diff 有 {line_count} 行，超过单次上限 {MAX_DIFF_LINES} 行，本次未审查。"

    blocks = _split_files(diff)

    # 情况 1：没识别到任何文件头
    if not blocks:
        return (
            head
            + "\n没有识别到 diff --git 文件头，可能是输入不是完整的 diff。"
            + "\n请确认传入的是 git diff 的完整输出，而不是几行改动片段。"
        )

    # 情况 2：最大的那个文件本身就超过上限 —— 切开就会破坏 hunk 头，行号全错
    biggest_name, biggest_lines = max(blocks, key=lambda b: b[1])
    if biggest_lines > MAX_DIFF_LINES:
        return (
            head
            + f"\n其中 {biggest_name} 单个文件就有 {biggest_lines} 行，超过上限，无法自动分批。"
            + "\n请缩小审查范围（例如只审某几次提交），或先把这个文件的改动拆成多次提交再分次审查。"
        )

    # 情况 3：多文件，给清单让它自己组合
    shown = blocks[:MAX_FILES_LISTED]
    out = [head, f"各文件行数（共 {len(blocks)} 个文件）："]
    for name, n in shown:
        out.append(f"  {name}  {n} 行")

    if len(blocks) > len(shown):
        rest_lines = sum(n for _, n in blocks[len(shown):])
        out.append(f"  …… 其余 {len(blocks) - len(shown)} 个文件共 {rest_lines} 行")

    out.append(
        f"\n建议按上面的行数自行组合，使每批不超过 {MAX_DIFF_LINES} 行，分多次调用 review_diff；"
        f"\n也可以缩小范围重试，例如 review_workspace(repo_path=..., since=\"HEAD~1..HEAD\")。"
    )
    return "\n".join(out)


def _render(out: dict, elapsed: float, line_count: int) -> str:
    merged = out.get("merged") or []
    errors = out.get("errors") or []

    counts: dict[str, int] = {}
    for f in merged:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    if merged:
        head = f"审查完成：{len(merged)} 条意见（{'，'.join(f'{k}×{v}' for k, v in sorted(counts.items()))}）"
    elif errors:
        head = "审查完成（不完整）：本次未取得有效结论"
    else:
        head = "审查完成：未发现问题"

    lines = [head, f"耗时 {elapsed:.1f}s，输入 {line_count} 行 diff"]

    if errors:
        lines.append("以下环节失败，结论不完整：")
        for e in errors:
            lines.append(f"  - {e}")

    if errors and not merged:
        body="_（因上述环节失败，未生成有效报告）_"
    else:
        body=out.get("report") or "_（报告为空）_"
    return "\n".join(lines) + "\n\n" + body


@server.tool()
def review_diff(diff: str) -> str:
    """
    做什么：审查一段已经拿到的 git diff 文本，返回按 P0–P3 分级的 Markdown 报告。
    报告首行是统计摘要（各级别数量、耗时、输入行数）。

    什么时候用：
    - 用户把改动贴给你了，比如「这是我刚跑出来的 diff，帮我看看」
    - 你刚在终端跑完 git diff，需要先审一遍再决定改什么
    - 用户让你审一段已经给出的改动，比如「这段有没有安全问题」
    - 用户想复查某个历史提交，而你已经用 git show 取到了它的 diff

    什么时候不要用：
    - 用户说「审一下我这次的改动」但你手上没有 diff 文本 → 用 review_workspace，不要自己拼字符串
    - 工作区没有任何改动时（比如刚提交完）→ 会返回「没有收到任何 diff 内容」，容易被误当成故障
    - 用户问「这个函数写得怎么样」但给的是一个文件或一段代码，不是改动 → 没有 diff 就没有输入，审不出东西
    - 用户要你修改代码 → 它只读，不会改任何文件
    - diff 超过 1500 行时不会审查，而是返回文件清单和建议 —— 这时要按提示分批，
      不要用同样的输入再调一次，结果不会变

    参数：
    - diff：完整的 diff 文本，必须带 diff --git / --- / +++ / @@ 这些头。
      只贴几行改动片段会让解析失败，结果是「未发现问题」——所以贴之前先确认是完整 diff。
    """
    if not diff or not diff.strip():
        return "没有收到任何 diff 内容，无法审查。请先确认真的有未提交的改动。"

    line_count = len(diff.splitlines())
    #超长直接拒绝，并把「怎么分批」告诉调用方。绝不做行级截断——
    #切在 hunk 中间会让 unidiff 解析失败，最终输出「未发现问题」，那是静默撒谎
    if line_count > MAX_DIFF_LINES:
        return _too_long(diff, line_count)

    started = time.time()
    try:
        out = graph.invoke(
            #auto_approve 必须为 True：无 checkpointer 时 review_gate 调 interrupt 会直接抛错
            {"patch": diff, "auto_approve": True},
            {"recursion_limit": 25},
        )
    except Exception as e:
        #绝不让异常抛出去：工具抛异常在宿主里可能被判成「server 挂了」而断连，
        #返回一句人话，模型还能自己决定下一步
        print(f"[review] invoke失败：{type(e).__name__}: {e}",file=sys.stderr,flush=True)
        return f"审查失败：{type(e).__name__}: {e}"

    return _render(out, time.time() - started, line_count)


@server.tool()
def review_workspace(repo_path: str, since: str = "HEAD") -> str:
    """
    做什么：在指定 git 仓库里跑 git diff，把改动交给审查器，返回按 P0–P3 分级的 Markdown 报告。

    什么时候用：
    - 用户说「审一下我这次的改动」但没给 diff，只说了项目 → 这个工具自己去取
    - 用户说「提交前帮我检查有没有 P0」→ 需要在 commit 之前拿工作区的改动
    - 用户指定了比较范围，比如「这个分支相对 main 的改动」「最近三次提交」
    - 你能确定仓库路径，但手上没有 diff 文本

    什么时候不要用：
    - 已经拿到 diff 文本 → 用 review_diff，别再跑一次 git，白多一次调用
    - 目标路径不是 git 仓库 → 会返回 git 的原话（比如 fatal: not a git repository），换对路径再试
    - 用户只是问「这段代码有什么问题」而不涉及改动 → 没有 diff，审不出东西
    - 用户要你修改代码 → 只读，不会改、不会暂存、不会提交
    - 改动超过 1500 行时不会审查，而是返回文件清单和建议 —— 这时要按提示缩小范围或分批，
      不要用同样的参数再调一次，结果不会变

    参数：
    - repo_path：git 仓库的绝对路径。必填，不会替你猜
      不确定时先问用户，或从宿主给出的工作区路径里取。路径错了会返回明确的失败原因。
    - since：比较基准。默认 "HEAD" = 工作区全部未提交改动（暂存+未暂存，不含未跟踪文件）；
      "HEAD~3" = 相对三次提交前的全部差异（含未提交部分）；
      只想看那几次提交本身，用范围写法 "HEAD~3..HEAD"。
    """
    #repo_path和since都是模型填的参数，不能直接拼进命令行
    #（1）先规范化成绝对路径并确认是目录：相对路径会按宿主的cwd解析，而那是用户主目录
    #（2）since以“-”开头会被git当成选项（如-p、-output），必须拒
    target=Path(repo_path).expanduser().resolve()
    if not target.is_dir():
        return f"repo_path不是一个目录：{target}"
    if not since or since.startswith("-") or any(c.isspace() for c in since):
        return(
            f"since参数不合法：{since!r}."
            "只接受修订号或范围，例如HEAD、HEAD~3、HEAD~3..HEAD、main。"
        )
        # 用git -C 而不是os.chdir：改工作目录是全局副作用，会影响同进程里其他逻辑。
        # timeout 必须有：大仓库或网络盘卡住时，stdio 是串行的，整个 server 都会被拖死。
        # --no-color / --no-ext-diff：用户配了 color.ui=always 或 diff.external 时，
        #  输出会带 ANSI 转义符或变成别的格式 → unidiff 解析失败 → 又一条「未发现问题」
    try:
        r = subprocess.run(
            ["git", "-C", str(target), "diff", "--no-color", "--no-ext-diff", since],
            capture_output=True,  # 把子进程的输出收进返回值，不往父进程的控制台打
            text=True,  # 返回str而不是bytes
            encoding="utf-8",
            errors="replace",  # 解码失败时换成占位符继续，别让整次调用失败
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return f"git diff 超时（{GIT_TIMEOUT}s）：{target}"

        # returncode是进程结束时的退出码，0表示成功
    if r.returncode != 0:
        return f"git diff 执行失败（目标：{target}）：{r.stderr.strip()}"

    if not r.stdout.strip():
        # git diff 不包含未跟踪文件：用户新建了文件但没 git add 时，这里就是空的。
        # 不解释清楚，模型会当成「没问题」，用户也不知道为什么。
        try:
            others = subprocess.run(
                ["git", "-C", str(target), "ls-files", "--others", "--exclude-standard"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT,
            )
            names = [n for n in (others.stdout or "").strip().splitlines() if n]
        except Exception as e:
            print(f"[review]ls-files失败: {e}",file=sys.stderr,flush=True)
            names=[]
        if names:
            shown = "、".join(names[:5]) + ("…" if len(names) > 5 else "")
            return (
                f"{target} 相对 {since} 没有任何已跟踪文件的改动。\n"
                f"注意：还有 {len(names)} 个未跟踪文件不在 git diff 范围内，不会被审查：{shown}\n"
                f"如需审查，先用 git add 加入暂存区。"
            )
        return f"{target} 相对 {since} 没有任何改动，无需审查。"

        # 把「实际审的绝对路径」写进结果头部：路径传错时模型能一眼看出来，
        # 而不是默默审了另一个仓库还不报错
    return f"审查目标：{target}（since={since}）\n\n" + review_diff(r.stdout)

if __name__ == "__main__":
    server.run()
