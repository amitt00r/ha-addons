FROM python:3.12-slim
RUN pip install --no-cache-dir wyoming==1.11.0
COPY server.py /app/server.py
CMD ["python", "-u", "/app/server.py"]
