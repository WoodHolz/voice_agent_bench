"""Model I/O only. Both independent routers use the same multilingual embedding model.
No cached query embeddings or classification results; no intent/keyword logic here.
"""

import os
from common import BASE

# Keep downloads inside the experiment's writable directory.
os.environ.setdefault("HF_HOME", str(BASE / ".cache/huggingface"))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


class LocalModels:
    def __init__(self, config, reranker=False):
        import torch
        from sentence_transformers import SentenceTransformer, CrossEncoder

        torch.set_num_threads(config["threads"])
        self.config = config
        self.embedding = SentenceTransformer(
            config["embedding"],
            device=config["device"],
            revision=config.get("embedding_revision"),
            local_files_only=config.get("local_files_only", True),
        )
        self.embedding.max_seq_length = config["max_length"]
        self.reranker = None
        if reranker:
            self.reranker = CrossEncoder(
                config["reranker"],
                device=config["device"],
                max_length=config["max_length"],
                revision=config.get("reranker_revision"),
                local_files_only=config.get("local_files_only", True),
            )

    def encode(self, texts):
        return self.embedding.encode(
            texts,
            batch_size=self.config["batch_size"],
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

    def score(self, query, documents):
        import torch

        if self.reranker is None:
            raise RuntimeError("Reranker model was not loaded")
        # Generic multilingual cross-encoder takes text pairs, not Qwen ChatML tokens.
        values = self.reranker.predict(
            [(query, d) for d in documents],
            batch_size=self.config["batch_size"],
            show_progress_bar=False,
            activation_fn=torch.nn.Sigmoid(),
        )
        return [float(v) for v in values]

    def metadata(self):
        snapshots = BASE / ".cache/huggingface/hub"
        revisions = {}
        for kind in ("embedding", "reranker"):
            path = (
                snapshots
                / ("models--" + self.config[kind].replace("/", "--"))
                / "snapshots"
            )
            revisions[kind] = (
                sorted(p.name for p in path.iterdir()) if path.exists() else []
            )
        return {
            "config": self.config,
            "cached_revisions": revisions,
            "query_cache": False,
            "transport": "in_process",
            "normalized_embeddings": True,
        }


if __name__ == "__main__":
    from common import load_config
    import json
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    config = load_config()["models"]
    if args.download:
        config["local_files_only"] = False
    model = LocalModels(config, reranker=True)
    print(json.dumps(model.metadata(), ensure_ascii=False, indent=2))
    print("Embedding dimension:", len(model.encode(["模型预热"])[0]))
    print(
        "Rerank smoke:",
        model.score("人脸识别失败", ["人脸核验步骤无法通过", "询问填写规则"]),
    )
