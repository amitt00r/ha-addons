FROM python:3.12-slim
RUN pip install --no-cache-dir paho-mqtt==2.1.0
COPY airport_weather.py /app/airport_weather.py
CMD ["python", "-u", "/app/airport_weather.py"]
