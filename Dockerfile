FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[api,app,postgres]"
COPY app.py ./
ENV PYTHONUNBUFFERED=1 SHELFWATCH_DB=sqlite:////data/shelfwatch.db
RUN mkdir -p /data
EXPOSE 8000 8501
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uvicorn", "shelfwatch.api:app", "--host", "0.0.0.0", "--port", "8000"]
