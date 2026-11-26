# Disposable SSH transport acceptance only.
FROM nginx:1.28-alpine
USER root
RUN apk add --no-cache openssh-server && mkdir -p /run/sshd /root/.ssh && chmod 700 /root/.ssh && passwd -d root
ENTRYPOINT ["/bin/sh"]
