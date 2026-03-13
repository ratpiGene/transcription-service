FROM nvidia/cuda:12.3.2-runtime-ubuntu22.04

WORKDIR /app

RUN apt-get update && apt-get install -y \
    python3 python3-pip ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/bin/python3 /usr/bin/python

# 1) torch CUDA (compatible CUDA 12.x)
# (PyTorch fournit ses wheels CUDA sur son index)
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu124 torch

# 2) deps worker
COPY requirements.worker.txt /app/requirements.worker.txt
RUN pip install --no-cache-dir -r /app/requirements.worker.txt

COPY . /app

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "worker.worker", "--daemon", "--jobs-dir", "/app/data/jobs"]