# Образ-«терминал» для сборки методички: Node 24 + docker CLI + psql + bash/curl.
# Демон — отдельный (docker:dind), см. tools/build-manual.py и src/run.json
FROM node:24-alpine
RUN apk add --no-cache bash curl jq git docker-cli docker-cli-compose postgresql18-client bind-tools ca-certificates coreutils util-linux
WORKDIR /work
CMD ["bash"]
COPY tools/schema-merge.mjs /usr/local/bin/schema-merge.mjs
COPY tools/prelude.sh /etc/prelude.sh
