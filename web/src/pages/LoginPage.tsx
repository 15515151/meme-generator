import { useState, type FormEvent } from 'react'

import { ApiError } from '../api'
import { useAuth } from '../context/AuthContext'
import { Alert } from '../components/ui'

export default function LoginPage() {
  const { initialized, setup, login, status } = useAuth()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const minLength = status?.min_password_length ?? 8
  const isSetup = !initialized

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')

    if (isSetup) {
      if (password.length < minLength) {
        setError(`密码长度至少为 ${minLength} 位`)
        return
      }
      if (password !== confirm) {
        setError('两次输入的密码不一致')
        return
      }
    } else if (!password) {
      setError('请输入密码')
      return
    }

    setBusy(true)
    try {
      if (isSetup) {
        await setup(password)
      } else {
        await login(password)
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '操作失败，请稍后重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={onSubmit}>
        <div className="auth-logo" aria-hidden>
          🎨
        </div>
        <h1 className="auth-title">
          {isSetup ? '初始化管理面板' : '登录管理面板'}
        </h1>
        <p className="auth-desc">
          {isSetup
            ? `这是首次使用，请设置管理员密码。密码长度至少 ${minLength} 位，设置后用于登录管理面板。`
            : '请输入管理员密码以继续。'}
        </p>

        {error && <Alert kind="error">{error}</Alert>}

        <div className="field">
          <label htmlFor="password">{isSetup ? '设置密码' : '密码'}</label>
          <input
            id="password"
            className="input"
            type="password"
            value={password}
            autoComplete={isSetup ? 'new-password' : 'current-password'}
            autoFocus
            placeholder={`至少 ${minLength} 位`}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {isSetup && (
          <div className="field">
            <label htmlFor="confirm">确认密码</label>
            <input
              id="confirm"
              className="input"
              type="password"
              value={confirm}
              autoComplete="new-password"
              placeholder="再次输入密码"
              onChange={(e) => setConfirm(e.target.value)}
            />
          </div>
        )}

        <button className="btn btn-primary btn-block" type="submit" disabled={busy}>
          {busy && <span className="spinner" />}
          {isSetup ? '设置密码并进入' : '登录'}
        </button>

        <p className="auth-desc" style={{ marginTop: 18, marginBottom: 0 }}>
          凭据保存在服务端数据目录，忘记密码可删除其中的 <code className="mono">admin.json</code> 后重新初始化。
        </p>
      </form>
    </div>
  )
}
