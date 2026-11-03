FROM python:3.11-slim

WORKDIR /app

# CPU-only PyTorch first: the default version includes GPU libraries (several GB) we don't need
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# requirements.txt is generated from uv.lock (see README), so the image uses the same versions as development
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY data/docs ./data/docs
ENV PYTHONPATH=/app/src

# Hugging Face's newer "xet" download path fails on some Docker networks; plain HTTPS downloads always work
ENV HF_HUB_DISABLE_XET=1

# Download the two small AI models now, so the first start does not depend on the internet and is fast.
# (docker-compose's model-cache volume starts out as a copy of this folder.)
RUN python -c "from bankingsupportagent.config import EMBEDDING_MODEL, RERANK_MODEL; \
from sentence_transformers import CrossEncoder, SentenceTransformer; \
SentenceTransformer(EMBEDDING_MODEL); CrossEncoder(RERANK_MODEL)"

EXPOSE 8000
# On the first start the app creates its login keys, demo database and policy index by itself.
# That downloads the AI models, so allow a long start period.
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uvicorn", "bankingsupportagent.api:app", "--host", "0.0.0.0", "--port", "8000"]
