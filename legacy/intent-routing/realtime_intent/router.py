"""Product adapter around the actual upstream RealtimeIntent decision pipeline.

We call IntentService.process and _process_rerank_or_direct unchanged. Dependencies
are bound at runtime: CPU models, Qdrant local storage, and product DOCUMENTS_MAP.
This is sequential, one instance per process. It deliberately excludes HTTP queues
and background summary LLM workers. Upstream source is never modified.
"""

import asyncio
import sys
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5
from common import BASE, Detection, empty_result, examples, messages


class Router:
    _active = False

    def __init__(self, intents, models, config, with_context=False):
        if Router._active:
            raise RuntimeError(
                "Only one RealtimeIntent Router may be active per process; close the previous instance"
            )
        path = (BASE / config["upstream_path"]).resolve()
        if not (path / "app/intent_service.py").exists():
            raise FileNotFoundError(f"RealtimeIntent source missing: {path}")
        sys.path.insert(0, str(path))
        from app import intent_service as upstream
        from app import async_qdrant_client as database
        from app import rerank
        from app.constants.intent_mappings import DOCUMENTS_MAP
        from qdrant_client import AsyncQdrantClient

        Router._active = True
        self._closed = False
        self.upstream, self.database, self.rerank = upstream, database, rerank
        self.models, self.config = models, config
        self.loop = asyncio.new_event_loop()
        self.service = upstream.IntentService()
        self.service._embed_semaphore = asyncio.Semaphore(1)
        self.service._rerank_semaphore = asyncio.Semaphore(1)
        self.valid_ids = {i["id"] for i in intents if i["input_kind"] == "text"}
        self._originals = (
            upstream.embed_single_text,
            upstream.rerank_single_api,
            upstream.TOP_K,
            upstream.NO_INTENT_RERANK_THRESHOLD,
            dict(DOCUMENTS_MAP),
            database.async_qdrant_manager.client,
        )
        # A runtime configuration mapping, not an alternative classifier.
        DOCUMENTS_MAP.clear()
        DOCUMENTS_MAP.update(
            {
                i["id"]: f"{i['name']}：{i['description']}"
                for i in intents
                if i["input_kind"] == "text"
            }
        )
        DOCUMENTS_MAP["__no_intent__"] = (
            "用户没有表达可判定的背调授权相关意图，或在讨论无关话题，或只是噪声和未完成的片段。"
        )
        database.async_qdrant_manager.client = AsyncQdrantClient(location=":memory:")
        upstream.TOP_K = config["top_k"]
        upstream.NO_INTENT_RERANK_THRESHOLD = config["no_intent_threshold"]
        self.captured, self.backend_error = [], None

        async def embed(text):
            return models.encode([text])[0]

        async def local_rerank(req, labels, logger):
            try:
                label_order, documents = rerank.process_labels_and_documents(labels)
                query = (
                    f"{req.context}\n\n[LatestUser]: {req.conversation[-1]['content']}"
                )
                scores = models.score(query, documents)
                result = rerank.build_reranked_results(
                    [{"index": i, "score": s} for i, s in enumerate(scores)],
                    label_order,
                )
                self.captured = result
                return result, {"backend": "local_multilingual_cross_encoder"}
            except Exception as exc:
                self.backend_error = (
                    exc  # upstream catches errors; do not count as rejection
                )
                raise

        upstream.embed_single_text = embed
        upstream.rerank_single_api = local_rerank
        try:
            self.loop.run_until_complete(self._seed(examples(intents, with_context)))
        except Exception:
            self.close()
            raise

    async def _seed(self, items):
        from qdrant_client.models import Distance, PointStruct, VectorParams

        vectors = self.models.encode([text for _, text in items])
        client = self.database.async_qdrant_manager.client
        collection = self.database.QDRANT_COLLECTION
        await client.create_collection(
            collection,
            vectors_config=VectorParams(size=len(vectors[0]), distance=Distance.DOT),
        )
        await client.upsert(
            collection,
            points=[
                PointStruct(
                    id=str(uuid5(NAMESPACE_URL, label + "\n" + text)),
                    vector=vector,
                    payload={"label": label, "text": text},
                )
                for (label, text), vector in zip(items, vectors)
            ],
        )

    async def _detect(self, text, context):
        from app.request_context import get_request_logger, RequestContext

        RequestContext.set_request_id(RequestContext.generate_request_id())
        req = self.upstream.IntentRequest(
            "poc", messages(text, context), self.loop.create_future(), debug=True
        )
        logger = get_request_logger("intent_poc")
        labels, payloads, summary = await self.service.process(req, logger)
        intent, payload = await self.service._process_rerank_or_direct(
            req, labels, payloads, summary, logger
        )
        if self.backend_error is not None:
            raise RuntimeError("RealtimeIntent reranker failed") from self.backend_error
        if intent and intent not in self.valid_ids:
            raise RuntimeError(f"Unexpected upstream label {intent!r}")
        score = next((r["score"] for r in self.captured if r["label"] == intent), None)
        # For no-match, score is deliberately None; inspect details for rejected candidates.
        return (
            intent,
            score,
            {
                "rerank_candidates": self.captured,
                "retrieved_labels": labels,
                "retrieval_score": payload["score"] if payload else None,
            },
        )

    def detect(self, text, context=None):
        if self._closed:
            raise RuntimeError("Router is closed")
        start = perf_counter()
        if not isinstance(text, str):
            raise TypeError("text must be str")
        if not text.strip():
            return empty_result(start)
        self.captured, self.backend_error = [], None
        intent, score, details = self.loop.run_until_complete(
            self._detect(text, context)
        )
        return Detection(
            intent,
            score,
            (perf_counter() - start) * 1000,
            "cross_encoder_sigmoid_relevance",
            None if intent else "upstream_no_match",
            details,
        )

    def close(self):
        if self._closed:
            return
        from app.constants.intent_mappings import DOCUMENTS_MAP

        self.loop.run_until_complete(self.database.async_qdrant_manager.client.close())
        (
            self.upstream.embed_single_text,
            self.upstream.rerank_single_api,
            self.upstream.TOP_K,
            self.upstream.NO_INTENT_RERANK_THRESHOLD,
            old_map,
            old_client,
        ) = self._originals
        DOCUMENTS_MAP.clear()
        DOCUMENTS_MAP.update(old_map)
        self.database.async_qdrant_manager.client = old_client
        # Let upstream monitoring tasks finish before disposing of the private event loop.
        pending = asyncio.all_tasks(self.loop)
        if pending:
            self.loop.run_until_complete(asyncio.gather(*pending))
        self.loop.close()
        self._closed = True
        Router._active = False
