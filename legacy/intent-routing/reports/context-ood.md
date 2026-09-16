# Intent routing benchmark

主准确率仅计 heldout 单标签样本；歧义集合命中率、原话重叠、OOD、错误另列。
延迟为进程内串行 detect 墙钟耗时，包含模型推理与检索，不含 ASR/TTS、HTTP、队列或模型加载。
CPU 多语言小模型配置，不代表上游 Qwen GPU 默认性能；阈值尚未校准。

| Router / mode | Heldout accuracy | Macro | Reject (ID) | OOD reject | p50 ms | p95 ms | p99 ms | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| semantic_router/context | N/A | N/A | N/A | 0.250 | 25.799 | 34.523 | 34.828 | 0 |
| realtime_intent/context | N/A | N/A | N/A | 0.375 | 192.076 | 246.743 | 257.564 | 0 |

## semantic_router/context

索引初始化：2499.2 ms；首个 detect：19.8 ms。

最常见留出集混淆：

逐意图准确率：

| Intent | Correct / n | Accuracy |
|---|---:|---:|

分类别结果（context_pair 在 text 模式下缺少判定上下文，仅作诊断）：

| Category | n | Accuracy | Negative rejection | Ambiguous set hit |
|---|---:|---:|---:|---:|
| ood | 8 | N/A | 0.250 | N/A |

## realtime_intent/context

索引初始化：2237.7 ms；首个 detect：172.0 ms。

最常见留出集混淆：

逐意图准确率：

| Intent | Correct / n | Accuracy |
|---|---:|---:|

分类别结果（context_pair 在 text 模式下缺少判定上下文，仅作诊断）：

| Category | n | Accuracy | Negative rejection | Ambiguous set hit |
|---|---:|---:|---:|---:|
| ood | 8 | N/A | 0.375 | N/A |

完整配置、包/模型版本、逐条结果、分数语义和混淆文本见同名 JSON。
重复请求不增加独立样本数；这批人工小样本不足以代表线上分布。p99 是样本分位数，不是生产 SLA。
