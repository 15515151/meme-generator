#! /usr/bin/env bash
set -e

# MEME_GENERATOR_CONFIG_FILE 指向 /data 下的配置，因此这里直接写该文件，
# 配置、管理凭据（admin.json）和同步的外部仓库都会留在挂载卷里。
mkdir -p "$(dirname "${MEME_GENERATOR_CONFIG_FILE:-/data/config.toml}")"

envsubst < /app/config.toml.template > "${MEME_GENERATOR_CONFIG_FILE:-/data/config.toml}"

exec python -m meme_generator.app
