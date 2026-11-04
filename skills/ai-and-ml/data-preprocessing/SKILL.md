---
name: data-preprocessing
description: Turn raw data into model-ready datasets—cleaning, type handling, missing values, encoding, scaling, text/image normalization—without leakage or silent data loss.
metadata:
  domain: ai-and-ml
  version: 1.0.0
  risk: medium
---

# Data Preprocessing

## 1. Purpose

Produce a reproducible, leak-free preprocessing pipeline that transforms raw records into a model-ready dataset, with every decision recorded. Preprocessing errors silently destroy model quality far more often than architecture choices do: fitting scalers on the full dataset, dropping rows with missing labels, or encoding high-cardinality categoricals wrongly. This skill makes each step explicit and testable.

**Scope:** datasets you are authorized to process. Raw data may contain personal information—apply minimization and retention rules, and never copy production data into notebooks or repositories.

## 2. Activation Conditions

- Building the dataset stage of a training pipeline.
- Data quality problems (missing values, mixed types, outliers, duplicates).
- Train/serve feature skew.
- Preparing text, image, or time-series data for modeling.
- Keywords: data cleaning, missing values, imputation, one-hot, target encoding, scaling, normalization, outliers, deduplication, data quality, leakage.

## 3. When Not to Use

- Dataset versioning/governance design without transformation work (use ml-pipeline-engineering).
- Feature derivation and selection (use feature-engineering).
- LLM text chunking and embedding preparation (use retrieval-augmented-generation).

## 4. Required Context

1. Data source(s), extraction method, and refresh cadence.
2. Schema expectations and business meaning of each column.
3. Label definition and label availability timing.
4. Serving constraints: which raw fields will exist at inference time.
5. Privacy classification of each column.

## 5. Operating Procedure

1. **Profile the raw data**: row/column counts, dtypes, null rates, cardinality, min/max, duplicate rate. Use `df.info()`, `df.describe(include="all")`, and value counts for categoricals.
2. **Write the expected schema** as code (pandera/Pydantic) and validate on ingest; fail loudly on mismatch.
3. **Deduplicate** with an explicit key; log how many rows were removed and why.
4. **Handle missing values** per column with a documented policy: drop (only if missingness is uninformative), constant fill (with an indicator column), median/mode imputation (fit on train only), or model-based imputation.
5. **Fix types**: dates to UTC timestamps, numerics parsed with error handling, categoricals to a consistent vocabulary, booleans normalized.
6. **Handle outliers** deliberately: investigate first; then clip to percentile bounds, log-transform, or keep and use robust models. Never delete silently.
7. **Encode categoricals**: one-hot for low cardinality, ordinal for ordered, target/frequency encoding for high cardinality—computed inside cross-validation folds to prevent leakage.
8. **Scale numerics** where the model requires it (linear models, kNN, neural nets); fit on train only. Tree models do not require scaling.
9. **Split before fitting any transformer**; wrap transformations in a pipeline so the fit/transform boundary is structural, not conventional.
10. **Persist the pipeline** (joblib/ONNX) alongside the model so serving applies identical transformations.
11. **Validate the output**: no nulls where prohibited, ranges within bounds, class balance unchanged, row count accounted for.
12. **Record** all decisions in a data card: removals, fills, transformations, and their justification.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Dataframes | pandas, Polars, DuckDB |
| Validation | pandera, great_expectations, `pydantic` |
| Pipelines | `sklearn.pipeline.Pipeline`, `ColumnTransformer` |
| Encoding | `OneHotEncoder`, `OrdinalEncoder`, `category_encoders` |
| Text | `regex`, `ftfy`, `unicodedata`, tokenizers |
| Images | Pillow, Albumentations, torchvision transforms |
| Time series | pandas resample/rolling, `tsfresh` |
| Versioning | DVC, lakeFS, Delta Lake |

## 7. Practical Implementation

**Profile + schema validation:**

```python
import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series

df = pd.read_parquet("data/raw/orders.parquet")
print(df.shape, df.isna().mean().round(3).sort_values(ascending=False).head(10))
print(df["status"].value_counts(dropna=False).head(10))
print("dupes:", df.duplicated(subset=["order_id"]).sum())

class RawOrders(pa.DataFrameModel):
    order_id: Series[str] = pa.Field(unique=True)
    customer_id: Series[str]
    created_at: Series[pa.DateTime]
    status: Series[str] = pa.Field(isin=["pending", "paid", "shipped", "cancelled"])
    total_cents: Series[float] = pa.Field(ge=0)
    country: Series[str] = pa.Field(str_length={"min_value": 2, "max_value": 2})

validated = RawOrders.validate(df, lazy=True)
```

**Leak-free preprocessing pipeline:**

```python
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder

numeric = ["total_cents", "n_items", "customer_age_days"]
categorical = ["country", "channel", "device"]
datetime_feats = ["order_hour", "day_of_week"]

preprocess = ColumnTransformer(
    transformers=[
        ("num", Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
        ]), numeric),
        ("cat", Pipeline([
            ("impute", SimpleImputer(strategy="constant", fill_value="__missing__")),
            ("encode", OneHotEncoder(handle_unknown="infrequent_if_exist",
                                     min_frequency=50, sparse_output=False)),
        ]), categorical),
    ],
    remainder="drop",
    verbose_feature_names_out=False,
)
# Fit ONLY on training split:
X_train_t = preprocess.fit_transform(train[numeric + categorical])
X_test_t = preprocess.transform(test[numeric + categorical])
```

**High-cardinality encoding without leakage (target encoding inside CV):**

```python
from category_encoders import TargetEncoder
from sklearn.model_selection import KFold
import numpy as np

def target_encode_oof(tr_df, te_df, col, target, n_splits=5, smoothing=20):
    oof = np.full(len(tr_df), np.nan)
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=7)
    for fit_idx, apply_idx in kf.split(tr_df):
        enc = TargetEncoder(cols=[col], smoothing=smoothing)
        enc.fit(tr_df.iloc[fit_idx][[col]], tr_df.iloc[fit_idx][target])
        oof[apply_idx] = enc.transform(tr_df.iloc[apply_idx][[col]])[col]
    enc_full = TargetEncoder(cols=[col], smoothing=smoothing).fit(tr_df[[col]], tr_df[target])
    return oof, enc_full.transform(te_df[[col]])[col]

merchant_oof, merchant_test = target_encode_oof(train, test, "merchant_id", "is_fraud")
```

**Missing-value policy with an indicator:**

```python
train["support_tickets_missing"] = train["support_tickets"].isna().astype("int8")
train["support_tickets"] = train["support_tickets"].fillna(0)   # known: no tickets recorded
# Document: NULL means "no ticket system data before 2024-06"; indicator preserves that signal.
```

**Text normalization (deterministic):**

```python
import re, unicodedata

def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"https?://\S+", "<url>", s)
    return s.lower()

# Apply identically at training and serving time — put it in the shared pipeline.
```

**Deduplication with accounting:**

```python
before = len(df)
df = df.sort_values("created_at").drop_duplicates(subset=["order_id"], keep="last")
print(f"dedup: removed {before - len(df)} rows ({(before-len(df))/before:.2%})")
```

**Output validation:**

```python
assert preprocess.transform(test[numeric + categorical]).shape[0] == len(test)
assert not pd.isna(X_train_t).any(), "unexpected NaNs after imputation"
```

## 8. Quality Standards

- Every transformer is fit on training data only; the pipeline enforces this structurally.
- The same preprocessing code path runs at training and serving.
- Row-count accounting: input rows = output rows + dropped rows, with reasons.
- Missing-value policy is documented per column, not global.
- Categorical vocabularies are versioned; unknown categories handled explicitly at serving.
- Data card records transformations and their justification.
- No silent coercion: type conversion errors are collected and reported.

## 9. Verification and Testing

```bash
pytest -q tests/test_preprocessing.py
```

Tests: schema validation rejects a malformed fixture; unknown categories at inference do not raise; the pipeline is deterministic across runs; imputation values match train statistics; dedup removes exactly the expected rows; no test row influences fitted parameters (train on a modified test set, assert the transform output is unchanged).

## 10. Security Considerations

- Hash or drop direct identifiers; ensure joins do not reintroduce them.
- Never persist raw production data to local disks or notebooks without approval; use access-controlled storage.
- Watch for prompt/CSV/formula injection if downstream consumers open exports in spreadsheets (prefix `=`, `+`, `-`, `@` with `'`).
- Validate against zip bombs and decompression attacks when ingesting archives.
- Treat column names and file paths from external sources as untrusted (path traversal, SQL injection in column names).
- Deletion requests must propagate to derived datasets; keep lineage so rows can be traced.

## 11. Failure Handling

- **Schema mismatch in production:** fail the job loudly instead of coercing; alert the data owner.
- **Sudden null-rate change:** upstream pipeline or API change—check the source before imputing.
- **Cardinality explosion:** use `min_frequency`/`handle_unknown` and monitor vocabulary size.
- **Precision loss in joins:** cast both sides to the same type (string IDs, not float) before merging.
- **Timezone bugs:** store UTC everywhere; convert for display only; assert `tz` on timestamps.
- **Train/serve skew:** share one feature module; add a parity test that runs the same raw record through both paths and compares outputs.

## 12. Expected Deliverables

1. Data profile report.
2. Schema definition and validation tests.
3. Preprocessing pipeline code (fit/transform separated).
4. Data card with all decisions and removals.
5. Output validation results.
6. Parity test between training and serving transformations.

## 13. References

- scikit-learn preprocessing guide — https://scikit-learn.org/stable/modules/preprocessing.html
- pandas documentation — https://pandas.pydata.org/docs/
- pandera — https://pandera.readthedocs.io/
- category_encoders — https://contrib.scikit-learn.org/category_encoders/
- Google "Training-serving skew" (MLOps) — https://cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning
- Polars user guide — https://docs.pola.rs/
