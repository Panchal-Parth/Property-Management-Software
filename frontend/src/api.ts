let csrf = ''
export function setCsrf(value: string) { csrf = value }
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const upload = body instanceof FormData
  const response = await fetch('/api' + path, {
    method, credentials: 'same-origin',
    headers: { ...(body && !upload ? { 'Content-Type': 'application/json' } : {}), ...(method !== 'GET' ? { 'X-CSRF-Token': csrf } : {}) },
    body: body ? (upload ? body : JSON.stringify(body)) : undefined,
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    const detail = typeof error.detail === 'string' ? error.detail
      : Array.isArray(error.detail) ? error.detail.map((e: { msg: string; loc?: (string | number)[] }) => {
        const field = e.loc?.filter(part => part !== 'body').join(' → ').replaceAll('_', ' ')
        return field ? `${field}: ${e.msg}` : e.msg
      }).join('; ')
      : 'Request failed. Check the backend and try again.'
    if (response.status === 401) window.dispatchEvent(new Event('havenly:unauthorized'))
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}
