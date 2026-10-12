FROM python:3.10 AS tmp

WORKDIR /tmp

COPY --from=ghcr.io/astral-sh/uv:0.8.19 /uv /uvx /usr/local/bin/

COPY ./pyproject.toml ./uv.lock /tmp/

RUN uv export --frozen --no-dev --no-hashes --no-emit-project --output-file requirements.txt

FROM node:20-slim AS web

WORKDIR /web

# 只复制依赖清单，让 npm ci 这层能被缓存
COPY ./web/package.json ./web/package-lock.json* /web/

RUN npm ci --no-audit --no-fund

COPY ./web /web

# 构建产物输出到包目录，下一步随应用到镜像里
RUN npm run build

FROM python:3.10-slim AS app

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.19 /uv /uvx /usr/local/bin/

EXPOSE 2233

VOLUME /data

# 配置、管理凭据和同步的外部仓库都放在 /data，容器重建后不会丢。
ENV TZ=Asia/Shanghai \
  MEME_GENERATOR_CONFIG_FILE=/data/config.toml \
  MEME_GENERATOR_DATA_DIR=/data \
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
# 用上面 web 阶段刚构建的产物覆盖源码目录里的旧文件
COPY --from=web /meme_generator/web_dist /app/meme_generator/web_dist

COPY ./docker/config.toml.template /app/config.toml.template
COPY ./docker/start.sh /app/start.sh
RUN chmod +x /app/start.sh
RUN python -m meme_generator.cli

CMD ["/app/start.sh"]
