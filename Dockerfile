FROM python:3.12-slim AS base
RUN useradd -m -u 1001 botuser
WORKDIR /app
COPY --chown=botuser:botuser pyproject.toml .
COPY --chown=botuser:botuser src/ src/
RUN pip install --no-cache-dir .
USER 1001:1001
ARG PORT
EXPOSE 8082
CMD ["python", "-m", "src.bot"]
