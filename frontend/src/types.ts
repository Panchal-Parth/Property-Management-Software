export type Property = { id: number; name: string; address: string; kind: string; notes: string; archived: number }
export type Unit = { expected_rent_cents: number | null; tenant_id: number | null; id: number; property_id: number; label: string; floor: string; kind: 'Residential' | 'Commercial'; notes: string; unavailable: number; archived: number }
export type Tenant = { id: number; name: string; phone: string; email: string; emergency_contact: string; notes: string; archived: number }
export type Lease = { id: number; unit_id: number; tenant_ids: number[]; start_date: string; end_date: string; rent_cents: number; deposit_cents: number; cancelled: number; notes: string }
export type Monthly = { expected_rent_cents: number | null; id: number; property_id: number; unit_id: number | null; month: string; amounts: number[]; notes: string }
export type Document = { id: number; filename: string; mime: string; size: number; kind: string; notes: string; property_id: number | null; unit_id: number | null; tenant_id: number | null; lease_id: number | null; record_id: number | null; created_at: string }
export type Deposit = { id: number; lease_id: number; kind: string; amount_cents: number; date: string; notes: string }
export type State = { today: string; settings: { name: string; email: string; currency: string; timezone: string }; categories: { id: number; name: string; kind: string }[]; properties: Property[]; units: Unit[]; tenants: Tenant[]; leases: Lease[]; records: Monthly[]; documents: Document[]; deposits: Deposit[]; dismissed_notifications: string[] }
