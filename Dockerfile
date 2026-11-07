FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FASTMCP_CHECK_FOR_UPDATES=off \
    port=9860 \
    addr=gpiochip0#11


WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
	&& apt-get install -y --no-install-recommends build-essential \
	&& python -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt \
	&& apt-get purge -y --auto-remove build-essential \
	&& rm -rf /var/lib/apt/lists/*


COPY *.py .

ARG VERSION=dev
ENV WINDSENSOR_VERSION=$VERSION

EXPOSE 9860 9862
STOPSIGNAL SIGINT

CMD ["sh", "-c", "exec python /app/run_server.py \"$port\" \"$addr\""]
