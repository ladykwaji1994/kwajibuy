FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
RUN mkdir -p /app/data

ENV KWAJIBUY_DB_PATH=/app/data/kwajibu.sqlite3
ENV KWAJIBUY_HOST=0.0.0.0
ENV FLET_SERVER_IP=0.0.0.0
ENV FLET_SERVER_PORT=8550

EXPOSE 8550
CMD ["python", "main.py"]