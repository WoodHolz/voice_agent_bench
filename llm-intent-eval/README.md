# Voice Agent LLM SOP Evaluation

这是 voice agent 项目的小 LLM 评测主线。当前范围是：给定对话状态、最近历史、用户回复和有限候选 SOP，测试模型能否实时输出正确 SOP 编号及给语音 LLM 的简短回复指导。

候选 SOP 如何产生不属于 v0.1 的评测范围；v0.1 假设合理候选已经给出且正确答案或兜底项存在。

## 目录

- `docs/`：测试集与标注规范
- `data/drafts/`：尚未完成人工复核的草稿数据
- `data/splits/`：审核后固定的开发集、验证集和盲测集
- `prompts/`：统一的模型提示词
- `schemas/`：测例和模型输出的 JSON Schema
- `scripts/`：从产品意图文档重建 v0.1 草稿集的脚本
- `configs/`：本地 vLLM 与云端模型的评测连接配置（不含密钥）
- `results/`：不同模型和 Prompt 的评测结果

## v0.1 数据集

- `data/drafts/cases_v0.1.jsonl`：73 条测例
- `data/drafts/sop_catalog_v0.1.json`：59 个产品意图和 3 个控制器兜底项
- `data/drafts/summary_v0.1.json`：数据量与类型分布
- `docs/testset-v0.1.md`：范围、格式和评分规则
- `prompts/controller-v0.1.txt`：首版统一 Prompt

当前 73 条全部为 `draft`，包括：

- 表 7 的 59 个正式意图各一条基础样本；
- 14 条跳阶段、全局旁路、多意图、含糊表达、SOP 外请求和 ASR 噪声样本。

这些数据可以用于检查评测程序和进行探索性跑分，但在业务复核前不能作为最终金标或模型上线依据。

## 产品文档来源

产品方案、流程、意图、上下文和话术原始文档位于上级目录 `../`。原始产品文档只读，不在本目录中修改。

## 基本原则

1. 测例输入固定为：状态、历史、用户回复、候选 SOP。
2. 模型输出固定为：`sop_id` 与不超过 50 个汉字的 `detail`。
3. 正常流程、全局旁路、跨阶段回答和恢复/兜底均需覆盖。
4. 同一 `group_id` 的原始场景及改写必须进入同一个数据集合，避免泄漏。
5. 所有模型使用完全相同的数据、候选顺序策略、Prompt 和推理参数。
6. `test` 是最终盲测集，在模型和 Prompt 定版前不得用于调参。

## 运行模型评测

`scripts/run_eval.py` 通过 OpenAI-compatible Chat Completions API 调用模型，因此本地
vLLM 和阿里云百炼 Qwen Flash 使用同一套数据、Prompt、解析与基础评分逻辑。当前自动
统计 JSON 合法率、候选内选择率、SOP 准确率和请求延迟；`detail` 的业务语义仍需人工复核。

以下命令均在 `llm-intent-eval/` 目录中执行：

```bash
cd llm-intent-eval
```

先用一条数据检查本地 vLLM：

```bash
python3 scripts/run_eval.py \
  --profile configs/vllm-qwen35-4b.json \
  --limit 1
```

确认无误后去掉 `--limit 1` 运行全部 73 条。结果分别写入带 UTC 时间戳的目录，包含
逐条 `results.jsonl` 和汇总 `summary.json`。

运行 Qwen Flash 前配置百炼密钥与所在地域/业务空间对应的 OpenAI-compatible Base URL：

```bash
export DASHSCOPE_API_KEY='替换为真实密钥'
export DASHSCOPE_BASE_URL='https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1'

python3 scripts/run_eval.py \
  --profile configs/qwen-flash.json \
  --limit 1
```

API Key 只能通过环境变量提供，不得写入 profile、结果文件或提交到 Git。不同地域的
Base URL 不同；使用此前实验的 Qwen Flash 时，可在 profile 中把 `model` 改为当时固定的
模型快照，避免浮动别名升级后影响可复现性。

只渲染第一条 Prompt、不发出网络请求：

```bash
python3 scripts/run_eval.py \
  --profile configs/vllm-qwen35-4b.json \
  --dry-run
```

运行基础测试：

```bash
python3 -m unittest discover -s tests -v
```

## 旧路线

此前的文档拆分、semantic routing、RealtimeIntent 和 intent-routing 实验统一保留在 `../legacy/`，仅作历史实现和技术参考。
