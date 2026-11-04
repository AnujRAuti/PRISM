---
name: feature-engineering
description: Create, select, and validate features that generalize—time-window aggregates, interaction terms, encodings, and leakage-safe point-in-time joins—with ablation evidence.
metadata:
  domain: ai-and-ml
  version: 1.0.0
  risk: medium
---

# Feature Engineering

## 1. Purpose

Improve model performance by constructing features that expose the underlying signal, while avoiding the two classic traps: leakage (features that encode the future or the label) and train/serve skew (features that cannot be computed at inference time). This skill provides concrete feature families, point-in-time correctness procedures, selection methods, and the ablation discipline that proves a feature earns its maintenance cost.

**Scope:** datasets you are authorized to use. Aggregations over user behavior are personal data—apply minimization and access controls.

## 2. Activation Conditions

- Model performance plateaus with raw features.
- Adding domain knowledge (seasonality, recency, interactions) to a model.
- Building a feature store or sharing features across models.
- Diagnosing suspiciously high offline performance (leakage suspicion).
- Keywords: feature engineering, aggregates, rolling window, point-in-time, leakage, interaction, binning, embedding, feature selection, feature store.

## 3. When Not to Use

- Raw data cleanup only (use data-preprocessing).
- Deep learning on raw signals where representation learning is the point (images, audio, text with pretrained models).
- When the dataset is too small to support extra features (risk of overfitting).

## 4. Required Context

1. The prediction time and the information available at that moment.
2. Event tables with timestamps and entity keys.
3. Business domain knowledge: what actually drives the outcome.
4. Serving constraints: latency budget, available precomputed stores.
5. Current baseline feature set and model.

## 5. Operating Procedure

1. **Define the prediction timestamp** (`as_of`) for each training row. Every feature must be computable from data with `event_ts <= as_of`.
2. **List candidate feature families**: recency/frequency/monetary, rolling aggregates, trends, categorical encodings, interactions, text statistics, external joins.
3. **Compute point-in-time joins**: use `asof` joins, not naive joins on IDs, and verify no future data leaks in.
4. **Build features in a shared module** callable in both training and serving.
5. **Handle cold start** explicitly: new entities have no history—define default values and an indicator feature.
6. **Prove value with ablation**: measure the metric with and without the feature group, using the same split and seed.
7. **Select**: remove features with near-zero importance AND no plausible mechanism; avoid recursive feature elimination on tiny datasets.
8. **Detect drift-prone features**: features whose distribution depends on external conditions (traffic, seasonality) need monitoring.
9. **Document each feature**: definition, source table, window, cadence, owner, and known failure modes.
10. **Version the feature set**; changing a definition is a breaking change that requires re-evaluation.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Dataframes | pandas, Polars, DuckDB, Spark |
| Rolling/point-in-time | `merge_asof`, window functions in SQL |
| Feature store | Feast, Tecton, Hopsworks |
| Encoding | category_encoders, target encoding with CV |
| Selection | `SelectFromModel`, permutation importance, SHAP |
| Validation | pandera, statistical tests (`scipy.stats`) |
| Orchestration | dbt models, Airflow/Dagster jobs |

## 7. Practical Implementation

**Point-in-time (asof) join in pandas:**

```python
import pandas as pd

orders = orders.sort_values("created_at")
labels = labels.sort_values("label_ts")

# For each label row, attach the most recent order BEFORE label_ts
features = pd.merge_asof(
    labels,
    orders[["customer_id", "created_at", "total_cents"]].sort_values("created_at"),
    left_on="label_ts",
    right_on="created_at",
    by="customer_id",
    direction="backward",
    allow_exact_matches=False,   # avoid using an event at the same instant
)
```

**Rolling aggregates with strict time windows (SQL):**

```sql
WITH base AS (
  SELECT l.customer_id, l.label_ts, o.created_at, o.total_cents
  FROM labels l
  JOIN orders o
    ON o.customer_id = l.customer_id
   AND o.created_at <  l.label_ts          -- NEVER use <= if same-second events are ambiguous
   AND o.created_at >= l.label_ts - INTERVAL '90 days'
),
agg AS (
  SELECT customer_id, label_ts,
         COUNT(*)                                AS orders_90d,
         COALESCE(SUM(total_cents), 0)           AS revenue_90d,
         MAX(created_at)                         AS last_order_ts,
         COUNT(DISTINCT date_trunc('day', created_at)) AS active_days_90d
  FROM base
  GROUP BY customer_id, label_ts
)
SELECT l.*,
       COALESCE(a.orders_90d, 0)   AS orders_90d,
       COALESCE(a.revenue_90d, 0)  AS revenue_90d,
       EXTRACT(EPOCH FROM (l.label_ts - a.last_order_ts)) / 86400.0 AS days_since_last_order
FROM labels l
LEFT JOIN agg a USING (customer_id, label_ts);
```

**Derived ratio features with zero-division guards:**

```python
def safe_ratio(num, den, eps=1e-9):
    return num / (den + eps)

df["avg_order_value_90d"] = safe_ratio(df["revenue_90d"], df["orders_90d"])
df["orders_per_active_day"] = safe_ratio(df["orders_90d"], df["active_days_90d"])
df["revenue_trend"] = safe_ratio(df["revenue_30d"], df["revenue_90d"])
```

**Cold-start handling:**

```python
df["is_new_customer"] = (df["orders_90d"].isna()).astype("int8")
df["orders_90d"] = df["orders_90d"].fillna(0)
df["avg_order_value_90d"] = df["avg_order_value_90d"].fillna(df["global_avg_order_value"])
```

**Interaction features (only where theory supports them):**

```python
df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype("int8")
df["high_value_weekend"] = (df["total_cents"] > 20_000) & df["is_weekend"].astype(bool)
df["high_value_weekend"] = df["high_value_weekend"].astype("int8")
```

**Ablation harness:**

```python
from sklearn.metrics import average_precision_score

def ablate(model_factory, X, y, train_idx, val_idx, groups):
    base = model_factory()
    base.fit(X.iloc[train_idx], y.iloc[train_idx])
    full = average_precision_score(y.iloc[val_idx], base.predict_proba(X.iloc[val_idx])[:, 1])
    print(f"full={full:.4f}")
    for name, cols in groups.items():
        m = model_factory()
        m.fit(X.iloc[train_idx].drop(columns=cols), y.iloc[train_idx])
        score = average_precision_score(y.iloc[val_idx], m.predict_proba(X.iloc[val_idx].drop(columns=cols))[:, 1])
        print(f"without {name:24} delta={full - score:+.4f}")
```

**Permutation importance (model-agnostic):**

```python
from sklearn.inspection import permutation_importance
r = permutation_importance(model, X_val, y_val, n_repeats=20, random_state=7,
                           scoring="average_precision", n_jobs=-1)
for i in r.importances_mean.argsort()[::-1][:15]:
    print(f"{X_val.columns[i]:28} {r.importances_mean[i]:+.4f} ± {r.importances_std[i]:.4f}")
```

**Leakage tripwire test:**

```python
def test_no_future_leakage(df):
    # Every feature's source timestamp must precede label_ts
    assert (df["last_order_ts"] < df["label_ts"]).all()
    assert (df["orders_90d"] >= 0).all()
```

## 8. Quality Standards

- Every feature has a written definition, window, source, and owner.
- Point-in-time correctness is tested automatically.
- Feature computation code is shared between training and serving (single module or feature store).
- Cold-start defaults and indicators are explicit.
- Ablation results justify each feature group.
- No features derived from the label (e.g. "refund_reason" when predicting refunds).
- Feature distributions are monitored in production (drift).

## 9. Verification and Testing

```bash
pytest -q tests/test_features.py
dbt test --select tag:features        # if features are built in dbt
```

Tests: leakage tripwire passes; asof join excludes same-timestamp events; ratio features never divide by zero; cold-start rows produce valid values; train and serving feature functions produce identical output for a fixed raw record; ablation table regenerated.

## 10. Security Considerations

- Behavioral aggregates can re-identify users; aggregate at coarse granularity and review with privacy stakeholders.
- Feature stores are sensitive: enforce row-level access and audit queries.
- Never derive features from data you are not licensed to use (purchased lists, scraped data).
- Avoid features that enable discriminatory decisions on protected attributes; test subgroup performance.
- Watch for feature-based prompt injection in text features (e.g. user-generated content passed to LLMs).
- Cache/serving systems must not persist raw PII where an aggregate would suffice.

## 11. Failure Handling

- **Offline great, online poor:** skew—check whether each feature is available and computed identically at inference.
- **Leakage suspected:** sort by importance, inspect top features for post-outcome information, remove and re-evaluate.
- **Feature store lag:** define freshness SLAs and fall back to stale values with an indicator rather than failing.
- **High-cardinality blowup:** cap categories, use frequency/target encoding, or embed.
- **Zero importance:** remove it; simplicity is a feature. Keep the ablation record to avoid re-adding it later.

## 12. Expected Deliverables

1. Feature catalogue with definitions and owners.
2. Point-in-time feature computation code.
3. Leakage tests.
4. Ablation and importance tables.
5. Cold-start policy.
6. Monitoring plan for feature drift.

## 13. References

- "Feature Engineering for Machine Learning" (Zheng & Casari).
- scikit-learn `merge_asof` / pandas asof join — https://pandas.pydata.org/docs/reference/api/pandas.merge_asof.html
- Feast feature store — https://docs.feast.dev/
- dbt documentation — https://docs.getdbt.com/
- Google's "ML Test Score" (feature tests) — https://research.google/pubs/pub46555/
- SHAP — https://shap.readthedocs.io/
