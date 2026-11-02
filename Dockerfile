FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system mechman && adduser --system --ingroup mechman mechman

COPY pyproject.toml README.md ./
COPY mechman_bot ./mechman_bot
RUN pip install --no-cache-dir .

RUN chown -R mechman:mechman /app
USER mechman

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

CMD ["mechman-dashboard"]
