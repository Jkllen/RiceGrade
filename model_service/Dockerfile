FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
WORKDIR /app
COPY requirements-server.txt ./
# Install CPU-only PyTorch wheels; GPU drivers are not available in a standard container.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.7.1 torchvision==0.22.1 && \
    pip install --no-cache-dir -r requirements-server.txt
COPY . /app
RUN python check_bundle.py
EXPOSE 8080
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
