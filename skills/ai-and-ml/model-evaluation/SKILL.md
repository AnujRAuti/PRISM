---
name: model-evaluation
description: Evaluate models honestly—correct splits, decision-relevant metrics, calibration, confidence intervals, subgroup analysis, and error inspection that finds real failure modes.
metadata:
  domain: ai-and-ml
  version: 1.0.0
  risk: low
---

# Model Evaluation

## 1. Purpose

Determine whether a model is actually good enough for its intended use, and under which conditions it fails. Accuracy alone is almost always the wrong metric. This skill covers split design, metric selection tied to error costs, threshold and calibration analysis, confidence intervals, subgroup/fairness breakdowns, and systematic error inspection.

**Scope:** evaluation on data you are permitted to use. Holdout data must remain unseen until the final decision—repeated peeking turns it into a training set.

## 2. Activation Conditions

- Comparing models or model versions.
- Deciding whether a model can ship.
- A model performs well offline but poorly in production.
- Need to justify metrics to stakeholders or auditors.
- Keywords: evaluation, metrics, precision/recall, F1, ROC-AUC, PR-AUC, calibration, confusion matrix, cross-validation, holdout, confidence interval, subgroup analysis.

## 3. When Not to Use

- Benchmarking LLM capabilities (use ai-evaluation-and-benchmarking).
- Evaluating agents (use agent-evaluation).
- Load/performance testing of the serving system (use performance-testing).

## 4. Required Context

1. The decision the prediction feeds and the cost of each error type.
2. Class distribution and how it will look in production (not just in the dataset).
3. Split strategy already used, and whether the test set has been touched.
4. Protected attributes or segments requiring subgroup reporting.
5. Minimum acceptable performance defined by the product owner.

## 5. Operating Procedure

1. **Define the metric before looking at results** (avoid metric shopping). Write it down with the threshold and the acceptable range.
2. **Verify the split**: no leakage, no duplicates across splits, time-ordered for temporal data, grouped by entity where needed.
3. **Compute the metric suite**: confusion matrix, precision, recall, F1, ROC-AUC, PR-AUC, and calibration (Brier score, reliability curve).
4. **Select an operating threshold** from the cost matrix or a business constraint (e.g. "recall ≥ 0.80 at the highest precision").
5. **Add confidence intervals** (bootstrap) — a point estimate without an interval invites over-interpretation.
6. **Break down by subgroup**: segments, regions, time periods, and any protected attribute. Report metric deltas, not just overall numbers.
7. **Inspect errors**: sample false positives and false negatives, read the inputs, and categorize the failure modes (label noise, ambiguous cases, distribution gaps).
8. **Compare against the baseline** with the same procedure and the same split.
9. **Check stability**: cross-validation or multiple seeds; report variance.
10. **Write the evaluation report** with an explicit ship/no-ship recommendation and the conditions that would invalidate it.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Metrics | scikit-learn `metrics`, `torchmetrics` |
| Calibration | `sklearn.calibration.calibration_curve`, `CalibratedClassifierCV` |
| Bootstrap CIs | `scipy.stats`, custom resampling |
| Subgroup analysis | pandas groupby + metric functions, `fairlearn` |
| Reports | `ydata-profiling`, Evidently, custom notebooks exported to HTML |
| Error analysis | Embedding visualization (UMAP), confusion-pair sampling |

## 7. Practical Implementation

**Metric suite with threshold selection and bootstrap CI:**

```python
import numpy as np
from sklearn.metrics import (confusion_matrix, precision_score, recall_score,
                             f1_score, roc_auc_score, average_precision_score, brier_score_loss)

def evaluate(y_true, y_prob, threshold: float) -> dict:
    y_pred = (y_prob >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return {
        "threshold": threshold,
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_true, y_prob),
        "pr_auc": average_precision_score(y_true, y_prob),
        "brier": brier_score_loss(y_true, y_prob),
        "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
    }

def bootstrap_metric(y_true, y_prob, fn, n: int = 1000, seed: int = 7) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    idx = np.arange(len(y_true))
    vals = []
    for _ in range(n):
        s = rng.choice(idx, size=len(idx), replace=True)
        try:
            vals.append(fn(y_true[s], y_prob[s]))
        except ValueError:
            continue
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return float(lo), float(hi)
```

**Subgroup breakdown:**

```python
import pandas as pd

def subgroup_report(df: pd.DataFrame, prob_col: str, y_col: str, group_col: str, threshold: float) -> pd.DataFrame:
    rows = []
    for group, g in df.groupby(group_col, dropna=False):
        m = evaluate(g[y_col], g[prob_col], threshold)
        m[group_col] = group
        m["n"] = len(g)
        m["positives"] = int(g[y_col].sum())
        rows.append(m)
    return pd.DataFrame(rows).sort_values("n", ascending=False)
```

**Calibration check:**

```python
from sklearn.calibration import calibration_curve
import numpy as np

frac_pos, mean_pred = calibration_curve(y_valid, p_valid, n_bins=10, strategy="quantile")
for mp, fp in zip(mean_pred, frac_pos):
    print(f"predicted={mp:.3f} observed={fp:.3f} gap={fp-mp:+.3f}")
# If the model outputs useful probabilities, recalibrate:
from sklearn.calibration import CalibratedClassifierCV
calibrated = CalibratedClassifierCV(base_model, method="isotonic", cv="prefit").fit(X_calib, y_calib)
```

**Cross-validation with grouping (no entity leakage):**

```python
from sklearn.model_selection import GroupKFold, cross_val_score
cv = GroupKFold(n_splits=5)
scores = cross_val_score(pipeline, X, y, groups=df["customer_id"], cv=cv, scoring="average_precision")
print(f"PR-AUC {scores.mean():.3f} ± {scores.std():.3f}")
```

**Error sample inspection:**

```python
errors = valid.assign(prob=p_valid).query("(churned == 1 and prob < 0.5)")  # false negatives
sample = errors.sample(min(20, len(errors)), random_state=7)
for _, row in sample.iterrows():
    print("----", row["order_id"])
    print({k: row[k] for k in ["n_previous_orders", "days_since_last_order", "support_tickets"]})
```

## 8. Quality Standards

- Metric and threshold are chosen before evaluating, with the rationale documented.
- No metric is reported without sample size and class balance.
- Confidence intervals accompany primary metrics.
- Subgroup results are reported; large deltas are investigated, not buried.
- Calibration is checked whenever probabilities drive decisions.
- Test set is touched once for the final decision, not during iteration.
- Baseline comparison uses identical splits and metrics.

## 9. Verification and Testing

- Recompute metrics from the raw predictions with an independent script; numbers must match.
- Validate split integrity: assert no overlapping IDs and no time-order violations.
- Check that the test set size supports the claimed precision: for a 1% event rate, a ±1% recall claim needs thousands of positives.
- Confirm the evaluation script is deterministic (fixed seeds for bootstrapping and sampling).
- Evidence: metrics table, CI, subgroup table, error samples with categories.

## 10. Security Considerations

- Error samples contain real records: redact PII before sharing reports.
- Do not evaluate on data you lack permission to process, even for "just a quick check".
- Evaluation reports may reveal sensitive business performance; restrict distribution.
- Beware of evaluation gaming: ensure the holdout is not used for feature selection or threshold tuning.
- If the model informs security decisions (fraud, abuse), evaluate adversarial behavior (evasion attempts), not just natural data.

## 11. Failure Handling

- **Metrics too good to be true:** audit for leakage—ID features, target-derived columns, duplicated rows across splits.
- **Huge variance across folds:** the dataset is small or heterogeneous; report intervals and gather more data.
- **Threshold unstable over time:** use a percentile-based threshold updated on a schedule, or recalibrate.
- **Subgroup performance gaps:** do not silently drop the subgroup; report the gap, investigate data coverage, and consider mitigation with the product owner.
- **Metric disagreement (ROC high, PR low):** class imbalance—use PR-AUC for the decision and state the constraint.

## 12. Expected Deliverables

1. Evaluation plan (metric, threshold, decision rule) written before results.
2. Split verification report.
3. Metric suite with confidence intervals.
4. Subgroup breakdown table.
5. Calibration analysis.
6. Error taxonomy with representative examples.
7. Ship/no-ship recommendation with conditions.

## 13. References

- scikit-learn model evaluation guide — https://scikit-learn.org/stable/modules/model_evaluation.html
- "On Calibration of Modern Neural Networks" — https://arxiv.org/abs/1706.04599
- fairlearn — https://fairlearn.org/
- NIST AI RMF (measurement) — https://www.nist.gov/itl/ai-risk-management-framework
- Andrew Ng, "Machine Learning Yearning" (error analysis) — https://www.mlyearning.org/
- TorchMetrics — https://lightning.ai/docs/torchmetrics/stable/
