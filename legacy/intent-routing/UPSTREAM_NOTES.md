# 上游实现核查记录

阅读日期：2026-09-09。两份源码由用户克隆到产品文档根目录，PoC 不改动它们。

## RealtimeIntent

固定提交：`dcd2f502a6711600d76952fe27c816425cc01f06`。

- [README](https://github.com/SquadyAI/RealtimeIntent/blob/dcd2f502a6711600d76952fe27c816425cc01f06/README.md)：服务接口 `/intent`、`/batch_insert` 和 GPU/外接服务配置。
- [IntentService](https://github.com/SquadyAI/RealtimeIntent/blob/dcd2f502a6711600d76952fe27c816425cc01f06/app/intent_service.py)：`process` 将对话包装为查询，embedding → Qdrant；`_process_rerank_or_direct` 对召回标签去重并追加 __no_intent__ 后重排和拒识。
- [Qdrant adapter](https://github.com/SquadyAI/RealtimeIntent/blob/dcd2f502a6711600d76952fe27c816425cc01f06/app/async_qdrant_client.py)：检索最低 score 0.4，召回更多样本后按标签分组，再取 top_k。
- [Rerank](https://github.com/SquadyAI/RealtimeIntent/blob/dcd2f502a6711600d76952fe27c816425cc01f06/app/rerank.py)：`process_labels_and_documents` 用 DOCUMENTS_MAP 将标签映射成语义描述；默认 Qwen ChatML 查询传给 `/score`，`build_reranked_results` 将服务分数映射回标签并排序。

适配点：仅在当前 PoC 进程中替换 `embed_single_text` 与 `rerank_single_api` 的模型 I/O；填充共享数据生成的 DOCUMENTS_MAP；把 Qdrant client 绑定到 `:memory:`。实际检索分组、候选生成、描述映射、分数排序与拒识来自上游模块。绕过 HTTP/worker 和摘要更新，因此无摘要污染、无额外 LLM、无网络时延。上游吞掉重排异常，适配器会捕获并重新向 benchmark 抛出，防止错误被当成正确拒识。

重要差异：本地通用 cross-encoder 使用对话与描述的文本对，不使用 Qwen 的 ChatML 模板。这是可运行的 CPU 模型后端替换，不能代表上游默认 GPU/Qwen 结果。后续可把两个模型 I/O 绑定回上游 `embedding.embed_single_text` / `rerank.rerank_single_api` 来测外部服务；本次没有实现或测量远程部署。

## semantic-router

固定提交：`d926cfcf8523cc28a468e59535899d16277fe55b`，本地安装版本 `0.2.0.dev1`。

- [README](https://github.com/aurelio-labs/semantic-router/blob/d926cfcf8523cc28a468e59535899d16277fe55b/README.md)：`Route(name, utterances)`，`SemanticRouter(encoder, routes, auto_sync='local')`。
- [SemanticRouter](https://github.com/aurelio-labs/semantic-router/blob/d926cfcf8523cc28a468e59535899d16277fe55b/semantic_router/routers/semantic.py)：dense encoder，默认 top_k=5、aggregation=mean。
- [BaseRouter](https://github.com/aurelio-labs/semantic-router/blob/d926cfcf8523cc28a468e59535899d16277fe55b/semantic_router/routers/base.py)：`__call__` → index query → 按 route 聚合 → `_pass_routes` 阈值 → `RouteChoice.similarity_score`。
- [LocalIndex similarity](https://github.com/aurelio-labs/semantic-router/blob/d926cfcf8523cc28a468e59535899d16277fe55b/semantic_router/linear.py)：归一化点积即余弦相似度。

适配点：实现官方 `DenseEncoder` 扩展点，将相同多语言 embedding 模型提供给原生 SemanticRouter。所有 route 是静态 route，无 function schema、LLM 或 workflow action；分支元数据不参与 route name。

本次两边使用相同数据和 embedding 权重，无微调。Demo A 多出独立 reranker 模型和产品描述字典；Demo B 主要需要 route 例句及相似度阈值。二者阈值需各自校准，不能直接交换。
