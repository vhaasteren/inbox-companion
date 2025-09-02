export type RecentItem = {
  id: number
  mailbox: string
  uid: number
  message_id: string | null
  subject: string
  from: string
  date: string | null
  snippet: string
}

export type RecentResponse = {
  items: RecentItem[]
}

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8000'

export async function fetchRecent(limit = 20): Promise<RecentResponse> {
  const r = await fetch(`${API_BASE}/api/messages/recent?limit=${limit}`)
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

