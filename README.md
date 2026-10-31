# code-review-agents

基于 LangGraph 的多智能体代码审查工具。提交前跑一次，拿到一份分级、去重、可定位到行的评审意见。

## 为什么做

一个人写代码时没人 review，那些"改完才发现"的坑只能靠调试找回来。放到团队里更明显：评审要排队，标准还随人变——A 觉得这里没问题，B 觉得有问题。

但这个场景里多数问题是机械的：字符串拼 SQL、循环里查库、异常被吞掉、关键路径没日志。这些不需要人来判断。

所以拆成三个审查员并行工作，各管一类，最后归并成一份报告。

## 架构

```
                        ┌──→ security     ──┐
git diff ──→ parse ─────┼──→ performance  ──┼──→ merge ──→ report
                        └──→ style        ──┘
```

| 节点 | 职责 |
|---|---|
| `parse` | 把 diff 解析成结构化变更（文件 / 行号 / 新增或删除） |
| `security` | 只审安全类：注入、越权、敏感信息、硬编码密钥、路径穿越 |
| `performance` | 只审性能类：N+1、循环内 HTTP、缺索引、无分页 |
| `style` | 只审规范类：命名、异常处理、日志、可读性 |
| `merge` | 按「文件 × 行号」归并，同位置只留最严重一条；多类别记冲突提示 |
| `report` | 渲染 Markdown，按 P0 → P3 分级 |

三个审查员在同一个 superstep 内并行执行，`findings` 通过 `Annotated[list[Finding], operator.add]` 合并。

## 评估结果

自建 25 个样本：17 个埋点（覆盖注入、硬编码、路径穿越、N+1、异常吞、缺事务等），8 个对照测误报。判定规则为「行号差 ≤1 且 message 含关键词」。

| 版本 | 召回率 | 对照误报 |
|---|---|---|
| 单 Agent（一个提示词审所有） | 82.4%（14/17） | 2 |
| **三路并行 + 归并** | **94.1%（16/17）** | **1** |

拆成三路后召回提升 11.7 个百分点，主要来自异常处理与命名类问题——单 Agent 时被安全和性能问题淹没了。

漏报的那 1 个需要业务上下文（`tax_rate` 传 13 还是 0.13），代码本身看不出来。

> 对照组那 1 条误报经人工核查是真实缺陷（`affected == 0` 时没记录失败日志），说明我的「正确代码」标准还不够严。完整实验记录见 [`evals/RESULTS.md`](evals/RESULTS.md)。

## 项目结构

```
app/
├── state.py              # ReviewState：流水线共享状态（含 reducer）
├── graph.py              # 图装配：三路并行 + 汇合
├── llm.py                # 模型客户端 + 结构化输出包装
├── nodes/
│   ├── parse.py          # diff → 结构化
│   ├── base.py           # 审查员工厂（三个节点共用骨架）
│   ├── security.py       # ↓ 四行一个，只声明 category 和提示词
│   ├── performance.py
│   ├── style.py
│   ├── merge.py          # 归并去重 + 冲突检测（纯函数，不调模型）
│   └── report.py         # Markdown 渲染
└── prompts/
    ├── security.md       # 三个提示词边界互斥，各含「只报什么 / 不要报 / 边界判断」
    ├── performance.md
    └── style.md

evals/
├── samples/              # 25 个样本
├── labels.json           # 标注：应报行号、类别、级别、关键词
├── run_eval.py           # 评分脚本
└── RESULTS.md            # 实验记录
```

## 技术选型

| 选择 | 理由 |
|---|---|
| **LangGraph** | 需要并行子图 + 状态合并。手写循环表达不了"三路同时跑、全部完成再继续"，也做不了后续的条件边和中断恢复 |
| **`operator.add` reducer** | 三个并行分支写同一字段，不声明合并规则会直接报 `InvalidUpdateError` |
| **merge 独立成节点、纯函数** | 归并去重不调模型，可以完全脱网单测，结果确定 |
| **合并结果放 `merged` 而非 `findings`** | `findings` 的 reducer 只能追加不能替换，merge 返回什么都会被拼到后面 |
| **提示词外置到 `prompts/*.md`** | 迭代频繁，放 md 里 `git diff` 能一眼看清改了哪句 |
| **DeepSeek + `method="function_calling"`** | DeepSeek 不支持 `response_format` 的 `json_schema` 类型，默认配置会返回 400 |
| **强制覆盖 `category`** | 不信任模型返回的分类，用代码覆盖，否则归并时全乱 |

## 快速开始

```bash
git clone https://github.com/mayiran23/code-review-agents.git
cd code-review-agents

python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS / Linux

pip install -r requirements.txt

# 配置 API Key（DeepSeek）
echo "DEEPSEEK_API_KEY=sk-你的key" > .env

# 跑评估集（约 1 分钟）
python -m evals.run_eval
```

预期输出：

```
======================================================
应报 17 个 | 报对 16 个 | 召回率 94.1%
干净样本误报 1 个
======================================================
```

**对任意 git 仓库跑一次审查：**

```python
from pathlib import Path
from app.graph import graph

diff = Path("your.diff").read_text(encoding="utf-8")
out = graph.invoke({"patch": diff}, {"recursion_limit": 25})
print(out["report"])
```

其中 `your.diff` 由 `git diff HEAD > your.diff` 生成。

> CLI 入口（`python main.py review`）尚未实现，目前在计划中。

## 已知局限

1. **只看 diff，看不到跨文件影响。** 改了一个函数签名，调用方不在 diff 里，它就发现不了。
2. **索引类判断需要 schema。** `LIKE '%x%'` 是否走索引取决于该字段有没有索引，模型看不到表结构。
3. **语义类问题需要业务约定。** `tax_rate` 传 13 还是 0.13，代码里看不出调用方怎么传。
4. **提示词边界是「优先不报」而非「绝对不报」。** 早期版本写成绝对禁止，导致跨类别的问题谁都不管，召回反而没有提升。
5. **同批样本多次运行结果会有波动。** `temperature=0` 不等于完全确定，单次评估反映的是量级而非精确值。

## 后续计划

- [ ] `interrupt` + `checkpointer`：P1 级问题暂停等人工确认，支持进程重启后从断点恢复
- [ ] 补充 schema 上下文（表结构、索引），解决索引类漏报
- [ ] CLI 入口与 pre-commit hook 集成
- [ ] 样本扩到 100 个，按代码类型分层抽样
