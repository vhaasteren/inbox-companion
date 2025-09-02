import { useEffect, useState } from 'react'
import { fetchPreview, type PreviewItem } from './lib/api'

function Row({ item }: { item: PreviewItem }) {
  const d = item.date ? new Date(item.date).toLocaleString() : '—'
  return (
    <div className="grid grid-cols-12 gap-2 py-2 border-b border-gray-200">
      <div className="col-span-4 font-medium truncate">{item.from}</div>
      <div className="col-span-7 truncate">{item.subject}</div>
      <div className="col-span-1 text-right text-sm text-gray-500">{d}</div>
    </div>
  )
}

export default function App() {
  const [items, setItems] = useState<PreviewItem[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    fetchPreview(10)
      .then((res) => setItems(res.items))
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="max-w-5xl mx-auto p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold">Inbox Companion</h1>
        <p className="text-gray-600">Preview of latest messages via Proton Bridge</p>
      </header>

      {loading && <div className="text-gray-600">Loading…</div>}
      {err && <div className="text-red-600">Error: {err}</div>}

      {!loading && !err && (
        <div className="bg-white shadow rounded-2xl p-4">
          <div className="grid grid-cols-12 gap-2 pb-2 border-b text-sm font-semibold">
            <div className="col-span-4">From</div>
            <div className="col-span-7">Subject</div>
            <div className="col-span-1 text-right">Date</div>
          </div>
          {items.map((it) => (
            <Row key={it.uid} item={it} />
          ))}
        </div>
      )}
    </div>
  )
}

