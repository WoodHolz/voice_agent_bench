"""Independent semantic-router demo using its public Route / SemanticRouter API."""

from time import perf_counter
from typing import Any
from semantic_router import Route
from semantic_router.encoders.base import DenseEncoder
from semantic_router.index.local import LocalIndex
from semantic_router.routers import SemanticRouter
from common import Detection, empty_result, render


class ModelEncoder(DenseEncoder):
    backend: Any

    def __call__(self, docs):
        return self.backend.encode(docs)


class Router:
    def __init__(self, intents, models, config, with_context=False):
        encoder = ModelEncoder(
            name=models.config["embedding"],
            backend=models,
            score_threshold=config["threshold"],
        )
        routes = [
            Route(
                name=i["id"],
                utterances=[
                    render(text, i["example_context"] if with_context else None)
                    for text in i["examples"]
                ],
                score_threshold=config["threshold"],
            )
            for i in intents
            if i["input_kind"] == "text"
        ]
        self.router = SemanticRouter(
            encoder=encoder,
            routes=routes,
            index=LocalIndex(),
            auto_sync="local",
            top_k=config["top_k"],
            aggregation=config["aggregation"],
        )
        self.score_kind = f"{config['aggregation']}_cosine_of_retrieved_route_examples"

    def detect(self, text, context=None):
        start = perf_counter()
        if not isinstance(text, str):
            raise TypeError("text must be str")
        if not text.strip():
            return empty_result(start)
        choice = self.router(render(text, context))
        score = (
            float(choice.similarity_score)
            if choice.similarity_score is not None
            else None
        )
        return Detection(
            choice.name,
            score,
            (perf_counter() - start) * 1000,
            self.score_kind,
            None if choice.name else "below_route_threshold",
        )

    def close(self):
        pass
