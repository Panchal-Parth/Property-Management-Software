import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { ArrowUpRight, BarChart3, Bell, Building2, CircleDollarSign, FileText, Home, LayoutDashboard, Menu, MoreHorizontal, Plus, Search, Settings, Users } from 'lucide-react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, setCsrf } from './api'
import type { State, Property, Unit, Tenant, Lease, Monthly, Document } from './types'
import Editor from './Editor'
import type { Edit, Field } from './Editor'
import './App.css'
import './pages.css'
import './typography.css'
import './live.css'

const totalExpense = (r: Monthly) => r.amounts.slice(1).reduce((a, b) => a + b, 0)
const match = (query: string, ...values: unknown[]) => values.join(' ').toLowerCase().includes(query.trim().toLowerCase())
const text = (data: FormData, key: string) => String(data.get(key) || '').trim()
const optionalId = (data: FormData, key: string) => text(data, key) ? Number(text(data, key)) : null
const cents = (data: FormData, key: string) => {
  const value = text(data, key)
  if (!/^\d+(\.\d{1,2})?$/.test(value)) throw new Error('Enter nonnegative amounts with at most two decimal places.')
  const result = Math.round(Number(value) * 100)
  if (!Number.isSafeInteger(result)) throw new Error('Amount is too large.')
  return result
}
const tooltip = { border: '1px solid #dbe5e1', borderRadius: 12, padding: '14px 18px', fontSize: 16, background: 'white', color: '#273c43', boxShadow: '0 8px 28px #20383d24' }
const colors = ['#416f73', '#ae512d', '#785991', '#356a9c', '#8a671c']

function Actions({ name, actions }: { name: string; actions: { label: string; run: () => void }[] }) {
  return <details className="property-actions" onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) e.currentTarget.open = false }} onKeyDown={e => { if (e.key === 'Escape') e.currentTarget.open = false }}>
    <summary aria-label={'Actions for ' + name}><MoreHorizontal /></summary><div className="property-action-menu">{actions.map(a => <button key={a.label} onClick={e => { e.currentTarget.closest('details')!.open = false; a.run() }}>{a.label}</button>)}</div>
  </details>
}
function Empty({ children }: { children: ReactNode }) { return <p className="empty-state">{children}</p> }

export default function App() {
  const [authenticated, setAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<State | null>(null)
  const [error, setError] = useState('')
  const [page, setPage] = useState('Dashboard')
  const [query, setQuery] = useState('')
  const [month, setMonth] = useState('')
  const [scope, setScope] = useState('')
  const [kind, setKind] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [selectedProperty, setSelectedProperty] = useState<number | null>(null)
  const [edit, setEdit] = useState<Edit | null>(null)
  const [mobile, setMobile] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [noticeOpen, setNoticeOpen] = useState(false)
  const [readNotices, setReadNotices] = useState<string[]>([])
  const uploadRef = useRef<HTMLInputElement>(null)
  const reload = useCallback(async () => { const state = await api<State>('/state'); setData(state); setMonth(current => current || state.today.slice(0, 7)) }, [])
  useEffect(() => {
    const expired = () => { setAuthenticated(false); setData(null); setEdit(null) }
    window.addEventListener('havenly:unauthorized', expired)
    ;(async () => {
      try { const s = await api<{ csrf: string }>('/auth/session'); setCsrf(s.csrf); setAuthenticated(true); await reload() }
      catch (e) { if (e instanceof Error && e.message !== 'Sign in to continue.') setError(e.message) }
      finally { setLoading(false) }
    })()
    return () => window.removeEventListener('havenly:unauthorized', expired)
  }, [reload])
  useEffect(() => { if (!notice) return; const timer = setTimeout(() => setNotice(''), 4000); return () => clearTimeout(timer) }, [notice])
  function navigate(next: string) { setPage(next); setQuery(''); setScope(''); setKind(''); setSelectedProperty(null); setMobile(false); setNoticeOpen(false); setError('') }
  async function save(path: string, method: string, body?: unknown) {
    await api(path, method, body)
    try { await reload() } catch { throw new Error('Saved, but refreshing the list failed. Refresh before submitting again.') }
    setNotice('Saved successfully')
  }
  async function action(path: string, method = 'POST') {
    setBusy(true); setError('')
    try { await save(path, method) } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  if (loading) return <main className="auth-shell"><div className="card auth-card">Loading your workspace…</div></main>
  if (!authenticated) return <Login onLogin={async () => { setAuthenticated(true); setLoading(true); setError(''); try { await reload() } catch (e) { setError((e as Error).message) } finally { setLoading(false) } }} />
  if (!data) return <main className="auth-shell"><div className="card auth-card"><p role="alert">{error || 'Unable to load workspace.'}</p><button className="primary-btn" onClick={() => reload().catch(e => setError(e.message))}>Retry</button></div></main>

  const state = data
  const currency = (value: number) => (value / 100).toLocaleString('en-US', { style: 'currency', currency: state.settings.currency })
  const propertyName = (id: number | null) => state.properties.find(p => p.id === id)?.name || 'Unassigned'
  const unitName = (id: number | null) => { const u = state.units.find(u => u.id === id); return u ? propertyName(u.property_id) + ' · ' + u.label : 'Whole property' }
  const activeLease = (unitId: number) => state.leases.find(l => l.unit_id === unitId && !l.cancelled && l.start_date <= state.today && l.end_date >= state.today)
  const activeProperties = state.properties.filter(p => !p.archived)
  const availableUnits = state.units.filter(u => !u.archived && activeProperties.some(p => p.id === u.property_id))
  const occupied = availableUnits.filter(u => activeLease(u.id)).length
  const financialRows = state.records.filter(r => r.month === month && (!scope || String(r.property_id) === scope))
  const income = financialRows.reduce((sum, r) => sum + r.amounts[0], 0)
  const expense = financialRows.reduce((sum, r) => sum + totalExpense(r), 0)
  const propertyOptions = activeProperties.map(p => ({ value: p.id, label: p.name + ' — ' + p.address }))
  const emptyOption = { value: '', label: 'Not assigned' }
  const moneyField = (name: string, label: string, amount = 0): Field => ({ name, label: label + ' (' + state.settings.currency + ')', type: 'number', min: '0', step: '0.01', value: (amount / 100).toFixed(2), required: true })
  const activeTenantOptions = state.tenants.filter(t => !t.archived).map(t => ({ value: t.id, label: t.name }))

  function propertyEditor(p?: Property) {
    setEdit({ title: p ? 'Edit property' : 'Add property', note: 'After saving, open Units to add each rentable apartment or commercial space.', fields: [
      { name: 'name', label: 'Property name', value: p?.name, required: true },
      { name: 'address', label: 'Full address', value: p?.address, required: true },
      { name: 'kind', label: 'Property type', value: p?.kind || 'Apartment', options: ['Apartment', 'Commercial'].map(value => ({ value, label: value })) },
      { name: 'notes', label: 'Notes', type: 'textarea', value: p?.notes },
    ], submit: f => save('/properties' + (p ? '/' + p.id : ''), p ? 'PUT' : 'POST', { name: text(f, 'name'), address: text(f, 'address'), kind: text(f, 'kind'), notes: text(f, 'notes') }) })
  }
  function unitEditor(propertyId: number, u?: Unit) {
    setEdit({ title: u ? 'Edit unit / space' : 'Add unit / space', fields: [
      { name: 'label', label: 'Apartment number or space label', required: true, value: u?.label || (state.properties.find(p => p.id === propertyId)?.kind === 'Commercial' ? 'Premises' : ''), help: 'Commercial properties can use “Premises” without an apartment number.' },
      { name: 'floor', label: 'Floor (optional)', value: u?.floor },
      { name: 'unavailable', label: 'Availability', value: u?.unavailable ? '1' : '0', options: [{ value: '0', label: 'Available for rental' }, { value: '1', label: 'Unavailable / maintenance' }] },
    ], submit: f => save('/units' + (u ? '/' + u.id : ''), u ? 'PUT' : 'POST', { property_id: propertyId, label: text(f, 'label'), floor: text(f, 'floor'), unavailable: text(f, 'unavailable') === '1' }) })
  }
  function tenantEditor(t?: Tenant) {
    setEdit({ title: t ? 'Edit tenant' : 'Add tenant', fields: [
      { name: 'name', label: 'Full name', required: true, value: t?.name }, { name: 'phone', label: 'Phone', value: t?.phone, type: 'tel' },
      { name: 'email', label: 'Email', value: t?.email, type: 'email' }, { name: 'emergency_contact', label: 'Emergency contact', value: t?.emergency_contact },
      { name: 'notes', label: 'Notes', value: t?.notes, type: 'textarea' },
    ], submit: f => save('/tenants' + (t ? '/' + t.id : ''), t ? 'PUT' : 'POST', Object.fromEntries(['name', 'phone', 'email', 'emergency_contact', 'notes'].map(k => [k, text(f, k)]))) })
  }
  function leaseEditor(l?: Lease) {
    setEdit({ title: l ? 'Edit lease / end tenancy' : 'Add lease', note: 'Dates are inclusive. To vacate a unit, set the end date to the last occupied day. Cancel only leases that should never take effect. Hold Ctrl / Cmd to select roommates.', fields: [
      { name: 'unit_id', label: 'Unit / space', required: true, value: l?.unit_id, options: availableUnits.map(u => ({ value: u.id, label: unitName(u.id) })) },
      { name: 'tenant_ids', label: 'Tenants', required: true, value: l?.tenant_ids.map(String) || [], multiple: true, options: activeTenantOptions },
      { name: 'start_date', label: 'Start date', type: 'date', required: true, value: l?.start_date || state.today },
      { name: 'end_date', label: 'End date', type: 'date', required: true, value: l?.end_date },
      moneyField('rent', 'Agreed monthly rent', l?.rent_cents), moneyField('deposit', 'Agreed security deposit', l?.deposit_cents),
      { name: 'cancelled', label: 'Lease status', value: l?.cancelled ? '1' : '0', options: [{ value: '0', label: 'Valid lease (occupancy follows dates)' }, { value: '1', label: 'Cancelled' }] },
      { name: 'notes', label: 'Notes', type: 'textarea', value: l?.notes },
    ], submit: f => save('/leases' + (l ? '/' + l.id : ''), l ? 'PUT' : 'POST', { unit_id: Number(text(f, 'unit_id')), tenant_ids: f.getAll('tenant_ids').map(Number), start_date: text(f, 'start_date'), end_date: text(f, 'end_date'), rent_cents: cents(f, 'rent'), deposit_cents: cents(f, 'deposit'), cancelled: text(f, 'cancelled') === '1', notes: text(f, 'notes') }) })
  }
  function monthlyEditor(r?: Monthly) {
    setEdit({ title: r ? 'Edit monthly entry' : 'Add monthly entry', note: 'Record rent actually received, not rent expected. Shared building expenses belong to Whole property; do not enter the same cost again for a unit. Deposits are tracked separately.', fields: [
      { name: 'property_id', label: 'Property', required: true, value: r?.property_id || scope, options: propertyOptions },
      { name: 'unit_id', label: 'Scope', value: r?.unit_id || '', options: [{ value: '', label: 'Whole property / shared costs' }, ...availableUnits.map(u => ({ value: u.id, label: unitName(u.id) }))] },
      { name: 'month', label: 'Month', type: 'month', required: true, value: r?.month || month },
      ...state.categories.map((c, i) => moneyField('amount' + i, c.name, r?.amounts[i])),
      { name: 'notes', label: 'Notes', type: 'textarea', value: r?.notes },
    ], submit: async f => {
      await save('/records' + (r ? '/' + r.id : ''), r ? 'PUT' : 'POST', { property_id: Number(text(f, 'property_id')), unit_id: optionalId(f, 'unit_id'), month: text(f, 'month'), amounts: state.categories.map((_, i) => cents(f, 'amount' + i)), notes: text(f, 'notes') })
      setMonth(text(f, 'month')); setScope(text(f, 'property_id')); setQuery('')
    } })
  }
  function settingsEditor() {
    setEdit({ title: 'Profile & preferences', note: 'Currency is the denomination of your records, not an exchange-rate conversion. It cannot be changed once leases or financial records exist.', fields: [
      { name: 'name', label: 'Owner name', required: true, value: state.settings.name },
      { name: 'currency', label: 'Currency', value: state.settings.currency, options: ['USD', 'CAD', 'GBP', 'EUR', 'INR'].map(value => ({ value, label: value })) },
      { name: 'timezone', label: 'Timezone', required: true, value: state.settings.timezone, help: 'IANA timezone, e.g. America/New_York or Asia/Kolkata' },
      { name: 'category5', label: 'Expense category five', required: true, value: state.categories[4].name },
      { name: 'category6', label: 'Expense category six', required: true, value: state.categories[5].name },
    ], submit: f => save('/settings', 'PUT', Object.fromEntries(['name', 'currency', 'timezone', 'category5', 'category6'].map(k => [k, text(f, k)]))) })
  }
  function documentEditor(d: Document) {
    setEdit({ title: 'Document details', note: 'Choose related records from the same property. Files are downloaded as attachments and require login.', fields: [
      { name: 'filename', label: 'Filename', required: true, value: d.filename },
      { name: 'kind', label: 'Document type', value: d.kind, options: ['Lease', 'Tenant', 'Receipt', 'Property', 'Other'].map(value => ({ value, label: value })) },
      { name: 'property_id', label: 'Property', value: d.property_id || '', options: [emptyOption, ...state.properties.map(p => ({ value: p.id, label: p.name + ' — ' + p.address }))] },
      { name: 'unit_id', label: 'Unit', value: d.unit_id || '', options: [emptyOption, ...state.units.map(u => ({ value: u.id, label: unitName(u.id) }))] },
      { name: 'tenant_id', label: 'Tenant', value: d.tenant_id || '', options: [emptyOption, ...state.tenants.map(t => ({ value: t.id, label: t.name }))] },
      { name: 'lease_id', label: 'Lease', value: d.lease_id || '', options: [emptyOption, ...state.leases.map(l => ({ value: l.id, label: unitName(l.unit_id) + ' · ' + l.start_date }))] },
      { name: 'record_id', label: 'Monthly record / receipt', value: d.record_id || '', options: [emptyOption, ...state.records.map(r => ({ value: r.id, label: propertyName(r.property_id) + ' · ' + r.month + ' · ' + unitName(r.unit_id) }))] },
      { name: 'notes', label: 'Notes', value: d.notes, type: 'textarea' },
    ], submit: f => save('/documents/' + d.id, 'PUT', { filename: text(f, 'filename'), kind: text(f, 'kind'), notes: text(f, 'notes'), ...Object.fromEntries(['property_id', 'unit_id', 'tenant_id', 'lease_id', 'record_id'].map(k => [k, optionalId(f, k)])) }) })
  }
  function depositEditor(l: Lease) {
    setEdit({ title: 'Record deposit transaction', note: 'Deposits do not count as rent income. Refunds and deductions cannot exceed the amount held.', fields: [
      { name: 'kind', label: 'Type', options: ['received', 'refunded', 'deducted'].map(value => ({ value, label: value })) },
      moneyField('amount', 'Amount'), { name: 'date', label: 'Date', required: true, type: 'date', value: state.today },
      { name: 'notes', label: 'Notes', type: 'textarea' },
    ], submit: f => save('/deposits', 'POST', { lease_id: l.id, kind: text(f, 'kind'), amount_cents: cents(f, 'amount'), date: text(f, 'date'), notes: text(f, 'notes') }) })
  }
  const archive = (resource: string, id: number, archived: number) => {
    if (window.confirm(archived ? 'Restore this record?' : 'Archive this record? Its financial and lease history will be retained.')) void action('/' + resource + '/' + id + (archived ? '/restore' : '/archive'))
  }
  const stat = (label: string, value: string | number, hint: string) => <div className="card mini-stat" key={label}><span>{label}</span><strong>{value}</strong><small>{hint}</small></div>
  const selectMonth = <label className="control">Month<input type="month" required value={month} onChange={e => setMonth(e.target.value)} /></label>
  const selectProperty = <label className="control">Property<select value={scope} onChange={e => setScope(e.target.value)}><option value="">All properties</option>{state.properties.map(p => <option key={p.id} value={p.id}>{p.name} — {p.address}</option>)}</select></label>
  const financialStats = <div className="metrics">{stat('Rent received', currency(income), month)}{stat('Expenses', currency(expense), 'Five expense categories')}{stat('Net profit', currency(income - expense), 'Rent received minus expenses')}{stat('Occupancy', availableUnits.length ? Math.round(occupied / availableUnits.length * 100) + '%' : '—', occupied + ' / ' + availableUnits.length + ' units today')}</div>
  const chartData = [...new Set(state.records.filter(r => !scope || String(r.property_id) === scope).map(r => r.month))].sort().map(m => {
    const list = state.records.filter(r => r.month === m && (!scope || String(r.property_id) === scope))
    const rent = list.reduce((sum, r) => sum + r.amounts[0], 0)
    const costs = list.reduce((sum, r) => sum + totalExpense(r), 0)
    return { month: m, income: rent, expenses: costs, profit: rent - costs }
  })
  const chart = (profit = false) => <div className="card chart-card"><h2>{profit ? 'Monthly net profit' : 'Income & expenses'}</h2><p className="subheading">All recorded months · {state.settings.currency} · Hover for details</p>{!chartData.length ? <Empty>Add a monthly entry to see your financial history.</Empty> : <ResponsiveContainer width="100%" height={300}>{profit ?
    <BarChart data={chartData}><CartesianGrid vertical={false} stroke="#dbe5e1" /><XAxis dataKey="month" tick={{ fontSize: 14, fill: '#4f666b' }} /><YAxis width={80} tickFormatter={v => String(v / 100)} tick={{ fontSize: 14, fill: '#4f666b' }} /><Tooltip content={({ active, payload }) => { const r = payload?.[0]?.payload; return active && r ? <div style={tooltip}><strong>{r.month}</strong><div>Rent: {currency(r.income)}</div><div>Expenses: {currency(r.expenses)}</div><div>Profit: {currency(r.profit)}</div></div> : null }} /><Bar dataKey="profit" fill="#416f73" maxBarSize={60} radius={[5, 5, 0, 0]} /></BarChart>
    : <AreaChart data={chartData}><CartesianGrid vertical={false} stroke="#dbe5e1" /><XAxis dataKey="month" tick={{ fontSize: 14, fill: '#4f666b' }} /><YAxis width={80} tickFormatter={v => String(v / 100)} tick={{ fontSize: 14, fill: '#4f666b' }} /><Tooltip formatter={(v, name) => [currency(Number(v)), name === 'income' ? 'Rent received' : 'Expenses']} contentStyle={tooltip} /><Area type="monotone" dataKey="income" stroke="#416f73" fill="#dcebe6" strokeWidth={3} activeDot={{ r: 6 }} /><Area type="monotone" dataKey="expenses" stroke="#ae512d" fill="transparent" strokeWidth={3} activeDot={{ r: 6 }} /></AreaChart>
  }</ResponsiveContainer>}</div>
  const initials = state.settings.name.split(/\s+/).slice(0, 2).map(n => n[0]).join('').toUpperCase()
  const nav = [{ name: 'Dashboard', icon: LayoutDashboard }, { name: 'Properties', icon: Building2 }, { name: 'Tenants', icon: Users }, { name: 'Leases', icon: FileText }, { name: 'Transactions', icon: CircleDollarSign }, { name: 'Documents', icon: FileText }, { name: 'Reports', icon: BarChart3 }, { name: 'Settings', icon: Settings }]
  const notifications = [
    ...availableUnits.filter(u => !u.unavailable && !activeLease(u.id)).map(u => ({ id: 'unit-' + u.id, message: unitName(u.id) + ' is vacant', page: 'Properties' })),
    ...state.leases.filter(l => !l.cancelled && l.start_date <= state.today && l.end_date >= state.today && (Date.parse(l.end_date) - Date.parse(state.today)) / 86400000 <= 60).map(l => ({ id: 'lease-' + l.id + '-' + l.end_date, message: unitName(l.unit_id) + ' lease ends ' + l.end_date, page: 'Leases' })),
  ]
  const unread = notifications.filter(n => !readNotices.includes(n.id)).length
  const exportReport = () => {
    const quote = (v: string | number) => '"' + String(v).replace(/^[=+@-]/, "'$&").replaceAll('"', '""') + '"'
    const csv = [['Property', 'Scope', 'Month', ...state.categories.map(c => c.name), 'Profit', 'Currency'], ...state.records.filter(r => (!scope || String(r.property_id) === scope) && match(query, propertyName(r.property_id), unitName(r.unit_id), r.month)).map(r => [propertyName(r.property_id), unitName(r.unit_id), r.month, ...r.amounts.map(n => (n / 100).toFixed(2)), ((r.amounts[0] - totalExpense(r)) / 100).toFixed(2), state.settings.currency])].map(row => row.map(quote).join(',')).join('\r\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); const a = document.createElement('a'); a.href = url; a.download = 'havenly-report.csv'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return <div className={mobile ? 'app-shell mobile-open' : 'app-shell'}>
    <aside className="sidebar"><div className="brand"><Home /> Havenly</div><button className="workspace workspace-button" onClick={() => navigate('Settings')}><span className="avatar">{initials}</span><span><strong>{state.settings.name}</strong><small>Property owner</small></span><ArrowUpRight size={17} /></button><nav>{nav.map(({ name, icon: Icon }) => <button key={name} className={'nav-item ' + (page === name ? 'active' : '')} onClick={() => navigate(name)}><Icon size={18} />{name}</button>)}</nav><div className="sidebar-bottom"><div className="help-card"><strong>Need a hand?</strong><p>Learn your portfolio workflows.</p><button onClick={() => navigate('Guide')}>View guide <ArrowUpRight size={15} /></button></div><button className="nav-item" disabled={busy} onClick={async () => { setBusy(true); try { await api('/auth/logout', 'POST'); setAuthenticated(false); setData(null); setCsrf('') } catch (e) { setError((e as Error).message) } finally { setBusy(false) } }}>Sign out</button></div></aside>
    <main className="main-content"><header className="topbar"><button className="mobile-menu" aria-label="Toggle navigation" onClick={() => setMobile(!mobile)}><Menu /></button><div className="breadcrumbs">Workspace / <strong>{page}</strong></div><div className="top-actions">
      <button className="icon-btn" aria-label={'Notifications, ' + unread + ' unread'} onClick={() => setNoticeOpen(!noticeOpen)}><Bell />{unread > 0 && <span className="notification-count">{unread}</span>}</button>
      <button className="top-avatar profile-button" aria-label="Profile settings" onClick={() => navigate('Settings')}>{initials}</button>
    </div></header>
    {noticeOpen && <section className="live-notifications card" aria-label="Notifications"><h2>Notifications</h2><div className="toolbar"><button className="secondary-btn" onClick={() => setReadNotices(notifications.map(n => n.id))}>Mark all as read</button><button className="secondary-btn" onClick={() => setNoticeOpen(false)}>Close</button></div>{!notifications.length && <Empty>All caught up.</Empty>}{notifications.map(n => <button key={n.id} className="notification-item" onClick={() => { setReadNotices([...readNotices, n.id]); navigate(n.page) }}>{n.message} →</button>)}</section>}
    <div className="page"><div className="page-heading"><div><p className="eyebrow">YOUR RENTAL WORKSPACE</p><h1>{page === 'Dashboard' ? 'Welcome, ' + state.settings.name.split(' ')[0] : page}</h1><p className="subheading">{page === 'Dashboard' ? 'Your saved portfolio at a glance.' : 'Manage your records securely in one place.'}</p></div>
      {page === 'Properties' && <button className="primary-btn" onClick={() => propertyEditor()}><Plus size={18} />Add property</button>}
      {page === 'Tenants' && <button className="primary-btn" onClick={() => tenantEditor()}><Plus size={18} />Add tenant</button>}
      {page === 'Leases' && <button className="primary-btn" disabled={!availableUnits.length || !activeTenantOptions.length} onClick={() => leaseEditor()}>Add lease</button>}
      {page === 'Transactions' && <button className="primary-btn" disabled={!activeProperties.length} onClick={() => monthlyEditor()}>Add monthly entry</button>}
      {page === 'Documents' && <button className="primary-btn" disabled={busy} onClick={() => uploadRef.current?.click()}>{busy ? 'Uploading…' : 'Upload document'}</button>}
      {page === 'Reports' && <button className="secondary-btn" onClick={exportReport}>Export CSV</button>}
    </div>
    {error && <div className="error-banner" role="alert">{error}<button className="text-btn" onClick={() => setError('')}>Dismiss</button></div>}
    {page !== 'Settings' && page !== 'Guide' && <div className="toolbar live-toolbar"><label className="list-search"><Search size={18} /><input aria-label="Search this page" value={query} placeholder={page === 'Documents' ? 'Search filename, tenant, address…' : 'Search this page…'} onChange={e => setQuery(e.target.value)} /></label>{query && <button className="text-btn" onClick={() => setQuery('')}>Clear search</button>}
      {['Dashboard', 'Transactions', 'Reports', 'Documents'].includes(page) && selectProperty}
      {['Dashboard', 'Transactions'].includes(page) && selectMonth}
      {['Properties', 'Documents'].includes(page) && <label className="control">Type<select value={kind} onChange={e => setKind(e.target.value)}><option value="">All types</option>{(page === 'Properties' ? ['Apartment', 'Commercial'] : ['Lease', 'Tenant', 'Receipt', 'Property', 'Other']).map(k => <option key={k}>{k}</option>)}</select></label>}
      {['Properties', 'Tenants'].includes(page) && <label><input type="checkbox" checked={showArchived} onChange={e => setShowArchived(e.target.checked)} /> Show archived</label>}
    </div>}
    {page === 'Dashboard' && <>{financialStats}<div className="dashboard-grid">{chart()}<div className="card expense-card"><h2>Expense breakdown</h2><p className="subheading">{month} · {currency(expense)}</p>{expense > 0 ? <ResponsiveContainer width="100%" height={260}><PieChart><Pie data={state.categories.slice(1).map((c, i) => ({ name: c.name, value: financialRows.reduce((sum, r) => sum + r.amounts[i + 1], 0), fill: colors[i] }))} dataKey="value" nameKey="name" innerRadius={60} outerRadius={90} paddingAngle={3} /><Tooltip formatter={v => currency(Number(v))} contentStyle={tooltip} /></PieChart></ResponsiveContainer> : <Empty>No expenses recorded for this month.</Empty>}{state.categories.slice(1).map((c, i) => <div className="category" key={c.id}><span><i className="dot" style={{ background: colors[i] }} />{c.name}</span><strong>{currency(financialRows.reduce((sum, r) => sum + r.amounts[i + 1], 0))}</strong></div>)}</div></div>
      <section className="card page-list"><div className="toolbar"><h2>Recent monthly records</h2><button className="text-btn" onClick={() => navigate('Transactions')}>See all →</button></div>{financialRows.filter(r => match(query, propertyName(r.property_id), unitName(r.unit_id))).slice(0, 5).map(r => <div className="live-row" key={r.id}><div><strong>{propertyName(r.property_id)}</strong><small>{r.month} · {unitName(r.unit_id)}</small></div><span>Rent {currency(r.amounts[0])}</span><span>Profit {currency(r.amounts[0] - totalExpense(r))}</span></div>)}{!financialRows.length && <Empty>Add a monthly entry in Transactions to get started.</Empty>}</section></>}
    {page === 'Properties' && <>{state.properties.filter(p => (showArchived || !p.archived) && (!kind || p.kind === kind) && match(query, p.name, p.address)).map(p => <section className="card page-list property-section" key={p.id}><div className="toolbar"><div><h2>{p.name}{p.archived ? ' (archived)' : ''}</h2><p className="subheading">{p.address} · {p.kind}</p>{p.notes && <p>{p.notes}</p>}</div><div className="toolbar-actions"><button className="secondary-btn" onClick={() => setSelectedProperty(selectedProperty === p.id ? null : p.id)}>Units & details</button><Actions name={p.name} actions={[{ label: 'Edit', run: () => propertyEditor(p) }, { label: p.archived ? 'Restore' : 'Archive', run: () => archive('properties', p.id, p.archived) }]} /></div></div>
      <p>{state.units.filter(u => u.property_id === p.id && !u.archived).length} units · {state.units.filter(u => u.property_id === p.id && !u.archived && activeLease(u.id)).length} occupied</p>
      {selectedProperty === p.id && <><button className="secondary-btn" disabled={!!p.archived} onClick={() => unitEditor(p.id)}>Add unit / commercial space</button>{state.units.filter(u => u.property_id === p.id).map(u => <div className="live-row" key={u.id}><div><strong>{u.label}</strong><small>{u.floor ? 'Floor ' + u.floor : 'No floor specified'}</small></div><span className="badge">{u.archived ? 'Archived' : u.unavailable ? 'Maintenance' : activeLease(u.id) ? 'Rented' : 'Vacant'}</span><Actions name={u.label} actions={[{ label: 'Edit', run: () => unitEditor(p.id, u) }, { label: u.archived ? 'Restore' : 'Archive', run: () => archive('units', u.id, u.archived) }]} /></div>)}
      <h3>Financial history</h3>{state.records.filter(r => r.property_id === p.id).map(r => <div className="live-row" key={r.id}><span>{r.month} · {unitName(r.unit_id)}</span><strong>Profit {currency(r.amounts[0] - totalExpense(r))}</strong></div>)}</>}
    </section>)}{!state.properties.some(p => (showArchived || !p.archived) && (!kind || p.kind === kind) && match(query, p.name, p.address)) && <Empty>No matching properties. Add your first property above.</Empty>}</>}
    {page === 'Tenants' && <section className="card page-list"><h2>Tenant directory</h2>{state.tenants.filter(t => (showArchived || !t.archived) && match(query, t.name, t.phone, t.email, ...state.leases.filter(l => l.tenant_ids.includes(t.id)).map(l => unitName(l.unit_id)))).map(t => <div className="live-row tenant-live" key={t.id}><div><strong>{t.name}{t.archived ? ' (archived)' : ''}</strong><small>{t.phone || 'No phone'} · {t.email || 'No email'}</small>{t.emergency_contact && <small>Emergency: {t.emergency_contact}</small>}{t.notes && <small>{t.notes}</small>}</div><div>{state.leases.filter(l => l.tenant_ids.includes(t.id)).map(l => <p key={l.id}>{unitName(l.unit_id)}<small>{l.start_date} – {l.end_date}{l.cancelled ? ' · Cancelled' : ''}</small></p>)}</div><Actions name={t.name} actions={[{ label: 'Edit', run: () => tenantEditor(t) }, { label: t.archived ? 'Restore' : 'Archive', run: () => archive('tenants', t.id, t.archived) }]} /></div>)}{!state.tenants.length && <Empty>Add tenant contacts, then create a lease to assign their unit.</Empty>}</section>}
    {page === 'Leases' && <section className="card page-list"><h2>Lease history & deposits</h2>{(!availableUnits.length || !activeTenantOptions.length) && <p>Add an available unit and tenant before creating a lease.</p>}{state.leases.filter(l => match(query, unitName(l.unit_id), ...l.tenant_ids.map(id => state.tenants.find(t => t.id === id)?.name))).map(l => {
      const depositRows = state.deposits.filter(d => d.lease_id === l.id)
      const balance = depositRows.reduce((sum, d) => sum + (d.kind === 'received' ? d.amount_cents : -d.amount_cents), 0)
      return <div className="lease-block" key={l.id}><div className="live-row"><div><strong>{unitName(l.unit_id)}</strong><small>{l.tenant_ids.map(id => state.tenants.find(t => t.id === id)?.name).join(', ')}</small><small>{l.start_date} – {l.end_date} · {l.cancelled ? 'Cancelled' : l.start_date > state.today ? 'Upcoming' : l.end_date < state.today ? 'Ended' : 'Active'}</small></div><div>Rent {currency(l.rent_cents)}<small>Agreed deposit {currency(l.deposit_cents)}</small><small>Deposit held {currency(balance)}</small></div><Actions name={'Lease ' + l.id} actions={[{ label: 'Edit / end lease', run: () => leaseEditor(l) }, { label: 'Record deposit', run: () => depositEditor(l) }]} /></div>{depositRows.length > 0 && <details><summary>Deposit history</summary>{depositRows.map(d => <p key={d.id}>{d.date} · {d.kind} · {currency(d.amount_cents)} · {d.notes}</p>)}</details>}</div>
    })}{!state.leases.length && <Empty>No leases yet. Vacancy will update automatically based on lease dates.</Empty>}</section>}
    {page === 'Transactions' && <>{financialStats}<section className="card page-list"><div className="toolbar"><h2>Monthly entries</h2><button className="secondary-btn" onClick={settingsEditor}>Customize categories</button></div><div className="scroll-table"><table><thead><tr><th>Property / unit</th>{state.categories.map(c => <th key={c.id}>{c.name}</th>)}<th>Profit</th><th>Actions</th></tr></thead><tbody>{financialRows.filter(r => match(query, propertyName(r.property_id), unitName(r.unit_id), r.notes)).map(r => <tr key={r.id}><td>{propertyName(r.property_id)}<small>{unitName(r.unit_id)}</small></td>{r.amounts.map((amount, i) => <td key={i}>{currency(amount)}</td>)}<td>{currency(r.amounts[0] - totalExpense(r))}</td><td><button className="text-btn" onClick={() => monthlyEditor(r)}>Edit</button><button className="text-btn" disabled={busy} onClick={() => { if (window.confirm('Delete this monthly record? This cannot be undone.')) void action('/records/' + r.id, 'DELETE') }}>Delete</button></td></tr>)}</tbody></table></div>{!financialRows.length && <Empty>No entries for this property and month.</Empty>}</section></>}
    {page === 'Documents' && <section className="card page-list"><h2>Private documents</h2><p>PDF, PNG or JPEG · up to 15 MB · use Edit details to link uploads to a tenant, property or lease.</p><input ref={uploadRef} type="file" accept=".pdf,.png,.jpg,.jpeg" hidden onChange={async e => {
      const file = e.target.files?.[0]; e.target.value = ''; if (!file) return
      if (file.size > 15 * 1024 * 1024) { setError('File exceeds 15 MB.'); return }
      setBusy(true); setError('')
      try { const form = new FormData(); form.append('file', file); const created = await api<{ id: number }>('/documents', 'POST', form); const fresh = await api<State>('/state'); setData(fresh); const doc = fresh.documents.find(d => d.id === created.id); if (doc) documentEditor(doc); setNotice('Uploaded successfully') } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
    }} />{state.documents.filter(d => {
      const unit = state.units.find(u => u.id === d.unit_id)
      const lease = state.leases.find(l => l.id === d.lease_id)
      const leaseUnit = state.units.find(u => u.id === lease?.unit_id)
      const record = state.records.find(r => r.id === d.record_id)
      const p = state.properties.find(p => p.id === (d.property_id || unit?.property_id || leaseUnit?.property_id || record?.property_id))
      return (!kind || d.kind === kind) && (!scope || String(p?.id) === scope) && match(query, d.filename, d.notes, p?.name, p?.address, state.tenants.find(t => t.id === d.tenant_id)?.name)
    }).map(d => <div className="live-row" key={d.id}><div><strong>{d.filename}</strong><small>{d.kind} · {Math.ceil(d.size / 1024)} KB · {d.created_at}</small><small>{propertyName(d.property_id)} · {state.tenants.find(t => t.id === d.tenant_id)?.name || 'No tenant assigned'}</small></div><Actions name={d.filename} actions={[{ label: 'Edit details', run: () => documentEditor(d) }, { label: 'Download', run: () => { window.location.href = '/api/documents/' + d.id + '/download' } }, { label: 'Delete', run: () => { if (window.confirm('Remove this document? It will no longer appear or be downloadable.')) void action('/documents/' + d.id, 'DELETE') } }]} /></div>)}{!state.documents.length && <Empty>No documents uploaded yet.</Empty>}</section>}
    {page === 'Reports' && <>{chart(true)}<section className="card page-list report-comparison"><h2>Property comparison</h2><p>All recorded months · deposits excluded</p>{state.properties.filter(p => (!scope || String(p.id) === scope) && match(query, p.name, p.address)).map(p => { const list = state.records.filter(r => r.property_id === p.id); return <div className="live-row" key={p.id}><strong>{p.name}</strong><span>{currency(list.reduce((sum, r) => sum + r.amounts[0] - totalExpense(r), 0))}</span></div> })}<button className="secondary-btn" onClick={() => window.print()}>Print / save as PDF</button></section></>}
    {page === 'Settings' && <section className="card page-list"><h2>Profile & financial preferences</h2><p>{state.settings.name} · {state.settings.email}</p><p>{state.settings.currency} · {state.settings.timezone}</p><p>Categories: {state.categories.map(c => c.name).join(', ')}</p><button className="primary-btn" onClick={settingsEditor}>Edit settings</button><h3>Security & backups</h3><p>Your account uses a private server session. Sign out on shared devices. Password resets and full backups are performed with the server management commands in the project README.</p></section>}
    {page === 'Guide' && <section className="card page-list"><h2>Quick-start guide</h2>{[
      ['Properties', 'Add a building or commercial property, then open Units & details to create each rentable space. Use Premises for a commercial space with no apartment number.'],
      ['Tenants', 'Add tenant contact details, including emergency contacts.'],
      ['Leases', 'Assign one or more tenants to a unit and enter lease dates, agreed rent and deposit. Occupancy follows lease dates. End a tenancy by updating its end date. Track deposit receipts and refunds separately.'],
      ['Transactions', 'Record rent received and five expense categories every month. Choose a unit or whole-property scope; never enter the same expense twice. Shared costs should be entered once at property level.'],
      ['Documents', 'Upload private PDF or image files. Use Edit details to assign property, unit, tenant, lease or receipt links.'],
      ['Reports', 'Review saved monthly profit, export CSV, or print to PDF.'],
      ['Settings', 'Update your name, timezone and category labels. Currency is locked once financial history exists.'],
    ].map(([target, description]) => <article className="guide-step" key={target}><h3>{target}</h3><p>{description}</p><button className="secondary-btn" onClick={() => navigate(target)}>Open {target}</button></article>)}<p>All records and uploads are saved on the server. Automated backups must be configured by the server operator.</p></section>}
    </div></main>{edit && <Editor edit={edit} close={() => setEdit(null)} />}{notice && <div className="toast" role="status">{notice}</div>}
  </div>
}

function Login({ onLogin }: { onLogin: () => Promise<void> }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [configured, setConfigured] = useState(true)
  useEffect(() => { api<{ configured: boolean }>('/auth/status').then(r => setConfigured(r.configured)).catch(() => setError('Backend unavailable. Start the API server and retry.')) }, [])
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setError('')
    const form = new FormData(e.currentTarget)
    try { const response = await api<{ csrf: string }>('/auth/login', 'POST', { email: text(form, 'email'), password: String(form.get('password')) }); setCsrf(response.csrf); await onLogin() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return <main className="auth-shell"><form className="card auth-card" onSubmit={submit}><div className="brand auth-brand"><Home /> Havenly</div><h1>Your portfolio, in one place.</h1><p>Sign in to manage your properties and financial records.</p>{!configured && <p className="error-banner">An owner account has not been created. In the backend terminal, run <code>python manage.py create-owner</code>, then refresh.</p>}<label>Email<input required autoComplete="username" name="email" type="email" /></label><label>Password<input required autoComplete="current-password" name="password" type="password" /></label>{error && <p role="alert" className="form-error">{error}</p>}<button className="primary-btn" disabled={busy || !configured}>{busy ? 'Signing in…' : 'Sign in'}</button></form></main>
}
