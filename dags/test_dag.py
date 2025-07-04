from __future__ import annotations

import pendulum

from airflow.decorators import dag
from airflow.operators.bash import BashOperator

@dag(
    dag_id="test_dag",
    schedule=None,
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    tags=["testing"],
)
def test_airflow_setup():
    """
    A simple test DAG to confirm the Airflow setup is working.
    """
    run_this = BashOperator(
        task_id="print_confirmation",
        bash_command='echo "Airflow is reading DAGs from the dags folder successfully!"',
    )

test_airflow_setup()