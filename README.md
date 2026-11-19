# code-review-agents

基于 LangGraph 的多智能体代码审查工具。提交前跑一次，拿到一份分级、去重、可定位到行的评审意见。

**四种入口，共用同一张图**：MCP Server（任何 Agent 宿主可调）、Skill（调用策略）、CLI、git pre-commit hook。

## 为什么做

一个人写代码时没人 review，那些"改完才发现"的坑只能靠调试找回来。放到团队里更明显：评审要排队，标准还随人变——A 觉得这里没问题，B 觉得有问题。

但这个场景里多数问题是机械的：字符串拼 SQL、循环里查库、异常被吞掉、关键路径没日志。这些不需要人来判断。

所以拆成三个审查员并行工作，各管一类，最后归并成一份报告。

## 架构

```
                        ┌──→ security     ──┐
git diff ──→ parse ─────┼──→ performance  ──┼──→ merge ──→ review_gate ──→ report
                        └──→ style        ──┘
```

| 节点            | 职责                                          |
| ------------- | ------------------------------------------- |
| `parse`       | 把 diff 解析成结构化变更（文件 / 行号 / 新增或删除）            |
| `security`    | 只审安全类：注入、越权、敏感信息、硬编码密钥、路径穿越                 |
| `performance` | 只审性能类：N+1、循环内 HTTP、缺索引、无分页                  |
| `style`       | 只审规范类：命名、异常处理、日志、可读性                        |
| `merge`       | 按「文件 × 行号 × 类别」归并，同位置只留最严重一条；多类别全部展示出来，防止丢弃 |
| `review_gate` | P1 级以上暂停等待人工确认；评估模式通过 `auto_approve` 绕过     |
| `report`      | 渲染 Markdown，按 P0 → P3 分级                    |

三个审查员在同一个 superstep 内并行执行，`findings` 通过 `Annotated[list[Finding], operator.add]` 合并。

`review_gate` 用 `interrupt` 暂停图执行，`SqliteSaver` 把状态落盘，进程重启后能从断点恢复。

> **所有入口共用这张图。** MCP Server、CLI、git hook、Python 直接调用，都只是它的外壳——加 MCP 的时候，图里一行没改。

## 评估结果

自建 25 个样本：17 个埋点（覆盖注入、硬编码、路径穿越、N+1、异常吞、缺事务等），8 个对照测误报。判定规则为「行号差 ≤1 且 message 含关键词」。

| 版本                | 召回率              | 对照误报    |
| ----------------- | ---------------- | ------- |
| 单 Agent（一个提示词审所有） | 82.4%（14/17）     | 2       |
| **三路并行 + 归并**     | **94.1%（16/17）** | **1~2** |

拆成三路后召回提升 11.7 个百分点，主要来自异常处理与命名类问题——单 Agent 时被安全和性能问题淹没了。

漏报的那 1 个需要业务上下文（`tax_rate` 传 13 还是 0.13），代码本身看不出来。

> 对照组的误报经人工核查多为真实缺陷（`affected == 0` 时没记录失败日志、`deleted = 1` 用了魔法数字），说明我的「正确代码」标准还不够严。完整实验记录见 [`evals/RESULTS.md`](evals/RESULTS.md)。

## 项目结构

```
mcp_server.py             # MCP Server：2 个工具，跨宿主可用
main.py                   # CLI 入口（argparse）
hooks/
└── pre-commit            # git hook 模板（复制到目标项目的 .git/hooks 启用）

skills/
└── code-review/
    └── SKILL.md          # Skill：调用策略与呈现规范（不提供能力，能力在 MCP）

app/
├── state.py              # ReviewState：流水线共享状态（含 reducer）
├── graph.py              # 图装配：三路并行 + 汇合 + 人工闸门
├── llm.py                # 模型客户端 + 结构化输出包装
├── nodes/
│   ├── parse.py          # diff → 结构化
│   ├── base.py           # 审查员工厂（三个节点共用骨架）
│   ├── security.py       # ↓ 四行一个，只声明 category 和提示词
│   ├── performance.py
│   ├── style.py
│   ├── merge.py          # 归并去重 + 冲突检测（纯函数，不调模型）
│   ├── review_gate.py    # 人工确认闸门（interrupt）
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

| 选择                                         | 理由                                                                                                          |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| **LangGraph**                              | 需要并行子图 + 状态合并 + 中断恢复。手写循环表达不了"三路同时跑、全部完成再继续"                                                                |
| **`operator.add` reducer**                 | 三个并行分支写同一字段，不声明合并规则会直接报 `InvalidUpdateError`                                                                |
| **merge 独立成节点、纯函数**                        | 归并去重不调模型，可以完全脱网单测，结果确定                                                                                      |
| **合并结果放 `merged` 而非 `findings`**           | `findings` 的 reducer 只能追加不能替换，merge 返回什么都会被拼到后面                                                             |
| **checkpointer 做成可选参数**                    | 装上 checkpointer 后所有 `invoke` 必须带 `thread_id`，会打挂批量评估。所以默认 `build_graph()` 不装，人工确认场景才 `with_checkpoint=True` |
| **`auto_approve` 标志**                      | 评估要在无人值守下跑完，遇到 P1 不能停下来等人。用标志位区分"自动模式"和"人工模式"                                                               |
| **提示词外置到 `prompts/*.md`**                  | 迭代频繁，放 md 里 `git diff` 能一眼看清改了哪句                                                                            |
| **DeepSeek + `method="function_calling"`** | DeepSeek 不支持 `response_format` 的 `json_schema` 类型，默认配置会返回 400                                               |
| **强制覆盖 `category`**                        | 不信任模型返回的分类，用代码覆盖，否则归并时全乱                                                                                    |
| **MCP 只暴露 2 个工具**                         | 工具数量会放大模型选错的概率。两个的边界是「数据在谁手上」：已有 diff 用 `review_diff`，只有路径用 `review_workspace`                                  |
| **MCP 用 stdio 传输**                        | 本地工具，不需要端口、不需要鉴权。代价是单连接串行，一次审查 5–10 秒期间宿主只能等                                                               |
| **超长 diff 拒绝而非截断**                        | 行级截断会切在 hunk 中间，unidiff 解析失败 → 输出「未发现问题」。宁可拒绝并给出分批建议                                                       |
| **`errors` 字段用 `add` 合并**                  | 三路并行会同时写这个字段，和 `findings` 一样必须声明 reducer                                                                    |
| **Skill 与 MCP 分层**                        | MCP 提供能力（能做什么），Skill 提供策略（什么时候用、结果怎么说）。工具管不到的行为才写进 Skill                                                   |

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

---

## 用法一：MCP Server（推荐）

`mcp_server.py` 把审查能力暴露成 2 个 MCP 工具，任何支持 MCP 的宿主（Cursor / Claude Desktop / Claude Code / WorkBuddy）都能直接调，不需要改一行代码。

### 配置

以 Cursor 为例，写进 `~/.cursor/mcp.json`（WorkBuddy 是 `~/.workbuddy/mcp.json`）：

```json
{
  "mcpServers": {
    "code-review": {
      "command": "/absolute/path/to/code-review-agents/.venv/Scripts/python.exe",
      "args": ["/absolute/path/to/code-review-agents/mcp_server.py"]
    }
  }
}
```

三个必须注意的点：

1. **绝对路径**，并且用正斜杠（反斜杠在 JSON 里要写成两个 `\\`）
2. `command` 必须指向 **venv 里的 python**，写 `python` 会用到系统解释器，找不到依赖
3. WorkBuddy 需要在「连接器管理 → 自定义连接器」里点一次 **Trust**，不点不会加载

### 两个工具

| 工具 | 参数 | 什么时候用 |
|---|---|---|
| `review_diff` | `diff`：diff 文本 | 手上已经有 diff |
| `review_workspace` | `repo_path`：仓库绝对路径<br>`since`：比较基准 | 只有路径，让 server 自己跑 `git diff` |

**为什么只有两个**：工具数量会放大模型选错的概率。取数据和数据处理也刻意分开了——取数据 Agent 有终端能做，审查才交给 server。

### 输出有三态

```
审查完成：3 条意见（P0×1，P2×2）        ← 审完了，有问题
审查完成：未发现问题                      ← 审完了，干净
审查完成（不完整）：本次未取得有效结论     ← 没审成，别当结论
```

第三态是必须的：解析失败、审查员调用失败、diff 超长被拒，都走这里。**少了它，故障会伪装成「代码很干净」。**

### 两个防漏机制

**超长 diff 不截断**：超过 1500 行直接返回文件清单和建议分批方式，而不是砍掉后半部分。

**未跟踪文件每次提示**：`git diff` 看不到没 `git add` 的文件，但它们往往是刚写的新代码。所以每次审查都会在结果头部提示：

```
审查目标：D:\path\to\repo（since=HEAD）
还有 2 个未跟踪文件不在 git diff 范围内（未被审查）：_preview.md、skills/...。
如需审查，先 git add -N 再跑一次。
```

### 端到端验收

四类场景，都在真实宿主里跑过：

| 场景 | 结果 |
|---|---|
| 干净仓库 | 转述「没有任何改动」，**未编造报告** |
| 真实改动 | 12s 出报告，P0 定位到具体行 |
| 直接贴 diff | 选 `review_diff`，未重复跑 git |
| 路径不存在 | 转述 git 原话，并给出修正建议 |

## 用法二：Skill（教 Agent 怎么用）

`skills/code-review/SKILL.md` 是一份**按需加载的操作手册**：宿主平时只看到它的一行描述，命中触发词才加载全文。

它不提供能力——**能力在 MCP 里**。它管的是工具管不到的那部分：

- 什么时候不该调（用户只是问概念时，直接回答）
- 结果怎么呈现（先给计数，不要原样贴整份报告）
- 工具返回「不完整」时怎么说（明确讲没结论，不能说「没问题」）
- 拿到报告后不要「顺手」把问题改掉

### 安装

```bash
# WorkBuddy
cp -r skills/code-review ~/.workbuddy/skills/

# Claude Code
cp -r skills/code-review ~/.claude/skills/
```

装完重启宿主，说一句「审一下我这次的改动」就能触发。

> Skill 是宿主特定格式，不是协议。**装之前先确认宿主支持 `SKILL.md`**——这也是它和 MCP 最大的区别。

## 用法三：人工确认（P1 暂停等你决策）

```python
from pathlib import Path
from langgraph.types import Command
from app.graph import build_graph

g = build_graph(with_checkpoint=True)
config = {"configurable": {"thread_id": "review-001"}}
diff = Path("your.diff").read_text(encoding="utf-8")

# 第一次：跑到 review_gate 会挂起
out = g.invoke({"patch": diff, "auto_approve": False}, config)
print(out["__interrupt__"])        # 待确认的问题清单

# 人做出决定后，用同一个 thread_id 恢复
out = g.invoke(Command(resume="这两条先不改，记录一下"), config)
print(out["report"])               # 末尾会多一段「人工确认」
```

## 用法四：其他入口

审查逻辑全在 `app/graph.py`，下面三种只是同一张图的不同外壳：

```python
# Python 里直接调
from app.graph import graph
out = graph.invoke({"patch": diff, "auto_approve": True}, {"recursion_limit": 25})
print(out["report"])
```

```bash
# CLI：有 P0 时退出码为 1
python main.py review                    # 审查工作区改动（对比 HEAD）
python main.py review --diff your.diff   # 审查指定 diff 文件
python main.py review --since HEAD~3     # 对比最近 3 次提交的累计改动
python main.py review --quiet            # 只输出一行结论
```

退出码：`0` = 无 P0，`1` = 存在 P0，`2` = 运行错误。

```bash
# git hook：hooks/pre-commit 是可直接复制的模板
cp hooks/pre-commit /path/to/your-project/.git/hooks/pre-commit
chmod +x /path/to/your-project/.git/hooks/pre-commit
```

装上后每次 `git commit` 自动审**暂存区**内容，有 P0 阻止提交；`--no-verify` 可跳过。
每次多花 5–10 秒——**什么时候该拦、什么时候不该拦，比怎么配 hook 更重要。**

## 已知局限

### 审查能力

1. **只看 diff，看不到跨文件影响。** 改了一个函数签名，调用方不在 diff 里，它就发现不了。
2. **索引类判断需要 schema。** `LIKE '%x%'` 是否走索引取决于该字段有没有索引，模型看不到表结构。
3. **语义类问题需要业务约定。** `tax_rate` 传 13 还是 0.13，代码里看不出调用方怎么传。
4. **提示词边界是「优先不报」而非「绝对不报」。** 早期版本写成绝对禁止，导致跨类别的问题谁都不管，召回反而没有提升。
5. **同批样本多次运行结果会有波动。** `temperature=0` 不等于完全确定，单次评估反映的是量级而非精确值。对照组的误报数在 1~2 之间浮动。

### MCP 层

6. **拿不到宿主的工作目录。** 实测宿主启动子进程时 cwd 是用户主目录，不是项目目录。所以 `repo_path` 必须显式传，**不提供默认值**——默认值会让「传错仓库」变成静默失败。
7. **stdio 是单连接串行。** 一次审查 5–10 秒，这期间宿主只能等。长任务的出口是 `Context` 上报进度或异步轮询，但异步要引入状态，和多副本冲突。
8. **未跟踪文件不参与审查。** 工具会在结果头部提示，但不会自动纳入——要不要 `git add` 由用户决定。
9. **单文件超长无法自动分批。** 切开会破坏 hunk 头导致行号全错，只能请用户缩小范围。多文件超限可以给清单让它自己组合，单文件不行。

### Skill

10. **依赖宿主支持的格式。** `SKILL.md` 是 WorkBuddy / Claude Code 的约定，不是协议；换成不支持的宿主就没法用。
11. **描述决定加载，写不好等于不存在。** 触发词没覆盖到用户的说法，Skill 不会被加载——这是它最常见的失效方式。

## 后续计划

- [x] MCP Server 封装（2 个工具，端到端验收 4/4）
- [x] Skill 封装（调用策略与呈现规范）
- [ ] 按文件分片审查：超过 1500 行时自动分批 + 跨片归并，替代当前的「拒绝」
- [ ] 补充 schema 上下文（表结构、索引），解决索引类漏报
- [ ] 样本扩到 100 个，按代码类型分层抽样
- [ ] 接入 CI（GitHub Actions），在 PR 上自动评论审查结果
