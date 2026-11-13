FROM apache/airflow:3.3.1-python3.12
COPY docker/requirements-airflow.txt /tmp/requirements-airflow.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" \
    -r /tmp/requirements-airflow.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.12.txt"
