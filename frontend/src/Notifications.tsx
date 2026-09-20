import { useRef, useState } from 'react'
import { Bell, X } from 'lucide-react'

export default function Notifications({ properties, onProperties }: {
  properties: { id: number; name: string; units: number; occupied: number }[]
  onProperties: () => void
}) {
  const panel = useRef<HTMLDetailsElement>(null)
  const [read, setRead] = useState<string[]>([])
  const notices = properties.filter(p => p.units > p.occupied).map(p => ({
    id: `${p.id}:${p.units - p.occupied}`,
    title: p.name,
    message: `${p.units - p.occupied} vacant unit(s) available to rent.`,
  }))
  const unread = notices.filter(n => !read.includes(n.id)).length
  return <details ref={panel} className="notifications" onBlur={e => {
    if (!e.currentTarget.contains(e.relatedTarget)) e.currentTarget.open = false
  }} onKeyDown={e => {
    if (e.key === 'Escape' && panel.current) {
      panel.current.open = false
      panel.current.querySelector('summary')?.focus()
    }
  }}>
    <summary className="icon-btn" aria-label={`Notifications, ${unread} unread`}><Bell size={20} />{unread > 0 && <span className="notification-count">{unread}</span>}</summary>
    <section className="notification-panel" aria-label="Notifications">
      <div className="notification-heading"><h2>Notifications</h2><button className="close-btn" aria-label="Close notifications" onClick={() => { if (panel.current) panel.current.open = false }}><X size={18} /></button></div>
      <p>Current property alerts</p>
      {notices.length > 0 ? <>
        <button className="text-btn" disabled={!unread} onClick={() => setRead(notices.map(n => n.id))}>Mark all as read</button>
        {notices.map(n => <button key={n.id} className={read.includes(n.id) ? 'notification-item' : 'notification-item unread'} onClick={() => {
          setRead(current => [...current, n.id])
          if (panel.current) panel.current.open = false
          onProperties()
        }}><strong>{n.title}</strong><span>{n.message}</span><small>View properties →</small></button>)}
      </> : <p className="empty-state">You're all caught up. No vacant units to review.</p>}
    </section>
  </details>
}
