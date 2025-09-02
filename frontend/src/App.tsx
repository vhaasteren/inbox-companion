import { useEffect, useMemo, useState } from 'react'
import {
  fetchRecent,
  type RecentItem,
  refreshNow,
  backfill,
  search as apiSearch,
  fetchBody,
  type BackfillParams,
  summarize,
  fetchAnalysis,
  fetchBacklog,
  llmPing,
  llmInspect,
  type Analysis,
  type BacklogItem,
  type SummarizeResult,
} from './lib/api'

type Mode = 'recent' | 'search' | 'backlog'

function Pill({
  title,
  children,
  tone = 'gray',
}: {
  title?: string
  children: React.ReactNode
  tone?: 'gray' | 'blue' | 'green' | 'amber' | 'rose' | 'purple'
}) {
  const tones: Record<string, string> = {
    gray: 'bg-gray-50 border-gray-200 text-gray-700',
    blue: 'bg-blue-50 border-blue-200 text-blue-700',
    green: 'bg-green-50 border-green-200 text-green-700',
    amber: 'bg-amber-50 border-amber-200 text-amber-700',
    rose: 'bg-rose-50 border-rose-200 text-rose-700',
    purple: 'bg-purple-50 border-purple-200 text-purple-700',
  }
  return (
    <span
      title={title}
      className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs ${tones[tone] || tones.gray}`}
    >
      {children}
    </span>
  )
}

function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-gray-600">
      <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" aria-hidden>
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" fill="none" opacity="0.25" />
        <path d="M22 12a10 10 0 0 1-10 10" stroke="currentColor" strokeWidth="3" fill="none" />
      </svg>
      {label || 'Working…'}
    </span>
  )
}

function FlagPills({ item }: { item: RecentItem }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <Pill title={item.is_unread ? 'Unread' : 'Read'} tone={item.is_unread ? 'blue' : 'gray'}>
        ●
      </Pill>
      <Pill title={item.is_answered ? 'Answered' : 'Not answered'} tone={item.is_answered ? 'green' : 'gray'}>
        ↩
      </Pill>
      <Pill title={item.is_flagged ? 'Starred' : 'Not starred'} tone={item.is_flagged ? 'amber' : 'gray'}>
        ★
      </Pill>
    </div>
  )
}

function meterTone(v: number) {
  if (v >= 4) return 'rose'
  if (v >= 3) return 'amber'
  if (v >= 2) return 'blue'
  return 'gray'
}

function computePriority(importance: number, urgency: number): number {
  // priority = round((2*importance + urgency)/3 * 20)  -> 0..100
  const imp = Math.max(0, Math.min((importance as number) | 0, 5))
  const urg = Math.max(0, Math.min((urgency as number) | 0, 5))
  const score = (2 * imp + urg) / 3.0
  return Math.round(score * 20)
}

function isEmptyObject(obj: any): boolean {
  if (!obj || typeof obj !== 'object') return true
  return Object.keys(obj).length === 0
}

function AnalysisCard({
  id,
  analysis,
  labels,
  error,
}: {
  id: number
  analysis: Analysis | null
  labels: string[] | null
  error?: string | null
}) {
  if (error) {
    return (
      <div className="mt-2 border rounded-lg p-3 bg-red-50 border-red-200 text-red-800 text-sm">
        LLM error: <span className="font-mono">{error}</span>
      </div>
    )
  }

  if (!analysis || isEmptyObject(analysis)) {
    return (
      <div className="text-xs text-gray-500 mt-2">
        No analysis stored yet. Click <span className="font-semibold">Summarize</span> to generate it.
      </div>
    )
  }

  const pr =
    typeof analysis.priority === 'number' && analysis.priority > 0
      ? analysis.priority
      : computePriority(analysis.importance ?? 0, analysis.urgency ?? 0)

  return (
    <div className="mt-3 bg-white border rounded-lg p-3">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <Pill tone="purple" title="Model">
          {analysis.model || '—'}
        </Pill>
        <Pill tone={meterTone(analysis.importance ?? 0)} title="Importance (0–5)">
          IMP {analysis.importance ?? 0}
        </Pill>
        <Pill tone={meterTone(analysis.urgency ?? 0)} title="Urgency (0–5)">
          URG {analysis.urgency ?? 0}
        </Pill>
        <Pill tone="green" title="Derived priority (0–100)">
          PRI {pr}
        </Pill>
        {analysis.truncated && (
          <Pill tone="amber" title="Email body was clipped before analysis">
            TRUNC
          </Pill>
        )}
        {typeof analysis.confidence === 'number' && (
          <Pill tone="blue" title="Model confidence (0–1)">
            conf {analysis.confidence.toFixed(2)}
          </Pill>
        )}
      </div>

      {labels && labels.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1">
          {labels.map((lab) => (
            <Pill key={`${id}-lab-${lab}`} tone="gray">
              {lab}
            </Pill>
          ))}
        </div>
      )}

      {analysis.bullets?.length > 0 && (
        <div className="mb-2">
          <div className="text-xs font-semibold text-gray-600 mb-1">Summary</div>
          <ul className="list-disc list-inside text-sm text-gray-800">
            {analysis.bullets.slice(0, 3).map((b, i) => (
              <li key={`b-${i}`}>{b}</li>
            ))}
          </ul>
        </div>
      )}

      {analysis.key_actions?.length > 0 && (
        <div className="mb-1">
          <div className="text-xs font-semibold text-gray-600 mb-1">Key actions</div>
          <ul className="list-disc list-inside text-sm text-gray-800">
            {analysis.key_actions.slice(0, 3).map((a, i) => (
              <li key={`a-${i}`}>{a}</li>
            ))}
          </ul>
        </div>
      )}

      {analysis.notes && analysis.notes.trim() && (
        <div className="mt-2 text-xs text-gray-600">
          <span className="font-semibold">Notes:</span> {analysis.notes}
        </div>
      )}
    </div>
  )
}

function Row({
  item,
  expanded,
  onToggle,
  body,
  onLoadBody,
  onSummarize,
  onLoadAnalysis,
  analysis,
  labels,
  showPriority,
  priorityValue,
  hasAnalysis,
  error,
  busy,
}: {
  item: RecentItem
  expanded: boolean
  onToggle: (id: number) => void
  body: string | undefined
  onLoadBody: (id: number) => void
  onSummarize: (id: number) => void
  onLoadAnalysis: (id: number) => void
  analysis: Analysis | null
  labels: string[] | null
  showPriority?: boolean
  priorityValue?: number
  hasAnalysis?: boolean
  error?: string | null
  busy?: boolean
}) {
  const d = item.date ? new Date(item.date).toLocaleString() : '—'
  const derivedPr =
    typeof priorityValue === 'number'
      ? priorityValue
      : analysis
        ? computePriority(analysis.importance ?? 0, analysis.urgency ?? 0)
        : 0

  return (
    <div className="border-b border-gray-200">
      <button
        onClick={() => onToggle(item.id)}
        className="grid grid-cols-12 gap-2 py-3 w-full text-left hover:bg-gray-50 focus:outline-none"
      >
        <div className="col-span-4">
          <div className="font-medium truncate flex items-center gap-2">
            <span>{item.from_name || item.from}</span>
            {error && (
              <span
                title={error}
                className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 text-red-700 border border-red-200"
              >
                LLM error
              </span>
            )}
          </div>
          {item.from_email && <div className="text-xs text-gray-500 truncate">{item.from_email}</div>}
        </div>
        <div className="col-span-6 truncate">
          <div className="font-semibold">{item.subject}</div>
          <div className="text-xs text-gray-600 mt-1 line-clamp-2">{item.snippet}</div>
        </div>
        <div className="col-span-1 text-right text-sm text-gray-500">{d}</div>
        <div className="col-span-1 flex items-center justify-end gap-2">
          {showPriority ? (
            <Pill tone="green" title="Priority">
              {derivedPr}
            </Pill>
          ) : (
            <FlagPills item={item} />
          )}
        </div>
      </button>

      {expanded && (
        <div className="bg-gray-50 px-4 pb-4 pt-2">
          <div className="text-xs text-gray-500 mb-2 flex flex-wrap gap-3">
            <span>Mailbox: {item.mailbox}</span>
            {item.in_reply_to && (
              <span>
                In-Reply-To: <code>{item.in_reply_to}</code>
              </span>
            )}
            {showPriority && typeof derivedPr === 'number' && (
              <span>
                Priority:&nbsp;
                <span className="font-semibold">{derivedPr}</span>
                {typeof hasAnalysis === 'boolean' && (
                  <span className="ml-2 text-gray-400">{hasAnalysis ? '(has analysis)' : '(no analysis)'}</span>
                )}
              </span>
            )}
          </div>

          <div className="text-sm whitespace-pre-wrap bg-white border rounded-lg p-3">
            {item.body_preview || '(no preview)'}
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              onClick={(e) => {
                e.stopPropagation()
                onLoadBody(item.id)
              }}
              className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100 text-sm"
            >
              Load full body
            </button>

            <button
              onClick={(e) => {
                e.stopPropagation()
                onSummarize(item.id)
              }}
              disabled={!!busy}
              className={`px-3 py-1.5 rounded-md border text-sm ${
                busy ? 'bg-gray-100 text-gray-400' : 'bg-white hover:bg-gray-100'
              }`}
              title="Generate or refresh LLM analysis"
            >
              {busy ? 'Summarizing…' : 'Summarize'}
            </button>

            <button
              onClick={(e) => {
                e.stopPropagation()
                onLoadAnalysis(item.id)
              }}
              className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100 text-sm"
              title="Fetch stored analysis (no LLM call)"
            >
              Load analysis
            </button>

            {body && <span className="text-xs text-gray-500">Loaded full body ({body.length} chars)</span>}
          </div>

          <AnalysisCard id={item.id} analysis={analysis} labels={labels} error={error || null} />

          {body && (
            <div className="mt-3">
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

  // recent/search items
  const [items, setItems] = useState<RecentItem[]>([])
  // backlog items
  const [backlogItems, setBacklogItems] = useState<BacklogItem[]>([])

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

  // analysis & error state
  const [analysisMap, setAnalysisMap] = useState<Record<number, Analysis>>({})
  const [labelsMap, setLabelsMap] = useState<Record<number, string[]>>({})
  const [llmErrors, setLlmErrors] = useState<Record<number, string>>({})

  // backlog filters
  const [minPriority, setMinPriority] = useState(0)
  const [backlogUnreadOnly, setBacklogUnreadOnly] = useState(false)

  // LLM progress
  const [summarizing, setSummarizing] = useState(false)
  const [inFlightIds, setInFlightIds] = useState<Set<number>>(new Set())

  const [banner, setBanner] = useState<string | null>(null)

  // initial load
  useEffect(() => {
    loadRecent()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // re-load when limit changes per view
  useEffect(() => {
    if (mode === 'recent' || mode === 'search') {
      loadRecent()
    } else if (mode === 'backlog') {
      loadBacklog()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limit])

  // Load recent
  const loadRecent = async () => {
    setLoading(true)
    setErr(null)
    try {
      const res = await fetchRecent(limit)
      setItems(res.items)
      setMode((prev) => (prev === 'backlog' ? 'recent' : prev)) // keep current unless switching from backlog
      setExpandedId(null)
    } catch (e: any) {
      setErr(String(e))
    } finally {
      setLoading(false)
    }
  }

  // Load backlog
  const loadBacklog = async () => {
    setLoading(true)
    setErr(null)
    try {
      const res = await fetchBacklog(limit, minPriority, backlogUnreadOnly)
      setBacklogItems(res.items)
      setMode('backlog')
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
      await loadRecent()
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

  const filteredItems = useMemo(() => {
    if (!unreadOnly) return items
    return items.filter((it) => it.is_unread)
  }, [items, unreadOnly])

  const onToggleRow = async (id: number) => {
    setExpandedId((cur) => (cur === id ? null : id))
    const willExpand = expandedId !== id
    if (!willExpand) return

    try {
      const res = await fetchAnalysis(id)
      // We have a stored analysis — render it and CLEAR any old error badge.
      setAnalysisMap((m) => ({ ...m, [id]: res.analysis as Analysis }))
      setLabelsMap((m) => ({ ...m, [id]: res.labels || [] }))
      setLlmErrors((m) => {
        const { [id]: _, ...rest } = m
        return rest
      })
    } catch {
      // No stored analysis — do NOT show an error automatically.
      // If you want to surface the last error only on demand, you can fetch it here
      // and stash it for a tooltip, but don’t set the red badge.
    }
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
      if (mode === 'backlog') {
        await loadBacklog()
      } else {
        await loadRecent()
      }
    } catch (e) {
      setBanner(`Refresh failed: ${String(e)}`)
    }
  }

  const doBackfill = async () => {
    setBanner(null)
    try {
      const res = await backfill(backfillParams)
      setBanner(`Backfill: fetched ${res.total_fetched}, inserted ${res.total_inserted}`)
      setBackfillOpen(false)
      if (mode === 'backlog') {
        await loadBacklog()
      } else {
        await loadRecent()
      }
    } catch (e) {
      setBanner(`Backfill failed: ${String(e)}`)
    }
  }

  const loadAnalysisOnly = async (id: number) => {
    try {
      const res = await fetchAnalysis(id)
      setAnalysisMap((m) => ({ ...m, [id]: res.analysis as Analysis }))
      setLabelsMap((m) => ({ ...m, [id]: res.labels || [] }))
      // Successful fetch: clear any previous error badge for this row.
      setLlmErrors((m) => {
        const { [id]: _, ...rest } = m
        return rest
      })
    } catch {
      // No stored analysis => try to show last_error from backend
      try {
        const insp = await llmInspect(id)
        if (insp?.last_error) {
          setLlmErrors((m) => ({ ...m, [id]: insp.last_error || 'Unknown error' }))
        } else {
          setBanner(`No stored analysis for id=${id}.`)
        }
      } catch (e: any) {
        setBanner(`Unable to load analysis for id=${id}: ${String(e)}`)
      }
    }
  }

  const eatSummarizeResultsIntoBanner = (results: SummarizeResult[]) => {
    let ok = 0
    let skipped = 0
    let errors = 0
    const errorMsgs: string[] = []
    for (const r of results) {
      if (r.status === 'ok') {
        ok += 1
        if ('skipped' in r && r.skipped) skipped += 1
      } else if (r.status === 'error') {
        errors += 1
        errorMsgs.push(`#${r.id}: ${r.error || 'Unknown error'}`)
      }
    }
    const base = `Summarize: ok=${ok}, skipped=${skipped}, errors=${errors}`
    setBanner(errorMsgs.length ? `${base}. ${errorMsgs.join(' | ')}` : base)
  }

  const doSummarizeOne = async (id: number) => {
    setInFlightIds((s) => new Set([...Array.from(s), id]))
    try {
      setBanner('Talking to LLM…')
      const resp = await summarize([id])
      // Record per-row errors for visibility
      for (const r of resp.results) {
        if (r.status === 'error') {
          setLlmErrors((m) => ({ ...m, [r.id]: r.error || 'Unknown error' }))
        } else if (r.status === 'ok') {
          setLlmErrors((m) => {
            const { [r.id]: _, ...rest } = m
            return rest
          })
        }
      }
      eatSummarizeResultsIntoBanner(resp.results)
      // then fetch stored analysis
      await loadAnalysisOnly(id)
    } catch (e: any) {
      setBanner(`Summarize failed for id=${id}: ${String(e)}`)
    } finally {
      setInFlightIds((s) => {
        const copy = new Set(Array.from(s))
        copy.delete(id)
        return copy
      })
    }
  }

  const doSummarizeVisible = async () => {
    try {
      const visibleIds =
        mode === 'backlog'
          ? backlogItems.map((b) => b.id)
          : filteredItems.map((it) => it.id)
      if (visibleIds.length === 0) return
      setSummarizing(true)
      setBanner('Talking to LLM…')

      const resp = await summarize(visibleIds.slice(0, 50)) // modest cap to keep UI responsive

      // Update error map immediately
      for (const r of resp.results) {
        if (r.status === 'error') {
          setLlmErrors((m) => ({ ...m, [r.id]: r.error || 'Unknown error' }))
        } else if (r.status === 'ok') {
          setLlmErrors((m) => {
            const { [r.id]: _, ...rest } = m
            return rest
          })
        }
      }

      eatSummarizeResultsIntoBanner(resp.results)

      // Pull stored analyses for these ids and update UI maps
      const BATCH = 10
      for (let i = 0; i < visibleIds.length; i += BATCH) {
        const chunk = visibleIds.slice(i, i + BATCH)
        await Promise.all(
          chunk.map(async (id) => {
            try {
              const res = await fetchAnalysis(id)
              setAnalysisMap((m) => ({ ...m, [id]: res.analysis as Analysis }))
              setLabelsMap((m) => ({ ...m, [id]: res.labels || [] }))
              if (res.error) {
                setLlmErrors((m) => ({ ...m, [id]: res.error || 'Unknown error' }))
              }
            } catch {
              // ignore missing analyses (e.g., model error)
            }
          })
        )
      }

      if (mode === 'backlog') {
        await loadBacklog()
      }
    } catch (e: any) {
      setBanner(`Summarize visible failed: ${String(e)}`)
    } finally {
      setSummarizing(false)
    }
  }

  const doPingLLM = async () => {
    setBanner('Checking LLM…')
    try {
      const res = await llmPing()
      if (res.ok) {
        setBanner(`LLM OK. Models: ${res.models.join(', ') || '(none)'}`)
      } else {
        setBanner(`LLM not reachable: ${res.error || 'unknown error'}`)
      }
    } catch (e: any) {
      setBanner(`LLM ping failed: ${String(e)}`)
    }
  }

  return (
    <div className="max-w-7xl mx-auto p-6">
      <header className="mb-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">Inbox Companion</h1>
            <p className="text-gray-600">Local email triage with LLM summaries, labels, and backlog prioritization</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setMode('recent')}
              className={`px-3 py-1.5 rounded-md border text-sm ${
                mode === 'recent' ? 'bg-gray-900 text-white border-gray-900' : 'bg-white hover:bg-gray-100'
              }`}
            >
              Recent
            </button>
            <button
              onClick={() => setMode('backlog')}
              className={`px-3 py-1.5 rounded-md border text-sm ${
                mode === 'backlog' ? 'bg-gray-900 text-white border-gray-900' : 'bg-white hover:bg-gray-100'
              }`}
            >
              Backlog
            </button>
          </div>
        </div>
      </header>

      {/* Toolbar */}
      <div className="bg-white shadow rounded-2xl p-4 mb-4">
        <div className="flex flex-wrap items-center gap-3">
          {mode !== 'backlog' ? (
            <>
              <div className="flex items-center gap-2">
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search (subject, from, snippet, preview)…"
                  className="border rounded-md px-3 py-1.5 w-72"
                />
                <button onClick={() => runSearch(searchQuery)} className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100">
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
                <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} className="border rounded-md px-2 py-1">
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={200}>200</option>
                </select>
              </div>

              <div className="flex items-center gap-2">
                <input id="unreadOnly" type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />
                <label htmlFor="unreadOnly" className="text-sm text-gray-700">
                  Unread only (client-side)
                </label>
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <label className="text-sm text-gray-600">Min priority</label>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={minPriority}
                  onChange={(e) => setMinPriority(Math.max(0, Math.min(100, Number(e.target.value) || 0)))}
                  className="border rounded-md px-2 py-1 w-24"
                />
                <button onClick={loadBacklog} className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100">
                  Apply
                </button>
              </div>

              <div className="flex items-center gap-2">
                <input
                  id="backlogUnread"
                  type="checkbox"
                  checked={backlogUnreadOnly}
                  onChange={(e) => setBacklogUnreadOnly(e.target.checked)}
                />
                <label htmlFor="backlogUnread" className="text-sm text-gray-700">
                  Only unread
                </label>
              </div>

              <div className="flex items-center gap-2">
                <label className="text-sm text-gray-600">Show</label>
                <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} className="border rounded-md px-2 py-1">
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={200}>200</option>
                </select>
              </div>
            </>
          )}

          <div className="flex-1" />

          <button
            onClick={doSummarizeVisible}
            disabled={summarizing}
            className={`px-3 py-1.5 rounded-md border text-sm ${
              summarizing ? 'bg-gray-100 text-gray-400' : 'bg-white hover:bg-gray-100'
            }`}
            title="Run LLM on all currently visible items"
          >
            {summarizing ? 'Summarizing…' : 'Summarize visible'}
          </button>

          <button onClick={doRefresh} className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100">
            Refresh now
          </button>

          <button onClick={() => setBackfillOpen((v) => !v)} className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100">
            Backfill…
          </button>

          <button onClick={doPingLLM} className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100" title="Check LLM connectivity">
            LLM status
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
                  onChange={(e) => setBackfillParams((p) => ({ ...p, limit: Number(e.target.value) || undefined }))}
                  className="border rounded-md px-3 py-1.5 w-full"
                />
              </div>
              <div className="flex items-end">
                <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={backfillParams.only_unseen ?? true}
                    onChange={(e) => setBackfillParams((p) => ({ ...p, only_unseen: e.target.checked }))}
                  />
                  Only UNSEEN
                </label>
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              <button onClick={doBackfill} className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100">
                Run backfill
              </button>
              <button onClick={() => setBackfillOpen(false)} className="px-3 py-1.5 rounded-md border bg-white hover:bg-gray-100">
                Close
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Banner */}
      {banner && (
        <div className="mb-4 bg-blue-50 border border-blue-200 text-blue-800 rounded-lg px-4 py-2 flex items-center gap-3">
          {(summarizing || inFlightIds.size > 0) && <Spinner />}
          <span>{banner}</span>
        </div>
      )}

      {/* List */}
      {loading && <div className="text-gray-600">Loading…</div>}
      {err && <div className="text-red-600">Error: {err}</div>}

      {!loading && !err && (mode === 'backlog' ? (
        <div className="bg-white shadow rounded-2xl">
          <div className="grid grid-cols-12 gap-2 p-3 border-b text-sm font-semibold">
            <div className="col-span-4">From</div>
            <div className="col-span-6">Subject / Snippet</div>
            <div className="col-span-1 text-right">Date</div>
            <div className="col-span-1 text-right">Priority</div>
          </div>
          {backlogItems.length === 0 && (
            <div className="p-6 text-gray-600 text-sm">No backlog items match your filters.</div>
          )}
          {backlogItems.map((it) => (
            <Row
              key={it.id}
              item={it}
              expanded={expandedId === it.id}
              onToggle={onToggleRow}
              body={bodyMap[it.id]}
              onLoadBody={onLoadBody}
              onSummarize={doSummarizeOne}
              onLoadAnalysis={loadAnalysisOnly}
              analysis={analysisMap[it.id] || null}
              labels={labelsMap[it.id] || null}
              showPriority
              priorityValue={it.priority}
              hasAnalysis={it.has_analysis}
              error={llmErrors[it.id] || null}
              busy={inFlightIds.has(it.id)}
            />
          ))}
        </div>
      ) : (
        <div className="bg-white shadow rounded-2xl">
          <div className="grid grid-cols-12 gap-2 p-3 border-b text-sm font-semibold">
            <div className="col-span-4">From</div>
            <div className="col-span-6">Subject / Snippet</div>
            <div className="col-span-1 text-right">Date</div>
            <div className="col-span-1 text-right">Flags</div>
          </div>
          {(unreadOnly ? filteredItems : items).length === 0 && (
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
              onSummarize={doSummarizeOne}
              onLoadAnalysis={loadAnalysisOnly}
              analysis={analysisMap[it.id] || null}
              labels={labelsMap[it.id] || null}
              error={llmErrors[it.id] || null}
              busy={inFlightIds.has(it.id)}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

