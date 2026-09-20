import { useState } from 'react'
import type { FormEvent } from 'react'

import { keys } from './financeModel'
import type { Amounts, Entry, useFinances } from './financeModel'
type Property = { id: number; name: string }
type Model = ReturnType<typeof useFinances>
const cents = (n: number) => Math.round(n * 100)
const expenses = (e: Amounts) => keys.slice(1).reduce((sum, key) => sum + cents(e[key]), 0) / 100
const currency = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export default function Finances({ properties, model, query, clearSearch }: {
  properties: Property[]; model: Model; query: string; clearSearch: () => void
}) {
  const { entries, setEntries, categories, setCategories } = model
  const [month, setMonth] = useState('2024-06')
  const [form, setForm] = useState<Entry | null>(null)
  const [editing, setEditing] = useState(false)
  const [categoryDraft, setCategoryDraft] = useState<string[] | null>(null)
  const [error, setError] = useState('')
  const labels = ['Rent', 'Water', 'Repairs', 'Miscellaneous', ...categories]
  const name = (id: number) => properties.find(p => p.id === id)?.name ?? 'Removed property'
  const monthly = entries.filter(e => e.month === month)
  const visible = monthly.filter(e => name(e.propertyId).toLowerCase().includes(query.trim().toLowerCase()))
  const income = monthly.reduce((sum, e) => sum + cents(e.rent), 0) / 100
  const expense = monthly.reduce((sum, e) => sum + cents(expenses(e)), 0) / 100
  function save(e: FormEvent) {
    e.preventDefault()
    if (!form) return
    if (!properties.some(p => p.id === form.propertyId)) { setError('Select an available property.'); return }
    if (keys.some(k => !Number.isFinite(form[k]) || form[k] < 0)) { setError('Enter a nonnegative amount for each category.'); return }
    const duplicate = entries.some(r => r.propertyId === form.propertyId && r.month === form.month)
    if (duplicate && !editing) { setError('An entry already exists for this property and month. Edit it in the table below.'); return }
    const saved = { ...form }
    keys.forEach(k => { saved[k] = cents(saved[k]) / 100 })
    setEntries(current => editing ? current.map(r => r.propertyId === saved.propertyId && r.month === saved.month ? saved : r) : [...current, saved])
    setMonth(saved.month); clearSearch(); setForm(null)
  }
  return <>
    <div className="page-heading"><div><p className="eyebrow">MONTHLY FINANCES</p><h1>Income & expenses</h1><p className="subheading">Record monthly rent and five expense categories.</p></div>
      <button className="primary-btn" disabled={!properties.length} onClick={() => { setError(''); setEditing(false); setForm({ propertyId: properties[0].id, month, rent: 0, water: 0, repairs: 0, misc: 0, insurance: 0, tax: 0 }) }}>Add monthly entry</button>
    </div>
    {!properties.length && <p>Add a property before recording monthly finances.</p>}
    <div className="finance-toolbar"><label>Month <input aria-label="Filter month" type="month" required value={month} onChange={e => setMonth(e.target.value)} /></label><span>{monthly.length} monthly entries</span></div>
    <div className="metrics">{[['Monthly rent', income], ['Total expenses', expense], ['Net profit', (cents(income) - cents(expense)) / 100]].map(([label, value]) => <div className="card mini-stat" key={label}><span>{label}</span><strong>{currency(Number(value))}</strong></div>)}</div>
    <div className="card page-list"><div className="toolbar"><div><h2 className="list-title">Monthly entries</h2><p className="list-subtitle">Amounts in USD. Entries remain available while navigating this session.</p></div><button className="secondary-btn" onClick={() => { setError(''); setCategoryDraft([...categories]) }}>Customize categories</button></div>
      <div className="finance-table"><div className="finance-row monthly-row finance-header"><span>Property</span>{labels.map((label, i) => <span key={i}>{label}</span>)}<span>Profit</span><span>Actions</span></div>
        {visible.map(record => <div className="finance-row monthly-row" key={record.propertyId}><strong>{name(record.propertyId)}</strong>{keys.map(k => <span key={k}>{currency(record[k])}</span>)}<strong>{currency((cents(record.rent) - cents(expenses(record))) / 100)}</strong><button className="secondary-btn" onClick={() => { setError(''); setEditing(true); setForm({ ...record }) }}>Edit</button></div>)}
      </div>{!visible.length && <p className="empty-state">No entries for this month and search.</p>}
    </div>
    {form && <div className="modal-backdrop"><form className="modal finance-modal" role="dialog" aria-modal="true" aria-labelledby="entry-heading" onSubmit={save} onKeyDown={e => { if (e.key === 'Escape') setForm(null) }}>
      <h2 id="entry-heading">{editing ? 'Edit monthly entry' : 'Add monthly entry'}</h2>
      <label>Property<select required disabled={editing} value={form.propertyId} onChange={e => setForm({ ...form, propertyId: Number(e.target.value) })}>{properties.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label>Month<input required disabled={editing} type="month" value={form.month} onChange={e => setForm({ ...form, month: e.target.value })} /></label>
      <div className="form-row">{keys.map((key, i) => <label key={key}>{labels[i]} (USD)<input required type="number" min="0" step="0.01" value={Number.isNaN(form[key]) ? '' : form[key]} onChange={e => setForm({ ...form, [key]: e.target.valueAsNumber })} /></label>)}</div>
      <p>Total expenses: {currency(expenses(form))}<br />Net profit: {currency((cents(form.rent) - cents(expenses(form))) / 100)}</p>
      {error && <p role="alert" className="form-error">{error}</p>}
      <div className="modal-actions"><button className="secondary-btn" type="button" onClick={() => setForm(null)}>Cancel</button><button className="primary-btn">Save entry</button></div>
    </form></div>}
    {categoryDraft && <div className="modal-backdrop"><form className="modal" role="dialog" aria-modal="true" aria-labelledby="categories-heading" onKeyDown={e => { if (e.key === 'Escape') setCategoryDraft(null) }} onSubmit={e => {
      e.preventDefault()
      const cleaned = categoryDraft.map(n => n.trim())
      const all = ['Rent', 'Water', 'Repairs', 'Miscellaneous', ...cleaned].map(n => n.toLowerCase())
      if (cleaned.some(n => !n) || new Set(all).size !== 6) { setError('Use two distinct category names, different from the four fixed categories.'); return }
      setCategories(cleaned); setCategoryDraft(null)
    }}><h2 id="categories-heading">Customize expense categories</h2><p>Rent, water, repairs, and miscellaneous stay fixed. Renaming a category keeps its recorded amounts.</p>{categoryDraft.map((value, i) => <label key={i}>Category {i + 5}<input required maxLength={40} value={value} onChange={e => setCategoryDraft(categoryDraft.map((n, index) => i === index ? e.target.value : n))} /></label>)}{error && <p role="alert" className="form-error">{error}</p>}<div className="modal-actions"><button type="button" className="secondary-btn" onClick={() => setCategoryDraft(null)}>Cancel</button><button className="primary-btn">Save categories</button></div></form></div>}
  </>
}
