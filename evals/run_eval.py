"""
跑评估：对每个样本执行完整流程，算召回率和误报数。

用法（必须在项目根目录执行）：
    .venv/Scripts/python.exe -m evals.run_eval

为什么用 -m 而不是直接跑脚本：
    直接跑 evals/run_eval.py 时，Python 会把 evals/ 当成工作目录，
    from app.graph 就找不到 app 了。-m 从项目根启动，路径才对。
"""
import json
from pathlib import Path

from app.graph import graph

BASE = Path(__file__).parent
SAMPLES = BASE / "samples"


def make_diff(path: str, content: str) -> str:
    """把完整文件包装成「新增文件」的 diff。

    所有行都是 '+'，正好模拟「你新写了一个文件」的场景。
    这样就不用给每个样本手写 diff，避免 @@ 数字算错。
    """
    #把文件拆成行列表（去掉换行符）
    lines = content.splitlines()
    #如果没有内容返回空
    if not lines:
        return ""
    #每一行都是+，取列表中的每一行
    body = "\n".join("+" + ln for ln in lines)
    #返回diff格式的文件
    return (
        f"diff --git a/{path} b/{path}\n"
        f"new file mode 100644\n"
        f"--- /dev/null\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}\n"
    )


def is_hit(finding, expected: dict) -> bool:
    """判断模型报的这条，是否命中我们标注的坑。

    两个条件同时满足才算命中：
      1. 行号差不超过 1（模型可能报在相邻行）
      2. message 里出现 keyword（措辞不可能完全一致，所以只要求包含）
    """
    return (
        #abs的用法是去掉正负号，只留大小
        abs(finding.start_line - expected["line"]) <= 1
        and expected["keyword"] in finding.message
    )


def main():
    #先读取标准答案，read_text拿到字符串->json.loads转成dict
    labels = json.loads((BASE / "labels.json").read_text(encoding="utf-8"))

    hit = 0             #报对了几个坑
    total = 0           #一共应该报几个坑
    false_positive = 0  #干净样本里误报了几条
    misses = []         #漏报详情
    fps = []            #误报详情
    #主循环
    for name, expected_list in labels.items():
        sample = SAMPLES / f"{name}.py"
        if not sample.exists():
            print(f"[跳过] 缺少 {name}.py")
            continue

        content = sample.read_text(encoding="utf-8")
        out = graph.invoke({"patch": make_diff(f"{name}.py", content)})
        findings = out.get("findings", [])

        if expected_list:
            # 有坑的样本：算召回
            for exp in expected_list:
                total += 1
                if any(is_hit(f, exp) for f in findings):
                    hit += 1
                else:
                    misses.append((name, exp, findings))
        else:
            # 干净样本：报出来的全是误报
            if findings:
                false_positive += len(findings)
                fps.append((name, findings))

    rate = hit / total * 100 if total else 0
    print("=" * 54)
    print(f"应报 {total} 个 | 报对 {hit} 个 | 召回率 {rate:.1f}%")
    print(f"干净样本误报 {false_positive} 个")
    print("=" * 54)

    for name, exp, findings in misses:
        print(f"\n[漏报] {name} 期望 L{exp['line']} 「{exp['keyword']}」，实际报了 {len(findings)} 条：")
        for f in findings:
            print(f"        {f.severity} L{f.start_line} {f.message[:46]}")

    for name, findings in fps:
        print(f"\n[误报] {name} 本该干净，报了 {len(findings)} 条：")
        for f in findings:
            print(f"        {f.severity} L{f.start_line} {f.message[:46]}")


if __name__ == "__main__":
    main()
