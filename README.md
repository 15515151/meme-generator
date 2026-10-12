# meme-generator

一个基于 Python、FastAPI、Pillow/skia 的表情包生成服务，**自带 Web 管理面板**和**外部表情仓库管理**。

仓库本身只保留两个示例表情（`google`、`alike`）作为模板，实际使用的表情通过外部仓库（如
[MemeCrafters/meme-generator-contrib](https://github.com/MemeCrafters/meme-generator-contrib)）在管理面板里一键添加。
这样仓库保持轻量，同时还能用上社区维护的完整表情集合。

## 功能

- **表情生成 API**：文本 / 图片模板，支持 GIF，输出 OpenAPI 文档。
- **Web 管理面板**：首次进入设置管理员密码，之后可管理表情、预览、搜索、封禁、添加仓库、检查更新。
- **外部表情仓库**：在面板里填地址即可下载并加载第三方表情，支持更新检测与卸载。
- **更新查询 API**：可查询哪些表情有更新、更新了哪些文件，并直接拿到新代码，方便下游同步。
- **统一的错误响应**：所有错误都带 `error.code`，便于程序化处理。
- **移动端适配**：管理面板在手机上使用底部导航栏，布局自适应。
- **uv 管理依赖**：依赖锁定、构建与发布统一走 uv。

## 快速开始

安装依赖：

```bash
uv sync --locked
```

启动服务：

```bash
uv run meme run
```

默认监听 `http://127.0.0.1:2233`。打开该地址即可看到管理面板，**首次进入会要求设置管理员密码**；
API 文档在 [http://127.0.0.1:2233/docs](http://127.0.0.1:2233/docs)。

内置示例表情：

| key | 类型 | 输入 | 说明 |
| --- | --- | --- | --- |
| `google` | 文本模板 | 1 段文本 | 把文字渲染成 Google 彩色风格 |
| `alike` | 图片模板 | 1 张图片 | “你怎么跟……一样”模板 |

```bash
# 生成文本表情
uv run meme generate google --texts "Hello"

# 生成图片表情
uv run meme generate alike --images avatar.jpg

# 查看已加载的表情
uv run meme list
```

## 添加表情的三种方式

### 1. 在管理面板中添加外部仓库（推荐）

打开面板 → 「仓库」→「添加仓库」，填入 GitHub 地址（`owner/repo` 或完整 URL）：

```
MemeCrafters/meme-generator-contrib
```

服务会下载该仓库中的表情并立即加载，无需重启。面板会显示每个仓库带来的表情，并支持
**更新**、**重新加载**、**移除**。移除仓库时，它带来的表情会一并卸载。

> 私有仓库需要在启动服务前设置 `GITHUB_TOKEN` 环境变量（CI 里自动可用 `GH_TOKEN`）。

### 2. 放到本地目录

在配置里声明目录，或直接在面板里填本地绝对路径：

```toml
[meme]
meme_dirs = ["/data/memes"]
```

### 3. 放进本仓库

在 `meme_generator/memes/<key>/__init__.py` 里定义并注册：

```python
from datetime import datetime

from pil_utils import BuildImage

from meme_generator import MemeArgsModel, add_meme


def hello(images: list[BuildImage], texts: list[str], args: MemeArgsModel):
    frame = BuildImage.new("RGB", (500, 200), "white")
    frame.draw_text((20, 20, 480, 180), texts[0], max_fontsize=64, halign="center")
    return frame.save_jpg()


add_meme(
    "hello",
    hello,
    min_texts=1,
    max_texts=1,
    default_texts=["Hello"],
    keywords=["hello"],
    date_created=datetime(2026, 1, 1),
)
```

如果表情带静态图片资源，放在该表情目录下并刷新资源清单：

```bash
uv run python tools/update_resource_list.py
```

## 管理面板

打开首页即可使用。首次访问设置管理员密码（至少 8 位），密码用 PBKDF2 加盐哈希后保存在
服务端数据目录，登录令牌是无状态 HMAC 签名，重启服务不影响已登录会话。

| 页面 | 功能 |
| --- | --- |
| 概览 | 表情总数、封禁数、仓库数，一键检查所有更新 |
| 表情 | 网格展示与预览图，按 key / 关键词 / 标签搜索，按状态与来源筛选，单个或批量封禁/启用 |
| 仓库 | 添加、更新、重新加载、移除外部仓库，查看每个仓库带来的表情 |
| 更新 | 按表情和按仓库汇总的变更，可查看变更文件的新旧代码并一键应用 |
| 设置 | 修改密码，查看服务信息与公开接口列表 |

**封禁**与删除不同：被禁用的表情仍然注册在服务里，只是不再出现在对外接口中，方便随时恢复。

数据目录位置：

| 平台 | 路径 |
| --- | --- |
| Windows | `%LOCALAPPDATA%\meme_generator` |
| Linux | `~/.local/share/meme_generator` |
| macOS | `~/Library/Application Support/meme_generator` |

其中 `admin.json` 是管理员凭据，`repos/` 是同步下来的外部仓库。忘记密码时删掉 `admin.json`
重启即可重新初始化。

## API

### 生成与查询（公开）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/memes/keys` | 已启用表情的 key 列表 |
| `GET` | `/memes/{key}/info` | 表情参数约束、关键词、标签 |
| `GET` | `/memes/{key}/preview` | 生成预览图（图片二进制） |
| `POST` | `/memes/{key}/` | 生成表情，`multipart/form-data` |
| `POST` | `/memes/render_list` | 渲染表情列表图片 |
| `GET` | `/meme/version` | 服务版本 |

```bash
curl -X POST http://127.0.0.1:2233/memes/google/ \
  -F "texts=Hello API" \
  --output google.jpg
```

### 清单与更新查询（公开）

适合下游服务同步表情：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/version` | 版本信息 |
| `GET` | `/api/memes` | 表情清单，支持 `q` 搜索与 `include_disabled` |
| `GET` | `/api/repos` | 已注册的外部仓库及其表情 |
| `GET` | `/api/updates` | 更新概览，`include_content=true` 时返回变更文件内容 |
| `GET` | `/api/updates/{meme_key}` | 单个表情的更新详情 |

**查询某个表情是否有更新、更新了哪些文件：**

```bash
curl "http://127.0.0.1:2233/api/updates/google?include_content=true"
```

响应中每个表情都会列出状态（`new` / `updated` / `removed`）、涉及的文件路径，以及
代码文件的新内容（`content`）与被覆盖前的内容（`previous_content`）。下游可以据此
只拉取变化的表情，而不必同步整个仓库。

### 管理接口（需登录）

挂在 `/api/admin/*` 下，需要 `Authorization: Bearer <token>`。令牌也可以作为 `token`
查询参数传递（预览图片在 `<img>` 中直接引用时用得上）。

<details>
<summary>展开查看接口列表</summary>

**认证**

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/admin/status` | 是否已初始化、当前是否已登录 |
| `POST` | `/api/admin/setup` | 首次设置管理员密码 |
| `POST` | `/api/admin/login` | 登录并获取令牌 |
| `POST` | `/api/admin/logout` | 登出（前端丢弃令牌即可） |
| `POST` | `/api/admin/password` | 修改密码，旧令牌全部失效 |
| `GET` | `/api/admin/health` | 服务概览数据 |

**表情管理**

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/admin/memes` | 列表，支持 `q`、`status`、`source` 过滤 |
| `GET` | `/api/admin/memes/{key}` | 详情，含快捷指令 |
| `GET` | `/api/admin/memes/{key}/assets` | 表情目录下的文件清单 |
| `GET` | `/api/admin/memes/{key}/preview` | 预览图，禁用状态也可预览 |
| `POST` | `/api/admin/memes/{key}/toggle` | 封禁 / 启用单个表情 |
| `POST` | `/api/admin/memes/batch-toggle` | 批量封禁 / 启用 |

**仓库与更新**

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/admin/repos` | 已注册仓库 |
| `POST` | `/api/admin/repos` | 添加仓库并下载 |
| `DELETE` | `/api/admin/repos/{identifier}` | 移除仓库并卸载其表情 |
| `POST` | `/api/admin/repos/{identifier}/update` | 更新，`apply=false` 时只检查 |
| `POST` | `/api/admin/repos/{identifier}/reload` | 从本地内容重新加载表情 |
| `GET` | `/api/admin/updates/check` | 检查单个仓库的更新 |
| `GET` | `/api/admin/updates/check-all` | 检查全部仓库 |
| `GET` | `/api/admin/updates/memes` | 按表情汇总的待同步列表 |

</details>

### 错误响应

所有错误都返回统一结构：

```json
{
  "error": {
    "code": "NO_SUCH_MEME",
    "message": "表情“xxx”不存在",
    "status_code": 531,
    "context": { "meme_key": "xxx" }
  },
  "detail": "表情“xxx”不存在"
}
```

`detail` 字段与历史版本一致，已有调用方无需改动。常见 `code`：

| code | 说明 |
| --- | --- |
| `NO_SUCH_MEME` | 表情不存在 |
| `MEME_DISABLED` | 表情已被管理员封禁 |
| `IMAGE_NUMBER_MISMATCH` / `TEXT_NUMBER_MISMATCH` | 图片 / 文本数量不符 |
| `OPEN_IMAGE_FAILED` | 图片无法解析 |
| `TEXT_OVER_LENGTH` | 文本过长 |
| `ARG_MODEL_MISMATCH` | 额外参数校验失败 |
| `VALIDATION_ERROR` | 请求格式错误（HTTP 422） |
| `UNAUTHORIZED` / `TOKEN_INVALID` | 未登录 / 令牌无效 |
| `REPO_NOT_FOUND` / `REPO_ALREADY_EXISTS` / `REPO_FETCH_FAILED` | 仓库相关错误 |

## 配置

默认配置文件位置见上面的数据目录表，可用环境变量覆盖：

| 环境变量 | 说明 |
| --- | --- |
| `MEME_GENERATOR_CONFIG_FILE` | 指定配置文件路径 |
| `MEME_GENERATOR_DATA_DIR` | 数据目录（管理员凭据、外部仓库） |
| `MEME_GENERATOR_CONFIG_DIR` | 配置目录 |
| `MEME_GENERATOR_CACHE_DIR` | 缓存目录 |
| `GITHUB_TOKEN` / `GH_TOKEN` | 访问私有仓库时使用 |

```toml
[meme]
load_builtin_memes = true
meme_dirs = []
# 被封禁的表情；管理面板会自动维护这个列表
meme_disabled_list = []

[resource]
resource_url = ""
resource_urls = []

[gif]
gif_max_size = 10
gif_max_frames = 100

[translate]
baidu_trans_appid = ""
baidu_trans_apikey = ""

[server]
host = "127.0.0.1"
port = 2233

[log]
log_level = "INFO"
```

## Docker

```bash
docker build -t meme-generator .
docker run --rm -p 2233:2233 -v meme-data:/data meme-generator
```

容器内监听 `0.0.0.0:2233`，配置与管理员凭据都放在 `/data` 卷里，重建容器不会丢失。

## 开发

管理面板源码在 `web/`（React + Vite + TypeScript）：

```bash
# 前端开发模式，自动代理到本地 2233 端口的后端
cd web && npm install && npm run dev

# 构建到 meme_generator/web_dist，随 Python 包一起分发
cd web && npm run build
```

后端：

```bash
uv sync --locked
uv run ruff check .
uv run ruff format .
uv run pytest
uv build
```

提交前至少运行 `uv run ruff check .` 和 `uv run pytest`。

## 已知问题

- **Windows 下程序无报错退出**：需要安装
  [Visual C++ 运行时](https://aka.ms/vs/17/release/VC_redist.x64.exe)
  （相关 [Issue](https://github.com/kyamagu/skia-python/issues/289)）。
- **Linux 下字体异常**：设置 `export LANG=en_US.UTF-8`
  （相关 [Issue](https://github.com/rust-skia/rust-skia/issues/963)）。

## 声明

本仓库的表情素材等均来自网络，如有侵权请联系作者删除。

## 鸣谢

本项目的表情生成部分源自 [MemeCrafters/meme-generator](https://github.com/MemeCrafters/meme-generator)，
表情资源整合自 [nonebot-plugin-petpet](https://github.com/noneplugin/nonebot-plugin-petpet) 和
[nonebot-plugin-memes](https://github.com/noneplugin/nonebot-plugin-memes)。

## License

MIT
