import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { KeyRound, ShieldCheck } from 'lucide-react'
import { api } from './api'

type AdminAccount = { owner_email: string | null; admin_email: string }

export default function AdminPanel() {
  const [account, setAccount] = useState<AdminAccount | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [adminPassword, setAdminPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api<AdminAccount>('/admin/account').then(value => { setAccount(value); setEmail(value.owner_email || '') }).catch(cause => setError((cause as Error).message))
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setNotice('')
    if (password !== confirm) { setError('New passwords do not match.'); return }
    const emailChanged = email.trim().toLowerCase() !== account?.owner_email?.toLowerCase()
    if (!emailChanged && !password) { setError('Enter a different owner email or a new password.'); return }
    setBusy(true)
    try {
      const result = await api<{ message: string }>('/admin/account', 'PUT', { email: emailChanged ? email : undefined, password: password || undefined, admin_password: adminPassword })
      setAccount(current => current ? { ...current, owner_email: email } : current)
      setPassword(''); setConfirm(''); setAdminPassword(''); setNotice(result.message)
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  return <section className="card page-list admin-panel" aria-labelledby="admin-access-title">
    <div className="admin-heading"><ShieldCheck size={28} /><div><p className="eyebrow">ADMINISTRATOR ONLY</p><h2 id="admin-access-title">Owner account access</h2></div></div>
    <p className="action-guidance">You are signed in as {account?.admin_email || 'an administrator'}. Changes here bypass email verification, are recorded in the security audit log, and immediately sign out every owner session.</p>
    <form onSubmit={submit}>
      <label>Owner email address<input required type="email" maxLength={254} autoComplete="off" value={email} onChange={event => setEmail(event.target.value)} /></label>
      <div className="form-row"><label>New owner password<input type="password" minLength={12} maxLength={256} autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} /><small>Leave blank to keep the current password.</small></label><label>Confirm new password<input type="password" minLength={12} maxLength={256} autoComplete="new-password" value={confirm} onChange={event => setConfirm(event.target.value)} /></label></div>
      <label>Confirm your administrator password<input required type="password" maxLength={256} autoComplete="current-password" value={adminPassword} onChange={event => setAdminPassword(event.target.value)} /><small>Required every time before owner credentials can be changed.</small></label>
      {error && <p className="form-error" role="alert">{error}</p>}
      {notice && <p className="action-guidance" role="status">{notice}</p>}
      <button className="primary-btn" disabled={busy}><KeyRound size={17} />{busy ? 'Updating securely…' : 'Update owner credentials'}</button>
    </form>
  </section>
}
