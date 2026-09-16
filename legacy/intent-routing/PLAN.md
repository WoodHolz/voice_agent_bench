# IntentRouter PoC 实施计划

1. 复读产品方案、主流程、表 7 意图、表 4/5 话术；保留原 ID 和分支元数据，不解决文档中的流程冲突。
2. 核对本地上游源码：RealtimeIntent `dcd2f502a6711600d76952fe27c816425cc01f06`，semantic-router `d926cfcf8523cc28a468e59535899d16277fe55b`。
3. 从表 7 导出 59 项共享配置。原话用于索引；人工衍生改写明确标注来源。独立留出评测，不把评测例句加入索引。7-1 保留为非文本事件，不用空文本推断超时。
4. Demo A 直接调用上游 IntentService 的检索和重排/拒识方法。仅适配模型 I/O、本地 Qdrant、产品 DOCUMENTS_MAP 和分数观测；不复制分类算法，不启动摘要 LLM 或工作流。
5. Demo B 使用上游 Route、SemanticRouter、LocalIndex 和 DenseEncoder 扩展点。目录叫 semantic_demo，避免遮蔽安装的 semantic_router 包。
6. 统一 detect(text, context) 返回结构；共享 benchmark 分别测 text-only/context，单列重叠原话、歧义、OOD、空输入、错误、冷启动和热请求分位延迟。增加逐步 ASR 模拟。
7. 校验数据来源、无评测泄漏、API 接入与指标计算；运行真实模型评测，记录配置、包版本、模型版本和硬件。无实测数据时不宣称准确率/延迟结论。

已确认的上游细节：RealtimeIntent 对检索到的 label 去重后按 DOCUMENTS_MAP 描述重排，并追加 __no_intent__；API debug payload.score 是检索分数，不是重排置信度。semantic-router 当前提交可返回聚合 similarity_score。两者分数不可横向比较。

本次选用可替换的多语言 CPU 模型作为初始可运行配置；这不代表上游 Qwen GPU 默认配置的性能。产品的分支、动作和终态仅保留为元数据。
