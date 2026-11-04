---
name: ml-pipeline-engineering
description: Orchestrate reproducible ML pipelines—DAG design, data validation gates, retraining triggers, artifact lineage, and backfills—without hidden manual steps.
metadata:
  domain: ai-and-ml
  version: 1.0.0
  risk: medium
---

# ML Pipeline Engineering

## 1. Purpose

Turn training and scoring into scheduled, observable, rerunnable pipelines rather than Colab notebooks with a cron job. This skill covers DAG design, idempotent tasks, data-quality gates, artifact and lineage tracking, backfills, retraining triggers, and the deployment handoff. The measure of success: any team member can reproduce last month's model from the pipeline, and a failed run is diagnosable from logs alone.

**Scope:** your own data platform. Pipelines touch production data stores—credentials are scoped per task and destructive operations require explicit approval.

## 2. Activation Conditions

- A model must retrain on a schedule or on data change.
- Notebook-to-production migration.
- Batch scoring jobs that must be reliable and backfillable.
- Need lineage: which data produced which model, and which model scored which records.
- Keywords: ML pipeline, DAG, orchestration, Airflow, Dagster, Prefect, retraining, backfill, lineage, feature store, model registry, data validation.

## 3. When Not to Use

- One-off analysis with no production consumer.
- Training that fits in a single script run manually on a workstation with no schedule.
- Model serving concerns (use local-llm-deployment / model serving skills).

## 4. Required Context

1. Data sources, their SLAs, and freshness requirements.
2. Trigger requirements: schedule, upstream data arrival, drift, or manual.
3. Compute environment and cost constraints (spot instances, GPU nodes).
4. Artifact storage (object store, registry) and retention policy.
5. Existing orchestration platform and team familiarity.
6. Failure policy: alerting, retries, and who fixes what.

## 5. Operating Procedure

1. **Define the DAG as separate, idempotent tasks**: `ingest → validate → transform/features → split → train → evaluate → register → deploy → monitor`.
2. **Make every task rerunnable for a given logical date** (partition key), with output paths derived from that key (no overwrites without versioning).
3. **Add data validation gates** that fail the run before training on bad data (schema, ranges, row counts, freshness).
4. **Version data and artifacts**: snapshot inputs or record content hashes; store the dataset identifier with the model.
5. **Log metrics and params** to a tracking server; register the model only when evaluation gates pass.
6. **Separate training from deployment**: registration is a data operation; deployment is a controlled rollout (flag, canary, or manual approval).
7. **Implement retraining triggers** explicitly: schedule, drift alert, performance degradation, or data volume change.
8. **Design backfills**: a parameterized run for a past date must work without manual edits; document how to run one.
9. **Add alerting on: failure, SLA miss, validation rejection, and evaluation regression.**
10. **Record lineage**: dataset → feature set → model → deployment, queryable.
11. **Test the pipeline** in a staging environment with production-shaped data, including a deliberate failure injection.
12. **Document the runbook**: how to inspect a failed task, rerun a single task, and roll back a deployment.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Orchestration | Airflow, Dagster, Prefect, Argo Workflows, Kubeflow Pipelines |
| Transformations | dbt, Spark, Polars, pandas |
| Validation | Great Expectations, pandera, dbt tests |
| Tracking/registry | MLflow, W&B, SageMaker/Vertex AI |
| Artifacts | S3/GCS, DVC, lakeFS, Delta Lake |
| Compute | Kubernetes jobs, Ray, Spark on YARN/K8s |
| Lineage | OpenLineage + Marquez, Dagster asset graph |

## 7. Practical Implementation

**Dagster-style asset pipeline (Python):**

```python
from dagster import asset, Definitions, MaterializeResult, MetadataValue, AssetCheckResult
import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series

class RawOrders(pa.DataFrameModel):
    order_id: Series[str] = pa.Field(unique=True)
    created_at: Series[pa.DateTime]
    total_cents: Series[float] = pa.Field(ge=0)

@asset(partitions_def=None)
def raw_orders() -> pd.DataFrame:
    return pd.read_parquet("s3://data-lake/orders/dt=latest/")

@asset
def validated_orders(raw_orders: pd.DataFrame) -> pd.DataFrame:
    RawOrders.validate(raw_orders, lazy=True)
    return raw_orders

@asset
def features(validated_orders: pd.DataFrame) -> pd.DataFrame:
    df = validated_orders.copy()
    df["order_hour"] = df["created_at"].dt.hour
    df["is_weekend"] = df["created_at"].dt.dayofweek >= 5
    return df

@asset
def trained_model(features: pd.DataFrame) -> MaterializeResult:
    from sklearn.ensemble import GradientBoostingClassifier
    import joblib
    X, y = features[["order_hour", "is_weekend"]], (features["total_cents"] > 10_000).astype(int)
    model = GradientBoostingClassifier(random_state=7).fit(X, y)
    joblib.dump(model, "artifacts/model.joblib")
    return MaterializeResult(metadata={"rows": len(features),
                                       "path": MetadataValue.path("artifacts/model.joblib")})

defs = Definitions(assets=[raw_orders, validated_orders, features, trained_model])
```

**Airflow DAG with validation gate and single-task reruns:**

```python
from airflow.decorators import dag, task
from datetime import datetime, timedelta
import pendulum

@dag(
    schedule="0 3 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=True,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5),
                  "retry_exponential_backoff": True},
    tags=["ml", "orders"],
)
def orders_training():
    @task
    def extract(ds: str | None = None) -> str:
        return f"s3://data-lake/orders/dt={ds}/"

    @task
    def validate(uri: str) -> str:
        import pandas as pd
        from great_expectations.dataset import PandasDataset
        df = PandasDataset(pd.read_parquet(uri))
        res = df.expect_column_values_to_be_between("total_cents", min_value=0)
        if not res.success:
            raise ValueError(f"validation failed: {res.result}")
        return uri

    @task
    def train(uri: str, ds: str | None = None) -> str:
        import mlflow
        with mlflow.start_run(run_name=f"orders-{ds}"):
            mlflow.log_param("data_uri", uri)
            # ... train, log metrics, register model if gates pass
            return f"runs:/{mlflow.active_run().info.run_id}/model"

    uri = extract()
    clean = validate(uri)
    train(clean)

orders_training()
```

**Idempotent task contract:**

```text
Each task MUST:
  1. Take a logical date / partition key as input.
  2. Write to a deterministic output location (e.g. dt=YYYY-MM-DD/).
  3. Be safe to rerun (overwrite the partition atomically or write a new version).
  4. Emit a row-count and checksum as metadata.
  5. Fail loudly on schema or count anomalies.
```

**Data validation gate (dbt tests):**

```yaml
models:
  - name: fct_orders
    columns:
      - name: order_id
        tests: [unique, not_null]
      - name: total_cents
        tests:
          - not_null
          - dbt_utils.accepted_range: {min_value: 0}
    tests:
      - dbt_utils.expression_is_true:
          expression: "created_at <= current_timestamp"
```

**Evaluation gate before registration:**

```python
import mlflow

def promote_if_better(run_id: str, metric: str = "pr_auc", margin: float = 0.0) -> bool:
    client = mlflow.tracking.MlflowClient()
    new = client.get_run(run_id).data.metrics[metric]
    prod = client.get_model_version_by_alias("churn-classifier", "production")
    prod_metric = client.get_run(prod.run_id).data.metrics[metric]
    if new >= prod_metric + margin:
        client.set_registered_model_alias("churn-classifier", "production", prod.version)
        return True
    return False
```

**Retraining trigger check (drift-based):**

```python
def should_retrain(drift_score: float, last_train_days: int, threshold: float = 0.2, max_age: int = 30) -> bool:
    return drift_score > threshold or last_train_days > max_age
```

**Backfill command (Airflow):**

```bash
airflow dags backfill orders_training \
  --start-date 2026-09-01 --end-date 2026-09-30 \
  --reset-dagruns --max-active-runs 1
```

**Lineage record:**

```json
{
  "run_id": "7f3c...",
  "dataset": "s3://data-lake/orders/dt=2026-10-01/",
  "dataset_hash": "sha256:9c1f...",
  "feature_version": "features-v12",
  "model_uri": "models:/churn-classifier/12",
  "git_commit": "a1b2c3d",
  "metrics": {"pr_auc": 0.41, "precision@0.5": 0.63},
  "promoted": true
}
```

## 8. Quality Standards

- Every task is idempotent for a given partition key.
- Validation gates run before expensive compute.
- Lineage is queryable for any deployed model.
- Retries are bounded and backoff is exponential; poison messages fail the run.
- Backfills are supported by design, not by manual surgery.
- Metrics/config/artifacts are recorded per run.
- Alerts fire on failure and on SLA breach.
- No credentials in DAG code; use connections/secret backends.

## 9. Verification and Testing

```bash
# Dagster
dagster asset materialize --select 'validated_orders+'
# Airflow
airflow tasks test orders_training validate 2026-10-01
airflow dags list-runs -d orders_training --state failed
# dbt
dbt build --select tag:ml --store-failures
```

Tests: rerunning a task for the same date produces identical output (hash match); injecting a schema violation fails the run at the validation step; a backfill of 30 days completes without manual intervention; alerts fire on a simulated failure.

## 10. Security Considerations

- Scope credentials per task: the training task should not have write access to production serving systems.
- Use workload identity (OIDC) for cloud access; no long-lived keys in DAG code.
- Orchestrator UIs can trigger arbitrary code: restrict access, enable auth, and disable example DAGs.
- Data snapshots may contain PII: encrypt at rest, restrict access, and honor deletion requests.
- Pipelines that pull external data must validate it (schema and sanity) before it influences a model.
- Audit who promoted a model to production and when.

## 11. Failure Handling

- **Task fails on retry but succeeds manually:** environment drift or non-idempotent writes; capture the exact command and inputs in logs.
- **Partial partition written:** write to a temp prefix and atomically move; never leave half-written partitions readable.
- **Metrics missing from a run:** training proceeded without evaluation—make evaluation a hard dependency of registration.
- **Backfill floods the warehouse:** throttle `max_active_runs`, run off-peak, and use a dedicated slot pool.
- **Schema change upstream:** validation gate fails fast; coordinate the contract change with the data owner before patching.
- **Stale features at serving:** freshness SLA alert; fall back to last-known-good with an indicator.

## 12. Expected Deliverables

1. DAG definition with task contracts and dependencies.
2. Validation gates and their failure behavior.
3. Artifact/lineage schema and example record.
4. Retraining trigger policy.
5. Backfill procedure and a rehearsal result.
6. Alerting configuration and runbook.
7. Staging test results including injected failure.

## 13. References

- Dagster docs — https://docs.dagster.io/
- Apache Airflow docs — https://airflow.apache.org/docs/
- Prefect docs — https://docs.prefect.io/
- dbt docs — https://docs.getdbt.com/
- Great Expectations — https://docs.greatexpectations.io/
- OpenLineage — https://openlineage.io/
- MLflow Model Registry — https://mlflow.org/docs/latest/model-registry.html
- Google, "MLOps: Continuous delivery and automation pipelines" — https://cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning
