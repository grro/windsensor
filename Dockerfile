FROM python:3.11-slim

ENV port=9860

WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends libgpiod2 \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

CMD ["sh", "-c", "python /app/run_server.py $port $chip $gpio"]
