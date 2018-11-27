FROM alpine-base:v1
COPY script/* /tmp/

RUN mkdir /script && \
    mv /tmp/* /script/ && \
    chmod +x /script/* && \
    pip install aiohttp apscheduler

ENTRYPOINT ["/usr/local/bin/python", "-u", "/script/entrypoint.py"]
