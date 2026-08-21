FROM python:3.12-slim AS base
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY migrations/ migrations/
COPY alembic.ini .
USER 1001:1001
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import httpx; httpx.get('http://localhost:8080/health').raise_for_status()"
EXPOSE 8080
CMD ["python", "-m", "src.bot"]
