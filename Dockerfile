FROM apache/airflow:2.8.3-python3.10

# Switch to root to copy files
USER root

COPY requirements.txt /requirements.txt

# Switch back to airflow user BEFORE installing packages
USER airflow

RUN pip install --no-cache-dir -r /requirements.txt
