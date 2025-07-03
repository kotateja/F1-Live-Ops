from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
from flin.livetiming import poll_and_write_feature_store

with DAG(
    "ingest_live",
    start_date=datetime(2025, 1, 1),
    schedule=timedelta(seconds=30),  # every 30 s
    catchup=False
) as dag:
    ingest = PythonOperator(
        task_id="live_poll",
        python_callable=poll_and_write_feature_store
    )
