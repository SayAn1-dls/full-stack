# Wind API image. Build from the repository root so the data snapshot is in the build context:
#   docker build -f backend/Dockerfile -t wind-intelligence-api .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt uvicorn==0.54.0

# Same relative layout as the repository: backend/app/... and data/elexon/... (the app locates data from its own path)
COPY backend/app/__init__.py /srv/backend/app/__init__.py
COPY backend/app/main.py /srv/backend/app/main.py
COPY backend/app/wind /srv/backend/app/wind
COPY data/elexon /srv/data/elexon

RUN useradd --system --no-create-home app
USER app
WORKDIR /srv/backend
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
