# TS11 — Provider-visible Tool surface ablation

TS10 added a subset-only Turn Tool Working Set. TS11 asks one narrower question on a real existing Harness surface: **does selecting only the Tools needed by one phase reduce Provider-visible schema while preserving exact selected Tool definitions and never widening authority?**

The deterministic treatment uses the existing independent repository-repair surface. The broad baseline exposes `read_workspace`, `patch_workspace`, `run_check`, and `diff_workspace`. The read/validate treatment exposes only `read_workspace` and `run_check`.

`python scripts/assess_tool_surface_ablation.py` serializes both surfaces through the current DeepSeek provider Tool projection, compares canonical bytes/digests, and verifies the selected Tool definitions are unchanged. The retained JSON evidence is generated from current source rather than hand-entered.

This is deliberately **not** a model-behavior result. Smaller schema and narrower authority are mechanically proven; better accuracy, latency, task success, or cross-Provider behavior remain unclaimed until a separately predeclared live experiment is justified.
