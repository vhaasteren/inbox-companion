import { useEffect, useMemo, useState } from 'react'
import {
  fetchRecent,
  type RecentItem,
  refreshNow,
  backfill,
  search as apiSearch,
  fetchBody,
  type BackfillParams,
} from './lib/api'

type Mode = 'recent' | 'search'

function FlagPills({ item }: { item: RecentItem }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      {/* Unread */}
      <span
        title={item.is_unread ? 'Unread' : 'Read'}
        className={`inline-flex items-center px-2 py-0.5 rounded-full border ${
          item.is_unread ? 'bg-blue-50 border-blue-200 text-blue-700' : 'bg-gray-50 border-gray-200 text-gray-500'
        }`}
      >
        ●
      </span>
      {/* Answered */}
      <span
        title={item.is_answered ? 'Answered' : 'Not answered'}
        className={`inline-flex items-center px-2 py-0.5 rounded-full border ${
          item.is_answered ? 'bg-green-50 border-green-200 text-green-700' : 'bg-gray-50 border-gray-200 text-gray-500'
        }`}
      >
        ↩
      </span>
      {/* Flagged */}
      <span
        title={item.is_flagged ? 'Starred' : 'Not starred'}
        className={`inline-flex items-center px-2 py-0.5 rounded-full border ${
          item.is_flagged ? 'bg-amber-50 border-amber-200 text-amber-700' : 'bg-gray-50 border-gray-200 text-gray-500'
        }`}
      >
        ★
      </span>
    </div>
  )
}

function Row({
  item,
  expanded,
  onToggle,
  body,
  onLoadBody,
}: {
  item: RecentItem
  expanded: boolean
  onToggle: (id: number) => void
  body: string | undefined
  onLoadBody: (id: number) => void
}) {
  const d = item.date ? new Date(item.date).toLocaleString() : '—'

  return (
    <div className="border-b border-gray-200">
      <button
        onClick={() => onToggle(item.id)}
        className="grid grid-cols-12 gap-2 py-3 w-full text-left hover:bg-gray-50 focus:outline-none"
      >
        <div className="col-span-4">
          <div className="font-medium truncate">{item.from_name || item.from}</div>
          {item.from_email && <div className="text-xs text-gray-500 truncate">{item.from_email}</div>}
        </div>
        <div className="col-span-6 truncate">
          <div className="font-semibold">{item.subject}</div>
          <div className="text-xs text-gray-600 mt-1 line-clamp-2">{item.snippet}</div>
        </div>
        <div className="col-span-1 text-right text-sm text-gray-500">{d}</div>
        <div className="col-span-1 flex justify-end">
          <FlagPills item={item} />
        </div>
      </button>

      {expanded && (
        <div className="bg-gray-50 px-4 pb-4 pt-2">
          <div className="text-xs text-gray-500 mb-2">
            <span className="mr-3">Mailbox: {item.mailbox}</span>
            {item.in_reply_to && <span className="mr-3">In-Reply-To: <code>{item.in_reply_to}</code></span>}
          </div>

          <div className="text-sm whitespace-pre-wrap bg-white border rounded-lg p-3">
            {item.body_preview || '(no preview)'}
          </div>

          <div className="mt-2 flex items-center gap-3">
            <button
              onClick={(e) => {
                e.stopPropagation()
                onLoadBody(item.id)
              }}
              className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100 text-sm"
            >
              Load full body
            </button>
            {body && (
              <span className="text-xs text-gray-500">
                Loaded full body ({body.length} chars){' '}
              </span>
            )}
          </div>

          {body && (
            <div className="mt-2">
              <div className="text-xs text-gray-600 mb-1">Full body</div>
              <div className="text-sm whitespace-pre-wrap bg-white border rounded-lg p-3 max-h-80 overflow-auto">
                {body}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function App() {
  const [mode, setMode] = useState<Mode>('recent')
  const [items, setItems] = useState<RecentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  const [limit, setLimit] = useState(20)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [bodyMap, setBodyMap] = useState<Record<number, string>>({})

  const [searchQuery, setSearchQuery] = useState('')
  const [unreadOnly, setUnreadOnly] = useState(false)

  const [backfillOpen, setBackfillOpen] = useState(false)
  const [backfillParams, setBackfillParams] = useState<BackfillParams>({
    mailbox: '',
    days: 450,
    only_unseen: true,
    limit: 2000,
  })
  const [banner, setBanner] = useState<string | null>(null)

  // Load recent
  const loadRecent = async () => {
    setLoading(true)
    setErr(null)
    try {
      const res = await fetchRecent(limit)
      setItems(res.items)
      setMode('recent')
      setExpandedId(null)
    } catch (e: any) {
      setErr(String(e))
    } finally {
      setLoading(false)
    }
  }

  // Run search
  const runSearch = async (q: string) => {
    if (!q.trim()) {
      loadRecent()
      return
    }
    setLoading(true)
    setErr(null)
    try {
      const res = await apiSearch(q, 100)
      setItems(res.items)
      setMode('search')
      setExpandedId(null)
    } catch (e: any) {
      setErr(String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadRecent()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limit])

  const filteredItems = useMemo(() => {
    if (!unreadOnly) return items
    return items.filter((it) => it.is_unread)
  }, [items, unreadOnly])

  const onToggleRow = (id: number) => {
    setExpandedId((cur) => (cur === id ? null : id))
  }

  const onLoadBody = async (id: number) => {
    if (bodyMap[id]) return
    try {
      const res = await fetchBody(id)
      setBodyMap((m) => ({ ...m, [id]: res.body }))
    } catch (e) {
      setBanner(`Failed to load full body: ${String(e)}`)
    }
  }

  const doRefresh = async () => {
    setBanner(null)
    try {
      const res = await refreshNow()
      setBanner(`Refreshed: fetched ${res.total_fetched}, inserted ${res.total_inserted}`)
      await loadRecent()
    } catch (e) {
      setBanner(`Refresh failed: ${String(e)}`)
    }
  }

  const doBackfill = async () => {
    setBanner(null)
    try {
      const res = await backfill(backfillParams)
      setBanner(
        `Backfill: fetched ${res.total_fetched}, inserted ${res.total_inserted}`
      )
      setBackfillOpen(false)
      await loadRecent()
    } catch (e) {
      setBanner(`Backfill failed: ${String(e)}`)
    }
  }

  return (
    <div className="max-w-7xl mx-auto p-6">
      <header className="mb-4">
        <h1 className="text-2xl font-bold">Inbox Companion</h1>
        <p className="text-gray-600">
          Recent messages (stored locally in SQLite, refreshed by a background poller)
        </p>
      </header>

      {/* Toolbar */}
      <div className="bg-white shadow rounded-2xl p-4 mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search (subject, from, snippet, preview)…"
              className="border rounded-md px-3 py-1.5 w-72"
            />
            <button
              onClick={() => runSearch(searchQuery)}
              className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100"
            >
              Search
            </button>
            {mode === 'search' && (
              <button
                onClick={() => {
                  setSearchQuery('')
                  loadRecent()
                }}
                className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100"
              >
                Clear
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-600">Show</label>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="border rounded-md px-2 py-1"
            >
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <input
              id="unreadOnly"
              type="checkbox"
              checked={unreadOnly}
              onChange={(e) => setUnreadOnly(e.target.checked)}
            />
            <label htmlFor="unreadOnly" className="text-sm text-gray-700">
              Unread only (client-side)
            </label>
          </div>

          <div className="flex-1" />

          <button
            onClick={doRefresh}
            className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100"
          >
            Refresh now
          </button>

          <button
            onClick={() => setBackfillOpen((v) => !v)}
            className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100"
          >
            Backfill…
          </button>
        </div>

        {/* Backfill panel */}
        {backfillOpen && (
          <div className="mt-4 border-t pt-4">
            <div className="grid sm:grid-cols-5 gap-3">
              <div className="sm:col-span-2">
                <label className="block text-sm text-gray-600 mb-1">Mailbox (optional)</label>
                <input
                  value={backfillParams.mailbox || ''}
                  onChange={(e) => setBackfillParams((p) => ({ ...p, mailbox: e.target.value || '' }))}
                  placeholder="INBOX (leave empty to run for all)"
                  className="border rounded-md px-3 py-1.5 w-full"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">Days (SINCE)</label>
                <input
                  type="number"
                  min={1}
                  value={backfillParams.days}
                  onChange={(e) => setBackfillParams((p) => ({ ...p, days: Number(e.target.value) }))}
                  className="border rounded-md px-3 py-1.5 w-full"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">Limit (optional)</label>
                <input
                  type="number"
                  min={1}
                  value={backfillParams.limit ?? 2000}
                  onChange={(e) =>
                    setBackfillParams((p) => ({ ...p, limit: Number(e.target.value) || undefined }))
                  }
                  className="border rounded-md px-3 py-1.5 w-full"
                />
              </div>
              <div className="flex items-end">
                <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={backfillParams.only_unseen ?? true}
                    onChange={(e) =>
                      setBackfillParams((p) => ({ ...p, only_unseen: e.target.checked }))
                    }
                  />
                  Only UNSEEN
                </label>
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              <button
                onClick={doBackfill}
                className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100"
              >
                Run backfill
              </button>
              <button
                onClick={() => setBackfillOpen(false)}
                className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Banner */}
      {banner && (
        <div className="mb-4 bg-blue-50 border border-blue-200 text-blue-800 rounded-lg px-4 py-2">
          {banner}
        </div>
      )}

      {/* List */}
      {loading && <div className="text-gray-600">Loading…</div>}
      {err && <div className="text-red-600">Error: {err}</div>}

      {!loading && !err && (
        <div className="bg-white shadow rounded-2xl">
          <div className="grid grid-cols-12 gap-2 p-3 border-b text-sm font-semibold">
            <div className="col-span-4">From</div>
            <div className="col-span-6">Subject / Snippet</div>
            <div className="col-span-1 text-right">Date</div>
            <div className="col-span-1 text-right">Flags</div>
          </div>
          {filteredItems.length === 0 && (
            <div className="p-6 text-gray-600 text-sm">No messages to show.</div>
          )}
          {filteredItems.map((it) => (
            <Row
              key={it.id}
              item={it}
              expanded={expandedId === it.id}
              onToggle={onToggleRow}
              body={bodyMap[it.id]}
              onLoadBody={onLoadBody}
            />
          ))}
        </div>
      )}
    </div>
  )
}

