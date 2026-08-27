FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OILSIGNAL_DATA_DIR=/data

WORKDIR /app
COPY backend /app/backend
COPY tests /app/tests
COPY examples /app/examples
RUN pip install --no-cache-dir /app/backend

EXPOSE 8000
CMD ["uvicorn", "oilsignal.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
