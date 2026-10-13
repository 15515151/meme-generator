#!/usr/bin/env bash
#
# 镜像冒烟测试：拉起容器，确认服务、管理面板、表情生成都正常。
# 用法：bash .github/scripts/smoke-test.sh <image> [data-dir] [port]
#
set -euo pipefail

image="${1:?请传入镜像名，例如 meme-generator:ci}"
data_dir="${2:-/tmp/meme-smoke-data}"
port="${3:-2233}"
container="meme-smoke-$$"

cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT

mkdir -p "$data_dir"
docker run -d --name "$container" -p "${port}:2233" -v "$data_dir:/data" "$image"

# 等待服务起来，最多 90 秒
for i in $(seq 1 45); do
  if curl -fsS "http://127.0.0.1:${port}/meme/version" > /tmp/meme-version.json 2>/dev/null; then
    echo "service is up after ${i} attempt(s)"
    break
  fi
  sleep 2
done

# 还没起来就直接失败，并打出容器日志
if ! curl -fsS "http://127.0.0.1:${port}/meme/version" > /tmp/meme-version.json; then
  echo "service did not start in time" >&2
  docker logs "$container" | tail -50
  exit 1
fi

cat /tmp/meme-version.json
echo ""

# 管理面板与其接口都应可用
curl -fsS -o /dev/null -w "UI: %{http_code}\n" "http://127.0.0.1:${port}/"
curl -fsS "http://127.0.0.1:${port}/api/admin/status"
echo ""

# 生成一张表情，确认 skia / 字体在镜像里都装好了
curl -fsS -X POST "http://127.0.0.1:${port}/memes/google/" -F "texts=CI" -o /tmp/meme-out.jpg
file /tmp/meme-out.jpg

docker logs "$container" | tail -20
