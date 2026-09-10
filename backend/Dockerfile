FROM python:3.10-slim

WORKDIR /app

# Install CPU-only torch FIRST — sentence-transformers otherwise pulls the
# full CUDA/GPU build (1GB+ of nvidia-* packages we don't need in Docker).
RUN pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
