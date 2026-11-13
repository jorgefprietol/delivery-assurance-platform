FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928
LABEL org.opencontainers.image.source="https://github.com/jorgefprietol/delivery-assurance-platform" \
      org.opencontainers.image.title="Delivery Assurance Platform" \
      org.opencontainers.image.licenses="MIT"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATABASE_PATH=/data/delivery.db
WORKDIR /opt/delivery
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock \
    && useradd --uid 10001 --create-home delivery \
    && mkdir /data && chown delivery:delivery /data
COPY --chown=delivery:delivery app ./app
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=5)"
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--limit-concurrency", "100"]
