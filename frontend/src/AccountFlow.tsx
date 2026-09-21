import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'

export type AccountMode = 'signup' | 'reset' | 'change-email' | 'change-password'

export default function AccountFlow({ mode, currentEmail, done, cancel }: { mode: AccountMode; currentEmail?: string; done: (message: string) => void; cancel: () => void }) {
  const [stage, setStage] = useState<'request' | 'confirm'>('request')
  const [email, setEmail] = useState(currentEmail || '')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const title = { signup: 'Create your account', reset: 'Reset password', 'change-email': 'Change account email', 'change-password': 'Change password' }[mode]
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const values = new FormData(event.currentTarget)
    try {
      if ((mode === 'signup' || mode === 'change-password' || (mode === 'reset' && stage === 'confirm')) && password !== confirmPassword) {
        throw new Error('Passwords do not match.')
      }
      if (stage === 'request') {
        if (mode === 'signup') await api('/auth/signup/request', 'POST', { name, email, password })
        if (mode === 'reset') await api('/auth/reset/request', 'POST', { email })
        if (mode === 'change-email') await api('/auth/change-email/request', 'POST', { email })
        if (mode === 'change-password') await api('/auth/change-password/request', 'POST')
        setStage('confirm')
      } else {
        if (mode === 'signup') await api('/auth/signup/confirm', 'POST', { email, code: String(values.get('code')) })
        if (mode === 'reset') await api('/auth/reset/confirm', 'POST', { email, code: String(values.get('code')), password })
        if (mode === 'change-password') await api('/auth/change-password/confirm', 'POST', { code: String(values.get('code')), password })
        if (mode === 'change-email') await api('/auth/change-email/confirm', 'POST', { email, current_code: String(values.get('current_code')), new_code: String(values.get('new_code')) })
        done(mode === 'signup' ? 'Email verified. Sign in with your new account.' : mode === 'reset' ? 'Password changed. Sign in with your new password.' : 'Account updated. Sign in again.')
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Please try again.') }
    finally { setBusy(false) }
  }
  return <form className="card auth-card account-flow" onSubmit={submit}>
    <h2>{title}</h2>
    {stage === 'request' ? <>
      {mode === 'signup' && <label>Your name<input required maxLength={150} autoComplete="name" value={name} onChange={e => setName(e.target.value)} /></label>}
      {mode === 'change-password' ? <p>A verification code will be sent to {currentEmail}.</p> : <label>{mode === 'change-email' ? 'New email address' : 'Email address'}<input required type="email" maxLength={254} autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} /></label>}
      {(mode === 'signup' || mode === 'change-password') && <><label>{mode === 'signup' ? 'Password' : 'New password'}<input required minLength={12} maxLength={256} type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} /><small>At least 12 characters.</small></label><label>Confirm password<input required minLength={12} maxLength={256} type="password" autoComplete="new-password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} /></label></>}
    </> : <>
      <p>{mode === 'change-email' ? `Enter the codes sent to ${currentEmail} and ${email}.` : `Enter the 6-digit code sent to ${mode === 'change-password' ? currentEmail : email}.`} Codes expire after 10 minutes.</p>
      {mode === 'change-email' && <label>Code from current email<input required name="current_code" inputMode="numeric" pattern="[0-9]{6}" autoComplete="one-time-code" /></label>}
      <label>{mode === 'change-email' ? 'Code from new email' : 'Verification code'}<input required name={mode === 'change-email' ? 'new_code' : 'code'} inputMode="numeric" pattern="[0-9]{6}" autoComplete="one-time-code" /></label>
      {mode === 'reset' && <><label>New password<input required minLength={12} maxLength={256} type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} /><small>At least 12 characters.</small></label><label>Confirm new password<input required minLength={12} maxLength={256} type="password" autoComplete="new-password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} /></label></>}
      <button type="button" className="text-btn" onClick={() => setStage('request')}>Start again or request a new code</button>
    </>}
    {error && <p role="alert" className="form-error">{error}</p>}
    <div className="modal-actions"><button type="button" className="secondary-btn" onClick={cancel}>Cancel</button><button className="primary-btn" disabled={busy}>{busy ? 'Please wait…' : stage === 'request' ? 'Send verification code' : 'Confirm'}</button></div>
  </form>
}
