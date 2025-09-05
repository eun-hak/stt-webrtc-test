FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY services/api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY services/api /app
COPY config /app/config
EXPOSE 8080
CMD ["python", "main.py"]
