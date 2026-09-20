import './guide.css'

const steps = [
  { page: 'Properties', title: 'Add your properties', text: 'Choose Add property, enter a name and address, select Apartment or Commercial, and enter the unit count. Use the … menu to edit or delete it.' },
  { page: 'Tenants', title: 'Keep tenant contacts', text: 'Choose Add tenant to enter a name, phone number, and email. Use the tenant’s … menu to update contact details or delete the record.' },
  { page: 'Transactions', title: 'Record monthly finances', text: 'Choose Add monthly entry, select a property and month, and enter rent plus five expense amounts. Net profit is rent minus expenses. Use Edit to change an entry and Customize categories to rename the two flexible expenses.' },
  { page: 'Documents', title: 'Organize documents', text: 'Upload a file, then use … → Edit details to assign a property and document type. Search by property name, address, tenant, or filename. Download is available for files uploaded during your current visit.' },
  { page: 'Reports', title: 'Review your profit', text: 'Reports summarizes recorded monthly entries. Hover over a profit bar to see rent, expenses, and net profit. Property comparisons show totals across all recorded months.' },
  { page: 'Settings', title: 'Update your profile', text: 'Change Owner name and choose Save settings. Your name updates in the sidebar and dashboard, and is saved in this browser.' },
]

export default function Guide({ onNavigate, query }: { onNavigate: (page: string) => void; query: string }) {
  const visible = steps.filter(step => `${step.page} ${step.title} ${step.text}`.toLowerCase().includes(query.trim().toLowerCase()))
  return <section aria-labelledby="guide-title">
    <div className="page-heading"><div><p className="eyebrow">GETTING STARTED</p><h1 id="guide-title">Quick-start guide</h1><p className="subheading">Set up your portfolio and learn the available workflows.</p></div><button className="secondary-btn" onClick={() => onNavigate('Dashboard')}>Back to dashboard</button></div>
    <div className="card guide-note"><strong>Current preview</strong><p>Properties and financial entries reset on refresh. Tenant and document changes also reset when leaving their page. Keep original files and records separately until permanent storage is connected. Dashboard charts still include sample data.</p></div>
    <div className="guide-grid">{visible.map(step => <article className="card guide-card" key={step.page}><h2>{step.title}</h2><p>{step.text}</p><button className="secondary-btn" onClick={() => onNavigate(step.page)}>Open {step.page}</button></article>)}</div>
    {!visible.length && <p className="empty-state">No guide topics match your search.</p>}
  </section>
}
