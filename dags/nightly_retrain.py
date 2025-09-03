# dags/nightly_retrain.py
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import pendulum
from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
from feast import FeatureStore

# Allow imports from /opt/airflow/src
sys.path.insert(0, "/opt/airflow/src")

from flin import etl_all, preprocess, clean_features, modelling  # noqa: E402

# ---------------------------------------------------------------------
# Constants & Paths
# ---------------------------------------------------------------------
DATA_ROOT = "/opt/airflow/data"
RAW_DIR = os.path.join(DATA_ROOT, "raw")
PROCESSED_DIR = os.path.join(DATA_ROOT, "processed")
GE_ROOT_DIR = "/opt/airflow/great_expectations"

DEFAULT_ARGS = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": pendulum.duration(minutes=5),
}


def _ensure_dirs() -> None:
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)


def _ensure_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Minimal, robust dtype enforcement for persisted Parquet.
    Ensures timedelta columns are proper timedeltas and LapStartDate is tz-aware UTC.
    """
    td_cols = [
        "Time", "LapTime", "PitOutTime", "PitInTime",
        "Sector1Time", "Sector2Time", "Sector3Time",
        "Sector1SessionTime", "Sector2SessionTime", "Sector3SessionTime",
        "LapStartTime",
    ]
    for c in td_cols:
        if c in df.columns and not pd.api.types.is_timedelta64_dtype(df[c]):
            df[c] = pd.to_timedelta(df[c], errors="coerce")

    if "LapStartDate" in df.columns:
        df["LapStartDate"] = pd.to_datetime(df["LapStartDate"], errors="coerce", utc=True)

    return df


@dag(
    dag_id="nightly_retrain_pipeline",
    schedule="0 3 * * *",  # daily at 03:00 UTC
    start_date=pendulum.datetime(2024, 7, 1, tz="UTC"),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["production", "ml"],
)
def nightly_retrain_pipeline():
    @task
    def fetch_data_task(year: int = 2024) -> str:
        """
        Fetch a full season of lap data and persist as Parquet.
        Returns the path to the raw Parquet file.
        """
        import fastf1

        _ensure_dirs()
        cache_dir = os.path.expanduser("~/.fastf1_cache")
        os.makedirs(cache_dir, exist_ok=True)
        fastf1.Cache.enable_cache(cache_dir)

        ctx = get_current_context()
        ds_nodash = ctx["ds_nodash"]

        df = etl_all.fetch_season(year)
        df = _ensure_types(df)

        out_path = os.path.join(RAW_DIR, f"laps_raw_{ds_nodash}.parquet")
        df.to_parquet(out_path, index=False)
        return out_path  # <- pass file path via XCom

    @task
    def process_data_task(raw_path: str) -> str:
        """
        Read raw Parquet, preprocess & feature-engineer, write processed Parquet.
        Returns the *asset name* (basename without .parquet) for GE/Feast steps.
        """
        _ensure_dirs()
        ctx = get_current_context()
        ds_nodash = ctx["ds_nodash"]

        raw_df = pd.read_parquet(raw_path)
        raw_df = _ensure_types(raw_df)

        processed, *_ = preprocess.preprocess(raw_df)
        featured = clean_features.add_advanced_features(processed)
        featured = _ensure_types(featured)

        asset_name = f"clean_laps_{ds_nodash}"
        out_path = os.path.join(PROCESSED_DIR, f"{asset_name}.parquet")
        featured.to_parquet(out_path, index=False)
        return asset_name

    @task(retries=0)
    def validate_with_ge(asset_name: str) -> None:
        """
        Run Great Expectations validation on the processed Parquet written above.
        """
        import great_expectations as gx
        from great_expectations.core.batch import RuntimeBatchRequest
        from great_expectations.checkpoint import Checkpoint

        parquet_path = os.path.join(PROCESSED_DIR, f"{asset_name}.parquet")
        print("Asset name:", asset_name)
        print("Parquet path:", parquet_path)
        print("Dir listing:", os.listdir(PROCESSED_DIR))
        if not os.path.exists(parquet_path):
            raise FileNotFoundError(f"{parquet_path} not found. Upstream task likely didn't write it.")

        # Force-load *only* your classic project
        os.environ["GREAT_EXPECTATIONS_HOME"] = GE_ROOT_DIR
        context = gx.get_context(context_root_dir=GE_ROOT_DIR)
        print("GE datasources:", [d["name"] for d in context.list_datasources()])

        br = RuntimeBatchRequest(
            datasource_name="processed_files",
            data_connector_name="default_runtime_data_connector_name",
            data_asset_name=asset_name,
            runtime_parameters={"path": parquet_path},
            batch_identifiers={"default_identifier_name": asset_name},
            batch_spec_passthrough={"reader_method": "read_parquet"},
        )

        validator = context.get_validator(
            batch_request=br,
            expectation_suite_name="clean_laps_suite",
        )
        print("Head of validated df:\n", validator.head())

        ep_cp = Checkpoint(
            name=f"adhoc_clean_laps_{asset_name}",
            data_context=context,
            validations=[{"batch_request": br, "expectation_suite_name": "clean_laps_suite"}],
            action_list=[
                {"name": "store_validation_result", "action": {"class_name": "StoreValidationResultAction"}},
                {"name": "store_evaluation_params", "action": {"class_name": "StoreEvaluationParametersAction"}},
                {"name": "update_data_docs", "action": {"class_name": "UpdateDataDocsAction"}},
            ],
            run_name_template=f"%Y%m%d-%H%M%S-clean-laps-{asset_name}",
        )

        result = ep_cp.run()
        success = getattr(result, "success", False) or result.get("success", False)
        if not success:
            raise ValueError("Great Expectations validation failed")

    @task
    def train_model_task(asset_name: str) -> None:
        """
        Train/tune models after validation, evaluate on hold-out races,
        log everything to MLflow, and register a blended sklearn model.
        """
        import mlflow
        from mlflow import sklearn as mlflow_sklearn
        from mlflow.models.signature import infer_signature
        from sklearn.metrics import mean_absolute_error
        from sklearn.ensemble import VotingRegressor
        from sklearn.pipeline import Pipeline
        import numpy as np

        parquet_path = os.path.join(PROCESSED_DIR, f"{asset_name}.parquet")
        df = pd.read_parquet(parquet_path)
        df = _ensure_types(df)

        # ---- train with your strict cross-validated routine ----
        best_hgbr, best_lgb, full_pre = modelling.strict_train_tune(df)

        # ---- build evaluation frame (hold-out = last 3 GPs) ----
        eval_df = (df.copy()
                    .dropna(subset=["LapTimeSeconds"])
                    .assign(IsFirstRaceOfSeason=lambda x: (x["Round"] == 1).astype(int)))

        need = [f"LapTime_lag{i}" for i in (1, 2, 3)] + ["DirtyAir_lag1"]
        eval_df = eval_df.dropna(subset=need).reset_index(drop=True)

        features = [
            "RacePct","Position","TyreLife","PrevLapDT","stint_lap",
            "PackCount_S3","GapToLeader","LastRacePace","IsFirstRaceOfSeason",
            "LapTime_lag1","LapTime_lag2","LapTime_lag3","DirtyAir_lag1","DirtyAir",
            "Driver","Compound","Team","LeadLapTime"
        ]
        X = eval_df[features]
        y = eval_df["LapTimeSeconds"]

        gp_order = (eval_df[["Season","Round","GrandPrix"]]
                    .drop_duplicates()
                    .sort_values(["Season","Round"]))
        hold_gps  = set(gp_order.tail(3)["GrandPrix"])
        mask_hold = eval_df["GrandPrix"].isin(hold_gps)

        X_hold, y_hold = X.loc[mask_hold], y.loc[mask_hold]
        X_tune, y_tune = X.loc[~mask_hold], y.loc[~mask_hold]


        # HGBR is already a Pipeline(preprocessor -> regressor)
        # Wrap LGBM with the same preprocessor so both accept raw feature frames
        lgb_pipe = Pipeline([("pre", full_pre), ("reg", best_lgb)])

        # Blend both (pure sklearn -> easy MLflow logging & serving)
        blend_est = VotingRegressor(
            estimators=[("hgbr", best_hgbr), ("lgbm", lgb_pipe)],
            weights=[0.5, 0.5]
        )
        blend_est.fit(X_tune, y_tune)

        # ---- hold-out metrics ----
        h_pred  = best_hgbr.predict(X_hold)
        l_pred  = lgb_pipe.predict(X_hold)
        b_pred  = blend_est.predict(X_hold)

        mae_hgbr  = float(mean_absolute_error(y_hold, h_pred))
        mae_lgb   = float(mean_absolute_error(y_hold, l_pred))
        mae_blend = float(mean_absolute_error(y_hold, b_pred))

        print(f"Hold-out MAE — HGBR:{mae_hgbr:.3f}s  LGBM:{mae_lgb:.3f}s  Blend:{mae_blend:.3f}s")

        # ---- MLflow logging & registration ----
        mlflow.set_experiment("f1-live-ops")
        with mlflow.start_run(run_name=f"nightly-{asset_name}"):
            # Params (best-effort)
            if hasattr(best_hgbr, "get_params"):
                mlflow.log_params({f"hgbr__{k}": v for k, v in best_hgbr.get_params().items()})
            if hasattr(best_lgb, "get_params"):
                mlflow.log_params({f"lgbm__{k}": v for k, v in best_lgb.get_params().items()})

            # Metrics
            mlflow.log_metrics({
                "mae_holdout_hgbr":  mae_hgbr,
                "mae_holdout_lgbm":  mae_lgb,
                "mae_holdout_blend": mae_blend,
            })

            # Artifacts: keep both individual models for debugging/analysis
            mlflow_sklearn.log_model(best_hgbr, artifact_path="hgbr_model")
            mlflow_sklearn.log_model(lgb_pipe,  artifact_path="lgbm_model")

            # Register the blended sklearn model as the serving candidate
            sig = infer_signature(X_hold.iloc[:100], b_pred[:100])
            mlflow_sklearn.log_model(
                sk_model=blend_est,
                artifact_path="model",
                registered_model_name="f1-laptime-blend",
                signature=sig,
                input_example=X_hold.iloc[:5]
            )

        print("Model training + MLflow logging complete.")


    # ---------- Feast tasks ----------
    @task
    def feast_apply_task() -> None:
        """
        Idempotently apply Feast repo (entities, sources, feature views).
        """
        store = FeatureStore(repo_path="/opt/airflow/feature_repo")
        from feature_repo.entities import driver, grand_prix, lap_number
        from feature_repo.lap_features import lap_features, offline
        store.apply([driver, grand_prix, lap_number, offline, lap_features])

    @task
    def feast_materialize_task() -> None:
        """
        Incrementally push new rows to Redis. For first run, do a manual backfill.
        """
        store = FeatureStore(repo_path="/opt/airflow/feature_repo")
        store.materialize_incremental(end_date=datetime.utcnow())

    # ------------------------------------------------------------------
    # DAG Wiring (file-path handoff, no JSON)
    # ------------------------------------------------------------------
    raw_path = fetch_data_task()
    asset_name = process_data_task(raw_path)
    validate = validate_with_ge(asset_name)

    apply_step = feast_apply_task()
    mat_step = feast_materialize_task()

    validate >> apply_step >> mat_step
    validate >> train_model_task(asset_name)


nightly_retrain_pipeline_dag = nightly_retrain_pipeline()
