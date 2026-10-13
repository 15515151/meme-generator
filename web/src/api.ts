// 与后端 /api 交互的封装。所有错误都会被规整成 ApiError，方便界面统一展示。

export interface ApiErrorBody {
  code: string
  message: string
  status_code: number
  context?: Record<string, unknown>
}

export class ApiError extends Error {
  code: string
  statusCode: number
  context: Record<string, unknown>

  constructor(body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.code = body.code
    this.statusCode = body.status_code
    this.context = body.context ?? {}
  }
}

const TOKEN_KEY = 'meme_admin_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

interface RequestOptions {
  method?: string
  body?: unknown
  formData?: FormData
  auth?: boolean
  raw?: boolean
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token && options.auth !== false) {
    headers['Authorization'] = `Bearer ${token}`
  }

  let body: BodyInit | undefined
  if (options.formData) {
    body = options.formData
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  const response = await fetch(path, {
    method: options.method ?? 'GET',
    headers,
    body,
  })

  if (options.raw) {
    if (!response.ok) {
      throw await toApiError(response)
    }
    return (await response.blob()) as unknown as T
  }

  const text = await response.text()
  let payload: unknown = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = text
    }
  }

  if (!response.ok) {
    const fallback: ApiErrorBody = {
      code: 'HTTP_ERROR',
      message: `请求失败（${response.status}）`,
      status_code: response.status,
    }
    const error =
      payload && typeof payload === 'object' && 'error' in payload
        ? ((payload as { error: ApiErrorBody }).error ?? fallback)
        : fallback
    throw new ApiError(error)
  }

  return payload as T
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const payload = await response.json()
    if (payload?.error) return new ApiError(payload.error)
  } catch {
    /* 忽略解析失败，落到下面的兜底 */
  }
  return new ApiError({
    code: 'HTTP_ERROR',
    message: `请求失败（${response.status}）`,
    status_code: response.status,
  })
}

// -- 类型 ------------------------------------------------------------------

export interface AuthStatus {
  initialized: boolean
  authenticated: boolean
  min_password_length: number
}

export interface TokenResponse {
  token: string
  expires_in: number
  initialized: boolean
}

export interface MemeSummary {
  key: string
  keywords: string[]
  tags: string[]
  disabled: boolean
  source: string
  min_images: number
  max_images: number
  min_texts: number
  max_texts: number
  default_texts: string[]
  date_created: string
  date_modified: string
  has_preview_assets: boolean
}

export interface MemeListResponse {
  total: number
  enabled: number
  disabled: number
  items: MemeSummary[]
  sources: string[]
}

export interface RepoInfo {
  identifier: string
  name: string
  display_name: string
  url: string
  ref: string
  enabled: boolean
  meme_dir: string
  proxy: string
  effective_proxy: string
  accelerated_url: string
  installed_at: number | null
  updated_at: number | null
  file_count: number
  meme_keys: string[]
  meme_count: number
  installed: boolean
  source: string
}

export interface RepoPreset {
  name: string
  url: string
  branch: string
  identifier: string
  installed: boolean
  installed_id: string | null
  meme_count: number
}

export interface RepoPreview {
  identifier: string
  name: string
  ref: string
  meme_dir: string
  proxy: string
  effective_proxy: string
  file_count: number
  meme_count: number
  meme_keys: string[]
  installed: boolean
}

export interface ProxyProbe {
  label: string
  url: string
  ok: boolean
  status: number
  elapsed_ms: number
  via_proxy: boolean
  error?: string
}

export interface ProxyTestResult {
  proxy: string
  identifier: string
  ref: string
  accelerated: ProxyProbe[]
  direct: ProxyProbe[]
  usable: boolean
  all_ok: boolean
}

export interface ProxyPresets {
  default: string
  items: string[]
}

export interface UpdateFile {
  path: string
  status: 'added' | 'modified'
  meme_key: string | null
  kind: string
  content?: string | null
  previous_content?: string | null
}

export interface UpdateResult {
  identifier: string
  name?: string
  proxy?: string
  has_update: boolean
  changes: {
    added: string[]
    modified: string[]
    removed: string[]
    added_memes: string[]
    modified_memes: string[]
    removed_memes: string[]
  }
  files: UpdateFile[]
  error?: string | null
}

export interface MemeUpdateItem {
  meme_key: string
  status: 'new' | 'updated' | 'removed'
  repo: string
  files: {
    path: string
    status: string
    kind: string
    content?: string | null
    previous_content?: string | null
  }[]
  file_count: number
  code_files: number
  installed: boolean
  disabled: boolean
}

export interface Health {
  ok: boolean
  version: string
  initialized: boolean
  memes: number
  disabled: number
  repos: number
}

export interface ServerSettings {
  api_domain: string
  host: string
  port: number
}

export interface RepoSettings {
  github_proxy: string
  effective_proxy: string
  proxy_presets: string[]
}

export interface SettingsResponse {
  server: ServerSettings
  repo: RepoSettings
  config_file: string
}

// -- 接口 ------------------------------------------------------------------

export const api = {
  // 认证
  authStatus: () => request<AuthStatus>('/api/admin/status'),
  setup: (password: string) =>
    request<TokenResponse>('/api/admin/setup', { method: 'POST', body: { password } }),
  login: (password: string) =>
    request<TokenResponse>('/api/admin/login', { method: 'POST', body: { password } }),
  changePassword: (oldPassword: string, newPassword: string) =>
    request<TokenResponse>('/api/admin/password', {
      method: 'POST',
      body: { old_password: oldPassword, new_password: newPassword },
    }),
  health: () => request<Health>('/api/admin/health'),

  // 表情管理
  listMemes: (params: { q?: string; status?: string; source?: string }) => {
    const search = new URLSearchParams()
    if (params.q) search.set('q', params.q)
    if (params.status) search.set('status', params.status)
    if (params.source) search.set('source', params.source)
    const qs = search.toString()
    return request<MemeListResponse>(`/api/admin/memes${qs ? `?${qs}` : ''}`)
  },
  toggleMeme: (key: string, disabled: boolean) =>
    request<{ key: string; disabled: boolean; message: string }>(
      `/api/admin/memes/${encodeURIComponent(key)}/toggle`,
      { method: 'POST', body: { disabled } },
    ),
  batchToggle: (keys: string[], disabled: boolean) =>
    request<{ updated: string[]; failed: Record<string, string> }>(
      '/api/admin/memes/batch-toggle',
      { method: 'POST', body: { keys, disabled } },
    ),
  memePreviewUrl: (key: string, texts: string) => {
    const search = new URLSearchParams()
    if (texts) search.set('texts', texts)
    // 预览走 <img>，令牌通过查询参数传递
    search.set('token', getToken() ?? '')
    return `/api/admin/memes/${encodeURIComponent(key)}/preview?${search.toString()}`
  },
  fetchMemePreview: async (key: string, texts: string): Promise<string> => {
    const blob = await request<Blob>(api.memePreviewUrl(key, texts), { raw: true })
    return URL.createObjectURL(blob)
  },
  memeDetail: (key: string) =>
    request<MemeSummary & { shortcuts: { key: string; humanized: string | null }[] }>(
      `/api/admin/memes/${encodeURIComponent(key)}`,
    ),
  memeAssets: (key: string) =>
    request<{ key: string; files: { path: string; size: number; kind: string }[]; count: number }>(
      `/api/admin/memes/${encodeURIComponent(key)}/assets`,
    ),

  // 仓库管理
  listRepos: () => request<{ total: number; items: RepoInfo[] }>('/api/admin/repos'),
  listPresets: () =>
    request<{ total: number; items: RepoPreset[] }>('/api/admin/repos/presets'),
  listProxies: () => request<ProxyPresets>('/api/admin/repos/proxies'),
  testProxy: (proxy: string, identifier: string, ref: string) =>
    request<ProxyTestResult>('/api/admin/repos/proxy-test', {
      method: 'POST',
      body: { proxy, identifier, ref },
    }),
  previewRepo: (url: string, ref: string, proxy: string) =>
    request<RepoPreview>('/api/admin/repos/preview', {
      method: 'POST',
      body: { url, ref, proxy },
    }),
  addRepo: (url: string, ref: string, name: string, memeDir: string, proxy: string) =>
    request<RepoInfo>('/api/admin/repos', {
      method: 'POST',
      body: { url, ref, name, meme_dir: memeDir, proxy },
    }),
  setRepoSettings: (
    identifier: string,
    payload: { proxy?: string; name?: string; apply?: boolean },
  ) =>
    request<RepoInfo>(`/api/admin/repos/${encodeURIComponent(identifier)}`, {
      method: 'PATCH',
      body: payload,
    }),
  removeRepo: (identifier: string) =>
    request<{ identifier: string; removed_memes: string[]; message: string }>(
      `/api/admin/repos/${encodeURIComponent(identifier)}`,
      { method: 'DELETE' },
    ),
  updateRepo: (identifier: string, apply: boolean) =>
    request<{ applied: boolean } & Partial<UpdateResult>>(
      `/api/admin/repos/${encodeURIComponent(identifier)}/update`,
      { method: 'POST', body: { apply } },
    ),
  reloadRepo: (identifier: string) =>
    request<{ identifier: string; loaded_memes: string[]; message: string }>(
      `/api/admin/repos/${encodeURIComponent(identifier)}/reload`,
      { method: 'POST' },
    ),

  // 更新检查
  checkUpdates: () =>
    request<{ total: number; updated: number; results: UpdateResult[] }>(
      '/api/admin/updates/check-all',
    ),
  checkRepoTUpdates: (identifier: string) =>
    request<UpdateResult>(
      `/api/admin/updates/check?identifier=${encodeURIComponent(identifier)}`,
    ),
  memeUpdates: () =>
    request<{ total: number; memes_updated: number; items: MemeUpdateItem[] }>(
      '/api/admin/updates/memes',
    ),

  // 设置
  getSettings: () => request<SettingsResponse>('/api/admin/settings'),
  updateSettings: (payload: { api_domain?: string; github_proxy?: string }) =>
    request<SettingsResponse>('/api/admin/settings', {
      method: 'PATCH',
      body: payload,
    }),
}

export const publicApi = {
  version: () => request<{ version: string }>('/api/version'),
  memes: (params: { q?: string; includeDisabled?: boolean } = {}) => {
    const search = new URLSearchParams()
    if (params.q) search.set('q', params.q)
    if (params.includeDisabled) search.set('include_disabled', 'true')
    const qs = search.toString()
    return request<{
      version: string
      total: number
      items: {
        key: string
        keywords: string[]
        tags: string[]
        source: string
        disabled: boolean
        params_type: Record<string, unknown>
      }[]
    }>(`/api/memes${qs ? `?${qs}` : ''}`)
  },
  updates: (identifier: string, includeContent: boolean) => {
    const search = new URLSearchParams()
    if (identifier) search.set('identifier', identifier)
    if (includeContent) search.set('include_content', 'true')
    return request<{ total: number; updated: number; results: UpdateResult[] }>(
      `/api/updates?${search.toString()}`,
    )
  },
}
