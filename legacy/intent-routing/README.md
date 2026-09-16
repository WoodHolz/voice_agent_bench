# 催授权 IntentRouter demo / bench

新增节点范围实验：[结论](NODE_SCOPED_FINDINGS.md) · [复现与接口](node_scoped/README.md) · [完整对照指标](reports/node_scoped/RESULTS.md)。首轮实验及其结果保留。

独立 PoC，评估产品 `7-xx` 意图分类。所有新代码位于本目录；产品文档与用户克隆的上游源码不修改。没有 WorkflowEngine、状态跳转、补发动作、回拨排期、ASR 或 TTS 集成。

## 快速运行

在本目录执行（Python 3.11）：

```bash
cd /home/WoodHolz/Desktop/voice-agent-docs/experiments/intent-routing

# 当前环境已安装。新环境可按以下顺序建立：
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python ../../semantic-router -r ../../RealtimeIntent/requirements.txt httpx pyyaml pytest
uv pip install --python .venv/bin/python torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv/bin/python sentence-transformers

# 第一次需要联网下载模型；缓存位于本目录 .cache/huggingface
.venv/bin/python models.py --download

# 正常运行配置 local_files_only=true，无需联网或 API key
.venv/bin/python demo.py --router realtime_intent --text '我这边一直人脸识别失败'
.venv/bin/python demo.py --router semantic_router --text '我刚才填错了能不能改'
.venv/bin/python demo.py --router semantic_router --text '好啊' --previous-assistant '今天下班前完成可以吗？'

.venv/bin/python -m benchmark.run --routers both --modes both --repeat 1
.venv/bin/python -m benchmark.stream --routers both
.venv/bin/python -m pytest -q
```

`config.yaml` 固定本次模型、模型 revision、阈值、top-k、聚合方式和 CPU 线程数。`requirements-observed.txt` 记录当前安装环境，不是跨平台锁文件；其中 torch 的 CPU wheel 需上面的专用索引。上游源码位置/提交见配置和 [UPSTREAM_NOTES.md](UPSTREAM_NOTES.md)。新机器需要在文档根目录克隆这两个仓库，并切换到配置中的提交。

## 文件

- `intent_data/intents.yaml`：唯一共享意图配置；59 个 ID、产品描述、例句、来源行号、分支和话术引用。
- `intent_data/eval.yaml`：统一评测集。
- `intent_data/build.py`：从产品意图 Markdown 原文导出元数据，合并 `curated.tsv` 的人工改写。
- `realtime_intent/router.py`：Demo A，直接调用上游检索/重排判定方法。
- `semantic_demo/router.py`：Demo B，原生 semantic-router 路由。目录避免命名为 `semantic_router`，以免遮蔽第三方包。
- `models.py`：共享模型 I/O；不含意图规则，不缓存查询结果。
- `benchmark/run.py`：评测、逐条 JSON 和 Markdown 报告。
- `benchmark/stream.py`：逐步 ASR 假设及修订模拟。
- `reports/`：真实运行产物和架构判断。

## Python 接口

```python
from common import load_config, load_intents
from models import LocalModels
from realtime_intent import Router  # 或 from semantic_demo import Router

config = load_config()
models = LocalModels(config['models'], reranker=True)  # Demo B 可设 False
router = Router(load_intents(), models, config['realtime_intent'])
try:
    result = router.detect(text='我这边一直人脸识别失败', context=[])
    print(result.intent_id, result.score, result.latency_ms)
finally:
    router.close()
```

Demo B 初始化使用 `config['semantic_router']`。`context` 为**不含当前发言**的先前 `[{role: 'assistant'/'user', content: '...'}]`，不是流程状态或候选标签。若用上下文实验，初始化时指定 `with_context=True`，使索引例句也带对应的产品上一轮提问。报告的 `text` 与 `context` 是两种独立索引配置。

`Detection` 返回 `intent_id / score / latency_ms / score_kind / reason / details`。拒识为 `intent_id=None, score=None`；模型故障抛异常，由 benchmark 独立记录错误，不能算作正确拒识。不会返回/执行 `a4-1` 等分支。时间、邮箱等 slot extraction 暂未实现。

Demo A 通过上游模块的模型 I/O 扩展接入本地模型，属于单进程串行 PoC，同一进程只允许一个活跃 Demo A 实例；用 `close()` 释放并恢复绑定。它绕过上游 HTTP、工作队列和摘要 LLM，保留 `IntentService.process`、Qdrant 检索/分组和 `_process_rerank_or_direct` 的实际判定逻辑。它不是对完整 RealtimeIntent 服务吞吐能力的测试。

## 数据与语义边界

数据来自四份产品原稿对应的 Markdown：产品方案、主流程、意图、话术。意图定义和分支对应以表 7 原文导出，上一轮提问参考主流程/话术。没有读取“拆分”文件或 `cursor`；流程图不是本次标签源。

共有 **59 个意图、58 个文本意图、129 条索引例句、220 条评测样本**：

- 116 条 heldout：每个文本意图两条人工改写（较完整表达和口语短句）；不与索引例句重叠。
- 71 条 source_overlap：产品原话，同时存在于索引中，只作接线/记忆诊断，不计泛化准确率。
- 33 条 challenge/challenge_overlap：歧义、相似意图、同一句不同上下文、ASR 瑕疵、不足以判定的片段、噪声、空输入和 OOD。部分歧义原话在索引中，会显式标注 overlap。

`original_examples` 与 `derived_examples` 分开；导出保留来源文件、表号、行号和意图号。`curated.tsv` 每行依次是 ID、增加的索引例句、留出改写、留出短句。它只用于构建数据，路由器仅加载 `intents.yaml`，不能读取评测文件。运行 `python intent_data/build.py` 可重建，测试验证结果确定且留出集无规范化文本重叠。

`7-1` 是持续静默事件，需 VAD/计时状态才能成立；本 PoC 保留定义但不把其括号中的说明或助手提示作为候选人训练文本。`detect('')` 返回 empty_input，不伪造 7-1，也不识别为放弃 offer。

产品原定义有层级重叠：

| 易混意图 | 需要的区分信息 |
|---|---|
| 7-8 / 7-37 / 7-46 | 开场直接报进展 / 回答送达确认 / 后台未完成后坚称完成 |
| 7-6 / 7-15 / 7-24 / 7-48 / 7-57 | “好啊”是在同意哪一个问题 |
| 7-7 / 7-20 | 开场“不方便”大类与“在忙”细类 |
| 7-43 / 7-53 | 未填归因“操作困难”大类与明确技术故障细类 |
| 7-16 / 7-33 | 核实来电真假与确认背调必要性 |
| 7-17 / 7-28 | 仍不信任且拒绝与一般明确拒绝 |
| 7-29 / 7-58 | 在职顾虑与自主寻访场景的暴露顾虑 |
| 7-38 / 7-41 | 未收到与查找后确认没有 |

不为提高准确率而合并或重命名这些标签。`expected` 为单元素表示单标签目标，多个元素表示歧义可接受集合，空列表表示应拒识。多标签集合命中率不是准确率；缺少上下文的 context_pair 结果只作诊断。样本解释不能替代后续产品标注复核。

## 分数和拒识

| Demo | result.score | 拒识 |
|---|---|---|
| RealtimeIntent / 本地 CPU | 选中意图描述与对话的 cross-encoder logit 经 sigmoid；相关性分数，非校准概率 | 保留上游 MIN_SCORE_THRESHOLD=0.01、__no_intent__ 阈值 0.55、近似并列差 0.02、检索最低分 0.4；并非“低于 0.55 就拒识” |
| semantic-router | 本次配置为全局 top-5 例句中、该 route 被召回例句的平均余弦相似度 | 上游聚合分数不达 route threshold=0.65 时不匹配 |

RealtimeIntent 上游 HTTP debug 的 `payload.score` 是 **Qdrant 检索分数**。适配器观测重排输出，单独放入 `result.score`；检索分数留在 `details.retrieval_score`，候选重排分数留在 `details.rerank_candidates`。两个库的分数不能当作相同量纲比较。阈值在评测前固定，未根据这批 heldout 结果调参，也没有新增逐意图关键词规则。

本地 reranker 是通用多语言文本对模型，适配器沿用上游描述映射与排序辅助函数，以 `(history + LatestUser, description)` 作为输入，不向该非 Qwen 模型添加 ChatML 专用 token。保留检索→重排→拒识路径，但这仍是**更换模型后的 CPU 配置**，需要与上游 Qwen 部署另行实测比较。

## 如何解读 benchmark

`reports/baseline.json` 和 `.md` 包含 heldout accuracy、macro/per-intent accuracy、混淆对/文本、拒识、OOD 误接受、后端错误、p50/p95/p99、模型加载和索引初始化耗时。JSON 保留每条结果、分数语义、配置、来源哈希、包版本和模型缓存 revision。

计时从 `detect` 入口到返回，包括预处理、embedding、检索及 Demo A 重排；不含模型加载、索引构建、ASR/TTS、网络和服务队列。索引/模型加载独立计时。每个 router 预热两次后，使用同一种子打乱相同的评测顺序，串行执行；两种 mode 中轮换 router 次序。进程和模型常驻，没有分类/embedding 查询缓存。空输入单列，不参与模型延迟分位数。错误不视为拒识，错误数单列。

`--repeat 3` 可以增加计时样本；重复例句不能扩大独立准确率样本量。默认每个意图仅两个独立留出样本、OOD 仅八条，因此结果属于小样本诊断，不能作为线上准确率或 SLA。当前量化比较只适用于记录的模型/硬件配置。

上下文模式把上一轮对话放进查询与索引，不做状态候选屏蔽，也不让预期答案参与检索。RealtimeIntent 仍保留上游自有的查询包装，因此两者并非逐字相同模型输入。该差异属于本次接入方式的一部分。

ASR 模拟记录每个 partial 的标签、分数、延迟、相邻预测是否变化、最终是否正确、何时开始持续正确及提前错误接受数。包含一次 ASR 文本修订；没有提交预测、稳定窗口或去抖机制。仅凭“变化次数少”不能判断更好，必须同时看是否一直拒识/一直预测错误。

## 当前结论

实测结果与限制见 [reports/FINDINGS.md](reports/FINDINGS.md)。目前不把任何一个 demo 接入生产，也不改产品流程。若需要继续调阈值或扩充例句，应建立独立 dev 集，保留当前 heldout 作为后续检验集，防止把测试结果调成训练结果。

补充压力诊断（与主评测分开保存）：

```bash
.venv/bin/python -m benchmark.run --routers both --modes context --eval intent_data/context_ood.yaml --output reports/context-ood.json
```

`context_ood.yaml` 复用八条 OOD，补上产品送达确认提问，检查历史上下文对误接受的影响。该文件同样由 `intent_data/build.py` 生成。
