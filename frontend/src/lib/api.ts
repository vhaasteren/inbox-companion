export type PreviewItem = {
  uid: number
  from: string
  subject: string
  date: string | null
}

export type PreviewResponse = {
  mailbox: string
  count: number
  items: PreviewItem[]
}

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8000'

export async function fetchPreview(limit = 10): Promise<PreviewResponse> {
  const r = await fetch(`${API_BASE}/api/mail/preview?limit=${limit}`)
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

