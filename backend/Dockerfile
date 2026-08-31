FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# CPU-only torch build: Whisper only ever runs on CPU here (services/transcriber.py),
# but plain "pip install torch" on Linux pulls the CUDA build (multiple GB of unused
# NVIDIA libraries). Installing it from the CPU index first keeps that out of the image.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["python", "main.py"]
