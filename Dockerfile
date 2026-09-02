FROM python@sha256:09f7da3bc104798d0afb40bc08d23ab2da20a76130cec1f2ef170848f5d85217 AS base
RUN useradd -m -u 1001 botuser
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --chown=botuser:botuser pyproject.toml .
COPY --chown=botuser:botuser src/ src/
RUN --mount=type=secret,id=BOTKIT_CORE_TOKEN bash <<'EOF'
    set -e
    if [ -f /run/secrets/BOTKIT_CORE_TOKEN ]; then
      git config --global url."https://x-access-token:$(cat /run/secrets/BOTKIT_CORE_TOKEN)@github.com/ninelegsdog/botkit-core".insteadOf "https://github.com/ninelegsdog/botkit-core"
    fi
    pip install --no-cache-dir .
    rm -f ~/.gitconfig
    apt-get purge -y --auto-remove git
    rm -rf /var/lib/apt/lists/*
EOF
USER 1001:1001
ARG PORT
EXPOSE 8082
CMD ["python", "-m", "src.bot"]
