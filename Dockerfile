FROM python@sha256:09f7da3bc104798d0afb40bc08d23ab2da20a76130cec1f2ef170848f5d85217 AS base
RUN useradd -m -u 1001 botuser
WORKDIR /app
COPY --chown=botuser:botuser pyproject.toml .
COPY --chown=botuser:botuser src/ src/
RUN pip install --no-cache-dir .
USER 1001:1001
ARG PORT
EXPOSE 8082
CMD ["python", "-m", "src.bot"]
