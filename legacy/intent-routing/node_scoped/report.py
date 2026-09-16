"""Render measured comparison tables; preserves the previous experiment reports."""

import json
from common import BASE
from node_scoped.router import load_map

NAMES = ["A_global_text", "B_global_context", "C_node_text"]
LABELS = {
    "A_global_text": "A 全局文本",
    "B_global_context": "B 全局+对话",
    "C_node_text": "C 节点文本",
    "S_node_plus_sides": "S 节点+文档旁路（文本）",
}


def pct(x):
    return "N/A" if x is None else f"{100 * x:.1f}%"


def num(x):
    return "N/A" if x is None else f"{x:.1f}"


def table(headers, rows):
    return [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ] + ["| " + " | ".join(map(str, r)) + " |" for r in rows]


def render():
    directory = BASE / "reports/node_scoped"
    report = json.loads((directory / "benchmark.json").read_text())
    mapping = load_map()
    runs = report["runs"]
    lines = [
        "# Workflow-node-scoped semantic-router：测量结果",
        "",
        "本报告的 C 是文档中局部回应/分类子树的候选过滤，不是整通电话禁止其他意图。文档允许横切旁路，因此另有 S 合并文档旁路的审计；相关负例分别标注，不把合法旁路说成产品非法输入。",
        "",
        f"运行日期：{report['created_at']}；CPU：{report['cpu']}；{report['config']['models']['threads']} 个推理线程。",
        f"{report['independent_cases']} 个节点样本（{report['unique_user_texts']} 种不同文本），每配置重复 {report['repeat']} 次。重复和跨节点复用不增加独立语言样本量。",
        "沿用首轮 embedding 模型/revision、129 条索引例句、top-k=5、mean 聚合和阈值0.65，无重排模型、阈值调优、关键词或工作流动作。",
        "A/B/C 对同一节点样本交错运行；B 沿用首轮带上下文索引，查询的上一句统一由节点给定，不根据预期标签选择。C 只编码当前用户发言。",
        "",
        "## 总体比较",
        "",
        "Accuracy 仅计非重叠的单标签正例；Overall 还包含正确拒识，排除多标签歧义。极性和口语改写均在主结果中；产品原话另列。",
    ]
    rows = []
    for name in NAMES:
        m = runs[name]["summary"]["primary"]
        l = m["latency"]
        rows.append(
            [
                LABELS[name],
                pct(m["accuracy"]),
                pct(m["overall_accuracy_including_rejection"]),
                pct(m["invalid_intent_rate"]),
                pct(m["ood_rejection_rate"]),
                pct(m["out_of_node_rejection_rate"]),
                num(l["p50_ms"]),
                num(l["p95_ms"]),
                num(l["p99_ms"]),
            ]
        )
    lines += [""] + table(
        [
            "配置",
            "Accuracy",
            "Overall含拒识",
            "局部无效标签率",
            "OOD拒识",
            "节点外拒识",
            "p50 ms",
            "p95 ms",
            "p99 ms",
        ],
        rows,
    )
    a = runs[NAMES[0]]["summary"]["primary"]
    b = runs[NAMES[1]]["summary"]["primary"]
    c = runs[NAMES[2]]["summary"]["primary"]
    lines += [
        "",
        f"A→C 正例准确率变化：**{(c['accuracy'] - a['accuracy']) * 100:+.1f} 个百分点**；Overall：{(c['overall_accuracy_including_rejection'] - a['overall_accuracy_including_rejection']) * 100:+.1f} 个百分点。",
        f"B→C 正例准确率变化：{(c['accuracy'] - b['accuracy']) * 100:+.1f} 个百分点。",
        f"A→C OOD拒识变化：{(c['ood_rejection_rate'] - a['ood_rejection_rate']) * 100:+.1f} 个百分点；节点外拒识变化：{(c['out_of_node_rejection_rate'] - a['out_of_node_rejection_rate']) * 100:+.1f} 个百分点。",
        "",
        "无效标签率分母为所有对应非重叠请求，指非空预测不在当前局部集合；C 的结构性零并不代表正确，错选合法候选计入混淆或强制匹配。",
        "",
    ]
    lines += table(
        [
            "配置",
            "拒识Precision",
            "拒识Recall",
            "正例误拒",
            "负例强制命中节点内",
            "节点外强制命中节点内",
            "错误",
        ],
        [
            [
                LABELS[n],
                pct((m := runs[n]["summary"]["primary"])["rejection_precision"]),
                pct(m["rejection_recall"]),
                pct(m["false_rejection_rate"]),
                pct(m["forced_in_scope_match_rate"]),
                pct(m["out_of_node_forced_match_rate"]),
                m["errors"],
            ]
            for n in NAMES
        ],
    )
    lines += [
        "",
        "拒识 precision=正确拒识/所有确定标注样本中的实际拒识；recall=正确拒识/应拒识样本。多标签集合不算拒识真值，后端错误不算正确拒识。",
        "",
        "## 逐节点",
        "",
    ]
    rows = []
    for node in mapping:
        ms = [runs[n]["summary"]["per_node"][node] for n in NAMES]
        rows.append(
            [
                node,
                mapping[node]["name"],
                len(mapping[node]["allowed_intents"]),
                *(pct(m["accuracy"]) for m in ms),
                f"{100 * (ms[2]['accuracy'] - ms[0]['accuracy']):+.1f}",
                pct(ms[2]["out_of_node_rejection_rate"]),
            ]
        )
    lines += table(
        [
            "节点",
            "局部判断",
            "候选数",
            "A准确率",
            "B准确率",
            "C准确率",
            "C−A pp",
            "C节点外拒识",
        ],
        rows,
    )
    lines += [
        "",
        "## 候选集大小",
        "",
        "这里按节点局部集合大小分组；A/B 实际仍检索58个标签。不同大小组属于不同节点、意图和难度，不是受控改变 K 的因果实验。",
        "",
    ]
    rows = []
    for k in sorted(runs[NAMES[2]]["summary"]["by_candidate_count"], key=int):
        ms = [runs[n]["summary"]["by_candidate_count"][k] for n in NAMES]
        rows.append(
            [
                k,
                sum(len(v["allowed_intents"]) == int(k) for v in mapping.values()),
                ms[2]["independent_cases"],
                *(pct(m["accuracy"]) for m in ms),
                pct(ms[2]["ood_rejection_rate"]),
                pct(ms[2]["out_of_node_rejection_rate"]),
                num(ms[0]["latency"]["p50_ms"]),
                num(ms[2]["latency"]["p50_ms"]),
                num(ms[2]["latency"]["p95_ms"]),
            ]
        )
    lines += table(
        [
            "K",
            "节点数",
            "样本数",
            "A准确率",
            "B准确率",
            "C准确率",
            "C OOD拒识",
            "C节点外拒识",
            "A p50",
            "C p50",
            "C p95",
        ],
        rows,
    )
    lines += [
        "",
        "## 极性与近义专项",
        "",
        "下表只统计专项 polarity 样本，每句取第一轮，列出用户指定的定向错误；C 不允许的标签不会被统计为该方向错误，但仍可能错选其他节点内标签或拒识。",
        "",
    ]
    pairs = [
        ("4-2", "7-38", "7-36"),
        ("b12-4", "7-41", "7-40"),
        ("a1-5", "7-16", "7-15"),
        ("5-2-b-2", "7-46", "7-47"),
    ]
    rows = []
    for node, gold, wrong in pairs:
        counts = []
        denom = 0
        for name in NAMES:
            rr = [
                r
                for r in runs[name]["rows"]
                if r["repeat"] == 0
                and r["current_node"] == node
                and r["category"] == "polarity"
                and r["expected"] == [gold]
            ]
            denom = len(rr)
            counts.append(sum(r["intent_id"] == wrong for r in rr))
        correct = sum(r["intent_id"] == gold for r in rr)
        rejected = sum(r["intent_id"] is None and not r.get("error") for r in rr)
        rows.append([node, f"{gold} → {wrong}", denom, *counts, correct, rejected])
    lines += table(
        [
            "节点",
            "定向混淆",
            "独立目标句",
            "A错误数",
            "B错误数",
            "C错误数",
            "C正确数",
            "C拒识数",
        ],
        rows,
    )
    lines += [""] + table(
        ["配置", "专项极性准确率", "多标签歧义集合命中", "低信息拒识"],
        [
            [
                LABELS[n],
                pct(runs[n]["summary"]["per_category"]["polarity"]["accuracy"]),
                pct(
                    runs[n]["summary"]["per_category"]["ambiguous"][
                        "ambiguous_set_hit_rate"
                    ]
                ),
                pct(
                    runs[n]["summary"]["per_category"]["insufficient"][
                        "rejection_recall"
                    ]
                ),
            ]
            for n in NAMES
        ],
    )
    lines += ["", "## C 常见混淆与新增强制匹配", ""]
    lines += table(
        ["预期", "预测", "次数（含重复）"],
        [
            [p["expected"], p["predicted"], p["count"]]
            for p in c["confusion_pairs"][:15]
        ],
    )
    changes = [
        r
        for r in report["paired_changes_A_C"]
        if not r["expected"] and r["C"] is not None and r["split"] != "source_overlap"
    ]
    lines += ["", "A→C 在负例上的变化示例：", ""] + table(
        ["节点", "输入", "A", "C"],
        [[r["node"], r["text"], r["A"] or "拒识", r["C"]] for r in changes[:12]],
    )
    lines += [
        "",
        "## 文档旁路合并审计",
        "",
        "仅对标记 main_flow 的节点合并产品 M5 的 a1–a6 意图组，得到保守候选上界。这些组含入口和处理后回应，实际 Policy 条件尚未实现；因此不是精确生产合法集。",
        "所有配置在本表使用同一个合并有效集与同一真值：原本局部集合外、但属于文档旁路的输入改为 legal_side_route 正例。此表不与上面的局部准确率直接相减。",
        "",
    ]
    side_ms = {n: runs[n]["side_audit_summary"]["primary"] for n in NAMES[:2]}
    side_ms["S_node_plus_sides"] = runs["S_node_plus_sides"]["summary"]["primary"]
    lines += table(
        ["配置", "Accuracy", "Overall", "合并集合无效率", "OOD拒识", "候选范围"],
        [
            [
                LABELS[n],
                pct(m["accuracy"]),
                pct(m["overall_accuracy_including_rejection"]),
                pct(m["invalid_intent_rate"]),
                pct(m["ood_rejection_rate"]),
                "58"
                if n.startswith(("A_", "B_"))
                else ",".join(
                    map(
                        str,
                        sorted(
                            {
                                len(e["allowed_including_documented_sides"])
                                for e in mapping.values()
                                if e["main_flow"]
                            }
                        ),
                    )
                ),
            ]
            for n, m in side_ms.items()
        ],
    )
    lines += ["", "## 逐意图准确率", ""]
    ids = sorted(
        set().union(*(runs[n]["summary"]["per_intent"] for n in NAMES)),
        key=lambda i: int(i[2:]),
    )
    lines += table(
        ["意图", "A", "B", "C"],
        [
            [
                i,
                *[
                    pct(runs[n]["summary"]["per_intent"].get(i, {}).get("accuracy"))
                    for n in NAMES
                ],
            ]
            for i in ids
        ],
    )
    stream = (
        json.loads((directory / "stream.json").read_text())
        if (directory / "stream.json").exists()
        else None
    )
    if stream:
        lines += [
            "",
            "## 增量 ASR",
            "",
            "主对照 A/C，不拼接历史；复用首轮四条序列并补充五条极性序列。下表按第一次重复展示；JSON 包含各 partial 的标签、score、延迟、变化、拒识及最终正确性。",
            "",
        ]
        sr = {
            n: {s["id"]: s for s in stream["runs"][n] if s["repeat"] == 0}
            for n in ["A_global_text", "C_node_text"]
        }
        rows = []
        for ident, a_s in sr["A_global_text"].items():
            c_s = sr["C_node_text"][ident]
            rows.append(
                [
                    ident,
                    c_s["current_node"],
                    a_s["prediction_changes"],
                    c_s["prediction_changes"],
                    a_s["final_correct"],
                    c_s["final_correct"],
                    a_s["insufficient_accepts"],
                    c_s["insufficient_accepts"],
                    c_s["stable_correct_from_chars"],
                ]
            )
        lines += table(
            [
                "序列",
                "节点",
                "A变化",
                "C变化",
                "A最终正确",
                "C最终正确",
                "A低信息接受",
                "C低信息接受",
                "C稳定正确字数",
            ],
            rows,
        )
        for n in ["A_global_text", "C_node_text"]:
            ss = list(sr[n].values())
            lines += [
                "",
                f"{LABELS[n]}：最终正确 {sum(s['final_correct'] for s in ss)}/{len(ss)}；低信息片段提前接受 {sum(s['insufficient_accepts'] for s in ss)} 次；相邻预测变化 {sum(s['prediction_changes'] for s in ss)} 次。",
            ]
        lines += [
            "",
            "低信息判定是实验人工标注。early_wrong_vs_final 只是与最终意图不一致：ASR 修订中的早期文本可能本来就表示不同意思，不能把该指标等同每条 hypothesis 的语义错误。变化少或分数高不代表可以提交业务动作。",
        ]
    lines += [
        "",
        "## 测量限制与产物",
        "",
        "上下文来自节点固定提示；a1/a2/a3/a4分类入口的辅助提问在数据中明确标为人工实验提示，其余为产品话术节选/改写。不能从本试验推断任意历史对话的效果。",
        "文档存在粗细标签重叠，跨节点负例跳过明显的7-43/7-53重叠，不把这种语义重叠偷偷算成明确非法。更多边界仍需产品复核。",
        "候选集变小会改变 top-k 内每个 route 的例句构成；mean 分数可能改变。小集合既可能降低误拒，也可能强行接受。这次不针对结果调阈值。",
        "分位数是进程内串行 detect 的热请求墙钟时间，不含模型/索引初始化、HTTP、ASR、TTS、队列；三个配置交错执行、无查询缓存。同机背景负载未固定，p99不是SLA。",
        f"旧 reports 顶层产物哈希保持不变：{report['all_previous_artifacts_unchanged']}。",
        "机器可读映射：../../intent_data/workflow_intent_map.yaml；样本：../../intent_data/node_eval.yaml；完整矩阵、逐条案例、分组指标：benchmark.json；ASR：stream.json。",
    ]
    (directory / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print(directory / "RESULTS.md")


if __name__ == "__main__":
    render()
