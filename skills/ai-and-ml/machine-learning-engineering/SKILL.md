---
name: machine-learning-engineering
description: Build production ML systems end-to-end—problem framing, data contracts, training, validation, deployment, and monitoring—with leakage prevention and reproducibility.
metadata:
  domain: ai-and-ml
  version: 1.0.0
  risk: medium
---

# Machine Learning Engineering

## 1. Purpose

Turn a business question into a maintained ML system rather than a notebook. This skill covers problem framing (is ML even appropriate?), dataset construction with a data contract, honest validation splits, baseline-first development, reproducible training, and deployment/monitoring. It targets the failure modes that kill ML projects: leakage, no baseline, unreproducible experiments, and a model with no owner after launch.

**Scope:** your own data and infrastructure. Training data often contains personal information—apply the organization's data handling rules before pulling samples.

## 2. Activation Conditions

- Starting an ML project or converting an analysis into a service.
- Improving an existing model's performance or reliability.
- Model performance in production differs from offline metrics.
- Designing a training pipeline or retraining schedule.
- Keywords: machine learning, model training, feature pipeline, train/test split, leakage, baseline, MLflow, retraining, model registry, drift.

## 3. When Not to Use

- The problem has a deterministic rule-based solution (write the rules).
- Deep learning specifics (use deep-learning).
- LLM application patterns (use llm-integration or retrieval-augmented-generation).
- Pure analytics/reporting without prediction.

## 4. Required Context

1. The decision the model informs and the cost of each error type (false positive vs. false negative).
2. Available labeled data: volume, label source, label quality, time span.
3. The serving constraint: batch, real-time, latency budget, hardware.
4. Baseline to beat: current heuristic, human performance, or a trivial model.
5. Regulatory constraints (explainability, fairness, data residency).
6. Who owns the model in production and how retraining is triggered.

## 5. Operating Procedure

1. **Frame the problem**: define the prediction target, the unit of prediction (user/session/order), the prediction time (when is the prediction made, using data available at that moment), and the metric tied to business value.
2. **Establish a baseline** first: majority class, business heuristic, or logistic regression. Record its metric before any complex model.
3. **Write a data contract**: schema, types, allowed ranges, nullability, freshness, and the source of truth for each column.
4. **Build the dataset with a time-aware split**: train < validation < test chronologically for temporal data; group splits by entity when leakage across entities is possible (same user in both splits).
5. **Audit for leakage**: target-derived features, post-outcome data, IDs that encode the label, aggregations computed over the full dataset.
6. **Feature pipeline in code** shared between training and serving (avoid train/serve skew).
7. **Track experiments**: parameters, metrics, dataset version, code commit, environment.
8. **Evaluate with the decision-relevant metric** (precision/recall at a chosen threshold, calibration, cost-weighted error) and report confidence intervals.
9. **Package**: model artifact + preprocessing pipeline + schema version, in a registry.
10. **Deploy**: batch scoring or online inference with fallbacks; shadow mode before full traffic.
11. **Monitor**: input drift, prediction distribution, and outcome metrics; alert on degradation.
12. **Retrain on a schedule or drift trigger**, with a documented promotion gate.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Modeling | scikit-learn, XGBoost, LightGBM, PyTorch |
| Experiment tracking | MLflow, Weights & Biases, DVC |
| Data | pandas, Polars, DuckDB, Spark |
| Pipelines | Airflow, Dagster, Prefect, Kubeflow |
| Serving | FastAPI + joblib/ONNX, BentoML, Ray Serve, KServe |
| Monitoring | Evidently, NannyML, Prometheus custom metrics |
| Registry | MLflow Model Registry, SageMaker, Vertex AI |
| Validation | `pandera`, `great-expectations`, `pydantic` |

## 7. Practical Implementation

**Time-aware split with a leakage guard (Python):**

```python
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

df = pd.read_parquet("data/orders_features.parquet").sort_values("event_ts")

cutoff_train = pd.Timestamp("2025-07-01", tz="UTC")
cutoff_valid = pd.Timestamp("2025-10-01", tz="UTC")

train = df[df["event_ts"] < cutoff_train]
valid = df[(df["event_ts"] >= cutoff_train) & (df["event_ts"] < cutoff_valid)]
test  = df[df["event_ts"] >= cutoff_valid]

# Leakage assertion: no entity overlaps between train and test
overlap = set(train["customer_id"]) & set(test["customer_id"])
assert not overlap, f"{len(overlap)} customers appear in both splits"
```

**Data contract with pandera:**

```python
import pandera.pandas as pa
from pandera.typing import Series

class OrderFeatures(pa.DataFrameModel):
    order_id: Series[str] = pa.Field(unique=True, str_matches=r"^ord_[0-9a-f]{16}$")
    customer_age_days: Series[int] = pa.Field(ge=0, le=36500)
    total_cents: Series[int] = pa.Field(ge=0, le=10_000_000)
    n_previous_orders: Series[int] = pa.Field(ge=0)
    event_ts: Series[pa.DateTime] = pa.Field()

    class Config:
        strict = True
        coerce = True

OrderFeatures.validate(df, lazy=True)
```

**Baseline-first training script:**

```python
import mlflow, joblib
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score

X_train, y_train = train[FEATURES], train["churned"]
X_valid, y_valid = valid[FEATURES], valid["churned"]

baseline = DummyClassifier(strategy="prior").fit(X_train, y_train)
model = LogisticRegression(max_iter=1000, class_weight="balanced").fit(X_train, y_train)

with mlflow.start_run() as run:
    mlflow.log_params({"model": "logreg", "class_weight": "balanced"})
    for name, m in (("baseline", baseline), ("logreg", model)):
        p = m.predict_proba(X_valid)[:, 1]
        mlflow.log_metrics({f"{name}_roc_auc": roc_auc_score(y_valid, p),
                            f"{name}_pr_auc": average_precision_score(y_valid, p)})
    mlflow.sklearn.log_model(model, artifact_path="model",
                             registered_model_name="churn-classifier")
    joblib.dump({"model": model, "features": FEATURES, "schema_version": 3},
                "artifacts/churn-v3.joblib")
```

**Threshold selection tied to the business cost:**

```python
import numpy as np
from sklearn.metrics import precision_recall_curve

p = model.predict_proba(X_valid)[:, 1]
prec, rec, thr = precision_recall_curve(y_valid, p)

COST_FN, COST_FP = 40.0, 5.0      # missed churner vs. wasted retention offer
expected = prec * (-COST_FP) + (1 - prec) * 0  # simplified; use full cost matrix in practice
best_idx = int(np.argmax(rec * (COST_FN * prec - COST_FP * (1 - prec))))
print(f"chosen threshold={thr[best_idx]:.3f} precision={prec[best_idx]:.3f} recall={rec[best_idx]:.3f}")
```

**Serving with a schema check (FastAPI):**

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import joblib, pandas as pd

app = FastAPI()
bundle = joblib.load("artifacts/churn-v3.joblib")

class Features(BaseModel):
    customer_age_days: int = Field(ge=0, le=36500)
    total_cents: int = Field(ge=0, le=10_000_000)
    n_previous_orders: int = Field(ge=0, le=100_000)

@app.post("/v1/churn-score")
def score(f: Features):
    if bundle["schema_version"] != 3:
        raise HTTPException(503, "model version mismatch")
    X = pd.DataFrame([f.model_dump()])[bundle["features"]]
    p = float(bundle["model"].predict_proba(X)[0, 1])
    return {"probability": p, "model_version": "churn-v3"}
```

**Drift check (Evidently, in a scheduled job):**

```python
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset

report = Report(metrics=[DataDriftPreset()])
report.run(reference_data=reference_df, current_data=recent_df)
summary = report.as_dict()["metrics"][0]["result"]
if summary["dataset_drift"]:
    raise SystemExit("drift detected: trigger retraining review")
```

## 8. Quality Standards

- A baseline metric exists before any model is trained.
- Splits are time-aware and leakage-audited; the audit is code, not a comment.
- Every experiment is reproducible from (commit, data version, params).
- The evaluation metric matches the decision, and threshold selection is documented.
- Train/serve feature computation is a shared code path.
- Model artifacts include the preprocessing pipeline and schema version.
- Monitoring covers drift, prediction distribution, and business outcome.
- Ownership and retraining triggers are written down.

## 9. Verification and Testing

```bash
pytest -q tests/                    # data contract, leakage, metric regression tests
mlflow runs list --experiment-id 1  # confirm tracked params/metrics
python scripts/evaluate.py --model artifacts/churn-v3.joblib --split test
```

Tests to include: schema validation fails on bad data; leakage assertion triggers on a crafted overlapping split; the model beats the baseline on the holdout; serving endpoint returns 400 on invalid features and 200 on valid ones; a golden request returns a stable score within tolerance.

## 10. Security Considerations

- Training data may contain PII: minimize columns, hash identifiers, and restrict access; never log raw rows.
- Model artifacts are code-like: loading a pickled model executes code—only load artifacts from your own registry, never from untrusted sources.
- Guard against data poisoning when labels come from user feedback; validate label source and rate-limit contribution.
- Model inversion/extraction: do not return confidence scores at full precision on sensitive classifiers; rate-limit scoring endpoints.
- Protect the serving endpoint with auth and quotas; scoring can be expensive.
- Keep training data out of public repos and notebooks; use access-controlled buckets with audit logging.
- Document intended use and limitations to avoid misuse of the model's outputs.

## 11. Failure Handling

- **Validation metrics great, production poor:** leakage or train/serve skew—compare feature distributions and recompute features from raw events at serving time.
- **Model cannot reproduce:** pin seed, library versions, and data snapshot; record the dataset hash.
- **Class imbalance dominates:** use PR-AUC over ROC-AUC, adjust class weights, and evaluate at the deployed threshold.
- **Retraining makes things worse:** keep the previous version deployable; gate promotion on holdout comparison and a shadow period.
- **Serving latency too high:** batch features, precompute, or switch to a smaller model (see model-optimization).
- **Label delay:** use proxy labels carefully and document the lag; evaluate on the subset with matured labels.

## 12. Expected Deliverables

1. Problem framing document with the decision and cost matrix.
2. Data contract and validation suite.
3. Dataset construction with split and leakage audit.
4. Baseline and candidate models with tracked metrics.
5. Model artifact with preprocessing and schema version.
6. Deployment code and monitoring configuration.
7. Ownership and retraining plan.

## 13. References

- Sculley et al., "Hidden Technical Debt in Machine Learning Systems" — https://papers.nips.cc/paper/5656-hidden-technical-debt-in-machine-learning-systems
- Google Rules of Machine Learning — https://developers.google.com/machine-learning/guides/rules-of-ml
- MLflow documentation — https://mlflow.org/docs/latest/
- scikit-learn user guide — https://scikit-learn.org/stable/user_guide.html
- pandera — https://pandera.readthedocs.io/
- Evidently — https://docs.evidentlyai.com/
- Chip Huyen, *Designing Machine Learning Systems*.
