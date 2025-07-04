from __future__ import annotations

import pendulum
from airflow.decorators import dag, task
import pandas as pd

# Import the functions from our source code.
# The path '/opt/airflow/src' is mapped to our local './src' folder in docker-compose.yml
import sys
sys.path.insert(0, '/opt/airflow/src')

from flin import etl_all, preprocess, clean_features, modelling

@dag(
    dag_id="nightly_retrain_pipeline",
    schedule="0 3 * * *",  # Run once a day at 3:00 AM UTC
    start_date=pendulum.datetime(2024, 7, 1, tz="UTC"),
    catchup=False,
    tags=["production", "ml"],
)
def nightly_retrain_dag():
    """
    This DAG defines the full pipeline for fetching F1 data, processing it,
    and retraining our prediction models.
    """

    @task
    def fetch_data_task():
        """
        Fetches a full season of data using the new API backend.
        """
        import fastf1
        import os

        print("--- Fetching season data ---")
        cache_dir = os.path.expanduser('~/.fastf1_cache')
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        fastf1.Cache.enable_cache(cache_dir)
        
        laps_df = etl_all.fetch_season(year=2024)
        return laps_df.to_json(orient='split')

    @task
    def process_data_task(laps_df_json: str):
        """
        Takes the raw lap data, cleans it, and engineers features.
        """
        print("--- Processing and Feature Engineering ---")
        laps_df = pd.read_json(laps_df_json, orient='split')

        # Convert columns back to their proper dtypes after JSON serialization
        timedelta_cols = [
            'Time', 'LapTime', 'PitOutTime', 'PitInTime', 'Sector1Time', 
            'Sector2Time', 'Sector3Time', 'Sector1SessionTime', 
            'Sector2SessionTime', 'Sector3SessionTime', 'LapStartTime'
        ]
        for col in timedelta_cols:
            if col in laps_df.columns:
                laps_df[col] = pd.to_timedelta(laps_df[col], errors='coerce')

        if 'LapStartDate' in laps_df.columns:
            laps_df['LapStartDate'] = pd.to_datetime(laps_df['LapStartDate'], errors='coerce')
        
        # Run the two main processing steps
        processed_laps, _, _, _, _ = preprocess.preprocess(laps_df)
        featured_laps = clean_features.add_advanced_features(processed_laps)
        
        return featured_laps.to_json(orient='split')

    @task
    def train_model_task(featured_laps_json: str):
        """
        Uses the final, feature-rich dataset to train our models.
        """
        print("--- Training Models ---")
        featured_laps = pd.read_json(featured_laps_json, orient='split')

        # Convert columns back to their proper dtypes after JSON serialization
        timedelta_cols = [
            'Time', 'LapTime', 'PitOutTime', 'PitInTime', 'Sector1Time',
            'Sector2Time', 'Sector3Time', 'Sector1SessionTime',
            'Sector2SessionTime', 'Sector3SessionTime', 'LapStartTime'
        ]
        for col in timedelta_cols:
            if col in featured_laps.columns:
                featured_laps[col] = pd.to_timedelta(featured_laps[col], errors='coerce')

        if 'LapStartDate' in featured_laps.columns:
            featured_laps['LapStartDate'] = pd.to_datetime(featured_laps['LapStartDate'], errors='coerce')
        
        # This function from your original code trains and tunes the models
        best_hgbr, best_lgb, _ = modelling.strict_train_tune(featured_laps)
        
        # In a future step, we will save these models to MLflow
        print("--- Model training complete ---")
        return "success"


    # Define the workflow structure
    raw_data = fetch_data_task()
    processed_data = process_data_task(raw_data)
    train_model_task(processed_data)

# Instantiate the DAG
nightly_retrain_dag()