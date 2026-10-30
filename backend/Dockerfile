FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY geosafe ./geosafe
COPY data ./data
RUN useradd --create-home geosafe
USER geosafe
CMD ["sh", "-c", "uvicorn geosafe.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
