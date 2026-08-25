FROM python:3.11-slim

ENV port=9860
ENV chip=gpiochip0
ENV gpio=11

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
	&& apt-get install -y --no-install-recommends build-essential \
	&& pip install --no-cache-dir -r requirements.txt \
	&& apt-get purge -y --auto-remove build-essential \
	&& rm -rf /var/lib/apt/lists/*


COPY *.py .

CMD ["sh", "-c", "python /app/run_server.py $port $chip $gpio"]
