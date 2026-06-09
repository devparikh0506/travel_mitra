# Travel Mitra API — FastAPI + LangGraph agent.
FROM python:3.12-slim

WORKDIR /srv

# Deps first for layer caching.
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# App + reused packages (agent.embeddings reuses etl.embed).
COPY etl ./etl
COPY agent ./agent
COPY app ./app

ENV PYTHONPATH=/srv
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
