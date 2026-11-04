---
name: ai-evaluation-and-benchmarking
description: Evaluate AI systems with credible benchmarks—task-grounded test sets, LLM-as-judge calibration, statistical significance, contamination checks, and reproducible reporting.
metadata:
  domain: ai-and-ml
  version: 1.0.0
  risk: low
---

# AI Evaluation and Benchmarking

## 1. Purpose

Produce evaluation results that survive scrutiny. This skill covers building task-specific evaluation sets, choosing or calibrating automated judges, handling variance and significance, detecting benchmark contamination, and reporting results without cherry-picking. It applies to foundation models, fine-tunes, and AI features where "it looks good" is not evidence.

**Scope:** evaluation of systems you build or legitimately test. Do not publish benchmark results for models you do not own without following their evaluation terms; do not use private data in public benchmarks.

## 2. Activation Conditions

- Selecting a model/provider for a product feature.
- Verifying a prompt, fine-tune, or pipeline change.
- Publishing a benchmark or comparison.
- Building an internal eval suite for CI.
- Keywords: evaluation, benchmark, LLM-as-judge, pass@k, MMLU, HELM, eval harness, contamination, statistical significance, model comparison, leaderboard.

## 3. When Not to Use

- Classic ML model evaluation with labeled data and a single metric (use model-evaluation).
- A/B testing in production with real users (that is experiment design with live traffic).
- Agent trajectory evaluation (use agent-evaluation).

## 4. Required Context

1. The decision the evaluation informs (choose a model? ship a prompt? claim superiority?).
2. Task definition with input/output format and success criteria.
3. Budget: number of samples × cost per sample (judge calls are expensive).
4. Available ground truth or the feasibility of human labeling.
5. Target audience for the results and their statistical literacy.

## 5. Operating Procedure

1. **Write the evaluation spec** before running anything: tasks, metrics, sample sizes, and the decision rule (e.g. "ship if pass rate ≥ 90% and no regression on safety set").
2. **Build a task-grounded dataset**: 100–500 cases from real usage, covering the long tail; include negative/adversarial cases and "should refuse" cases.
3. **Split** into dev (iterate) and test (decide); never tune on the test set.
4. **Choose metrics**: exact match/f1 for extraction, rubric scores for open-ended, pass@k for code, retrieval metrics for RAG. Prefer deterministic checkers where possible.
5. **Calibrate any LLM judge** against human labels on 50–100 items; measure agreement (Cohen's κ); fix the rubric until agreement is acceptable (κ > 0.6 at minimum).
6. **Fix judge parameters** (model version, temperature 0, prompt version) and record them; judges drift with model updates.
7. **Run with multiple samples** where outputs are stochastic; report mean and confidence intervals (bootstrap), not single numbers.
8. **Test for contamination**: check whether test items appear in training data (n-gram overlap, exact match) or are leaked on the web; use held-out/private sets for claims.
9. **Report the full picture**: per-task results, variance, cost, latency, and failure examples; state what was not tested.
10. **Version the harness**: dataset hash, judge prompt hash, code commit, and model snapshot IDs.
11. **Automate in CI** for regressions; keep a human review lane for subjective quality.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Standard harnesses | `lm-evaluation-harness`, HELM, `openai/evals`, `inspect_ai` |
| Custom suites | pytest, promptfoo, `deepeval` |
| Judging | Strong LLM judge with rubric, pairwise comparison |
| Statistics | bootstrap CIs, McNemar's test, paired bootstrap |
| Contamination | n-gram overlap scripts, canary strings |
| Human labeling | Label Studio, internal review tools |
| Reporting | notebooks exported to HTML, static reports |

## 7. Practical Implementation

**Evaluation spec (committed with the harness):**

```yaml
name: support-reply-eval-v2
decision: ship prompt v7 only if pass_rate >= 0.90 and safety_pass == 1.0
dataset: evals/support/support_300.jsonl   # sha256 recorded at run time
splits: {dev: 100, test: 200}
metrics:
  - name: correct_action
    type: exact_match            # expected action label
  - name: grounded
    type: llm_judge
    rubric: evals/rubrics/grounded_v1.md
    judge_model: gpt-4.1-mini
  - name: safety
    type: rule                   # must not contain PII or promises of refunds
sampling: {n: 3, temperature: 0.7}
reporting: {bootstrap_ci: 1000, seed: 42}
```

**Runner with bootstrap confidence intervals:**

```python
import json, hashlib, random, numpy as np
from pathlib import Path

def run_case(system, case) -> dict:
    out = system(case["input"])
    return {"id": case["id"], "output": out,
            "correct": int(out.strip() == case["expected"].strip())}

def bootstrap_ci(values: list[int], n: int = 1000, seed: int = 42) -> tuple[float, float]:
    rng = random.Random(seed)
    arr = np.array(values)
    means = [float(np.mean([arr[rng.randrange(len(arr))] for _ in range(len(arr))])) for _ in range(n)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))

cases = [json.loads(l) for l in Path("evals/support/support_300.jsonl").read_text().splitlines()]
test_cases = cases[100:300]

results = [run_case(system_under_test, c) for c in test_cases]
score = sum(r["correct"] for r in results) / len(results)
lo, hi = bootstrap_ci([r["correct"] for r in results])
dataset_hash = hashlib.sha256(Path("evals/support/support_300.jsonl").read_bytes()).hexdigest()[:16]
print(f"pass_rate={score:.3f} CI95=[{lo:.3f},{hi:.3f}] n={len(results)} dataset={dataset_hash}")
```

**Paired comparison with McNemar's test (two systems, same cases):**

```python
from statsmodels.stats.contingency_tables import mcnemar

a = [r["correct"] for r in results_a]
b = [r["correct"] for r in results_b]
b01 = sum(1 for x, y in zip(a, b) if x == 0 and y == 1)   # A wrong, B right
b10 = sum(1 for x, y in zip(a, b) if x == 1 and y == 0)   # A right, B wrong
table = [[0, b01], [b10, 0]]
res = mcnemar(table, exact=True)
print(f"b01={b01} b10={b10} p={res.pvalue:.4f}")
```

**Judge calibration against human labels:**

```python
from sklearn.metrics import cohen_kappa_score

human = [row["human_pass"] for row in calibration_rows]
judge = [row["judge_pass"] for row in calibration_rows]
kappa = cohen_kappa_score(human, judge)
print(f"judge agreement kappa={kappa:.2f}")
assert kappa >= 0.6, "judge rubric needs revision before use"
```

**Judge prompt template (rubric-anchored, order-randomized for pairwise):**

```text
You are grading an assistant reply against a reference.

Criteria:
1. Correctness: does the reply state the correct policy? (0/1)
2. Grounding: is every factual claim supported by the quoted policy text? (0/1)
3. Tone: professional and non-committal about refunds when policy says escalation? (0/1)

Return JSON: {"correctness": 0|1, "grounding": 0|1, "tone": 0|1, "rationale": "<= 40 words"}

<reference_policy>{policy}</reference_policy>
<assistant_reply>{reply}</assistant_reply>
```

**Contamination check (n-gram overlap):**

```python
def ngrams(text: str, n: int = 13) -> set[str]:
    toks = text.lower().split()
    return {" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)}

def overlap_ratio(test_text: str, train_corpus_sample: list[str]) -> float:
    t = ngrams(test_text)
    if not t:
        return 0.0
    hits = sum(1 for tr in train_corpus_sample if t & ngrams(tr))
    return hits / len(train_corpus_sample)
```

**Regression gate in CI:**

```python
import sys
baseline = json.load(open("evals/baselines/support_v6.json"))
current = {"pass_rate": score, "safety_pass": safety_score}
if current["pass_rate"] < baseline["pass_rate"] - 0.02:
    sys.exit(f"regression: {current['pass_rate']:.3f} vs baseline {baseline['pass_rate']:.3f}")
```

## 8. Quality Standards

- The evaluation spec (dataset, metrics, decision rule) is written before running.
- Test split is used once per release decision and never for tuning.
- Judge models are calibrated against human labels and their version is pinned.
- Results include confidence intervals and sample sizes.
- Per-slice results (task type, length, language, difficulty) are reported.
- Contamination is checked before any comparative claim.
- Failure examples are included; a 95% score with no analysis is incomplete.
- Cost and latency accompany quality numbers.

## 9. Verification and Testing

- Re-run the harness and confirm identical results for deterministic settings.
- Verify the dataset hash recorded in the report matches the file used.
- Spot-check 10 judge decisions against human judgment each cycle.
- Confirm the CI gate fails when a deliberately degraded prompt is supplied.
- Check that no test items appear in the dev split (exact and near-duplicate).

## 10. Security Considerations

- Evaluation data may contain customer content: anonymize before storing in the harness repo.
- Judge calls send data to a third party—apply the same data policy as production calls.
- Keep test sets private where leaked sets would invalidate the evaluation (also reduces contamination risk).
- Benchmark results can be gamed; publish the harness version and dataset stats so others can reproduce.
- Do not claim state-of-the-art results on public benchmarks without checking the benchmark's own rules on training data, prompting, and tool use.

## 11. Failure Handling

- **Scores swing between runs:** stochastic outputs—increase samples, fix seeds where possible, report intervals.
- **Judge and human disagree:** revise rubric, add anchors/examples, or replace judge criteria with deterministic checks.
- **Benchmark looks contaminated:** move to private test sets; report both public and private numbers.
- **No clear winner:** report equivalence ("no significant difference at n=300") rather than picking a favorite from noise.
- **Eval set too small for the decision:** state the limitation; collect more data or narrow the claim.

## 12. Expected Deliverables

1. Evaluation spec with decision rule.
2. Dataset with splits, provenance, and hash.
3. Harness code with deterministic checking and judge integration.
4. Judge calibration report (κ) and prompt version.
5. Results table with CIs, per-slice breakdown, cost/latency.
6. Failure analysis with representative examples.
7. Reproducibility record (versions, commits, hashes).

## 13. References

- `lm-evaluation-harness` — https://github.com/EleutherAI/lm-evaluation-harness
- HELM (Stanford CRFM) — https://crfm.stanford.edu/helm/
- `inspect_ai` — https://inspect.aisi.org.uk/
- "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena" — https://arxiv.org/abs/2306.05685
- NIST AI 600-1 (evaluation guidance) — https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf
- Model Cards (Mitchell et al.) — https://arxiv.org/abs/1810.03993
- promptfoo — https://www.promptfoo.dev/docs/
