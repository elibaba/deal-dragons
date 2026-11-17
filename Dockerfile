FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY deal_dragons ./deal_dragons
COPY server.py .
# Run as non-root; no secrets are baked into the image (Secret Manager at runtime).
RUN useradd --uid 10001 --create-home agent && chown -R agent /app
USER agent
EXPOSE 8080
CMD ["python", "server.py"]
