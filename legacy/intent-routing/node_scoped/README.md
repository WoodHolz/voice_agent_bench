# 节点范围路由实验

结论见 [NODE_SCOPED_FINDINGS.md](../NODE_SCOPED_FINDINGS.md)，完整表格见 [RESULTS.md](../reports/node_scoped/RESULTS.md)。先阅读其中局部回应集合与合法旁路的区别。

从 `experiments/intent-routing` 执行，使用已安装环境和本地模型，无需下载：

```bash
.venv/bin/python -m node_scoped.build_data
.venv/bin/python -m node_scoped.run --repeat 3
.venv/bin/python -m node_scoped.stream --repeat 3
.venv/bin/python -m node_scoped.report
.venv/bin/python -m pytest -q
```

默认只更新 `reports/node_scoped/`。保留本轮原始结果另跑时，为 run/stream 指定 `--output reports/node_scoped/new-benchmark.json` 和 `--output reports/node_scoped/new-stream.json`；report 默认读取原文件名。旧全局实验报告不会被覆盖。

```python
from common import load_config, load_intents
from models import LocalModels
from node_scoped.router import Router

config = load_config()
models = LocalModels(config["models"], reranker=False)
router = Router(load_intents(), models, config["semantic_router"])
result = router.detect("我这边一直人脸识别失败", current_node="a4")
print(result.intent_id, result.score, result.latency_ms)
for partial in ["我", "我刚才", "我刚才填错了", "我刚才填错了能改吗"]:
    print(router.detect(partial, current_node="a4"))
router.close()
```

此接口无对话拼接或跨调用状态；返回候选意图，不执行分支。`include_sides=True` 仅用于文档旁路集合上界审计。未知节点报错，空文本拒识。

`build_data.py` 的映射取自产品分支表，输出逐边来源及文档哈希。人工改写与专项负例属于评测数据，产品原话重叠另列。共享 `intents.yaml` 未修改。`route_filter` 在本地上游 `semantic_router/index/local.py` 中先过滤向量再检索；版本和模型 revision 记录在 benchmark JSON 中。score 沿用上游 mean cosine 语义，不是校准置信概率。
