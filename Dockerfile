FROM python:3.11-slim

WORKDIR /app

# CPU-only PyTorch first: the default version includes GPU libraries (several GB) we don't need
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
ENV PYTHONPATH=/app/src

EXPOSE 8000
CMD ["uvicorn", "bankingsupportagent.api:app", "--host", "0.0.0.0", "--port", "8000"]