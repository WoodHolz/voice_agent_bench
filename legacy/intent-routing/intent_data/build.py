"""Rebuild shared data from product table 7 and explicitly authored held-out variants."""

import hashlib
import re
from pathlib import Path
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DOC = ROOT / "催授权流程 v1.1 - 意图.md"
# Previous assistant prompts are context, never classifier labels or policy actions.
PROMPTS = {
    "A": ("现在方便吗？", "话术5-2"),
    "B": ("您可以核实我们的身份。", "a1/话术5-4（节选改写）"),
    "C": ("您看什么时候方便再联系？", "a2-7（改写）"),
    "D": ("您对背调授权有什么顾虑？", "5-1-b-3（改写）"),
    "E": ("您收到背调授权通知了吗？", "话术5-36（节选改写）"),
    "F": ("是最近比较忙？还是对填写有疑问？", "b14-1"),
    "G": ("后台还没显示完成，电子签名和人脸识别都做了吗？", "话术5-29（节选改写）"),
    "H": ("今天下班前完成可以吗？", "b17-1-a"),
    "I": ("您在操作时遇到了什么问题？", "a4/a5（改写）"),
}
OVERRIDES = {
    15: ("您可以回拨官方号码核实这次通话。", "话术5-4（节选改写）"),
    16: ("您可以回拨官方号码核实这次通话。", "话术5-4（节选改写）"),
    17: ("您可以回拨官方号码核实这次通话。", "话术5-4（节选改写）"),
    24: ("如果您现在方便听一分钟，我只说一件事。", "话术5-21（节选）"),
    40: ("您看下骚扰拦截或垃圾邮件箱里有吗？", "话术5-28/5-43（改写）"),
    41: ("您看下骚扰拦截或垃圾邮件箱里有吗？", "话术5-28/5-43（改写）"),
    55: ("您方便提供一个常用邮箱吗？", "话术5-49（节选）"),
    56: ("您方便提供一个常用邮箱吗？", "话术5-49（节选）"),
    57: (
        "我们可能通过公司官方渠道联系其他在职同事核实，您可以吗？",
        "话术5-38（改写）",
    ),
    58: (
        "我们可能通过公司官方渠道联系其他在职同事核实，您可以吗？",
        "话术5-38（改写）",
    ),
    59: (
        "我们可能通过公司官方渠道联系其他在职同事核实，您可以吗？",
        "话术5-38（改写）",
    ),
}


def dump(path, obj):
    path.write_text(
        yaml.safe_dump(obj, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def build():
    curated = {}
    for line in (HERE / "curated.tsv").read_text().splitlines():
        if line and not line.startswith("#"):
            k, *v = line.split("|")
            assert len(v) == 3
            curated[k] = v
    intents, cases = [], []
    group = None
    for lineno, line in enumerate(DOC.read_text().splitlines(), 1):
        if line.startswith("### 7-"):
            group = line[6]
        if not re.match(r"\| 7-\d+\s*\|", line):
            continue
        cells = [
            re.sub(r"\\([_~])", r"\1", x.strip()) for x in line.strip("|").split("|")
        ]
        ident, name, desc, raw, branch, script = cells
        n = int(ident.split("-")[1])
        source = {
            "file": DOC.name,
            "line": lineno,
            "section": f"表7 / 7-{group}",
            "intent_id": ident,
        }
        prompt, prompt_source = OVERRIDES.get(n, PROMPTS[group])
        context = [{"role": "assistant", "content": prompt}]
        # Silence is an event, not the words inside the parenthesized product annotation.
        originals = [] if n == 1 else re.findall(r'"([^"]+)"', raw)
        originals = [
            re.sub(r"\[([^]]+)\]\(mailto:[^)]+\)", r"\1", x) for x in originals
        ]
        examples = list(
            dict.fromkeys(originals + ([] if n == 1 else [curated[ident][0]]))
        )
        intents.append(
            {
                "id": ident,
                "name": name,
                "description": desc,
                "input_kind": "silence_event" if n == 1 else "text",
                "source": source,
                "workflow_branches": branch,
                "script_refs": script,
                "example_context": context,
                "context_source": prompt_source,
                "examples": examples,
                "original_examples": originals,
                "derived_examples": [] if n == 1 else [curated[ident][0]],
            }
        )
        if n == 1:
            continue
        for j, (text, category) in enumerate(
            zip(curated[ident][1:], ["paraphrase", "short_spoken"])
        ):
            cases.append(
                {
                    "id": f"{ident}-heldout-{j}",
                    "text": text,
                    "expected": [ident],
                    "category": category,
                    "split": "heldout",
                    "context": context,
                    "source": source,
                    "derivation": "人工依据该产品意图改写；不是产品原话",
                }
            )
        # Intent-table originals are explicitly a separate, contaminated resubstitution diagnostic.
        for j, text in enumerate(originals):
            cases.append(
                {
                    "id": f"{ident}-source-{j}",
                    "text": text,
                    "expected": [ident],
                    "category": "source_example",
                    "split": "source_overlap",
                    "context": context,
                    "source": source,
                    "derivation": "产品原话；也在索引中，仅作接线/记忆诊断",
                }
            )
    extra = [
        ("好啊", ["7-6", "7-15", "7-24", "7-48", "7-57"], "ambiguous", []),
        ("已经填好了", ["7-8", "7-37", "7-46"], "ambiguous", []),
        ("那个链接我打不开", ["7-43", "7-53"], "ambiguous", []),
        ("我在开会", ["7-7", "7-20"], "ambiguous", []),
        ("我先问问HR", ["7-16", "7-33"], "ambiguous", []),
        ("你们别再打了我不信", ["7-17", "7-28"], "ambiguous", []),
        ("我还在公司别找我同事", ["7-29", "7-58"], "ambiguous", []),
        (
            "好啊",
            ["7-6"],
            "context_pair",
            [{"role": "assistant", "content": "现在方便说两分钟吗？"}],
        ),
        (
            "好啊",
            ["7-48"],
            "context_pair",
            [{"role": "assistant", "content": "明天下班前完成授权可以吗？"}],
        ),
        (
            "好啊",
            ["7-57"],
            "context_pair",
            [
                {
                    "role": "assistant",
                    "content": "可以通过公司官方渠道联系其他在职同事核实吗？",
                }
            ],
        ),
        (
            "已经填好了",
            ["7-8"],
            "context_pair",
            [
                {
                    "role": "assistant",
                    "content": "您好，我是协助办理入职背调的AI助手，现在方便吗？",
                }
            ],
        ),
        (
            "已经填好了",
            ["7-37"],
            "context_pair",
            [{"role": "assistant", "content": "您收到授权通知了吗，填了吗？"}],
        ),
        (
            "已经填好了",
            ["7-46"],
            "context_pair",
            [
                {
                    "role": "assistant",
                    "content": "后台还没完成，确认一下签名人脸和提交都做了吗？",
                }
            ],
        ),
        (
            "没看到",
            ["7-38"],
            "context_pair",
            [{"role": "assistant", "content": "此前发送的背调授权短信收到了吗？"}],
        ),
        (
            "没看到",
            ["7-41"],
            "context_pair",
            [{"role": "assistant", "content": "刚才让您查的拦截和垃圾箱都找过了吗？"}],
        ),
        ("我这边人连识别一直失 bai", ["7-51"], "asr_imperfect", []),
        ("刚刚填错啦那个能改不", ["7-52"], "asr_imperfect", []),
        ("链接打不 开一直报错", ["7-53"], "asr_imperfect", []),
        ("我在开 车呢", ["7-18"], "asr_imperfect", []),
        ("不不用再再打电话了", ["7-28"], "asr_imperfect", []),
        ("我", [], "partial_insufficient", []),
        ("我刚", [], "partial_insufficient", []),
        ("嗯呃", [], "noise", []),
        ("", [], "empty", []),
        ("   ", [], "empty", []),
        ("明天北京天气怎么样", [], "ood", []),
        ("帮我订一张去上海的机票", [], "ood", []),
        ("来一首周杰伦的歌", [], "ood", []),
        ("这份外卖怎么退款", [], "ood", []),
        ("帮我写一个排序程序", [], "ood", []),
        ("设置早上七点的闹钟", [], "ood", []),
        ("我想查银行卡余额", [], "ood", []),
        ("晚饭吃什么比较好", [], "ood", []),
    ]
    for j, (text, expected, category, context) in enumerate(extra):
        # Ambiguous copies of training quotes must not enter held-out generalization metrics.
        overlap = any(text in i["examples"] for i in intents)
        cases.append(
            {
                "id": f"contrast-{j:02d}",
                "text": text,
                "expected": expected,
                "category": category,
                "split": "challenge_overlap" if overlap else "challenge",
                "context": context,
                "source": {"file": DOC.name, "intent_ids": expected},
                "derivation": "人工对照产品意图构造的歧义/上下文/噪声/OOD样本",
            }
        )
    dump(
        HERE / "intents.yaml",
        {
            "schema_version": 1,
            "product_sha256": hashlib.sha256(DOC.read_bytes()).hexdigest(),
            "intents": intents,
        },
    )
    dump(
        HERE / "eval.yaml",
        {
            "schema_version": 1,
            "notes": "expected=[] 要求拒识；多标签仅用于歧义集合命中率，不计单标签准确率。source_overlap 不计泛化。",
            "cases": cases,
        },
    )
    # Separate diagnostic: OOD utterances while a real product question is pending.
    # Do not change the original held-out set after inspecting its benchmark.
    contextual_ood = []
    for case in cases:
        if case["category"] == "ood":
            contextual_ood.append(
                {
                    **case,
                    "id": case["id"] + "-in-conversation",
                    "context": [
                        {
                            "role": "assistant",
                            "content": "此前发送的背调授权通知，您收到了吗？",
                        }
                    ],
                    "derivation": "原 OOD 样本加话术5-36改写上下文；独立压力诊断，不用于调参",
                }
            )
    dump(HERE / "context_ood.yaml", {"schema_version": 1, "cases": contextual_ood})
    print(
        f"{len(intents)} intents; {sum(len(i['examples']) for i in intents)} index examples; {len(cases)} eval cases"
    )


if __name__ == "__main__":
    build()
