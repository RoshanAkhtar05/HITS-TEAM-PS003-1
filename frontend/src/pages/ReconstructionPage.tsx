import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'

type CaseResults = {
  case_id: string
  manifest: {
    processed_at?: string
    staged_sources?: Record<string, string>
    unsupported_files?: string[]
    source_processing?: Array<{
      category: string
      source_file?: string | null
      status: string
      entities?: number
      relations?: number
      error?: string | null
    }>
    report_available?: boolean
    entity_count?: number
    relation_count?: number
    timeline_event_count?: number
    timeline_scene_count?: number
    unplaced_event_count?: number
    validation?: { person_profiles_count?: number; relationship_profiles_count?: number }
  }
  summary: any
  timeline: any
  graph: { nodes: any[]; links: any[] }
  alerts: any[]
  person_profiles?: any[]
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export default function ReconstructionPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const caseId = searchParams.get('case_id') || (location.state as any)?.processResult?.case_id || ''
  const [results, setResults] = useState<CaseResults | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!caseId) {
      setError('No case was selected. Return to Case Files and create or open an investigation.')
      setLoading(false)
      return
    }

    const controller = new AbortController()
    setLoading(true)
    setError('')
    fetch(`${API_BASE}/api/cases/${encodeURIComponent(caseId)}/results`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) {
          let detail = `Could not load case results (HTTP ${response.status})`
          try {
            const payload = await response.json()
            detail = payload.detail || detail
          } catch { /* use HTTP fallback */ }
          throw new Error(detail)
        }
        return response.json()
      })
      .then((payload: CaseResults) => setResults(payload))
      .catch((err: unknown) => {
        if (err instanceof Error && err.name !== 'AbortError') {
          setError(err.message)
        }
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [caseId])

  const scenes = useMemo(() => results?.timeline?.scenes ?? [], [results])
  const topEvents = useMemo(
    () => scenes.flatMap((scene: any) => scene.events ?? []).slice(0, 12),
    [scenes],
  )

  const statCards = results ? [
    { label: 'Entities', value: results.manifest.entity_count ?? results.graph.nodes.length },
    { label: 'Relationships', value: results.manifest.relation_count ?? results.graph.links.length },
    { label: 'Timeline events', value: results.manifest.timeline_event_count ?? results.timeline.total_events ?? 0 },
    { label: 'Scenes', value: results.manifest.timeline_scene_count ?? results.timeline.total_scenes ?? 0 },
  ] : []

  return (
    <div className="min-h-screen reconstruction-page" style={{ background: '#0a0a0b', color: '#e5e2e3', fontFamily: 'Geist, sans-serif' }}>
      <header className="h-16 border-b border-[#3f4852]/30 flex items-center justify-between px-6 md:px-10" style={{ background: '#131314' }}>
        <button onClick={() => navigate('/')} className="font-black tracking-widest" style={{ color: '#feb700', fontSize: 24 }}>TATHYA-DF</button>
        <div className="flex gap-3">
          <button onClick={() => navigate('/case/new')} className="px-4 py-2 rounded border border-[#3f4852] text-sm">Case Files</button>
          <button disabled={!results?.manifest.report_available} onClick={() => window.open(`${API_BASE}/api/cases/${encodeURIComponent(caseId)}/export-pdf`, '_blank', 'noopener,noreferrer')} className="px-4 py-2 rounded text-sm border border-[#3f4852] disabled:opacity-40" style={{ color: '#e5e2e3' }}>Export report</button>
          <button disabled={!results} onClick={() => navigate(`/investigation?case_id=${encodeURIComponent(caseId)}`)} className="px-4 py-2 rounded text-sm font-semibold disabled:opacity-40" style={{ background: '#feb700', color: '#412d00' }}>Open Investigation</button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto p-5 md:p-8 space-y-6">
        <div>
          <p className="uppercase tracking-widest text-xs mb-2" style={{ color: '#98cbff', fontFamily: 'JetBrains Mono' }}>Evidence processing results</p>
          <h1 className="text-3xl font-semibold">Case reconstruction</h1>
          <p className="text-sm mt-2" style={{ color: '#bec7d4' }}>Case ID: <span style={{ color: '#ffdb9d', fontFamily: 'JetBrains Mono' }}>{caseId || 'Not selected'}</span></p>
        </div>

        {loading && (
          <div className="rounded-xl border border-[#3f4852]/40 p-8 text-center" style={{ background: '#1c1b1c' }}>
            <div className="w-8 h-8 rounded-full border-2 border-[#feb700]/30 border-t-[#feb700] animate-spin mx-auto mb-4" />
            <p className="font-medium">Loading case-specific processing results…</p>
            <p className="text-xs mt-2" style={{ color: '#bec7d4' }}>This page reads the saved outputs for this case. It does not simulate processing progress.</p>
          </div>
        )}

        {!loading && error && (
          <div className="rounded-xl border p-5" style={{ background: 'rgba(255,180,171,0.08)', borderColor: 'rgba(255,180,171,0.35)' }}>
            <p className="font-semibold mb-2" style={{ color: '#ffb4ab' }}>Unable to load reconstruction</p>
            <p className="text-sm">{error}</p>
            <button onClick={() => navigate('/case/new')} className="mt-4 px-4 py-2 rounded text-sm" style={{ background: '#feb700', color: '#412d00' }}>Return to Case Files</button>
          </div>
        )}

        {!loading && results && (
          <>
            <div className="rounded-xl p-4 border" style={{ background: '#15201d', borderColor: 'rgba(168,216,168,0.3)' }}>
              <p className="font-semibold" style={{ color: '#a8d8a8' }}>Processing completed</p>
              <p className="text-sm mt-1">This view is populated from the saved graph, summary, timeline and validation outputs for this case.</p>
              {results.manifest.processed_at && <p className="text-xs mt-2" style={{ color: '#bec7d4' }}>Processed: {new Date(results.manifest.processed_at).toLocaleString()}</p>}
            </div>

            <section className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {statCards.map(card => (
                <div key={card.label} className="rounded-xl border border-[#3f4852]/40 p-4" style={{ background: '#1c1b1c' }}>
                  <p className="text-xs uppercase tracking-wider" style={{ color: '#bec7d4', fontFamily: 'JetBrains Mono' }}>{card.label}</p>
                  <p className="text-3xl font-semibold mt-2" style={{ color: '#98cbff' }}>{Number(card.value).toLocaleString()}</p>
                </div>
              ))}
            </section>

            <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="rounded-xl border border-[#3f4852]/40 p-5" style={{ background: '#1c1b1c' }}>
                <h2 className="text-lg font-semibold mb-3">Evidence source processing</h2>
                <div className="space-y-2">
                  {(results.manifest.source_processing ?? []).map((source, index) => {
                    const statusColor = source.status === 'processed' ? '#a8d8a8' : source.status === 'failed' ? '#ffb4ab' : '#bec7d4'
                    return (
                      <div key={`${source.category}-${source.source_file ?? index}`} className="flex items-start justify-between gap-3 rounded-lg border border-[#3f4852]/30 px-3 py-2" style={{ background: '#15191f' }}>
                        <div className="min-w-0">
                          <p className="text-sm font-medium capitalize">{source.category.replace(/_/g, ' ')}</p>
                          <p className="text-[11px] mt-0.5 truncate" style={{ color: '#98a4b3' }}>{source.source_file || 'No file supplied'}</p>
                          {source.error && <p className="text-[10px] mt-1 break-words" style={{ color: '#ffb4ab' }}>{source.error}</p>}
                          {source.status === 'processed' && <p className="text-[10px] mt-1" style={{ color: '#98a4b3' }}>{source.entities ?? 0} entities · {source.relations ?? 0} relationships</p>}
                        </div>
                        <span className="shrink-0 text-[10px] uppercase tracking-wider font-mono" style={{ color: statusColor }}>{source.status.replace(/_/g, ' ')}</span>
                      </div>
                    )
                  })}
                  {(!results.manifest.source_processing || results.manifest.source_processing.length === 0) && (
                    <div className="flex flex-wrap gap-2">
                      {Object.keys(results.manifest.staged_sources ?? {}).map(source => (
                        <span key={source} className="px-3 py-1 rounded-full text-xs" style={{ background: 'rgba(152,203,255,0.12)', color: '#98cbff' }}>{source.replace(/_/g, ' ')}</span>
                      ))}
                    </div>
                  )}
                </div>
                {(results.manifest.unsupported_files ?? []).length > 0 && (
                  <div className="mt-4 pt-4 border-t border-[#3f4852]/30">
                    <p className="text-xs font-semibold mb-2" style={{ color: '#ffdb9d' }}>Uploaded but not parsed by this prototype</p>
                    <p className="text-xs" style={{ color: '#bec7d4' }}>{(results.manifest.unsupported_files ?? []).join(', ')}</p>
                  </div>
                )}
              </div>
              <div className="rounded-xl border border-[#3f4852]/40 p-5" style={{ background: '#1c1b1c' }}>
                <h2 className="text-lg font-semibold mb-3">Timeline quality indicators</h2>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><p style={{ color: '#bec7d4' }}>Unplaced events</p><p className="text-2xl mt-1">{results.manifest.unplaced_event_count ?? results.timeline.unplaced_event_count ?? 0}</p></div>
                  <div><p style={{ color: '#bec7d4' }}>Timezone-unknown events</p><p className="text-2xl mt-1">{results.timeline.stats?.timezone_unknown_event_count ?? 0}</p></div>
                  <div><p style={{ color: '#bec7d4' }}>Person profiles</p><p className="text-2xl mt-1">{results.manifest.validation?.person_profiles_count ?? results.person_profiles?.length ?? 0}</p></div>
                  <div><p style={{ color: '#bec7d4' }}>Alerts generated</p><p className="text-2xl mt-1">{results.alerts?.length ?? 0}</p></div>
                </div>
                <p className="text-xs mt-4" style={{ color: '#bec7d4' }}>An alert or association is an investigative lead, not proof of identity, presence or guilt.</p>
              </div>
            </section>

            <section className="rounded-xl border border-[#3f4852]/40 p-5" style={{ background: '#1c1b1c' }}>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">Reconstructed event sequence</h2>
                <span className="text-xs" style={{ color: '#bec7d4' }}>{topEvents.length} shown</span>
              </div>
              {topEvents.length === 0 ? (
                <p className="text-sm" style={{ color: '#bec7d4' }}>No timestamped events were reconstructed from the supported evidence files.</p>
              ) : (
                <div className="space-y-3">
                  {topEvents.map((event: any, index: number) => (
                    <div key={`${event.record_id ?? event.from_id}-${event.timestamp}-${index}`} className="pl-4 border-l-2 border-[#98cbff]/40 py-1">
                      <p className="text-xs" style={{ color: '#ffdb9d', fontFamily: 'JetBrains Mono' }}>{event.timestamp_utc || event.timestamp} · {event.timestamp_status === 'timezone_unknown' ? 'TIMEZONE UNKNOWN' : 'TIMEZONE-AWARE'}</p>
                      <p className="text-sm mt-1">{event.description || `${event.from} → ${event.to}`}</p>
                      <p className="text-xs mt-1" style={{ color: '#bec7d4' }}>Source: {event.source_type || 'unknown'}{event.record_id ? ` · Record: ${event.record_id}` : ''}</p>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  )
}
