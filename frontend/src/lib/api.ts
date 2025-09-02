export type RecentItem = {
  id: number
  mailbox: string
  uid: number
  message_id: string | null
  subject: string
  from: string
  from_name: string | null
  from_email: string | null
  date: string | null
  snippet: string
  body_preview: string | null
  is_unread: boolean
  is_answered: boolean
  is_flagged: boolean
  in_reply_to: string | null
  references: string | null
}

export type RecentResponse = {
  items: RecentItem[]
}

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8000'

async function handle(r: Response) {
  if (!r.ok) {
    const txt = await r.text().catch(() => '')
    throw new Error(`HTTP ${r.status} ${r.statusText}${txt ? `: ${txt}` : ''}`)
  }
  return r.json()
}

export async function fetchRecent(limit = 20): Promise<RecentResponse> {
  const r = await fetch(`${API_BASE}/api/messages/recent?limit=${limit}`)
  return handle(r)
}

export async function refreshNow(): Promise<any> {
  const r = await fetch(`${API_BASE}/api/refresh`, { method: 'POST' })
  return handle(r)
}

export type BackfillParams = {
  mailbox?: string
  days: number
  only_unseen?: boolean
  limit?: number | null
}

export async function backfill(params: BackfillParams): Promise<any> {
  const r = await fetch(`${API_BASE}/api/backfill`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      mailbox: params.mailbox || undefined,
      days: params.days,
      only_unseen: params.only_unseen ?? true,
      limit: params.limit ?? null,
    }),
  })
  return handle(r)
}

export async function search(q: string, limit = 50): Promise<RecentResponse> {
  const url = new URL(`${API_BASE}/api/search`)
  url.searchParams.set('q', q)
  url.searchParams.set('limit', String(limit))
  const r = await fetch(url.toString())
  return handle(r)
}

export async function fetchBody(messageId: number): Promise<{ message_id: number; body: string }> {
  const r = await fetch(`${API_BASE}/api/messages/${messageId}/body`)
  return handle(r)
}

