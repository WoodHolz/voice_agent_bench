"""Pre-search node filter via semantic-router's public API. No policy/actions."""

from pathlib import Path
from time import perf_counter
import yaml
from common import BASE, Detection, empty_result
from semantic_demo.router import Router as GlobalRouter


def load_map(path=None):
    return yaml.safe_load(
        Path(path or BASE / "intent_data/workflow_intent_map.yaml").read_text()
    )["nodes"]


class Router(GlobalRouter):
    def __init__(self, intents, models, config, mapping=None, include_sides=False):
        # Current user text only, including indexed utterances. No context in this API.
        super().__init__(intents, models, config, with_context=False)
        self.mapping = mapping if mapping is not None else load_map()
        self.include_sides = include_sides
        self.field = (
            "allowed_including_documented_sides" if include_sides else "allowed_intents"
        )
        known = {route.name for route in self.router.routes}
        for node, entry in self.mapping.items():
            candidates = entry[self.field]
            if (
                not candidates
                or len(set(candidates)) != len(candidates)
                or not set(candidates) <= known
            ):
                raise ValueError(f"Invalid candidate set for {node}")

    def detect(self, text, current_node):
        start = perf_counter()
        # Unknown nodes must fail closed explicitly, never fall back to global routing.
        if current_node not in self.mapping:
            raise ValueError(f"Unknown workflow node: {current_node!r}")
        allowed = self.mapping[current_node][self.field]
        if not isinstance(text, str):
            raise TypeError("text must be str")
        if not text.strip():
            result = empty_result(start)
        else:
            # Library LocalIndex.query filters vectors FIRST, then similarity and top-k.
            choice = self.router(text, route_filter=allowed)
            result = Detection(
                choice.name,
                float(choice.similarity_score)
                if choice.similarity_score is not None
                else None,
                (perf_counter() - start) * 1000,
                self.score_kind,
                None if choice.name else "below_route_threshold",
            )
        result.details.update(
            current_node=current_node,
            allowed_intents=allowed,
            candidate_count=len(allowed),
            include_sides=self.include_sides,
        )
        result.latency_ms = (perf_counter() - start) * 1000
        return result
