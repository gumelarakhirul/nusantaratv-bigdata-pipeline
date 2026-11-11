"""Four chained DAGs. Unpause all; schedule/trigger only ntv_01_crawling."""
from datetime import timedelta

import pendulum
from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator

DEFAULT_ARGS = {"owner": "nusantaratv", "retries": 2,
                "retry_delay": timedelta(minutes=5)}


def make_dag(dag_id, modules, downstream=None, schedule=None):
    with DAG(
        dag_id=dag_id, schedule=schedule,
        start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Jakarta"),
        catchup=False, max_active_runs=1, default_args=DEFAULT_ARGS,
        tags=["nusantaratv"],
        description="Run only the crawling DAG to start the complete pipeline.",
    ) as dag:
        previous = None
        for task_id, module in modules:
            task = BashOperator(
                task_id=task_id, bash_command=f"python -m {module}",
                cwd="/opt/project", execution_timeout=timedelta(hours=6),
                do_xcom_push=False,
            )
            if previous is not None:
                previous >> task
            previous = task
        if downstream:
            trigger = TriggerDagRunOperator(
                task_id="trigger_next_dag", trigger_dag_id=downstream,
                trigger_run_id="chain__{{ run_id }}",
                wait_for_completion=True, deferrable=True,
                poke_interval=30, retries=0, reset_dag_run=True,
            )
            previous >> trigger
    return dag


# Waiting for the whole downstream chain keeps the next scheduled crawl from
# overwriting the shared Bronze files while another pipeline is still running.
crawling = make_dag("ntv_01_crawling", [
    ("collect_urls", "src.crawling.crawler"),
    ("scrape_details", "src.crawling.scrape_details"),
], "ntv_02_ingestion", "0 7 * * *")
ingestion = make_dag("ntv_02_ingestion", [
    ("initialize_schema", "src.ingestion.initialize_schema"),
    ("ingest_articles", "src.ingestion.ingest_articles"),
], "ntv_03_transformation")
transformation = make_dag("ntv_03_transformation", [
    ("transform_silver", "src.transformation.transform_silver"),
    ("transform_gold", "src.transformation.transform_gold"),
], "ntv_04_analytics")
analytics = make_dag("ntv_04_analytics", [
    ("validate_and_export", "src.analytics.export_analytics"),
])
