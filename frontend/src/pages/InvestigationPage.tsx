import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

// ====================================================================
// TATHYA-DF | Investigation Analysis Console
// Stitch screen: 874c9b67e93441d9b66890e4075bba9a
// Layout: TopNav + SideNav (Left 288px) + Graph (Center) + Right Panel (384px)
// overflow: hidden — full viewport
// ====================================================================

import ForceGraphKnowledgeGraph from '../components/ForceGraphKnowledgeGraph'
import {
  type GraphRenderPayload,
  type GraphView,
  type AssessmentsMap,
  type EntityStatus,
  GRAPH_FILTERS,
  filterGraphData,
} from '../types/graph'
import type { ReconstructedTimeline, ReconstructedEvent } from '../types/timeline'

// Results and annotations are scoped to the selected case ID in the URL.
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const STATUS_OPTIONS: EntityStatus[] = ['ACTIVE', 'CLEARED', 'PERSON_OF_INTEREST', 'PRIORITY_TARGET'];

const STATUS_COLORS: Record<EntityStatus, string> = {
  ACTIVE:             '#ffdb9d',
  CLEARED:            '#9ca3af',
  PERSON_OF_INTEREST: '#f97316',
  PRIORITY_TARGET:    '#ef4444',
};

type TabType = 'EXPLAINABILITY' | 'TIMELINE' | 'ASSISTANT'

export default function InvestigationPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const activeCaseId = searchParams.get('case_id') || ''
  const [caseTimeline, setCaseTimeline] = useState<ReconstructedTimeline | null>(null)
  const [rawCaseGraph, setRawCaseGraph] = useState<any>(null)
  const [activeTab, setActiveTab] = useState<TabType>('EXPLAINABILITY')
  const [suspects, setSuspects] = useState<any[]>([])
  const [selectedEntity, setSelectedEntity] = useState<any>(null)

  // ── Graph data & filter state ───────────────────────────────────────────
  const [graphView, setGraphView] = useState<GraphView>('FULL')
  const [fullGraphData, setFullGraphData] = useState<GraphRenderPayload | null>(null)
  const [graphLoading, setGraphLoading] = useState(true)
  const [graphError, setGraphError] = useState<string | null>(null)

  // ── Assessment state ────────────────────────────────────────────────────
  const [assessments, setAssessments] = useState<AssessmentsMap>({})
  const [showCleared, setShowCleared] = useState(true)
  // Entity detail panel: assessment edit state
  const [detailStatus, setDetailStatus] = useState<EntityStatus>('ACTIVE')
  const [detailReason, setDetailReason] = useState('')
  const [savingAssessment, setSavingAssessment] = useState(false)

  // ── Relation Details state ──────────────────────────────────────────────
  const [selectedRelation, setSelectedRelation] = useState<any | null>(null)
  const [relationDetails, setRelationDetails] = useState<any | null>(null)
  const [relationLoading, setRelationLoading] = useState(false)

  const [riskProfiles, setRiskProfiles] = useState<any[]>([])

  // Load one case-scoped result bundle. Avoid global graph/timeline endpoints so
  // switching cases cannot silently display another investigation's evidence.
  useEffect(() => {
    if (!activeCaseId) {
      setGraphError('No case ID was supplied. Open this screen from a processed case.')
      setGraphLoading(false)
      return
    }

    const controller = new AbortController()
    setGraphLoading(true)
    setGraphError(null)
    fetch(`${API_BASE}/api/cases/${encodeURIComponent(activeCaseId)}/results`, { signal: controller.signal })
      .then(async res => {
        if (!res.ok) {
          let message = `Unable to load case results (HTTP ${res.status})`
          try { const payload = await res.json(); message = payload.detail || message } catch { /* HTTP fallback */ }
          throw new Error(message)
        }
        return res.json()
      })
      .then(data => {
        setFullGraphData(data.graph)
        setRawCaseGraph(data.raw_graph)
        setCaseTimeline(data.timeline)
        setRiskProfiles(data.person_profiles || [])
        setSuspects((data.person_profiles || []).map((profile: any) => ({
          master_id: profile.person_id,
          name: profile.name,
          risk_score: profile.risk_score,
          degree_centrality: profile.graph_metrics?.degree ?? 0,
          identifiers: profile.identifiers || [],
          reasons: profile.triggered_rules || [],
        })))
        setGraphLoading(false)
      })
      .catch(err => {
        if (err instanceof Error && err.name !== 'AbortError') {
          setGraphError(err.message)
          setGraphLoading(false)
        }
      })

    return () => controller.abort()
  }, [activeCaseId])

  // Derive the selected entity's risk profile
  const selectedProfile = useMemo(() => {
    if (!selectedEntity) return null
    return riskProfiles.find(p => p.person_id === selectedEntity.id)
  }, [selectedEntity, riskProfiles])

  const handleLinkClick = async (link: any) => {
    const endpointId = (value: any): string => {
      if (typeof value === 'string' || typeof value === 'number') return String(value)
      if (value && typeof value === 'object') {
        const id = value.id ?? value.master_id ?? value.entity_id ?? value.value
        return id == null ? '' : String(id)
      }
      return ''
    }
    const srcId = endpointId(link.source ?? link.source_id)
    const tgtId = endpointId(link.target ?? link.target_id)
    if (!srcId || !tgtId) {
      console.warn('Selected graph connection has no resolvable endpoints', link)
      return
    }

    setSelectedEntity(null)
    setSelectedRelation(link)
    setRelationLoading(true)
    setRelationDetails(null)

    const nodes = fullGraphData?.nodes ?? []
    const nameFor = (id: string) => nodes.find(node => node.id === id)?.label || id
    const relations = (rawCaseGraph?.relations ?? []).filter((relation: any) => {
      const relationSource = endpointId(relation.source ?? relation.source_id ?? relation.from)
      const relationTarget = endpointId(relation.target ?? relation.target_id ?? relation.to)
      return (relationSource === srcId && relationTarget === tgtId) ||
        (relationSource === tgtId && relationTarget === srcId)
    })
    const edgeType = link.type || link.relation || 'RELATED'
    setRelationDetails({
      source_name: nameFor(srcId),
      target_name: nameFor(tgtId),
      edge_type: edgeType,
      edge_confidence: link.confidence,
      interactions_count: relations.length,
      summary: relations.length
        ? `This case contains ${relations.length} retained source relationship record(s) connecting these entities. Review the source, record and timestamp details below; a connection is an investigative lead, not proof of identity, presence or guilt.`
        : `The graph contains a ${edgeType} connection between these entities, but no matching raw relationship record was found. Treat this connection as unverified until its source record is located.`,
      relations: relations.map((relation: any) => {
        const provenance = relation.provenance
        const provenanceText = typeof provenance === 'string'
          ? provenance
          : provenance && typeof provenance === 'object'
            ? JSON.stringify(provenance)
            : null
        return {
          type: relation.relation || relation.type || edgeType,
          timestamp: relation.timestamp ?? relation.timestamp_utc ?? null,
          timestamp_status: relation.timestamp_status ?? null,
          confidence: relation.confidence,
          source_file: relation.source_file ?? null,
          evidence_id: relation.evidence_id ?? null,
          artifact_id: relation.artifact_id ?? null,
          record_id: relation.record_id ?? null,
          provenance: provenanceText,
          description: `${nameFor(endpointId(relation.source ?? relation.source_id ?? relation.from) || srcId)} ${relation.relation || relation.type || edgeType} ${nameFor(endpointId(relation.target ?? relation.target_id ?? relation.to) || tgtId)}`,
        }
      }),
    })
    setRelationLoading(false)
  }


  // Load investigator assessments for this case only.
  useEffect(() => {
    if (!activeCaseId) return
    fetch(`${API_BASE}/api/entity-assessments/${encodeURIComponent(activeCaseId)}`)
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data: AssessmentsMap) => setAssessments(data))
      .catch(err => console.error('Failed to fetch case assessments', err))
  }, [activeCaseId])

  // Sync entity detail panel status when selection changes
  useEffect(() => {
    if (selectedEntity) {
      const existing = assessments[selectedEntity.id]
      setDetailStatus((existing?.status as EntityStatus) ?? 'ACTIVE')
      setDetailReason(existing?.reason ?? '')
    }
  }, [selectedEntity, assessments])

  // ── Assessment save helper ────────────────────────────────────────────
  const saveAssessment = async (entityId: string, status: EntityStatus, reason?: string) => {
    setSavingAssessment(true)
    try {
      await fetch(`${API_BASE}/api/entity-assessments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ case_id: activeCaseId, entity_id: entityId, status, reason: reason || null }),
      })
      setAssessments(prev => ({ ...prev, [entityId]: { status, reason } }))
    } catch (err) {
      console.error('Failed to save assessment', err)
    } finally {
      setSavingAssessment(false)
    }
  }

  // Derive filtered subgraph from the full payload — no extra API calls
  const filteredGraphData = useMemo(
    () => (fullGraphData ? filterGraphData(fullGraphData, graphView) : null),
    [fullGraphData, graphView],
  )

  return (
    <div className="investigation-shell overflow-hidden" style={{ color: '#e5e2e3', fontFamily: 'Geist, sans-serif', height: '100vh', display: 'flex', flexDirection: 'column' }}>

      {/* ── TOP NAV BAR ── */}
      <header className="investigation-topbar flex justify-between items-center w-full h-16 border-b border-[#3f4852]/30 z-50 flex-shrink-0"
        style={{ background: 'rgba(16,22,30,0.94)', backdropFilter: 'blur(18px)', padding: '0 26px' }}>
        <div className="flex items-center gap-8">
          <span
            className="font-black tracking-widest cursor-pointer"
            onClick={() => navigate('/')}
            style={{ fontFamily: 'Geist', fontSize: '27px', fontWeight: '900', color: '#feb700', letterSpacing: '0.1em' }}
          >
            TATHYA-DF
          </span>
          <nav className="hidden md:flex gap-6">
            <a href="#" onClick={(e) => { e.preventDefault(); navigate('/dashboard') }} className="font-medium hover:text-[#ffdb9d] transition-colors duration-200" style={{ color: '#bec7d4', fontFamily: 'Geist', fontSize: '16px' }}>Dashboard</a>
          </nav>
        </div>
        <div className="investigation-case-context hidden xl:flex items-center gap-2 rounded-lg border px-3 py-2" title={activeCaseId}
          style={{ borderColor: 'rgba(145,199,245,0.18)', background: 'rgba(145,199,245,0.06)', minWidth: 260, maxWidth: 420 }}>
          <span className="material-symbols-outlined" style={{ color: '#91c7f5', fontSize: 16 }}>folder_managed</span>
          <span style={{ color: '#91c7f5', fontFamily: 'JetBrains Mono', fontSize: 9, letterSpacing: '0.08em', whiteSpace: 'nowrap' }}>ACTIVE CASE</span>
          <span className="truncate" style={{ color: '#d8e3ee', fontFamily: 'JetBrains Mono', fontSize: 10 }}>{activeCaseId || 'No case selected'}</span>
        </div>
        <div className="flex items-center gap-4">
          <div className="relative group">
            <span className="material-symbols-outlined cursor-pointer hover:text-[#ffdb9d] transition-transform scale-95 active:scale-90" style={{ color: '#bec7d4' }}>notifications</span>
            <div className="absolute top-0 right-0 w-2 h-2 bg-[#ffb4ab] rounded-full border-2 border-[#131314]" />
          </div>
          <span className="material-symbols-outlined cursor-pointer hover:text-[#ffdb9d] transition-transform scale-95 active:scale-90" style={{ color: '#bec7d4' }}>settings</span>
          <div className="flex items-center gap-2 pl-4 border-l border-[#3f4852]/30">
            <img src="/assets/avatars/investigator-2.jpg" alt="Profile" className="w-8 h-8 rounded-full border border-[#feb700]/30 object-cover" />
            <span className="hidden lg:block" style={{ fontFamily: 'JetBrains Mono', fontSize: '12px', color: '#bec7d4' }}>ID-9422 // AGENT</span>
          </div>
        </div>
      </header>

      {/* ── MAIN WORKSPACE ── */}
      <div className="investigation-workspace flex flex-1 overflow-hidden" style={{ height: 'calc(100vh - 64px)' }}>

        {/* ── LEFT SIDEBAR: Entity Navigator ── */}
        <aside className="investigation-sidebar w-64 flex flex-col border-r border-[#3f4852]/30 z-40 flex-shrink-0"
          style={{ background: 'rgba(18,24,32,0.96)', backdropFilter: 'blur(14px)', padding: '20px 0' }}>
          <div className="px-6 mb-8">
            <div className="flex items-center gap-3 mb-2">
              <span className="material-symbols-outlined text-[#e5e2e3]">shield</span>
              <div>
                <div style={{ fontFamily: 'Geist', fontSize: '24px', fontWeight: '600', color: '#e5e2e3' }}>Unit 01</div>
                <div style={{ fontFamily: 'JetBrains Mono', fontSize: '12px', color: '#bec7d4' }} className="uppercase">Forensic Division</div>
              </div>
            </div>
            <button
              onClick={() => navigate('/case/new')}
              className="w-full mt-6 border border-[#feb700]/30 py-3 flex items-center justify-center gap-2 transition-all duration-300 hover:bg-[#feb700]/10"
              style={{ color: '#ffdb9d', background: 'rgba(254,183,0,0.05)' }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>add</span>
              <span style={{ fontFamily: 'JetBrains Mono', fontSize: '14px', fontWeight: '500' }} className="uppercase tracking-wider">New Investigation</span>
            </button>
          </div>

          {/* Search */}
          <div className="flex-1 overflow-y-auto space-y-1">
            <div className="px-6 py-2">
              <div className="relative">
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[#bec7d4]" style={{ fontSize: '18px' }}>search</span>
                <input
                  type="text"
                  placeholder="SEARCH ENTITIES..."
                  className="w-full bg-[#353436]/50 border-none outline-none py-2 pl-10 text-[#e5e2e3] placeholder:text-[#bec7d4]/50 focus:ring-1 focus:ring-[#feb700]/50"
                  style={{ fontFamily: 'JetBrains Mono', fontSize: '12px' }}
                />
              </div>
            </div>

            {/* Nav Items — driven by GRAPH_FILTERS, no routing */}
            {(Object.entries(GRAPH_FILTERS) as [GraphView, typeof GRAPH_FILTERS[GraphView]][]).map(
              ([view, def]) => {
                const isActive = view === graphView
                return (
                  <button
                    key={view}
                    onClick={() => setGraphView(view)}
                    className={`w-full flex items-center gap-3 px-6 py-3 transition-all duration-300 text-left ${
                      isActive
                        ? 'border-r-4 border-[#feb700]'
                        : 'text-[#bec7d4] hover:text-[#e5e2e3]'
                    }`}
                    style={isActive ? { background: 'rgba(254,183,0,0.1)', color: '#ffdb9d' } : {}}
                  >
                    <span className="material-symbols-outlined">{def.icon}</span>
                    <span className="uppercase tracking-wider" style={{ fontFamily: 'JetBrains Mono', fontSize: '14px', fontWeight: '500' }}>
                      {def.label}
                    </span>
                    {def.badge && (
                      <span className="ml-auto px-1.5 py-0.5 rounded-sm text-[10px] font-bold" style={{ background: '#feb700', color: '#412d00' }}>
                        {def.badge}
                      </span>
                    )}
                  </button>
                )
              }
            )}
          </div>

          {/* Footer links */}
          <div className="mt-auto pt-4 border-t border-[#3f4852]/20">
            <a href="#" className="flex items-center gap-3 text-[#bec7d4] px-6 py-2 hover:text-[#e5e2e3] transition-colors">
              <span className="material-symbols-outlined text-sm">help</span>
              <span style={{ fontFamily: 'JetBrains Mono', fontSize: '12px' }} className="uppercase tracking-widest">Help Center</span>
            </a>
            <a href="#" className="flex items-center gap-3 text-[#bec7d4] px-6 py-2 hover:text-[#e5e2e3] transition-colors">
              <span className="material-symbols-outlined text-sm">analytics</span>
              <span style={{ fontFamily: 'JetBrains Mono', fontSize: '12px' }} className="uppercase tracking-widest">System Status</span>
            </a>
          </div>
        </aside>

        {/* ── CENTER: 3D Knowledge Graph Space ── */}
        <main className="investigation-graph flex-1 min-w-0 relative overflow-hidden">
          {/* 3D Force Knowledge Graph — data from GET /graph/render */}
          <div className="absolute inset-0 z-0">
            <ForceGraphKnowledgeGraph
              graphData={filteredGraphData}
              loading={graphLoading}
              error={graphError}
              onNodeClick={(node) => {
                setSelectedEntity(node)
                setSelectedRelation(null) // Clear selected relation on node click
              }}
              onLinkClick={handleLinkClick}
              assessments={assessments}
              showCleared={showCleared}
              onToggleCleared={setShowCleared}
            />
          </div>


          {/* ── NEW DYNAMIC RELATION INTELLIGENCE HUD PANEL ── */}
          {selectedRelation && (
            <div className="relation-intelligence-panel absolute top-5 right-5 glass-panel p-5 rounded-xl flex flex-col gap-3 z-30 transition-all duration-300 animate-fade-in" 
                 style={{ border: '1px solid rgba(254,183,0,0.28)', width: 'min(400px, calc(100% - 40px))', maxHeight: 'calc(100% - 40px)', overflowY: 'auto', backdropFilter: 'blur(18px)', background: 'rgba(17, 23, 31, 0.96)' }}>
              <div className="flex justify-between items-center border-b border-[#3f4852]/30 pb-2">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[#feb700]" style={{ fontSize: '16px' }}>share_reviews</span>
                  <span className="uppercase font-bold" style={{ fontFamily: 'JetBrains Mono', fontSize: '12px', color: '#feb700' }}>
                    Relation Intelligence
                  </span>
                </div>
                <button onClick={() => { setSelectedRelation(null); setRelationDetails(null); }} className="text-[#bec7d4] hover:text-[#feb700] transition-colors material-symbols-outlined text-sm">
                  close
                </button>
              </div>
              
              {relationLoading ? (
                <div className="flex flex-col items-center py-8 gap-2">
                  <div className="w-6 h-6 rounded-full border-2 border-[#feb700]/30 border-t-[#feb700] animate-spin" />
                  <span style={{ fontFamily: 'JetBrains Mono', fontSize: '10px', color: '#bec7d4' }} className="uppercase tracking-widest">Reconstructing Connection...</span>
                </div>
              ) : relationDetails ? (
                <div className="space-y-4">
                  {/* Entity Breadcrumb Header */}
                  <div>
                    <div className="flex items-center gap-2 justify-center text-center py-2 px-3 bg-[#353436]/40 rounded mb-2 border border-[#3f4852]/20">
                      <span className="font-bold text-xs" style={{ color: '#ffdb9d' }}>{relationDetails.source_name}</span>
                      <span className="material-symbols-outlined text-[#feb700] animate-pulse" style={{ fontSize: '14px' }}>swap_horiz</span>
                      <span className="font-bold text-xs" style={{ color: '#ffdb9d' }}>{relationDetails.target_name}</span>
                    </div>
                    <div style={{ fontFamily: 'JetBrains Mono', fontSize: '11px', color: '#bec7d4' }} className="text-center">
                      Relationship: <strong className="text-[#feb700]">{relationDetails.edge_type}</strong>
                      {' · '}Source records: <strong className="text-[#feb700]">{relationDetails.interactions_count}</strong>
                    </div>
                    {typeof relationDetails.edge_confidence === 'number' && (
                      <div style={{ fontFamily: 'JetBrains Mono', fontSize: '10px', color: '#bec7d4' }} className="text-center">
                        Parser-supplied confidence field (not a calibrated probability): {relationDetails.edge_confidence}
                      </div>
                    )}
                  </div>

                  {/* Narrative summary */}
                  <div className="bg-[#feb700]/5 border border-[#feb700]/15 rounded p-3 text-xs leading-relaxed" style={{ color: '#bec7d4', fontFamily: 'Geist' }}>
                    <div className="font-bold text-[10px] text-[#feb700] uppercase tracking-wider mb-1" style={{ fontFamily: 'JetBrains Mono' }}>Narrative Summary</div>
                    {relationDetails.summary}
                  </div>

                  {/* Chronological events */}
                  <div className="space-y-2">
                    <div className="font-bold text-[10px] text-[#bec7d4] uppercase tracking-wider mb-1" style={{ fontFamily: 'JetBrains Mono' }}>Detailed Interacting Signals</div>
                    <div className="space-y-2 max-h-48 overflow-y-auto custom-scrollbar pr-1">
                      {relationDetails.relations.map((rel: any, idx: number) => (
                        <div key={idx} className="border-l-2 border-[#feb700]/30 pl-3 py-1 space-y-1 hover:bg-[#353436]/20 rounded transition-all">
                          <div className="flex justify-between items-center text-[10px]" style={{ fontFamily: 'JetBrains Mono' }}>
                            <span className="px-1.5 py-0.5 rounded text-[8px] font-bold" style={{ background: '#feb700', color: '#412d00' }}>
                              {rel.type}
                            </span>
                            <span className="text-[#bec7d4]/60">
                              {rel.timestamp ? new Date(rel.timestamp).toLocaleString() : 'N/A'}
                            </span>
                          </div>
                          <p className="text-xs text-[#bec7d4]" style={{ fontFamily: 'Geist' }}>{rel.description}</p>
                          {(rel.source_file || rel.evidence_id || rel.artifact_id || rel.record_id || rel.provenance || rel.timestamp_status) && (
                            <div className="space-y-0.5 text-[10px] text-[#bec7d4]/80" style={{ fontFamily: 'JetBrains Mono' }}>
                              {rel.source_file && <div>Source file: {rel.source_file}</div>}
                              {rel.evidence_id && <div>Evidence ID: {rel.evidence_id}</div>}
                              {rel.artifact_id && <div>Artifact ID: {rel.artifact_id}</div>}
                              {rel.record_id && <div>Record ID: {rel.record_id}</div>}
                              {rel.timestamp_status && <div>Timestamp status: {rel.timestamp_status}</div>}
                              {rel.provenance && <div className="break-all">Provenance: {rel.provenance}</div>}
                            </div>
                          )}
                          {typeof rel.confidence === 'number' && (
                            <div style={{ fontSize: '9px', color: '#feb700' }} className="font-mono">
                              Source confidence field (not a calibrated probability): {rel.confidence}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-xs text-[#bec7d4] py-4 text-center">No connection data available.</div>
              )}
            </div>
          )}
        </main>

        {/* ── RIGHT PANEL: Intelligence & Explainability ── */}
        <aside className="investigation-inspector glass-panel border-l border-[#3f4852]/35 flex flex-col z-40 overflow-hidden flex-shrink-0">
          {/* Tabs */}
          <div className="flex border-b border-[#3f4852]/30 flex-shrink-0">
            {(['EXPLAINABILITY', 'TIMELINE', 'ASSISTANT'] as TabType[]).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`investigation-tab flex-1 py-3 uppercase tracking-wider transition-all ${activeTab === tab
                  ? 'border-b-2 border-[#feb700]'
                  : 'hover:bg-[#353436]/20'
                }`}
                style={{
                  fontFamily: 'JetBrains Mono',
                  fontSize: '14px',
                  fontWeight: '500',
                  color: activeTab === tab ? '#ffdb9d' : '#bec7d4',
                  background: activeTab === tab ? 'rgba(254,183,0,0.05)' : 'transparent'
                }}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="investigation-inspector-content flex-1 overflow-y-auto custom-scrollbar p-5 space-y-5">
            {activeTab === 'EXPLAINABILITY' && (
              <>
                {/* Selected Node Details or Generic Intelligence Summary */}
                {selectedEntity ? (
                  <div className="glass-panel p-4 rounded-lg relative overflow-hidden mb-6" style={{ border: '1px solid rgba(254,183,0,0.2)' }}>
                    <div className="flex items-center gap-2 mb-3 border-b border-[#3f4852]/20 pb-2">
                      <span className="material-symbols-outlined text-sm" style={{ color: '#feb700' }}>info</span>
                      <span className="uppercase font-bold" style={{ fontFamily: 'JetBrains Mono', fontSize: '11px', color: '#feb700' }}>Entity Details</span>
                      <span className="ml-auto px-1.5 py-0.5 rounded text-[10px] font-bold" style={{ background: '#feb700', color: '#412d00' }}>
                        {selectedEntity.type}
                      </span>
                    </div>
                    <h4 style={{ fontFamily: 'Geist', fontSize: '18px', fontWeight: 'bold', color: '#e5e2e3', marginBottom: '8px' }}>
                      {selectedEntity.name}
                    </h4>
                    <p style={{ fontFamily: 'JetBrains Mono', fontSize: '11px', color: '#bec7d4', marginBottom: '12px', wordBreak: 'break-all' }}>
                      ID: {selectedEntity.id} <br />
                      Sub-Type: <span className="text-[#feb700]">{selectedEntity.val}</span>
                    </p>

                    {/* Premium Profile Section */}
                    {selectedProfile ? (
                      <div className="mt-4 border-t border-[#3f4852]/30 pt-3 space-y-4">
                        {/* Risk Metric Badge */}
                        <div className="flex justify-between items-center bg-[#ef4444]/10 border border-[#ef4444]/20 p-2.5 rounded">
                          <div>
                            <div style={{ fontFamily: 'JetBrains Mono', fontSize: '10px', color: '#bec7d4' }}>RULE INDICATOR BAND</div>
                            <div style={{ fontFamily: 'JetBrains Mono', fontSize: '16px', fontWeight: 'bold', color: '#ef4444' }}>
                              {selectedProfile.risk_level}
                            </div>
                          </div>
                          <div className="text-right">
                            <div style={{ fontFamily: 'JetBrains Mono', fontSize: '10px', color: '#bec7d4' }}>RULE INDICATOR SCORE · HEURISTIC</div>
                            <div style={{ fontFamily: 'JetBrains Mono', fontSize: '20px', fontWeight: '900', color: '#ef4444' }}>
                              {selectedProfile.risk_score.toFixed(0)}
                            </div>
                          </div>
                        </div>

                        <p className="text-[9px] leading-relaxed" style={{ color: '#98a4b3' }}>Heuristic rule score only. It is not a probability, identity conclusion or finding of guilt.</p>

                        {/* Narrative Explanation */}
                        <div className="space-y-1">
                          <div style={{ fontFamily: 'JetBrains Mono', fontSize: '10px', color: '#feb700' }} className="uppercase font-bold tracking-wider">Forensic Summary</div>
                          <p style={{ fontFamily: 'Geist', fontSize: '12px', color: '#bec7d4', lineHeight: '18px' }}>
                            {selectedProfile.explanation}
                          </p>
                        </div>

                        {/* Contributing Risk Factors */}
                        <div className="space-y-2">
                          <div style={{ fontFamily: 'JetBrains Mono', fontSize: '10px', color: '#feb700' }} className="uppercase font-bold tracking-wider">Triggered Rule Indicators ({selectedProfile.evidence.length})</div>
                          <div className="space-y-1.5 max-h-40 overflow-y-auto custom-scrollbar pr-1">
                            {selectedProfile.evidence.map((ev: any, idx: number) => (
                              <div key={idx} className="bg-[#1c1b1c] border border-[#3f4852]/30 rounded p-2 text-xs space-y-1">
                                <div className="flex justify-between items-center text-[#ffb4ab] font-bold">
                                  <span>{ev.rule_name}</span>
                                  <span>+{ev.weighted_contribution.toFixed(1)}</span>
                                </div>
                                {ev.evidence?.text_snippet && (
                                  <p className="italic text-[#bec7d4]/60">"{ev.evidence.text_snippet}"</p>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Suspicious/Notable Actions Timeline */}
                        <div className="space-y-2">
                          <div style={{ fontFamily: 'JetBrains Mono', fontSize: '10px', color: '#feb700' }} className="uppercase font-bold tracking-wider">Related Timeline Records</div>
                          <div className="space-y-2 max-h-40 overflow-y-auto custom-scrollbar pr-1">
                            {selectedProfile.timeline.map((act: any, idx: number) => (
                              <div key={idx} className="border-l border-[#feb700]/30 pl-2.5 py-0.5 space-y-0.5">
                                <div style={{ fontSize: '9px', color: 'rgba(190,199,212,0.6)' }} className="font-mono">
                                  {new Date(act.timestamp).toLocaleString()}
                                </div>
                                <div className="text-xs font-bold text-[#ffdb9d]">{act.action}</div>
                                <p className="text-xs text-[#bec7d4]/80">{act.description}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    ) : suspects.find(s => s.master_id === selectedEntity.id) ? (
                      /* Legacy suspects fallback if not resolved in premium */
                      <div className="mt-4 border-t border-[#3f4852]/30 pt-3">
                        <div style={{ fontFamily: 'JetBrains Mono', fontSize: '12px', color: '#ffb4ab', fontWeight: 'bold', marginBottom: '4px' }}>
                          Indicator score: {suspects.find(s => s.master_id === selectedEntity.id).risk_score}
                        </div>
                        <ul className="list-disc pl-4 space-y-1 mt-2 text-xs text-[#bec7d4] font-sans">
                          {suspects.find(s => s.master_id === selectedEntity.id).reasons.map((reason: string, ri: number) => (
                            <li key={ri}>{reason}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}

                    {/* ── Investigator Assessment Section (kept intact) ── */}
                    <div className="mt-4 border-t border-[#3f4852]/30 pt-3 space-y-2">
                      <div style={{ fontFamily: 'JetBrains Mono', fontSize: '11px', color: '#bec7d4', letterSpacing: '0.05em', marginBottom: '6px' }}>INVESTIGATOR ASSESSMENT</div>
                      <select
                        value={detailStatus}
                        onChange={e => setDetailStatus(e.target.value as EntityStatus)}
                        className="w-full rounded px-2 py-1.5 text-xs outline-none border border-[#3f4852]/50 focus:border-[#feb700] transition-colors"
                        style={{ background: '#1c1b1c', color: STATUS_COLORS[detailStatus], fontFamily: 'JetBrains Mono', fontWeight: 'bold' }}
                      >
                        {STATUS_OPTIONS.map(s => (
                          <option key={s} value={s} style={{ color: STATUS_COLORS[s] }}>{s.replace(/_/g, ' ')}</option>
                        ))}
                      </select>
                      <textarea
                        value={detailReason}
                        onChange={e => setDetailReason(e.target.value)}
                        placeholder="Reason (optional)..."
                        rows={2}
                        className="w-full rounded px-2 py-1.5 text-xs outline-none border border-[#3f4852]/50 focus:border-[#feb700] transition-colors resize-none"
                        style={{ background: '#1c1b1c', color: '#e5e2e3', fontFamily: 'Geist', fontSize: '12px' }}
                      />
                      <button
                        onClick={() => saveAssessment(selectedEntity.id, detailStatus, detailReason)}
                        disabled={savingAssessment}
                        className="w-full py-2 rounded flex items-center justify-center gap-2 font-bold uppercase tracking-wider hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-50"
                        style={{ background: '#feb700', color: '#412d00', fontFamily: 'JetBrains Mono', fontSize: '11px' }}
                      >
                        <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>save</span>
                        {savingAssessment ? 'Saving...' : 'Save Assessment'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="glass-panel p-4 rounded-lg relative overflow-hidden" style={{ border: '1px solid rgba(152,203,255,0.2)' }}>
                    <div className="flex items-center gap-2 mb-3">
                      <span className="material-symbols-outlined text-sm" style={{ color: '#98cbff' }}>psychology</span>
                      <span className="uppercase font-bold" style={{ fontFamily: 'JetBrains Mono', fontSize: '12px', color: '#98cbff' }}>Intelligence Summary</span>
                      <span className="ml-auto" style={{ fontFamily: 'JetBrains Mono', fontSize: '10px', color: '#bec7d4' }}>MDL-84</span>
                    </div>
                    <p style={{ fontFamily: 'Geist', fontSize: '14px', color: '#bec7d4', lineHeight: '20px' }}>
                      Select a node in this case's knowledge graph to inspect its available attributes, transaction history, centrality measures, and linked evidence. Select a connection to inspect the relationship details and its recorded provenance.
                    </p>
                    <div className="mt-4 flex gap-2">
                      <span className="text-[10px] px-2 py-0.5 rounded" style={{ background: 'rgba(152,203,255,0.1)', border: '1px solid rgba(152,203,255,0.2)', color: '#98cbff' }}>INTERACTIVE</span>
                      <span className="text-[10px] px-2 py-0.5 rounded" style={{ background: 'rgba(254,183,0,0.1)', border: '1px solid rgba(254,183,0,0.2)', color: '#ffdb9d' }}>CASE-SCOPED GRAPH</span>
                    </div>
                  </div>
                )}



                {/* Suspects List Section */}
                {activeTab === 'EXPLAINABILITY' && suspects.length > 0 && (
                  <div className="mt-6">
                    <h3 className="uppercase tracking-widest border-b border-[#3f4852]/20 pb-2 mb-4" style={{ fontFamily: 'JetBrains Mono', fontSize: '12px', color: '#bec7d4' }}>Entity Review Profiles</h3>
                    <div className="space-y-3">
                      {suspects.map((s, i) => (
                        <div
                          key={i}
                          onClick={() => setSelectedEntity({ id: s.master_id, name: s.name, type: 'PERSON', val: s.identifiers[0] })}
                          className={`p-3 rounded border transition-all cursor-pointer ${
                            selectedEntity?.id === s.master_id
                              ? 'bg-[#feb700]/10 border-[#feb700]'
                              : 'bg-[#201f20]/40 border-[#3f4852]/30 hover:border-[#feb700]/50'
                          }`}
                        >
                          <div className="flex justify-between items-center mb-1">
                            <span style={{ fontFamily: 'Geist', fontSize: '14px', fontWeight: '600', color: '#e5e2e3' }}>{s.name}</span>
                            <span style={{ fontFamily: 'JetBrains Mono', fontSize: '12px', color: '#ffb4ab', fontWeight: 'bold' }}>{s.risk_score} RULE SCORE</span>
                          </div>
                          <p style={{ fontFamily: 'JetBrains Mono', fontSize: '10px', color: '#bec7d4', marginBottom: '6px' }}>Centrality: {s.degree_centrality}</p>
                          {/* Status dropdown */}
                          <div onClick={e => e.stopPropagation()}>
                            <select
                              value={assessments[s.master_id]?.status ?? 'ACTIVE'}
                              onChange={e => saveAssessment(s.master_id, e.target.value as EntityStatus)}
                              className="w-full rounded px-2 py-1 text-[10px] outline-none border border-[#3f4852]/40 focus:border-[#feb700] transition-colors"
                              style={{
                                background: '#1c1b1c',
                                color: STATUS_COLORS[(assessments[s.master_id]?.status as EntityStatus) ?? 'ACTIVE'],
                                fontFamily: 'JetBrains Mono',
                                fontWeight: 'bold',
                              }}
                            >
                              {STATUS_OPTIONS.map(st => (
                                <option key={st} value={st} style={{ color: STATUS_COLORS[st] }}>{st.replace(/_/g, ' ')}</option>
                              ))}
                            </select>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {activeTab === 'TIMELINE' && (
              <TimelineTab selectedEntityId={selectedEntity?.id} timeline={caseTimeline} />
            )}

            {activeTab === 'ASSISTANT' && (
              <AssistantTab selectedEntity={selectedEntity} />
            )}
          </div>

          {/* Action Area */}
          <div className="investigation-actions p-4 border-t border-[#3f4852]/35 space-y-3 flex-shrink-0">
            <button
              onClick={() => {
                if (!activeCaseId) return
                window.open(`${API_BASE}/api/cases/${encodeURIComponent(activeCaseId)}/export-pdf`, '_blank', 'noopener,noreferrer')
              }}
              disabled={!activeCaseId || graphLoading || Boolean(graphError)}
              title="Generate and export the processed case report as PDF."
              className="w-full py-4 rounded-lg flex items-center justify-center gap-2 hover:brightness-110 active:scale-[0.99] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ background: '#eeb94f', color: '#2a210f', fontFamily: 'Geist', fontSize: '15px', fontWeight: '650', letterSpacing: '0.01em' }}
            >
              <span className="material-symbols-outlined">description</span>
              <span style={{ fontSize: '16px' }}>Export investigation report (PDF)</span>
            </button>
            <div
              className="w-full py-3 rounded-lg border border-[#3f4852]/30 text-center uppercase tracking-widest"
              style={{ background: '#202021', color: '#8f98a5', fontFamily: 'JetBrains Mono', fontSize: '11px', fontWeight: '500' }}
              title="Agency peer-review workflow is outside the current demonstration prototype."
            >
              Agency peer review · future scope
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}

function TimelineTab({ selectedEntityId, timeline }: { selectedEntityId?: string; timeline: ReconstructedTimeline | null }) {
  const [events, setEvents] = useState<ReconstructedEvent[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<ReconstructedEvent | null>(null);

  useEffect(() => {
    setLoading(true)
    setError(null)
    setSelectedEvent(null)
    if (!timeline) {
      setEvents([])
      setError('No case timeline is available. Process this case first.')
      setLoading(false)
      return
    }
    const allEvents = timeline.scenes ? timeline.scenes.flatMap(scene => scene.events || []) : []
    setEvents(allEvents)
    setLoading(false)
  }, [timeline])

  const displayedEvents = useMemo(() => {
    if (selectedEntityId) {
      return events.filter(e => e.from_id === selectedEntityId || e.to_id === selectedEntityId);
    }
    return events;
  }, [events, selectedEntityId]);

  useEffect(() => {
    if (selectedEvent && !displayedEvents.includes(selectedEvent)) {
      setSelectedEvent(null)
    }
  }, [displayedEvents, selectedEvent])

  const renderDetailValue = (value: unknown) => {
    if (value === null || value === undefined || value === '') return 'Not recorded in timeline output'
    if (typeof value === 'object') return JSON.stringify(value, null, 2)
    return String(value)
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-[#bec7d4] font-mono text-xs">
        <div className="w-8 h-8 rounded-full border-2 border-[#feb700]/30 border-t-[#feb700] animate-spin mb-4" />
        LOADING TIMELINE EVENTS...
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-8 text-[#ffb4ab] text-xs font-mono">
        <span className="material-symbols-outlined text-sm block mb-2">error</span>
        {error}
      </div>
    );
  }

  const detailRows: Array<[string, unknown]> = selectedEvent ? [
    ['Event action', selectedEvent.action],
    ['Event time (source clock)', selectedEvent.timestamp],
    ['Timestamp status', selectedEvent.timestamp_status || selectedEvent.time_basis],
    ['Normalised UTC time', selectedEvent.timestamp_utc],
    ['Source type', selectedEvent.source_type],
    ['Source file', selectedEvent.source_file],
    ['Evidence ID', selectedEvent.evidence_id],
    ['Evidence SHA-256', selectedEvent.evidence_sha256],
    ['Source record number', selectedEvent.source_record_number],
    ['Artifact ID', selectedEvent.artifact_id],
    ['Record ID', selectedEvent.record_id],
    ['From entity', selectedEvent.from],
    ['From entity ID', selectedEvent.from_id],
    ['To entity', selectedEvent.to],
    ['To entity ID', selectedEvent.to_id],
    ['Parser confidence field (not a calibrated probability)', selectedEvent.confidence],
    ['Provenance', selectedEvent.provenance],
    ['Provenance method', selectedEvent.provenance_type],
    ['Additional attributes', selectedEvent.attributes],
  ] : []

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 justify-between">
        <h3 className="uppercase tracking-widest border-b border-[#3f4852]/20 pb-2 flex-grow" style={{ fontFamily: 'JetBrains Mono', fontSize: '12px', color: '#bec7d4' }}>
          {selectedEntityId ? 'Filtered Intel Timeline' : 'Global Temporal Sequence'}
        </h3>
        <span className="text-[10px] font-mono text-[#bec7d4]">{displayedEvents.length} events</span>
      </div>

      {selectedEvent && (
        <section className="rounded-lg border border-[#feb700]/50 bg-[#1b1a17] p-3 space-y-3" aria-label="Selected timeline event details">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-[#ffdb9d] uppercase tracking-widest text-[11px] font-mono">Selected event details</h4>
            <button
              type="button"
              onClick={() => setSelectedEvent(null)}
              className="text-[#bec7d4] hover:text-white text-[11px] underline"
              aria-label="Clear selected event"
            >Clear</button>
          </div>
          <p className="text-sm text-[#e5e2e3] font-medium">{selectedEvent.description}</p>
          {selectedEvent.timestamp_status === 'timezone_unknown' && (
            <p className="text-[10px] text-[#f6c66b]">Timezone not supplied. This event is ordered only within its source clock and should not be treated as a verified cross-source UTC time.</p>
          )}
          {selectedEvent.timestamp_status === 'timezone_aware' && selectedEvent.timestamp_utc && (
            <p className="text-[10px] text-[#8bd5a5]">UTC comparison time: {selectedEvent.timestamp_utc}</p>
          )}
          <div className="space-y-2">
            {detailRows.map(([label, value]) => (
              <div key={label} className="border-t border-[#3f4852]/40 pt-2">
                <div className="text-[9px] uppercase tracking-wider text-[#98a4b3] font-mono">{label}</div>
                <pre className="mt-1 whitespace-pre-wrap break-words text-[10px] leading-relaxed text-[#e5e2e3] font-mono">{renderDetailValue(value)}</pre>
              </div>
            ))}
          </div>
          <p className="text-[9px] text-[#98a4b3]">Displayed values are fields retained by the current timeline output. Missing fields mean the processor did not provide them in this event record.</p>
        </section>
      )}

      {displayedEvents.length === 0 ? (
        <div className="text-center py-8 text-[#bec7d4]/50 text-xs font-mono">No chronological activities found for this node.</div>
      ) : (
        <div className="relative border-l-2 border-[#3f4852]/50 pl-4 ml-2 space-y-4">
          {displayedEvents.map((event, index) => {
            const isSelected = selectedEvent === event
            return (
              <button
                type="button"
                key={event.record_id || event.evidence_id || `${event.timestamp}-${event.action}-${index}`}
                onClick={() => setSelectedEvent(event)}
                aria-pressed={isSelected}
                className="relative group block w-full rounded-md p-2 -ml-2 text-left transition-colors focus:outline-none focus:ring-1 focus:ring-[#feb700]"
                style={{ background: isSelected ? 'rgba(254,183,0,0.10)' : 'transparent', cursor: 'pointer' }}
                title="Select this event to inspect its source and provenance details"
              >
                <div
                  className="absolute -left-[14px] top-3 w-2.5 h-2.5 rounded-full border border-black transition-transform duration-300 group-hover:scale-125"
                  style={{
                    background: event.action === 'TRANSFERRED_TO' || event.action === 'TRANSFERRED_MONEY' ? '#00a3ff' :
                                event.action === 'CALLED' ? '#98cbff' : '#feb700'
                  }}
                />
                <div style={{ fontFamily: 'JetBrains Mono', fontSize: '11px', color: '#98cbff' }}>{event.timestamp.replace('T', ' ')}</div>
                {event.timestamp_status === 'timezone_unknown' && (
                  <div style={{ fontFamily: 'Geist', fontSize: '10px', color: '#f6c66b', marginTop: '2px' }}>
                    Timezone not supplied — ordered only within this source clock
                  </div>
                )}
                {event.timestamp_status === 'timezone_aware' && event.timestamp_utc && (
                  <div style={{ fontFamily: 'Geist', fontSize: '10px', color: '#8bd5a5', marginTop: '2px' }}>
                    Normalised for comparison: {event.timestamp_utc}
                  </div>
                )}
                <div style={{ fontFamily: 'Geist', fontSize: '13px', fontWeight: '500', color: '#e5e2e3', marginTop: '2px' }}>{event.description}</div>
                <div style={{ fontFamily: 'JetBrains Mono', fontSize: '9px', color: '#bec7d4', marginTop: '4px' }}>
                  Source: {event.source_type} // Parser field: {event.confidence}
                </div>
                <div className="mt-1 text-[9px] font-mono text-[#ffdb9d] opacity-0 group-hover:opacity-100 focus-visible:opacity-100">SELECT TO INSPECT EVENT →</div>
              </button>
            )
          })}
        </div>
      )}
    </div>
  );
}

function AssistantTab({ selectedEntity }: { selectedEntity?: any }) {
  const [messages, setMessages] = useState<{ sender: 'user' | 'system'; text: string }[]>([
    { sender: 'system', text: 'Prototype analyst helper. This panel is not connected to a live language model in this build; use evidence inspectors for verified case data.' }
  ]);
  const [input, setInput] = useState('');

  const handleSend = () => {
    if (!input.trim()) return;
    const userMsg = input;
    setMessages(prev => [...prev, { sender: 'user', text: userMsg }]);
    setInput('');

    // This is an explicitly-labelled prototype helper, not a connected LLM.
    const reply = selectedEntity
      ? `Selected entity: ${selectedEntity.name} (${selectedEntity.type}). Use the Explainability panel to review its recorded attributes and linked relationships. This helper does not infer identity or guilt.`
      : `This assistant is a prototype interface and is not connected to a live language model in this build. Use the graph, relationship inspector and timeline to review evidence-backed information. Your query was: "${userMsg}".`;
    setMessages(prev => [...prev, { sender: 'system', text: reply }]);
  };

  return (
    <div className="flex flex-col h-[400px]">
      <h3 className="uppercase tracking-widest border-b border-[#3f4852]/20 pb-2 mb-3" style={{ fontFamily: 'JetBrains Mono', fontSize: '12px', color: '#bec7d4' }}>
        Tactical Assistant
      </h3>
      <div className="flex-1 overflow-y-auto space-y-3 pr-2 mb-3 max-h-[300px] custom-scrollbar">
        {messages.map((m, idx) => (
          <div key={idx} className={`p-3 rounded-lg text-xs leading-relaxed max-w-[85%] ${
            m.sender === 'user' 
              ? 'bg-[#feb700]/10 border border-[#feb700]/30 text-[#ffdb9d] ml-auto' 
              : 'bg-[#353436]/40 border border-[#3f4852]/20 text-[#bec7d4]'
          }`}>
            <div className="font-bold mb-1 uppercase tracking-wider" style={{ fontSize: '9px', opacity: 0.8 }}>
              {m.sender === 'user' ? 'AGENT // INQUIRY' : 'TATHYA-DF // PROTOTYPE HELPER'}
            </div>
            <div>{m.text}</div>
          </div>
        ))}
      </div>
      <div className="flex gap-2 mt-auto">
        <input 
          type="text" 
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder={selectedEntity ? `Ask about ${selectedEntity.name}...` : "Query graph intelligence..."}
          className="flex-grow bg-[#201f20] border border-[#3f4852]/50 rounded px-3 py-2 text-xs text-[#e5e2e3] focus:outline-none focus:border-[#feb700]"
          style={{ fontFamily: 'Geist' }}
        />
        <button 
          onClick={handleSend}
          className="px-4 bg-[#feb700] hover:brightness-110 text-[#412d00] text-xs font-bold rounded flex items-center justify-center"
        >
          <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>send</span>
        </button>
      </div>
    </div>
  );
}

