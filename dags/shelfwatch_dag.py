"""Daily competitor crawl. The task fails (and Airflow alerts) only when the run is quarantined;
a partial crawl succeeds with its issues recorded, so one timed-out page does not page anyone."""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def run_shelfwatch(ds: str, **_):
    import os
    from datetime import date

    from shelfwatch.monitor import Monitor
    from shelfwatch.sources import Frankfurter, LiveSite, OpenErApi
    from shelfwatch.store import Store

    store = Store(os.environ["SHELFWATCH_DB"])
    res = Monitor(store, LiveSite(), Frankfurter(), OpenErApi()).run(date.fromisoformat(ds))
    print(res.status, res.coverage, len(res.alerts), res.issues)
    if res.status == "quarantined":
        raise RuntimeError("crawl quarantined: " + "; ".join(res.issues))


with DAG(
    dag_id="shelfwatch_daily",
    start_date=datetime(2026, 1, 1),
    schedule="0 6 * * *",
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=10)},
    tags=["shelfwatch"],
) as dag:
    PythonOperator(task_id="crawl_check_and_load", python_callable=run_shelfwatch)
