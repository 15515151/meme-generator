/**
 * GitHub 加速源选择器。
 *
 * 加速源是纯前缀：`https://ghfast.top/` 会把
 * `https://github.com/owner/repo` 变成
 * `https://ghfast.top/https://github.com/owner/repo`。
 * 组件负责预设 chip、拼接预览和可用性测试，添加仓库与全局设置共用。
 *
 * 自建/自用加速源直接填在输入框里即可，只写进本机配置，不涉及代码。
 */

import { useState } from 'react'

import { ApiError, api, type ProxyProbe, type ProxyTestResult } from '../api'
import { Alert } from './ui'
import { IconZap } from './icons'

const EXAMPLE_URL = 'https://github.com/owner/repo'

export function ProxyPicker({
  value,
  onChange,
  presets,
  fallback,
  testIdentifier,
  testRef,
  disabled,
}: {
  value: string
  onChange: (next: string) => void
  presets: string[]
  /** 留空时实际使用的加速源（全局默认），用于占位提示 */
  fallback?: string
  testIdentifier?: string
  testRef?: string
  disabled?: boolean
}) {
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<ProxyTestResult | null>(null)
  const [error, setError] = useState('')

  const trimmed = value.trim().replace(/\/+$/, '')
  const preview = trimmed
    ? trimmed.includes('{url}')
      ? trimmed.replace('{url}', EXAMPLE_URL)
      : `${trimmed}/${EXAMPLE_URL}`
    : ''

  async function runTest() {
    setTesting(true)
    setError('')
    setResult(null)
    try {
      setResult(await api.testProxy(value.trim(), testIdentifier ?? '', testRef ?? ''))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '测试失败')
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="field">
      <label htmlFor="repo-proxy">加速源</label>
      <input
        id="repo-proxy"
        className="input mono"
        value={value}
        spellCheck={false}
        disabled={disabled}
        placeholder={fallback ? `留空使用全局默认：${fallback}` : '留空直连 GitHub'}
        onChange={(e) => onChange(e.target.value)}
      />
      <div className="proxy-chips">
        <button
          type="button"
          className={`proxy-chip${value.trim() === '' ? ' active' : ''}`}
          disabled={disabled}
          onClick={() => onChange('')}
        >
          直连
        </button>
        {presets.map((preset) => (
          <button
            key={preset}
            type="button"
            className={`proxy-chip${trimmed === preset ? ' active' : ''}`}
            disabled={disabled}
            onClick={() => onChange(preset)}
          >
            {preset}
          </button>
        ))}
      </div>
      {preview && (
        <div className="proxy-preview">
          拼接效果：<span className="mono">{preview}</span>
        </div>
      )}
      <div className="btn-row" style={{ marginTop: 8 }}>
        <button
          type="button"
          className="btn btn-sm"
          disabled={testing || disabled}
          onClick={() => void runTest()}
        >
          {testing ? <span className="spinner" /> : <IconZap size={13} />}
          测试加速源
        </button>
        <span className="field-hint">分别访问 GitHub 接口与 raw 内容，并和直连比耗时。</span>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      {result && (
        <>
          {result.accelerated.length > 0 && !result.usable && (
            <Alert kind="warn">
              这个加速源没测通（下面的明细里能看到是哪个端点失败）。加速源不可用时服务会自动
              退回直连，但仍建议换一个更稳的加速源。
            </Alert>
          )}
          {result.accelerated.length > 0 && result.usable && !result.all_ok && (
            <Alert kind="info">
              部分端点可用：该加速源只代理了其中几种请求，其余会直连。服务按主机分别回退，
              功能和直接用是完全一样的。
            </Alert>
          )}
          <ProbeList label="经加速源" probes={result.accelerated} />
          <ProbeList label="直连" probes={result.direct} />
        </>
      )}
    </div>
  )
}

function ProbeList({ label, probes }: { label: string; probes: ProxyProbe[] }) {
  if (!probes.length) return null
  return (
    <div className="proxy-result">
      <div style={{ fontWeight: 600 }}>{label}</div>
      {probes.map((probe) => (
        <div key={probe.url} className="row between" style={{ gap: 8 }}>
          <span style={{ flex: '0 0 auto' }}>{probe.label}</span>
          <span className="mono" style={{ flex: 1, fontSize: 11, wordBreak: 'break-all' }}>
            {probe.url}
          </span>
          <span className={probe.ok ? 'ok' : 'fail'}>
            {probe.error ? '连接失败' : `HTTP ${probe.status}`} · {probe.elapsed_ms}ms
          </span>
        </div>
      ))}
    </div>
  )
}
