# Custom Airflow image: stock Airflow 3.x + our ETL/auth dependencies baked in.
# Baking deps (vs _PIP_ADDITIONAL_REQUIREMENTS) avoids reinstalling on every container start.
FROM apache/airflow:3.0.0-python3.12

# Install extras AGAINST Airflow's official constraints so we never upgrade a
# package Airflow owns (e.g. SQLAlchemy) into an incompatible version.
ARG AIRFLOW_VERSION=3.0.0
ARG PYTHON_VERSION=3.12
ENV CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

COPY airflow/requirements.txt /requirements.txt

# Airflow images must pip-install as the 'airflow' user.
USER airflow
RUN pip install --no-cache-dir -r /requirements.txt --constraint "${CONSTRAINT_URL}"
