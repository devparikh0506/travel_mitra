# Travel Mitra UI — Streamlit chat front-end.
FROM python:3.12-slim

WORKDIR /srv

COPY requirements-ui.txt .
RUN pip install --no-cache-dir -r requirements-ui.txt

COPY ui ./ui

EXPOSE 8501

CMD ["streamlit", "run", "ui/streamlit_app.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]
