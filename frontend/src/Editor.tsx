import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { X } from 'lucide-react'

export type Field = { name: string; label: string; value?: string | number | string[]; type?: string; required?: boolean; options?: { value: string | number; label: string }[]; multiple?: boolean; min?: string; step?: string; help?: string }
export type Edit = { title: string; fields: Field[]; submit: (data: FormData) => Promise<void>; note?: string }
export default function Editor({ edit, close }: { edit: Edit; close: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close() }, [])
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setError('')
    const data = new FormData(e.currentTarget)
    try { await edit.submit(data); close() } catch (e) { setError(e instanceof Error ? e.message : 'Could not save. Please try again.') } finally { setBusy(false) }
  }
  return <dialog ref={ref} className="editor" onCancel={e => { e.preventDefault(); if (!busy) close() }}>
    <form onSubmit={submit}><div className="modal-head"><h2>{edit.title}</h2><button type="button" aria-label="Close form" className="close-btn" disabled={busy} onClick={close}><X /></button></div>
      {edit.note && <p className="subheading">{edit.note}</p>}
      <fieldset disabled={busy}>{edit.fields.map(field => <label key={field.name}>{field.label}
        {field.options ? <select aria-label={field.label} name={field.name} required={field.required} multiple={field.multiple} defaultValue={field.value ?? ''}>{field.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
          : field.type === 'textarea' ? <textarea name={field.name} defaultValue={String(field.value ?? '')} maxLength={4000} />
          : <input name={field.name} required={field.required} type={field.type || 'text'} defaultValue={typeof field.value === 'object' ? '' : field.value} min={field.min} step={field.step} maxLength={field.type === 'password' ? 256 : 500} />}
        {field.help && <small>{field.help}</small>}
      </label>)}</fieldset>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="modal-actions"><button type="button" className="secondary-btn" disabled={busy} onClick={close}>Cancel</button><button className="primary-btn" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button></div>
    </form>
  </dialog>
}
