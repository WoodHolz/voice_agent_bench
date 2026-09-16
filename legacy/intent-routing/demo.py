import argparse
import json
import logging
from common import load_config, load_intents
from benchmark.run import make_router


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--router", choices=["realtime_intent", "semantic_router"], required=True
    )
    p.add_argument("--text", default="我这边一直人脸识别失败")
    p.add_argument("--previous-assistant")
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR)
    from models import LocalModels

    config = load_config()
    models = LocalModels(config["models"], reranker=args.router == "realtime_intent")
    router = make_router(
        args.router, load_intents(), models, config, bool(args.previous_assistant)
    )
    try:
        context = (
            [{"role": "assistant", "content": args.previous_assistant}]
            if args.previous_assistant
            else []
        )
        print(
            json.dumps(
                router.detect(args.text, context).to_dict(),
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        router.close()


if __name__ == "__main__":
    main()
