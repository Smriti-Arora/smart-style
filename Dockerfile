FROM node:20-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch==2.7.0 torchvision==0.22.0 \
    && pip install --no-cache-dir -r requirements-prod.txt

COPY server.py engine.py detect.py outfit.py outfit_image.py rag.py hdphotos.py tryon.py ./
COPY styling_guide.txt image_urls.csv ./
COPY --from=ui /ui/dist /app/frontend/dist

RUN mkdir -p hd_cache outfit_cache tryon_cache

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=8s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

ENV PYTHONUNBUFFERED=1
ENV TRYON_ENABLED=0

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
