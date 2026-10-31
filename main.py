"""
code-review-agents 命令行入口

用法：
    python main.py review                     # 审查工作区改动（对比 HEAD）
    python main.py review --diff x.diff       # 审查指定的 diff 文件
    python main.py review --since HEAD~3      # 对比最近 3 次提交的累计改动
    python main.py review --quiet             # 只输出结论，不打印完整报告

退出码：
    0 = 无 P0 问题
    1 = 存在 P0 问题（pre-commit hook 靠这个阻止提交）
    2 = 运行错误（git 失败、文件不存在等）
"""
import argparse
import subprocess
import sys
from pathlib import Path

from app.graph import build_graph


def read_git_diff(since: str) -> str:
    """调 git diff 拿工作区改动。

    失败时直接 exit 2，不要静默返回空字符串——
    否则你会以为"没有改动"，实际是 git 报错了。
    """
    r = subprocess.run(
        ["git", "diff", since],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if r.returncode != 0:
        print(f"[错误] git diff 失败：{r.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return r.stdout


def cmd_review(args) -> int:
    # ---------- 1. 拿 diff ----------
    if args.diff:
        p = Path(args.diff)
        if not p.exists():
            print(f"[错误] 找不到文件：{p}", file=sys.stderr)
            return 2
        diff = p.read_text(encoding="utf-8")
    else:
        diff = read_git_diff(args.since)

    if not diff.strip():
        print("没有改动可审查。")
        return 0

    # ---------- 2. 跑流水线 ----------
    # 注意：CLI 用 build_graph()（无 checkpointer），
    # 所以 auto_approve 必须为 True —— 否则 review_gate 调 interrupt 会报错。
    # 人工确认场景请走 README 里的「用法二」。
    g = build_graph()
    out = g.invoke(
        {"patch": diff, "auto_approve": True},
        {"recursion_limit": 25},
    )

    merged = out.get("merged") or []

    # ---------- 3. 输出 ----------
    if args.quiet:
        # 只打一行结论
        counts = {}
        for f in merged:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        summary = "，".join(f"{k} × {v}" for k, v in sorted(counts.items())) or "无意见"
        print(summary)
    else:
        print(out["report"])

    # ---------- 4. 退出码：有 P0 就算失败 ----------
    has_p0 = any(f.severity == "P0" for f in merged)
    if has_p0:
        print("[结果] 存在 P0 级问题，建议修改后再提交。", file=sys.stderr)
        return 1

    print(f"[结果] 共 {len(merged)} 条意见，无 P0。", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="code-review",
        description="多智能体代码审查工具",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("review", help="审查代码改动")
    p.add_argument("--diff", help="从文件读 diff（默认用 git diff）")
    p.add_argument("--since", default="HEAD", help="git diff 的基准，默认 HEAD")
    p.add_argument("--quiet", action="store_true", help="只输出结论，不打印完整报告")
    p.set_defaults(func=cmd_review)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
