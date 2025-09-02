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

export type Analysis = {
  version: number
  lang: string
  bullets: string[]
  key_actions: string[]
  urgency: number
  importance: number
  priority: number
  labels: string[]
  confidence: number
  truncated: boolean
  model: string
  token_usage: { prompt: number; completion: number }
  notes?: string
}

export type SummarizeResult =
  | { id: number; status: 'ok'; skipped?: boolean; analysis?: Analysis }
  | { id: number; status: 'not_found' }
  | { id: number; status: 'error'; error?: string }

export type SummarizeResponse = {
  results: SummarizeResult[]
  summary?: { ok: number; skipped: number; errors: number }
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

// --- LLM analysis ---

export function summarize(
  ids: number[],
  opts?: { model?: string | null; force?: boolean }
): Promise<SummarizeResponse> {
  const base = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8000'
  return fetch(`${base}/api/llm/summarize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ids,
      model: opts?.model ?? null,
      force: opts?.force ?? false,
    }),
  }).then(handle)
}

export async function fetchAnalysis(
  messageId: number
): Promise<{ message_id: number; analysis: Analysis; labels: string[]; error?: string | null }> {
  const r = await fetch(`${API_BASE}/api/messages/${messageId}/analysis`)
  return handle(r)
}

export type BacklogItem = RecentItem & { priority: number; has_analysis: boolean }

export async function fetchBacklog(
  limit = 50,
  min_priority = 0,
  only_unread = false
): Promise<{ items: BacklogItem[] }> {
  const url = new URL(`${API_BASE}/api/backlog`)
  url.searchParams.set('limit', String(limit))
  url.searchParams.set('min_priority', String(min_priority))
  url.searchParams.set('only_unread', String(!!only_unread))
  const r = await fetch(url.toString())
  return handle(r)
}

export async function llmPing(): Promise<{ ok: boolean; models: string[]; error?: string | null }> {
  const r = await fetch(`${API_BASE}/api/llm/ping`)
  return handle(r)
}

export async function llmInspect(
  messageId: number
): Promise<{ message_id: number; has_summary: boolean; last_error: string | null; body_hash: string | null; updated_at: string | null }> {
  const r = await fetch(`${API_BASE}/api/llm/inspect/${messageId}`)
  return handle(r)
}

