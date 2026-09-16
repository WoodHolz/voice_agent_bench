# Node-scoped experiment plan

1. Read existing FINDINGS, semantic adapter, product table 7 and main/side/branch definitions.
2. Export documented local response sets at actual product node IDs. Preserve intent→branch as metadata and file/line/quote provenance. Timer/backend-only nodes are excluded. Do not synthesize missing intent IDs.
3. Primary C measures local response recognition (2–8 candidates where documented). Product M5 also permits side routes; keep these separate and audit their union on main-flow nodes. An out-of-local-node sample may be a legal side route: never call it invalid for the entire product.
4. Use native SemanticRouter(...)(text, route_filter=allowed_ids); LocalIndex filters vectors before similarity/top-k. Same embedding, examples, top-k, aggregation and threshold as baseline; no keyword rules, tuning, context concatenation in C, or post-filtering.
5. Matched evaluation A global text / B global context / C scoped text. Cases grouped by node, including disjoint paraphrases, short replies, polarity, ambiguity, insufficient text, OOD, and globally known but out-of-local-node replies. Separate source overlap and broad/narrow intent overlap.
6. Report exact-positive and rejection-inclusive accuracy, per node/intent, invalid labels, forced in-scope matches, rejection precision/recall, OOD, matrix/pairs and latency. Group by candidate count without interpreting observational node difficulty as a causal size effect.
7. Repeat original ASR sequences with real relevant node IDs and add polarity sequences. Measure changes, rejection, earliest stable correct and premature wrong matches; no tracking/commit logic.
8. Preserve all prior reports and RealtimeIntent code; publish NODE_SCOPED_FINDINGS.md with measured limits.
