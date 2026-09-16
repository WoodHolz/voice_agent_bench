"""Export cited local decision vocabularies, NOT executable policy transitions."""

import re
import yaml
from common import BASE, load_intents, sha256

DOC = BASE / "../../催授权流程 v1.1.md"
PRODUCT = BASE / "../../催授权产品方案 v1.md"
OUT = BASE / "intent_data"
# Each edge is explicitly present under this decision subtree in table 1/2/3.
# Entry subtrees (a1/a3/a4) exclude later response decisions, which have their own node.
SPECS = [
    (
        "3-2",
        "开场回应",
        "3",
        True,
        [
            (n, f"3-2-{c}")
            for n, c in [
                (2, "b"),
                (3, "g"),
                (4, "c"),
                (5, "d"),
                (6, "e"),
                (7, "f"),
                (8, "h"),
            ]
        ],
        "现在方便吗？",
        "话术5-2",
    ),
    (
        "4-2",
        "送达回应",
        "4",
        True,
        [(36, "4-2-a"), (37, "4-2-b"), (38, "4-2-c"), (39, "4-2-d"), (32, "4-2-e")],
        "您收到背调授权通知了吗？",
        "话术5-36",
    ),
    (
        "b12-4",
        "查找结果",
        "b12",
        True,
        [(40, "b12-4-a"), (41, "b12-4-b"), (32, "b12-4-c")],
        "您看下骚扰拦截和垃圾邮件箱里有没有？",
        "b12-3/话术5-28",
    ),
    (
        "b14-2",
        "未填归因",
        "b14",
        True,
        [(42, "b14-2-a"), (43, "b14-2-b"), (44, "b14-2-c")],
        "是最近比较忙？还是对填写有疑问？",
        "b14-1",
    ),
    (
        "5-2-b-2",
        "未完成排查",
        "5",
        True,
        [(45, "5-2-b-2-a"), (46, "5-2-b-2-b"), (47, "5-2-b-2-c")],
        "后台还没显示完成，电子签名和人脸识别都做了吗？",
        "话术5-29",
    ),
    (
        "5-4-c",
        "时限回应（含文档明确的横切回应）",
        "5",
        True,
        [
            (48, "5-4-c-1"),
            (49, "5-4-c-2"),
            (50, "5-4-c-3"),
            (27, "5-4-c-2-c"),
            (23, "5-4-c-2-d"),
            (28, "5-4-c-2-e"),
        ],
        "今天下班前完成可以吗？",
        "b17-1-a",
    ),
    (
        "a1",
        "信任质疑分类入口",
        "a1",
        False,
        [
            (9, "a1-1"),
            (10, "a1-2-a"),
            (11, "a1-2-b"),
            (12, "a1-2-c"),
            (13, "a1-3"),
            (14, "a1-4"),
        ],
        "您对这次来电有什么疑问？",
        "a1（辅助实验提示，非产品逐字话术）",
    ),
    (
        "a1-5",
        "解释后的信任判断",
        "a1",
        False,
        [(15, "a1-5-a"), (16, "a1-5-b"), (17, "a1-5-c")],
        "您可以回拨官方号码核实这次通话。",
        "话术5-4",
    ),
    (
        "a2",
        "改约触发原因分类入口",
        "a2",
        False,
        [
            (18, "a2-1"),
            (19, "a2-1"),
            (20, "a2-2"),
            (21, "a2-3"),
            (22, "a2-4"),
            (23, "a2-5"),
        ],
        "您现在有什么不方便的情况？",
        "a2（辅助实验提示，非产品逐字话术）",
    ),
    (
        "a2-7",
        "时间锚定",
        "a2",
        False,
        [(25, "a2-7-1"), (26, "a2-7-2"), (27, "a2-7-3")],
        "您看几点方便我再联系？",
        "话术5-8",
    ),
    (
        "a3",
        "意愿阻力分类入口",
        "a3",
        False,
        [(29, "a3-1"), (30, "a3-2"), (31, "a3-3"), (32, "a3-4"), (33, "a3-5")],
        "您对背调授权有什么顾虑？",
        "a3（辅助实验提示，非产品逐字话术）",
    ),
    (
        "a3-6-a",
        "自主寻访同意",
        "a3",
        False,
        [(57, "a3-6-a-1"), (58, "a3-6-a-2"), (59, "a3-6-a-3")],
        "我们可能通过公司官方渠道联系其他在职同事核实，您可以吗？",
        "话术5-38",
    ),
    (
        "a4",
        "操作问题分类入口",
        "a4",
        False,
        [(51, "a4-1"), (21, "a4-2"), (52, "a4-3"), (53, "a4-4")],
        "您在操作时遇到了什么问题？",
        "a4（辅助实验提示，非产品逐字话术）",
    ),
    (
        "b16-2-a",
        "链接短信查找",
        "b16",
        True,
        [(40, "b16-2-a-1"), (41, "b16-2-a-2")],
        "您看下骚扰拦截文件夹里有没有那条短信？",
        "话术5-41",
    ),
    (
        "b16-2-b",
        "邮件查找",
        "b16",
        True,
        [(40, "b16-2-b-1"), (41, "b16-2-b-2")],
        "您看下收件箱和垃圾箱里有这封邮件吗？",
        "话术5-43",
    ),
    (
        "b16-2-c",
        "兜底短信查找",
        "b16",
        True,
        [(40, "b16-2-c-1"), (38, "b16-2-c-2")],
        "那一条不带链接的提醒短信，您看到了吗？",
        "话术5-44",
    ),
    (
        "b16-2-e-2",
        "邮箱登记回应",
        "b16",
        True,
        [(55, "b16-2-e-2-b"), (56, "b16-2-e-2-a")],
        "您方便提供一个常用邮箱吗？",
        "话术5-49",
    ),
]
# Product M5 explicitly lists these side-route groups. This audit conservatively
# unions the published groups (including broad response groups), not a new guard policy.
SIDE_GROUPS = {
    "a1": list(range(9, 18)),
    "a2": list(range(18, 29)),
    "a3": list(range(29, 34)),
    "a4": [21, 51, 52, 53],
    "a5": [54],
    "a6": [34, 35, 53],
}
# Polarity pairs & ambiguous mixtures, independently authored from product definitions.
# IDs are annotations, never provided to the classifier as text.
TARGETS = {
    "3-2": [(6, "现在可以聊，您继续说"), (7, "现在不能聊，请先停一下")],
    "4-2": [
        (36, "通知是收到的，只是还没有填"),
        (38, "通知根本就没有收到，不是收到没填"),
        (37, "通知收到了，授权也确实办完了"),
        (38, "没有收到那条授权通知"),
    ],
    "b12-4": [
        (40, "查过之后找到了，不用继续找"),
        (41, "查过之后没有找到，确实没有"),
        (40, "已经从垃圾箱找出来了"),
        (41, "连垃圾箱也翻了，还是找不着"),
    ],
    "b14-2": [(42, "没有别的问题，就是忙忘了"), (43, "不是忙忘了，是不知道该怎么操作")],
    "5-2-b-2": [
        (46, "签名人脸和最后提交都做完了，一个没漏"),
        (47, "签名人脸做了，最后提交可能没点"),
        (45, "表填了，可电子签名还没有做"),
        (46, "不是漏了步骤，是你们系统还没有同步"),
    ],
    "5-4-c": [
        (48, "今天下班以前能完成，我答应"),
        (49, "今天下班以前不能完成，时间不够"),
    ],
    "a1": [(9, "我想要一种方法核验您的官方身份"), (11, "我觉得这很可能是一通诈骗电话")],
    "a1-5": [
        (15, "现在我信了，可以继续说授权"),
        (16, "现在我还没核实，先找HR确认真假"),
        (17, "你解释了也没用，我还是不信，不要再找我"),
        (15, "已经不怀疑了，您继续吧"),
    ],
    "a2": [
        (18, "我正在驾驶车辆，没法分心接电话"),
        (20, "我不是在开车，是正在参加会议"),
    ],
    "a2-7": [(25, "明天下午两点整给我电话"), (27, "现在说不准几点，再等等看")],
    "a3": [
        (29, "还在职，不希望现单位知道我找工作"),
        (32, "我已经决定不去入职，这个机会不要了"),
    ],
    "a3-6-a": [
        (57, "可以另找同事核实，我同意"),
        (59, "不可以另找同事，只用我提供的证明人"),
    ],
    "a4": [
        (51, "不是网页坏了，是刷脸总失败"),
        (53, "还没到刷脸，整个网页就报错打不开"),
    ],
    "b16-2-a": [
        (40, "拦截短信里找到了，之前没注意"),
        (41, "拦截短信里没有，我已经查看了"),
    ],
    "b16-2-b": [
        (40, "垃圾邮件箱里有，已经看见了"),
        (41, "垃圾邮件箱里也没有，已经查了"),
    ],
    "b16-2-c": [(40, "不带链接的那条看到了"), (38, "不带链接的那条也没收到")],
    "b16-2-e-2": [
        (56, "可以给邮箱，发到person@example.org吧"),
        (55, "不可以，我不愿意提供邮箱"),
    ],
}
AMBIGUOUS = {
    "3-2": ("方便不方便我也说不准", [6, 7]),
    "4-2": ("收到过，好像填过了，又好像还没填", [36, 37]),
    "b12-4": ("我找到了点东西，但不确定是不是那条", []),
    "b14-2": ("最近又忙，那个页面我也不太会弄", [42, 43]),
    "5-2-b-2": ("做没做完我都记不清了", []),
    "5-4-c": ("也许能按时，也许来不及，我还不能确定", []),
    "a1": ("号码看着怪怪的，会不会是骗子", [11, 12]),
    "a1-5": ("您这么说我还是拿不准", []),
    "a2": ("既在开车又要赶去医院有急事", [18, 19]),
    "a2-7": ("下午两三点左右吧", [25, 26]),
    "a3": ("怕现公司知道，也怕资料泄露", [29, 31]),
    "a3-6-a": ("要不行，要不不行，我再想想", []),
    "a4": ("人脸失败了，而且资料也写错了", [51, 52]),
    "b16-2-a": ("有一条短信，但我不确定是不是您说的", []),
    "b16-2-b": ("有一封邮件，但我不确定是不是您说的", []),
    "b16-2-c": ("好像收到过，又好像不是", []),
    "b16-2-e-2": ("我想想要不要给邮箱", []),
}


def dump(path, data):
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def source_row(root):
    for n, line in enumerate(DOC.read_text().splitlines(), 1):
        if line.startswith(f"| **{root}**"):
            return n, line
    raise ValueError(root)


def build():
    intents = {i["id"]: i for i in load_intents()}
    nodes = {}
    all_sides = sorted(
        {f"7-{n}" for group in SIDE_GROUPS.values() for n in group},
        key=lambda x: int(x[2:]),
    )
    for node, name, root, is_main, edges, prompt, prompt_source in SPECS:
        line_no, line = source_row(root)
        routes = []
        for n, branch in edges:
            ident = f"7-{n}"
            assert branch in line, (node, branch)
            # Every edge cites a branch clause plus its original intent-table definition.
            clause = next(part for part in line.split("<br/>") if branch in part)
            routes.append(
                {
                    "intent_id": ident,
                    "branch_ref": branch,
                    "all_product_branch_refs": intents[ident]["workflow_branches"],
                    "sources": [
                        {
                            "file": DOC.name,
                            "line": line_no,
                            "quote": " ".join(clause.split()),
                        },
                        intents[ident]["source"],
                    ],
                }
            )
        allowed = [r["intent_id"] for r in routes]
        nodes[node] = {
            "name": name,
            "allowed_intents": allowed,
            "intent_branches": routes,
            "text_scope": "documented local response / classification subtree",
            "event_intents": ["7-1"] if node in ("3-2", "4-2", "b12-4") else [],
            "previous_assistant": prompt,
            "prompt_source": prompt_source,
            "main_flow": is_main,
            "side_route_intents": all_sides if is_main else [],
            "allowed_including_documented_sides": sorted(
                set(allowed + (all_sides if is_main else [])), key=lambda x: int(x[2:])
            ),
        }
    map_data = {
        "schema_version": 1,
        "scope_note": "allowed_intents 是本地回应分类集合，不是整通电话全部合法意图。M5旁路另列；合并审计不是新工作流策略。",
        "source_hashes": {DOC.name: sha256(DOC), PRODUCT.name: sha256(PRODUCT)},
        "side_route_source": {
            "file": PRODUCT.name,
            "line": 78,
            "quote": "旁路可从任意主流程节点横切进入",
        },
        "side_groups": {k: [f"7-{n}" for n in v] for k, v in SIDE_GROUPS.items()},
        "nodes": nodes,
        "unmapped_notes": [
            "b15、补发状态轮询是后台状态，不是用户意图。",
            "a2-6压缩失败、b3本人过来等没有完整独立7-xx标签；不发明映射。",
            "7-57~59保留文档informed方案的测试，文档标注冒烟期暂缓。",
            "不把父节点所有递归子步骤机械当作同一回应集合；映射以所列decision subtree为边界。",
        ],
    }
    dump(OUT / "workflow_intent_map.yaml", map_data)
    old = yaml.safe_load((OUT / "eval.yaml").read_text())["cases"]
    indexed = {
        re.sub(r"[\W_]+", "", t).lower()
        for item in intents.values()
        for t in item["examples"]
    }
    cases = []

    def add(node, text, expected, category, source, **extra):
        norm = re.sub(r"[\W_]+", "", text).lower()
        overlap = norm in indexed
        cases.append(
            {
                "id": f"node-{len(cases):04d}",
                "current_node": node,
                "text": text,
                "expected": expected,
                "category": category,
                "split": "source_overlap" if overlap else "heldout",
                "context": [
                    {"role": "assistant", "content": nodes[node]["previous_assistant"]}
                ],
                "source": source,
                **extra,
            }
        )

    for node, definition in nodes.items():
        allowed = definition["allowed_intents"]
        loc_source = {"node": node, "mapping": "workflow_intent_map.yaml"}
        for case in old:
            if (
                case["split"] == "heldout"
                and len(case["expected"]) == 1
                and case["expected"][0] in allowed
            ):
                add(
                    node,
                    case["text"],
                    case["expected"],
                    case["category"],
                    {"old_eval_id": case["id"], **case["source"]},
                )
        for ident in allowed:
            if intents[ident]["original_examples"]:
                add(
                    node,
                    intents[ident]["original_examples"][0],
                    [ident],
                    "obvious_source",
                    intents[ident]["source"],
                )
        for n, text in TARGETS[node]:
            add(node, text, [f"7-{n}"], "polarity", loc_source)
        text, ids = AMBIGUOUS[node]
        add(
            node,
            text,
            [f"7-{n}" for n in ids],
            "ambiguous",
            loc_source,
            annotation="多意图集合或不足以得出确定答案；人工评测标注，不是新增产品规则",
        )
        for text in ["我", "那个", "呃……", ""]:
            add(
                node,
                text,
                [],
                "insufficient",
                loc_source,
                annotation="要求拒识的实验标注；空文本不表示静默超时",
            )
        for case in old:
            if case["category"] == "ood":
                add(node, case["text"], [], "ood", {"old_eval_id": case["id"]})
        # Negative examples with literal intended meanings distinct from allowed labels.
        # Overlapping broad/narrow labels are not silently declared invalid: list them separately.
        targets = [
            ("7-52", "我刚才把身份证号码填错了，可以修改吗？"),
            ("7-56", "给您邮箱applicant@example.net，请登记"),
            ("7-48", "我答应在您给的截止时间之前完成授权"),
            ("7-40", "我刚翻了垃圾邮件箱，找到那封授权邮件了"),
            ("7-53", "整个授权网页报系统错误，根本打不开"),
        ]
        overlap_pairs = {
            frozenset(p)
            for p in [
                ("7-43", "7-53"),
                ("7-8", "7-37"),
                ("7-8", "7-46"),
                ("7-37", "7-46"),
            ]
        }
        for ident, text in targets:
            if ident in allowed:
                continue
            if any(frozenset((ident, a)) in overlap_pairs for a in allowed):
                continue
            add(
                node,
                text,
                [],
                "out_of_node",
                intents[ident]["source"],
                global_intent=ident,
                documented_side_route=ident in definition["side_route_intents"],
                annotation="局部分类器应拒识；若标记documented_side_route，整通电话仍可由旁路处理",
            )
    dump(
        OUT / "node_eval.yaml",
        {
            "schema_version": 1,
            "notes": "节点上下文由固定node提供，不由预期标签决定；索引/阈值沿用首轮；新增样本均标注而非训练。",
            "cases": cases,
        },
    )
    print(
        f"{len(nodes)} nodes; {len(cases)} node cases; counts={sorted({len(n['allowed_intents']) for n in nodes.values()})}"
    )


if __name__ == "__main__":
    build()
