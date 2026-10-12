FROM python:3.10 AS tmp

WORKDIR /tmp

COPY --from=ghcr.io/astral-sh/uv:0.8.19 /uv /uvx /usr/local/bin/

COPY ./pyproject.toml ./uv.lock /tmp/

RUN uv export --frozen --no-dev --no-hashes --no-emit-project --output-file requirements.txt

FROM python:3.10-slim AS app

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.19 /uv /uvx /usr/local/bin/

EXPOSE 2233

VOLUME /data

ENV TZ=Asia/Shanghai \
  LOAD_BUILTIN_MEMES=true \
  MEME_DIRS="[\"/data/memes\"]" \
  MEME_DISABLED_LIST="[]" \
  GIF_MAX_SIZE=10.0 \
  GIF_MAX_FRAMES=100 \
  BAIDU_TRANS_APPID="" \
  BAIDU_TRANS_APIKEY="" \
  LOG_LEVEL="INFO"

COPY --from=tmp /tmp/requirements.txt /app/requirements.txt

COPY ./resources/fonts/* /usr/share/fonts/meme-fonts/

RUN apt-get update \
  && apt-get install -y --no-install-recommends fontconfig fonts-noto-color-emoji libgl1-mesa-glx libgl1-mesa-dri libegl1-mesa gettext \
  && fc-cache -fv \
  && apt-get purge -y --auto-remove \
  && rm -rf /var/lib/apt/lists/* \
  && uv pip install --system --no-cache --upgrade -r /app/requirements.txt

COPY ./meme_generator /app/meme_generator

COPY ./docker/config.toml.template /app/config.toml.template
COPY ./docker/start.sh /app/start.sh
RUN chmod +x /app/start.sh
RUN python -m meme_generator.cli

CMD ["/app/start.sh"]
