import re
import yaml
from common import BASE, load_intents


def test_all_product_ids_and_metadata_are_preserved():
    intents = load_intents()
    assert {i["id"] for i in intents} == {f"7-{n}" for n in range(1, 60)}
    doc = (BASE / "../../催授权流程 v1.1 - 意图.md").read_text().splitlines()
    for i in intents:
        line = doc[i["source"]["line"] - 1]
        assert re.match(rf"\| {i['id']}\s*\|", line)
        assert i["name"] in line
        assert i["workflow_branches"] in re.sub(r"\\([_~])", r"\1", line)
        assert i["input_kind"] == "silence_event" or i["examples"]
    assert intents[0]["examples"] == []


def normalize(text):
    return re.sub(r"[\W_]+", "", text).lower()


def test_heldout_is_disjoint_and_covers_every_text_intent():
    intents = load_intents()
    indexed = {normalize(x) for i in intents for x in i["examples"]}
    cases = yaml.safe_load((BASE / "intent_data/eval.yaml").read_text())["cases"]
    heldout = [c for c in cases if c["split"] == "heldout"]
    assert {c["expected"][0] for c in heldout} == {f"7-{n}" for n in range(2, 60)}
    assert len({c["id"] for c in cases}) == len(cases)
    for c in heldout:
        assert normalize(c["text"]) not in indexed, c
    for c in cases:
        assert set(c["expected"]) <= {i["id"] for i in intents}
        assert "7-1" not in c["expected"]
        for msg in c["context"]:
            assert not re.search(r"7-\d+", msg["content"])


def test_rebuild_is_deterministic():
    import runpy

    paths = [BASE / "intent_data/intents.yaml", BASE / "intent_data/eval.yaml"]
    before = [p.read_bytes() for p in paths]
    runpy.run_path(str(BASE / "intent_data/build.py"), run_name="__main__")
    assert [p.read_bytes() for p in paths] == before


def test_context_ood_diagnostic_has_real_context_and_no_labels():
    cases = yaml.safe_load((BASE / "intent_data/context_ood.yaml").read_text())["cases"]
    assert len(cases) == 8
    assert all(c["context"] and c["expected"] == [] for c in cases)
