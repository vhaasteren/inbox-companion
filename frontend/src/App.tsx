import { useEffect, useState } from 'react'
import { fetchRecent, type RecentItem } from './lib/api'

function Row({ item }: { item: RecentItem }) {
  const d = item.date ? new Date(item.date).toLocaleString() : '—'
  return (
    <div className="grid grid-cols-12 gap-2 py-3 border-b border-gray-200">
      <div className="col-span-4 font-medium truncate">{item.from}</div>
      <div className="col-span-7 truncate">
        <div className="font-semibold">{item.subject}</div>
        <div className="text-xs text-gray-600 mt-1 line-clamp-2">{item.snippet}</div>
      </div>
      <div className="col-span-1 text-right text-sm text-gray-500">{d}</div>
    </div>
  )
}

export default function App() {
  const [items, setItems] = useState<RecentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    fetchRecent(20)
      .then((res) => setItems(res.items))
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="max-w-6xl mx-auto p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold">Inbox Companion</h1>
        <p className="text-gray-600">
          Recent messages (stored locally in SQLite, refreshed by a background poller)
        </p>
      </header>

      {loading && <div className="text-gray-600">Loading…</div>}
      {err && <div className="text-red-600">Error: {err}</div>}

      {!loading && !err && (
        <div className="bg-white shadow rounded-2xl p-4">
          <div className="grid grid-cols-12 gap-2 pb-2 border-b text-sm font-semibold">
            <div className="col-span-4">From</div>
            <div className="col-span-7">Subject / Snippet</div>
            <div className="col-span-1 text-right">Date</div>
          </div>
          {items.map((it) => (
            <Row key={it.id} item={it} />
          ))}
        </div>
      )}
    </div>
  )
}

