import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { CaseListItem } from '../types/case'
import '../dashboard-command.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

type StatusFilter = 'all' | 'open' | 'in_progress' | 'closed'

const workflowStages = [
  {
    number: '01', symbol: '⇧', title: 'Evidence intake', tag: 'COLLECT',
    description: 'Create an investigation and add source files. Uploaded evidence is organised within its case so later analysis can be traced back to the originating material.',
    action: 'Start an investigation', route: 'intake',
  },
  {
    number: '02', symbol: '⌕', title: 'Entity extraction', tag: 'EXTRACT',
    description: 'Review the entities and events extracted from supported evidence formats. Check source records before treating an extracted detail as an investigative fact.',
    action: 'Explore the knowledge graph', route: 'graph',
  },
  {
    number: '03', symbol: '⌘', title: 'Source correlation', tag: 'CORRELATE',
    description: 'Inspect links between records and entities across sources. Correlations are investigative leads and should be verified against the original evidence.',
    action: 'Inspect correlated evidence', route: 'graph',
  },
  {
    number: '04', symbol: '⌁', title: 'Event reconstruction', tag: 'RECONSTRUCT',
    description: 'Explore the reconstructed event sequence, including placed and unplaced events. Timezone uncertainty and incomplete timestamps remain visible for analyst review.',
    action: 'Open event reconstruction', route: 'timeline',
  },
  {
    number: '05', symbol: '✓', title: 'Analyst review', tag: 'REVIEW',
    description: 'Review the available findings, source traceability and report output. Automated indicators are not conclusions of guilt and require investigator assessment.',
    action: 'Review the latest case', route: 'timeline',
  },
]

function formatDate(value: string | null): string {
  if (!value) return 'Date unavailable'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? 'Date unavailable'
    : parsed.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

function statusLabel(status: string): string {
  const normalized = (status || 'open').toLowerCase().replace(/_/g, ' ')
  return normalized.replace(/\b\w/g, letter => letter.toUpperCase())
}

function statusClass(status: string): string {
  switch ((status || 'open').toLowerCase()) {
    case 'closed': return 'td-status td-status-closed'
    case 'in_progress': return 'td-status td-status-active'
    default: return 'td-status td-status-open'
  }
}

function shortId(value: string): string {
  if (value.length <= 33) return value
  return `${value.slice(0, 17)}…${value.slice(-10)}`
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const [cases, setCases] = useState<CaseListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [activeStage, setActiveStage] = useState(0)
  const searchInputRef = useRef<HTMLInputElement>(null)

  const loadCases = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${API_BASE}/api/cases`)
      if (!response.ok) throw new Error(`Case repository returned HTTP ${response.status}`)
      const payload = await response.json()
      setCases(Array.isArray(payload) ? payload : [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load the case repository')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void loadCases() }, [loadCases])

  useEffect(() => {
    const handleSearchShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        searchInputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', handleSearchShortcut)
    return () => window.removeEventListener('keydown', handleSearchShortcut)
  }, [])

  const orderedCases = useMemo(() => [...cases].sort((a, b) => {
    const aTime = a.created_at ? new Date(a.created_at).getTime() : 0
    const bTime = b.created_at ? new Date(b.created_at).getTime() : 0
    return bTime - aTime
  }), [cases])

  const counts = useMemo(() => ({
    total: cases.length,
    open: cases.filter(item => (item.status || '').toLowerCase() === 'open').length,
    active: cases.filter(item => (item.status || '').toLowerCase() === 'in_progress').length,
    closed: cases.filter(item => (item.status || '').toLowerCase() === 'closed').length,
  }), [cases])

  const filteredCases = useMemo(() => {
    const query = search.trim().toLowerCase()
    return orderedCases.filter(item => {
      const status = (item.status || 'open').toLowerCase()
      const matchesStatus = statusFilter === 'all' || status === statusFilter
      const matchesQuery = !query || `${item.title} ${item.case_id} ${item.investigator}`.toLowerCase().includes(query)
      return matchesStatus && matchesQuery
    })
  }, [orderedCases, search, statusFilter])

  const selectedCase = filteredCases.find(item => item.case_id === selectedCaseId) || filteredCases[0] || orderedCases.find(item => item.case_id === selectedCaseId) || orderedCases[0]

  useEffect(() => {
    if (!selectedCaseId && orderedCases[0]) setSelectedCaseId(orderedCases[0].case_id)
    if (selectedCaseId && !orderedCases.some(item => item.case_id === selectedCaseId)) {
      setSelectedCaseId(orderedCases[0]?.case_id || '')
    }
  }, [orderedCases, selectedCaseId])

  const openCase = (caseId: string) => navigate(`/reconstruction?case_id=${encodeURIComponent(caseId)}`)
  const openGraph = (caseId?: string) => caseId
    ? navigate(`/investigation?case_id=${encodeURIComponent(caseId)}`)
    : navigate('/case/new')
  const runStageAction = () => {
    if (workflowStages[activeStage].route === 'intake') navigate('/case/new')
    else if (workflowStages[activeStage].route === 'graph') openGraph(selectedCase?.case_id)
    else if (selectedCase) openCase(selectedCase.case_id)
    else navigate('/case/new')
  }

  return (
    <div className="dossier-app">
      <header className="dossier-masthead">
        <button className="dossier-wordmark" onClick={() => navigate('/')} aria-label="TATHYA-DF home">
          <span className="dossier-wordmark-main">TATHYA</span><span className="dossier-wordmark-divider">/</span><span className="dossier-wordmark-suffix">DF</span>
        </button>
        <div className="dossier-masthead-context">
          <span>Digital forensics</span><span className="dossier-context-separator">/</span><span>Investigation command centre</span>
        </div>
        <div className="dossier-masthead-right">
          <span className="dossier-environment"><i /> Local prototype</span>
          <button className="dossier-avatar" aria-label="Analyst workspace">A</button>
        </div>
      </header>

      <div className="dossier-layout">
        <aside className="dossier-rail">
          <div className="dossier-rail-intro">
            <span className="dossier-rail-number">01</span>
            <div><strong>Forensic Division</strong><small>Analyst workspace</small></div>
          </div>
          <div className="dossier-rail-label">Workspace</div>
          <button className="dossier-nav-item is-current" onClick={() => navigate('/dashboard')}><span>01</span>Case register</button>
          <button className="dossier-nav-item" onClick={() => navigate('/case/new')}><span>02</span>New investigation</button>
          <div className="dossier-rail-rule" />
          <div className="dossier-rail-label">Analysis tools</div>
          <button type="button" className="dossier-rail-static dossier-rail-action" onClick={() => openGraph(selectedCase?.case_id)} title="Open the selected case in the knowledge graph"><span>03</span>Knowledge graph</button>
          <button type="button" className="dossier-rail-static dossier-rail-action" onClick={() => selectedCase ? openCase(selectedCase.case_id) : navigate('/case/new')} title="Open the selected case event reconstruction"><span>04</span>Event reconstruction</button>
          <div className="dossier-rail-foot">
            <span className="dossier-foot-mark">!</span>
            <p>Automated links and rule indicators are leads for analyst review, not findings of guilt.</p>
          </div>
        </aside>

        <main className="dossier-main td-command-main">
          <div className="dossier-page-topline">
            <span>Operational workspace <b className="td-live-dot" /></span>
            <span>{new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'long', year: 'numeric' })}</span>
          </div>

          <section className="td-command-hero">
            <div className="td-hero-copy">
              <div className="td-eyebrow"><span className="td-eyebrow-mark" /> TATHYA-DF <i>/</i> INVESTIGATION COMMAND CENTRE</div>
              <h1>Connect the evidence.<br/><em>Reconstruct the timeline.</em></h1>
              <p>One workspace to organise digital evidence, explore relationships and reconstruct event sequences across investigations.</p>
              <div className="td-hero-actions">
                <button className="td-primary-action" onClick={() => navigate('/case/new')}><span>＋</span> Start investigation</button>
                <button className="td-secondary-action" onClick={() => selectedCase ? openCase(selectedCase.case_id) : navigate('/case/new')}>Continue latest case <span>↗</span></button>
              </div>
            </div>
            <div className="td-hero-visual" aria-hidden="true">
              <div className="td-radar-ring td-radar-ring-one" />
              <div className="td-radar-ring td-radar-ring-two" />
              <div className="td-radar-ring td-radar-ring-three" />
              <div className="td-radar-cross td-radar-cross-h" />
              <div className="td-radar-cross td-radar-cross-v" />
              <svg className="td-network-lines" viewBox="0 0 360 250" role="presentation">
                <path d="M72 70 L150 42 L236 82 L290 48 M72 70 L114 164 L206 190 L290 130 L236 82 M150 42 L206 190 M114 164 L290 130" />
                <path d="M236 82 L322 204" className="td-network-line-soft" />
                <circle cx="72" cy="70" r="5"/><circle cx="150" cy="42" r="7"/><circle cx="236" cy="82" r="5"/><circle cx="290" cy="48" r="4"/><circle cx="114" cy="164" r="4"/><circle cx="206" cy="190" r="7"/><circle cx="290" cy="130" r="5"/><circle cx="322" cy="204" r="3" className="td-network-muted"/>
              </svg>
              <div className="td-visual-core"><span>DF</span><small>LINK ANALYSIS</small></div>
              <span className="td-visual-label td-visual-label-a">SOURCE A</span>
              <span className="td-visual-label td-visual-label-b">ENTITY LINK</span>
              <span className="td-visual-label td-visual-label-c">EVENT NODE</span>
            </div>
            <div className="td-hero-index">01 <span> / 05</span></div>
          </section>

          <section className="td-metric-grid" aria-label="Case repository metrics">
            <article className="td-metric-card td-metric-main">
              <div className="td-metric-top"><span>Repository</span><span className="td-metric-glyph">▦</span></div>
              <strong>{loading ? '—' : String(counts.total).padStart(2, '0')}</strong>
              <div className="td-metric-bottom"><span>All investigations</span><i>01</i></div>
            </article>
            <article className="td-metric-card">
              <div className="td-metric-top"><span>Open</span><span className="td-metric-dot amber" /></div>
              <strong>{loading ? '—' : String(counts.open).padStart(2, '0')}</strong>
              <div className="td-metric-bottom"><span>Currently open</span><i>02</i></div>
            </article>
            <article className="td-metric-card">
              <div className="td-metric-top"><span>In progress</span><span className="td-metric-dot blue" /></div>
              <strong>{loading ? '—' : String(counts.active).padStart(2, '0')}</strong>
              <div className="td-metric-bottom"><span>Active work</span><i>03</i></div>
            </article>
            <article className="td-metric-card">
              <div className="td-metric-top"><span>Closed</span><span className="td-metric-dot green" /></div>
              <strong>{loading ? '—' : String(counts.closed).padStart(2, '0')}</strong>
              <div className="td-metric-bottom"><span>Completed cases</span><i>04</i></div>
            </article>
          </section>

          <section className="td-workflow-panel">
            <div className="td-panel-heading">
              <div><span className="td-section-index">01 / METHOD</span><h2>Investigation workflow</h2><p>Explore the five stages of a digital forensic investigation.</p></div>
              <span className="td-panel-hint">SELECT A STAGE <b>＋</b></span>
            </div>
            <div className="td-workflow-track">
              <div className="td-workflow-connector"><span style={{ width: `${activeStage * 25}%` }} /></div>
              {workflowStages.map((stage, index) => (
                <button key={stage.number} type="button" className={`td-workflow-step ${activeStage === index ? 'is-active' : ''}`} onClick={() => setActiveStage(index)} aria-pressed={activeStage === index}>
                  <span className="td-step-node"><i>{stage.symbol}</i><b>{stage.number}</b></span>
                  <span className="td-step-copy"><small>{stage.tag}</small><strong>{stage.title}</strong></span>
                </button>
              ))}
            </div>
            <div className="td-stage-detail" key={activeStage}>
              <div className="td-stage-detail-mark">{workflowStages[activeStage].number}</div>
              <div className="td-stage-detail-copy"><span>{workflowStages[activeStage].tag} / STAGE OVERVIEW</span><p>{workflowStages[activeStage].description}</p></div>
              <button type="button" onClick={runStageAction}>{workflowStages[activeStage].action}<span>↗</span></button>
            </div>
          </section>

          <section className="td-casework-layout">
            <div className="td-casework-panel">
              <div className="td-panel-heading td-casework-heading">
                <div><span className="td-section-index">02 / REGISTER</span><h2>Investigation files</h2><p>Search, filter and select a case to inspect its workspace.</p></div>
                <span className="td-case-total">{loading ? '—' : String(cases.length).padStart(2, '0')} <small>RECORDS</small></span>
              </div>
              <div className="td-case-tools">
                <label className="td-search-box"><span>⌕</span><input ref={searchInputRef} value={search} onChange={event => setSearch(event.target.value)} placeholder="Search by case name, ID or investigator" aria-label="Search investigations"/><kbd>⌘ K</kbd></label>
                <div className="td-filter-tabs" role="group" aria-label="Filter cases by status">
                  {([{ id: 'all', label: 'All' }, { id: 'open', label: 'Open' }, { id: 'in_progress', label: 'In progress' }, { id: 'closed', label: 'Closed' }] as const).map(filter => (
                    <button type="button" key={filter.id} className={statusFilter === filter.id ? 'is-active' : ''} onClick={() => setStatusFilter(filter.id)} aria-pressed={statusFilter === filter.id}>{filter.label}</button>
                  ))}
                </div>
              </div>

              {loading && <div className="td-empty-state"><span className="td-loading-pulse"/> Loading investigation register…</div>}
              {!loading && error && <div className="td-error-state"><div><strong>Unable to reach the case repository</strong><p>{error}. Check that the backend is running, then retry.</p></div><button onClick={() => void loadCases()}>Retry ↻</button></div>}
              {!loading && !error && filteredCases.length === 0 && (
                <div className="td-empty-state"><span className="td-empty-symbol">⌕</span><strong>{cases.length ? 'No matching investigations' : 'Your register is ready'}</strong><p>{cases.length ? 'Try another search or status filter.' : 'Create your first investigation to begin organising evidence.'}</p>{!cases.length && <button onClick={() => navigate('/case/new')}>Create investigation ↗</button>}</div>
              )}
              {!loading && !error && filteredCases.length > 0 && (
                <div className="td-case-list">
                  {filteredCases.map((item, index) => {
                    const selected = selectedCase?.case_id === item.case_id
                    return (
                      <article key={item.case_id} className={`td-case-row ${selected ? 'is-selected' : ''}`}>
                        <button type="button" className="td-case-select" onClick={() => setSelectedCaseId(item.case_id)} aria-pressed={selected}>
                          <span className="td-case-index">{String(index + 1).padStart(2, '0')}</span>
                          <span className="td-case-symbol">{selected ? '◈' : '◇'}</span>
                          <span className="td-case-text"><strong>{item.title || 'Untitled investigation'}</strong><small>{shortId(item.case_id)}</small></span>
                          <span className={statusClass(item.status)}><i />{statusLabel(item.status)}</span>
                          <span className="td-case-date">{formatDate(item.created_at)}</span>
                          <span className="td-case-chevron">{selected ? '↗' : '›'}</span>
                        </button>
                      </article>
                    )
                  })}
                </div>
              )}
            </div>

            <aside className="td-inspector-panel">
              <div className="td-inspector-top"><span className="td-section-index">03 / CASE INSPECTOR</span><span className="td-inspector-state"><i /> {selectedCase ? 'SELECTED' : 'NO SELECTION'}</span></div>
              {selectedCase ? (
                <>
                  <div className="td-inspector-emblem"><span>DF</span><i>CASE FILE</i></div>
                  <span className="td-inspector-label">ACTIVE SELECTION</span>
                  <h3>{selectedCase.title || 'Untitled investigation'}</h3>
                  <p className="td-inspector-id">{selectedCase.case_id}</p>
                  <div className="td-inspector-meta">
                    <div><span>STATUS</span><strong className={statusClass(selectedCase.status)}><i />{statusLabel(selectedCase.status)}</strong></div>
                    <div><span>CREATED</span><strong>{formatDate(selectedCase.created_at)}</strong></div>
                    <div><span>INVESTIGATOR</span><strong>{selectedCase.investigator || 'Unassigned'}</strong></div>
                  </div>
                  <div className="td-inspector-actions">
                    <button className="td-inspector-primary" onClick={() => openCase(selectedCase.case_id)}>Open investigation <span>↗</span></button>
                    <button className="td-inspector-secondary" onClick={() => openGraph(selectedCase.case_id)}>Explore knowledge graph <span>⌘</span></button>
                  </div>
                  <div className="td-inspector-foot"><span className="td-foot-orbit">◎</span><p>Case outputs are scoped to this investigation. Verify associations against their originating records.</p></div>
                </>
              ) : (
                <div className="td-inspector-placeholder"><span>◈</span><strong>Select an investigation</strong><p>Choose a case from the register to inspect its details and open its analysis workspace.</p></div>
              )}
            </aside>
          </section>

          <footer className="td-command-footer"><span>TATHYA-DF <i>·</i> DIGITAL FORENSICS &amp; CYBER INTELLIGENCE</span><span>SELECTION PROTOTYPE <i>·</i> LOCAL DEMONSTRATION BUILD</span></footer>
        </main>
      </div>
    </div>
  )
}
