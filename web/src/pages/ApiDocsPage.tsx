import { useCallback, useEffect, useMemo, useState } from 'react'

import { Alert, Badge, Card, Spinner } from '../components/ui'
import { IconRefresh, IconServer } from '../components/icons'

/** 简化的 OpenAPI 结构，只取我们渲染需要的字段。 */
interface OpenApiSchema {
  type?: string
  format?: string
  description?: string
  default?: unknown
  example?: unknown
  enum?: unknown[]
  items?: OpenApiSchema
  properties?: Record<string, OpenApiSchema>
  required?: string[]
  $ref?: string
  anyOf?: OpenApiSchema[]
  allOf?: OpenApiSchema[]
  title?: string
}

interface OpenApiParameter {
  name: string
  in: string
  required?: boolean
  description?: string
  schema?: OpenApiSchema
}

interface OpenApiRequestBody {
  required?: boolean
  description?: string
  content?: Record<string, { schema?: OpenApiSchema }>
}

interface OpenApiOperation {
  tags?: string[]
  summary?: string
  description?: string
  operationId?: string
  parameters?: OpenApiParameter[]
  requestBody?: OpenApiRequestBody
  deprecated?: boolean
}

interface OpenApiDoc {
  info?: { title?: string; version?: string; description?: string }
  paths?: Record<string, Record<string, OpenApiOperation>>
  components?: { schemas?: Record<string, OpenApiSchema> }
}

interface Endpoint {
  id: string
  method: string
  path: string
  tag: string
  summary: string
  operation: OpenApiOperation
}

/** 把 $ref 解析成实际 schema。 */
function resolveSchema(
  schema: OpenApiSchema | undefined,
  doc: OpenApiDoc,
  depth = 0,
): OpenApiSchema {
  if (!schema || depth > 6) return schema ?? {}
  if (schema.$ref) {
    const name = schema.$ref.split('/').pop() ?? ''
    const target = doc.components?.schemas?.[name]
    return target ? resolveSchema(target, doc, depth + 1) : schema
  }
  if (schema.anyOf?.length) {
    // anyOf 常用来表达「T | null」，取第一个非空分支
    const branch = schema.anyOf.find((item) => item.type !== 'null') ?? schema.anyOf[0]
    return resolveSchema(branch, doc, depth + 1)
  }
  if (schema.allOf?.length) {
    return schema.allOf.reduce<OpenApiSchema>(
      (acc, item) => ({ ...acc, ...resolveSchema(item, doc, depth + 1) }),
      {},
    )
  }
  return schema
}

/** 把 schema 压成一行可读的类型描述。 */
function describeType(schema: OpenApiSchema | undefined, doc: OpenApiDoc): string {
  const resolved = resolveSchema(schema, doc)
  if (!resolved || !resolved.type) {
    if (resolved?.properties) return 'object'
    return 'any'
  }
  if (resolved.type === 'array') {
    return `${describeType(resolved.items, doc)}[]`
  }
  if (resolved.type === 'object' && resolved.properties) {
    return 'object'
  }
  if (resolved.enum?.length) {
    return resolved.enum.map((v) => JSON.stringify(v)).join(' | ')
  }
  return resolved.type
}

/** 收集一个 schema 下需要展示的字段（含一层嵌套对象展开）。 */
function collectFields(
  schema: OpenApiSchema | undefined,
  doc: OpenApiDoc,
): { name: string; type: string; required: boolean; description: string }[] {
  const resolved = resolveSchema(schema, doc)
  if (!resolved?.properties) return []
  const required = new Set(resolved.required ?? [])
  return Object.entries(resolved.properties).map(([name, prop]) => {
    const propResolved = resolveSchema(prop, doc)
    return {
      name,
      type: describeType(prop, doc),
      required: required.has(name),
      description: propResolved.description ?? '',
    }
  })
}

function buildTagLabel(path: string, tag?: string): string {
  if (tag) return tag
  if (path.startsWith('/api/admin')) return '管理'
  if (path.startsWith('/api')) return '公开接口'
  if (path.startsWith('/memes') || path.startsWith('/meme')) return '表情'
  return '其他'
}

const TAG_ORDER = ['表情', '公开接口', '管理', 'admin', 'memes', 'meta', 'public', '其他']

export default function ApiDocsPage({ apiDomain }: { apiDomain: string }) {
  const [doc, setDoc] = useState<OpenApiDoc | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [activeId, setActiveId] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const baseUrl = useMemo(() => {
    if (apiDomain) return apiDomain.replace(/\/$/, '')
    return window.location.origin
  }, [apiDomain])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/openapi.json')
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      setDoc((await response.json()) as OpenApiDoc)
    } catch (e) {
      setError(e instanceof Error ? e.message : '无法加载 OpenAPI 文档')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  // 把 paths 展开成端点列表，按 tag 分组
  const endpoints = useMemo<Endpoint[]>(() => {
    if (!doc?.paths) return []
    const list: Endpoint[] = []
    for (const [path, methods] of Object.entries(doc.paths)) {
      for (const [method, operation] of Object.entries(methods)) {
        if (!['get', 'post', 'put', 'patch', 'delete'].includes(method)) continue
        list.push({
          id: `${method}-${path}`,
          method,
          path,
          tag: buildTagLabel(path, operation.tags?.[0]),
          summary: operation.summary ?? operation.description ?? '',
          operation,
        })
      }
    }
    return list.sort((a, b) => {
      const tagDiff = TAG_ORDER.indexOf(a.tag) - TAG_ORDER.indexOf(b.tag)
      if (tagDiff !== 0) return tagDiff
      return a.path.localeCompare(b.path)
    })
  }, [doc])

  const groups = useMemo(() => {
    const map = new Map<string, Endpoint[]>()
    for (const endpoint of endpoints) {
      const list = map.get(endpoint.tag) ?? []
      list.push(endpoint)
      map.set(endpoint.tag, list)
    }
    return [...map.entries()]
  }, [endpoints])

  // 高亮当前可见的端点
  useEffect(() => {
    if (endpoints.length === 0) return
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible[0]) setActiveId((visible[0].target as HTMLElement).id)
      },
      { rootMargin: '-80px 0px -70% 0px', threshold: 0 },
    )
    for (const endpoint of endpoints) {
      const node = document.getElementById(endpoint.id)
      if (node) observer.observe(node)
    }
    return () => observer.disconnect()
  }, [endpoints])

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function scrollTo(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setActiveId(id)
  }

  if (loading) {
    return (
      <Card pad>
        <Spinner label="正在加载接口文档…" />
      </Card>
    )
  }

  if (error) {
    return (
      <Card pad>
        <Alert kind="error">加载接口文档失败：{error}</Alert>
        <button className="btn" onClick={() => void load()}>
          <IconRefresh size={14} />
          重试
        </button>
      </Card>
    )
  }

  return (
    <>
      <Card pad>
        <div className="row between" style={{ alignItems: 'flex-start' }}>
          <div style={{ minWidth: 0 }}>
            <div className="row" style={{ gap: 8, marginBottom: 8 }}>
              <IconServer size={16} />
              <span style={{ fontWeight: 620 }}>
                {doc?.info?.title ?? 'meme-generator'} API
              </span>
              <Badge tone="info">v{doc?.info?.version ?? '—'}</Badge>
              <Badge>{endpoints.length} 个接口</Badge>
            </div>
            <p className="text-sm text-muted mb-0" style={{ maxWidth: 720 }}>
              下方接口由服务端 OpenAPI 自动生成。请求示例中的地址取自「设置 → API
              域名」，未配置时使用当前访问地址。
            </p>
          </div>
          <div className="row">
            <div className="text-sm text-dim mono" style={{ maxWidth: 340 }}>
              {baseUrl}
            </div>
            <a className="btn btn-sm" href="/docs" target="_blank" rel="noreferrer">
              原生文档
            </a>
          </div>
        </div>
      </Card>

      <div className="docs-layout mt-4">
        <div className="docs-toc glass">
          <div className="docs-toc-group">
            <div className="docs-toc-title">接口列表</div>
            {groups.map(([tag, list]) => (
              <div key={tag} className="docs-toc-group">
                <div className="docs-toc-title">{tag}</div>
                {list.map((endpoint) => (
                  <button
                    key={endpoint.id}
                    className={`docs-toc-item${activeId === endpoint.id ? ' active' : ''}`}
                    onClick={() => scrollTo(endpoint.id)}
                  >
                    <span className={`method method-${endpoint.method}`}>
                      {endpoint.method}
                    </span>
                    <span className="docs-toc-path" title={endpoint.path}>
                      {endpoint.path}
                    </span>
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>

        <div>
          {endpoints.map((endpoint) => (
            <EndpointCard
              key={endpoint.id}
              endpoint={endpoint}
              doc={doc!}
              baseUrl={baseUrl}
              open={expanded.has(endpoint.id)}
              onToggle={() => toggle(endpoint.id)}
            />
          ))}
          {endpoints.length === 0 && (
            <Card pad>
              <Alert kind="warn">OpenAPI 文档里没有可展示的接口</Alert>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}

function EndpointCard({
  endpoint,
  doc,
  baseUrl,
  open,
  onToggle,
}: {
  endpoint: Endpoint
  doc: OpenApiDoc
  baseUrl: string
  open: boolean
  onToggle: () => void
}) {
  const url = `${baseUrl}${endpoint.path}`

  // 路径与查询参数
  const params = (endpoint.operation.parameters ?? []).filter(
    (p) => p.in === 'path' || p.in === 'query',
  )

  // 请求体：取第一个 content 类型（优先 JSON）
  const bodyContent = endpoint.operation.requestBody?.content ?? {}
  const bodyEntry =
    bodyContent['application/json'] ??
    Object.entries(bodyContent).find(([type]) => type.includes('json'))?.[1] ??
    Object.values(bodyContent)[0]
  const bodyFields = collectFields(bodyEntry?.schema, doc)

  // 响应 schema：取 200 系列
  const responses = (
    endpoint.operation as unknown as {
      responses?: Record<string, { content?: Record<string, { schema?: OpenApiSchema }> }>
    }
  ).responses
  const okResponse = responses
    ? Object.entries(responses).find(([code]) => code.startsWith('2'))?.[1]
    : undefined
  const responseSchema = okResponse?.content?.['application/json']?.schema

  const curl = buildCurl(endpoint, url, bodyFields)

  return (
    <div className="endpoint card" id={endpoint.id}>
      <button className="endpoint-head" onClick={onToggle} aria-expanded={open}>
        <span className={`method method-${endpoint.method}`}>{endpoint.method}</span>
        <span className="endpoint-path">{endpoint.path}</span>
        {endpoint.summary && <span className="endpoint-summary">{endpoint.summary}</span>}
        {endpoint.operation.deprecated && <Badge tone="off">已废弃</Badge>}
      </button>

      {open && (
        <div className="endpoint-body">
          <div className="docs-section-title">请求地址</div>
          <pre className="code-block">{`${endpoint.method.toUpperCase()} ${url}`}</pre>

          {params.length > 0 && (
            <>
              <div className="docs-section-title">参数</div>
              <table className="param-table">
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>类型</th>
                    <th>位置</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  {params.map((param) => (
                    <tr key={`${param.in}-${param.name}`}>
                      <td className="param-name">
                        {param.name}
                        {param.required && <span className="param-required">*</span>}
                      </td>
                      <td className="param-type">{describeType(param.schema, doc)}</td>
                      <td>{param.in === 'path' ? '路径' : '查询'}</td>
                      <td>{param.description ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {endpoint.operation.requestBody && (
            <>
              <div className="docs-section-title">
                请求体
                {bodyEntry && (
                  <span className="text-dim" style={{ textTransform: 'none', marginLeft: 8 }}>
                    {Object.keys(bodyContent)[0] ?? 'application/json'}
                  </span>
                )}
              </div>
              {bodyFields.length > 0 ? (
                <table className="param-table">
                  <thead>
                    <tr>
                      <th>字段</th>
                      <th>类型</th>
                      <th>说明</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bodyFields.map((field) => (
                      <tr key={field.name}>
                        <td className="param-name">
                          {field.name}
                          {field.required && <span className="param-required">*</span>}
                        </td>
                        <td className="param-type">{field.type}</td>
                        <td>{field.description || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="text-sm text-muted">
                  {resolveSchema(bodyEntry?.schema, doc).type === 'string'
                    ? 'multipart/form-data 表单'
                    : '—'}
                </div>
              )}
            </>
          )}

          {responseSchema && (
            <>
              <div className="docs-section-title">响应</div>
              <div className="text-sm text-muted">
                类型：<span className="param-type">{describeType(responseSchema, doc)}</span>
                {(() => {
                  const fields = collectFields(responseSchema, doc)
                  if (fields.length === 0) return null
                  return (
                    <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
                      {fields.map((field) => (
                        <li key={field.name} style={{ marginBottom: 3 }}>
                          <span className="param-name">{field.name}</span>
                          <span className="text-dim"> · {field.type}</span>
                          {field.description && (
                            <span className="text-dim"> — {field.description}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )
                })()}
              </div>
            </>
          )}

          {curl && (
            <>
              <div className="docs-section-title">请求示例</div>
              <pre className="code-block">{curl}</pre>
            </>
          )}
        </div>
      )}
    </div>
  )
}

/** 根据端点信息拼一个可直接粘贴的 curl 示例。 */
function buildCurl(
  endpoint: Endpoint,
  url: string,
  bodyFields: { name: string; type: string; required: boolean }[],
): string {
  const method = endpoint.method.toUpperCase()
  const lines: string[] = []

  if (method === 'GET' || method === 'DELETE') {
    lines.push(`curl "${url}"`)
    return lines.join(' \\\n  ')
  }

  lines.push(`curl -X ${method} "${url}"`)

  const isAdmin = endpoint.path.startsWith('/api/admin') && !endpoint.path.endsWith('/status')
  if (isAdmin) {
    lines.push(`  -H "Authorization: Bearer <token>"`)
  }

  if (bodyFields.length > 0) {
    lines.push(`  -H "Content-Type: application/json"`)
    const example: Record<string, unknown> = {}
    for (const field of bodyFields) {
      example[field.name] =
        field.type.includes('[]') ? [] : field.type === 'string' ? '' : field.type === 'integer' ? 0 : null
    }
    lines.push(`  -d '${JSON.stringify(example)}'`)
  } else if (method === 'POST' && endpoint.path.includes('{key}')) {
    // 生成表情接口是 multipart 表单
    lines.push(`  -F "texts=Hello"`)
    lines.push(`  -o result.jpg`)
  }

  return lines.join(' \\\n  ')
}
