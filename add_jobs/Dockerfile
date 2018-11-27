FROM alpine-base:latest
COPY script/* /tmp/

RUN mkdir /script && \
    mv /tmp/* /script/ && \
    chmod +x /script/*

ENTRYPOINT ["/script/entrypoint.sh"]

CMD ["crond", "-f", "-l", "5"]
