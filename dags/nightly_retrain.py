# dags/nightly_retrain.py
from __future__ import annotations

import os
import sys
from datetime import timedelta

import pandas as pd
import pendulum
from airflow.decorators import dag, task
from airflow.operators.python import get_current_context

# Make sure we can import from /opt/airflow/src inside the container
sys.path.insert(0, "/opt/airflow/src")

from flin import etl_all, preprocess, clean_features, modelling  # noqa: E402

# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------
AIRFLOW_DATA_DIR = "/opt/airflow/data/processed"
GE_ROOT_DIR = "/opt/airflow/great_expectations"

DEFAULT_ARGS = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": pendulum.duration(minutes=5),
}


def _restore_time_like_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Utility to restore timedelta/datetime columns after JSON roundtrip if needed."""
    td_cols = [
        "Time",
        "LapTime",
        "PitOutTime",
        "PitInTime",
        "Sector1Time",
        "Sector2Time",
        "Sector3Time",
        "Sector1SessionTime",
        "Sector2SessionTime",
        "Sector3SessionTime",
        "LapStartTime",
    ]
    for col in td_cols:
        if col in df.columns:
            df[col] = pd.to_timedelta(df[col], errors="coerce")

    if "LapStartDate" in df.columns:
        df["LapStartDate"] = pd.to_datetime(df["LapStartDate"], errors="coerce")

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
        Fetch a full season of lap data and return as JSON (orient='split').
        """
        # Enable FastF1 cache
        import fastf1

        cache_dir = os.path.expanduser("~/.fastf1_cache")
        os.makedirs(cache_dir, exist_ok=True)
        fastf1.Cache.enable_cache(cache_dir)

        laps_df = etl_all.fetch_season(year)
        return laps_df.to_json(orient="split")

    @task
    def process_data_task(laps_json: str) -> str:
        """
        Clean & feature-engineer the laps. Returns JSON (orient='split').
        """
        laps_df = pd.read_json(laps_json, orient="split")
        laps_df = _restore_time_like_cols(laps_df)

        processed, *_ = preprocess.preprocess(laps_df)
        featured = clean_features.add_advanced_features(processed)
        return featured.to_json(orient="split")

    @task
    def save_for_validation(featured_json: str) -> str:
        """
        Write the featured DataFrame to Parquet for GE to validate.
        Returns the *asset name* (no .parquet) as required by the GE Filesystem connector.
        """
        ctx = get_current_context()
        ds_nodash = ctx["ds_nodash"]  # e.g. "20250706"

        featured = pd.read_json(featured_json, orient="split")
        featured = _restore_time_like_cols(featured)

        os.makedirs(AIRFLOW_DATA_DIR, exist_ok=True)

        asset_name = f"clean_laps_{ds_nodash}"
        out_path = os.path.join(AIRFLOW_DATA_DIR, f"{asset_name}.parquet")
        featured.to_parquet(out_path, index=False)

        return asset_name

    @task(retries=0)
    def validate_with_ge(asset_name: str) -> None:
        import os
        import great_expectations as gx
        from great_expectations.core.batch import RuntimeBatchRequest
        from great_expectations.checkpoint import Checkpoint

        parquet_path = os.path.join(AIRFLOW_DATA_DIR, f"{asset_name}.parquet")
        print("Asset name:", asset_name)
        print("Parquet path:", parquet_path)
        print("Dir listing:", os.listdir(AIRFLOW_DATA_DIR))
        if not os.path.exists(parquet_path):
            raise FileNotFoundError(f"{parquet_path} not found. Upstream task likely didn't write it.")

        # Force-load *only* your classic project
        os.environ["GREAT_EXPECTATIONS_HOME"] = GE_ROOT_DIR
        context = gx.get_context(context_root_dir=GE_ROOT_DIR)
        print("GE datasources:", [d["name"] for d in context.list_datasources()])

        # Build a RuntimeBatchRequest – no connector discovery involved
        br = RuntimeBatchRequest(
            datasource_name="processed_files",
            data_connector_name="default_runtime_data_connector_name",
            data_asset_name=asset_name,  # just a label
            runtime_parameters={"path": parquet_path},
            batch_identifiers={"default_identifier_name": asset_name},
            batch_spec_passthrough={"reader_method": "read_parquet"},
        )

        # Sanity-check: can we build a validator?
        validator = context.get_validator(
            batch_request=br,
            expectation_suite_name="clean_laps_suite",
        )
        print("Head of validated df:\n", validator.head())

        # Run an *ephemeral* checkpoint with the same BR (bypasses the stored cp)
        ep_cp = Checkpoint(
            name=f"adhoc_clean_laps_{asset_name}",
            data_context=context,
            validations=[{
                "batch_request": br,
                "expectation_suite_name": "clean_laps_suite",
            }],
            action_list=[
                {"name": "store_validation_result",
                "action": {"class_name": "StoreValidationResultAction"}},
                {"name": "store_evaluation_params",
                "action": {"class_name": "StoreEvaluationParametersAction"}},
                {"name": "update_data_docs",
                "action": {"class_name": "UpdateDataDocsAction"}},
            ],
            run_name_template=f"%Y%m%d-%H%M%S-clean-laps-{asset_name}",
        )

        result = ep_cp.run()

        success = getattr(result, "success", False) or result.get("success", False)
        if not success:
            raise ValueError("Great Expectations validation failed")

    @task
    def train_model_task(validated_asset_name: str) -> None:
        """
        Train/tune models only after validation has passed.
        Loads the parquet we validated.
        """
        parquet_path = os.path.join(AIRFLOW_DATA_DIR, f"{validated_asset_name}.parquet")
        df = pd.read_parquet(parquet_path)
        df = _restore_time_like_cols(df)

        best_hgbr, best_lgb, _ = modelling.strict_train_tune(df)
        # TODO: log these to MLflow, save artifacts, etc.
        print("Model training complete.")

    # ------------------------------------------------------------------
    # DAG Wiring
    # ------------------------------------------------------------------
    raw_json = fetch_data_task()
    feat_json = process_data_task(raw_json)
    asset_name = save_for_validation(feat_json)
    validate_with_ge(asset_name) >> train_model_task(asset_name)


nightly_retrain_pipeline_dag = nightly_retrain_pipeline()
