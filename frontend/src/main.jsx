import React, { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { AnimatePresence, motion } from "motion/react";
import {
  Activity, ArrowDown, ArrowUp, ArrowUpRight, Check, ChevronRight, CircleAlert,
  Clock3, Command, Database, FileText, Filter, Layers3, LoaderCircle, MessageSquareText,
  Network, RotateCw, Search, ShieldCheck, Sparkles, TriangleAlert, X,
} from "lucide-react";
import { api, ApiError } from "./api.js";
import "./styles.css";

const ReplayChart = lazy(() => import("./ReplayChart.jsx"));

const pageNames = ["Incident desk", "Replay lab", "Learning & memory"];
const number = (value) => Number.isFinite(value) ? value.toLocaleString() : "—";
const dateLabel = (value) => value ? new Date(value).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" }) : "Date not recorded";

function BrandMark() {
  return <div className="brand-mark" aria-hidden="true"><svg viewBox="0 0 38 38" fill="none"><path d="m4 13 15-9 15 9-15 9L4 13Z"/><path d="m4 13 15 9v12L4 25V13Z"/><path d="m34 13-15 9v12l15-9V13Z"/><path d="m12 17 15-9" strokeDasharray="2 3"/></svg></div>;
}

function Masthead({ page, setPage, health, counts, refresh, refreshing }) {
  return <>
    <header className="topbar">
      <a className="brand" href="#top" aria-label="IncidentMind home" onClick={() => setPage(pageNames[0])}>
        <BrandMark /><span className="brand-word">INCIDENTMIND</span><span className="brand-divider"/><span className="brand-sub">Memory for operations</span>
      </a>
      <div className="topbar-right">
        <div className={`connection ${health ? "is-live" : "is-offline"}`}><span className="connection-dot" aria-hidden="true"/>{health ? "API connected" : "API unavailable"}</div>
        <button className="icon-button" type="button" onClick={refresh} disabled={refreshing} aria-label="Refresh dashboard" title="Refresh dashboard"><RotateCw size={16} className={refreshing ? "spin" : ""}/></button>
        <div className="avatar" aria-label="On-call operator">ON</div>
      </div>
    </header>
    <section id="top" className="hero">
      <div className="hero-copy">
        <div className="eyebrow"><span>OPERATIONS</span><span className="eyebrow-slash">/</span><span>MEMORY, MADE USEFUL</span></div>
        <h1>Every incident<br/><em>leaves a signal.</em></h1>
        <p>A calmer control room for the details that help teams understand what failed, what worked, and what to watch next.</p>
      </div>
      <div className="hero-visual" aria-hidden="true">
        <svg className="wire-art" viewBox="0 0 470 260" fill="none">
          <g stroke="currentColor" strokeWidth="1.15" strokeLinejoin="round">
            <path d="m28 178 88-52 88 52-88 51-88-51Z"/><path d="m116 126 1-76 87 50v76"/><path d="m28 178 1-77 87-51"/><path d="m116 229 1-77 88-52"/><path d="M29 101 116 50l88 50-87 52-88-51Z"/><path d="m75 128 1-76m42 100 1-76m43 100 1-76" strokeDasharray="3 5"/>
            <path d="m203 178 87-51 87 51-87 51-87-51Z"/><path d="m290 127 1-77 87 50v78"/><path d="m203 178 1-77 87-51"/><path d="m290 229 1-77 87-51"/><path d="m204 101 87-51 87 50-87 52-87-51Z"/>
          </g><g fill="var(--paper)" stroke="currentColor"><circle cx="29" cy="101" r="3"/><circle cx="204" cy="101" r="3"/><circle cx="378" cy="100" r="3"/></g>
        </svg>
        <div className="hero-art-caption"><span>RETAIN / RECALL / REFLECT</span><span>01—03</span></div>
      </div>
      <div className="hero-index"><span>INCIDENT RESPONSE</span><span>INTELLIGENCE CONSOLE&nbsp; / &nbsp;01</span></div>
    </section>
    <nav className="tabs" aria-label="Dashboard sections" role="tablist" onKeyDown={(event) => {
      const current = pageNames.indexOf(page);
      const next = event.key === "ArrowRight" ? (current + 1) % pageNames.length : event.key === "ArrowLeft" ? (current - 1 + pageNames.length) % pageNames.length : event.key === "Home" ? 0 : event.key === "End" ? pageNames.length - 1 : -1;
      if (next >= 0) { event.preventDefault(); setPage(pageNames[next]); document.getElementById(`dashboard-tab-${next}`)?.focus(); }
    }}>
      {pageNames.map((name, index) => <button id={`dashboard-tab-${index}`} role="tab" aria-controls="dashboard-panel" tabIndex={page === name ? 0 : -1} aria-selected={page === name} className={`tab ${page === name ? "active" : ""}`} key={name} onClick={() => setPage(name)}>
        <span className="tab-number">0{index + 1}</span>{name}<ChevronRight size={13}/>
      </button>)}
      <div className="tab-spacer"/>
      <div className="tab-count"><span className="status-mini"/><span>{number(counts.incidents)} EVENTS</span></div>
    </nav>
  </>;
}

function SectionHead({ index, title, note, action }) {
  return <div className="section-head"><div className="section-title"><span className="section-index">{index}</span><h2>{title}</h2><div className="section-rule"/></div>{action}<p>{note}</p></div>;
}

function StatusPill({ label, kind = "neutral" }) {
  return <span className={`pill pill-${kind}`}><span className="pill-dot"/>{label}</span>;
}

function severityKind(severity = "unknown") {
  return ["critical", "high"].includes(severity.toLowerCase()) ? "danger" : severity.toLowerCase() === "medium" ? "warning" : "neutral";
}

function outcomeFor(row) {
  return row.synthetic ? { label: "Synthetic", kind: "synthetic" } : row.feedback_outcome ? { label: row.feedback_outcome, kind: row.feedback_outcome === "resolved" ? "success" : row.feedback_outcome === "failed" ? "danger" : "warning" } : { label: "Needs review", kind: "neutral" };
}

function Snapshot({ rows, memory, onSelect }) {
  const real = rows.filter((item) => !item.synthetic);
  const open = real.filter((item) => !item.feedback_outcome).length;
  const synthetic = rows.filter((item) => item.synthetic).length;
  return <section className="snapshot">
    <SectionHead index="00" title="Operational snapshot" note="Counts reflect persisted incidents and confirmed Hindsight Retain responses."/>
    <div className="metric-grid">
      <Metric icon={Activity} label="Incidents recorded" value={number(rows.length)} foot="Real and synthetic"/>
      <Metric icon={Clock3} label="Awaiting verification" value={number(open)} foot="Real incidents"/>
      <Metric icon={Database} label="Hindsight retains" value={number(memory?.retained_in_hindsight)} foot="Confirmed responses"/>
      <Metric icon={Layers3} label="Synthetic exercises" value={number(synthetic)} foot="Excluded from verified totals"/>
    </div>
    <div className="data-note"><ShieldCheck size={15}/> No success rate is inferred. Synthetic scenarios are labeled and excluded from verified outcome counts.</div>
  </section>;
}

function Metric({ icon: Icon, label, value, foot }) {
  return <div className="metric-card"><div className="metric-top"><span>{label}</span><Icon size={16}/></div><strong>{value}</strong><span className="metric-foot">{foot}</span></div>;
}

function IncidentList({ rows, selectedId, onSelect }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const filtered = useMemo(() => rows.filter((row) => {
    const item = row.incident;
    const state = outcomeFor(row).label.toLowerCase();
    const matchesFilter = filter === "all" || (filter === "needs-review" && state === "needs review") || state === filter;
    const haystack = `${item.service} ${item.error} ${item.id} ${item.category || ""}`.toLowerCase();
    return matchesFilter && haystack.includes(query.trim().toLowerCase());
  }), [rows, filter, query]);
  const actual = filtered.filter((row) => !row.synthetic);
  const synthetic = filtered.filter((row) => row.synthetic);
  return <section className="incident-list panel">
    <div className="list-toolbar">
      <div className="list-intro"><span className="micro-label">LATEST SIGNALS</span><span className="list-total">{filtered.length} records</span></div>
      <label className="search-box"><Search size={15}/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search service, summary, ID" aria-label="Search incidents"/><kbd>/</kbd></label>
      <label className="filter-box"><Filter size={14}/><select value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Filter incidents"><option value="all">All states</option><option value="needs-review">Needs review</option><option value="resolved">Resolved</option><option value="failed">Failed</option><option value="partial">Partial</option><option value="synthetic">Synthetic</option></select></label>
    </div>
    <IncidentRows rows={actual} selectedId={selectedId} onSelect={onSelect}/>
    {synthetic.length > 0 && <><div className="subsection-label"><span>S</span><span>Synthetic exercises</span><i/></div><p className="muted-caption">Chaos Dojo records stay distinct from production history.</p><IncidentRows rows={synthetic} selectedId={selectedId} onSelect={onSelect}/></>}
    {!filtered.length && <div className="empty-list"><div className="empty-icon"><Search size={18}/></div><strong>{rows.length ? "No incidents match this view" : "No incidents recorded yet"}</strong><p>{rows.length ? "Try another status or search term." : "Submit an alert to the FastAPI service to begin building operational memory."}</p></div>}
  </section>;
}

function IncidentRows({ rows, selectedId, onSelect }) {
  if (!rows.length) return null;
  return <div className="incident-rows">
    <div className="row-head"><span>Service / type</span><span>Incident summary</span><span>Severity</span><span>Outcome</span><span>Date</span><span/></div>
    {rows.map(({ incident, ...meta }, index) => {
      const outcome = outcomeFor({ incident, ...meta });
      return <button key={incident.id} className={`incident-row ${selectedId === incident.id ? "selected" : ""}`} onClick={() => onSelect(incident.id)} aria-label={`Open ${incident.service}: ${incident.error}`}>
        <span className="row-service"><span className="row-number">{String(index + 1).padStart(2, "0")}</span><span><strong>{incident.service}</strong><small>{incident.category || "Unclassified"}</small></span></span>
        <span className="row-summary">{incident.error}</span>
        <span><StatusPill label={incident.severity || "unknown"} kind={severityKind(incident.severity)}/></span>
        <span><StatusPill label={outcome.label} kind={outcome.kind}/></span>
        <span className="row-date">{dateLabel(incident.created_at)}</span>
        <span className="row-arrow"><ArrowUpRight size={15}/></span>
      </button>;
    })}
  </div>;
}

function IncidentDetail({ row, incident, feedbackHistory, analysis, analysisBusy, onAnalyze, onFeedback, feedbackBusy, error, warning, notice }) {
  if (!row) return <section className="detail-card detail-empty"><div className="empty-icon"><Command size={18}/></div><strong>Select an incident</strong><p>Choose a record from the register to inspect its history and request a memory-grounded assessment.</p></section>;
  if (!incident) return <section className="detail-card detail-loading"><LoaderCircle className="spin" size={18}/><span>Loading incident detail…</span></section>;
  const outcome = outcomeFor(row);
  return <motion.section className="detail-card" key={incident.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .24 }}>
    <div className="detail-topline"><span className="micro-label">INCIDENT DETAIL</span><button className="text-button" type="button" onClick={() => navigator.clipboard?.writeText(incident.id)} title="Copy incident ID"><FileText size={14}/> COPY ID</button></div>
    <div className="detail-badges"><StatusPill label={incident.severity || "unknown"} kind={severityKind(incident.severity)}/><StatusPill label={outcome.label} kind={outcome.kind}/>{incident.tags?.includes("synthetic=true") && <StatusPill label="Synthetic" kind="synthetic"/>}</div>
    <h3>{incident.service}</h3><p className="detail-summary">{incident.error}</p>
    <div className="detail-metadata"><div><span>INCIDENT ID</span><code>{incident.id}</code></div><div><span>CLASSIFICATION</span><strong>{incident.category || "Unclassified"}</strong></div><div><span>OCCURRED</span><strong>{dateLabel(incident.occurred_at || incident.created_at)}</strong></div></div>
    {incident.symptoms?.length > 0 && <div className="symptoms"><span className="micro-label">OBSERVED SYMPTOMS</span><div>{incident.symptoms.map((item) => <span key={item}>{item}</span>)}</div></div>}
    {feedbackHistory?.length > 0 && <section className="verified-record"><div className="verified-record-head"><StatusPill label="Verified by engineer" kind="success"/><span>{dateLabel(feedbackHistory[0].created_at)}</span></div><strong>{feedbackHistory[0].verified_cause}</strong>{feedbackHistory[0].steps_taken?.length > 0 && <ol>{feedbackHistory[0].steps_taken.map((step, index) => <li key={`${step}-${index}`}>{step}</li>)}</ol>}{feedbackHistory[0].notes && <p>{feedbackHistory[0].notes}</p>}{feedbackHistory.length > 1 && <details><summary>Earlier verifications ({feedbackHistory.length - 1})</summary>{feedbackHistory.slice(1).map((item) => <div className="earlier-verification" key={item.feedback_id}><span>{dateLabel(item.created_at)} · {item.outcome}</span><strong>{item.verified_cause}</strong>{item.steps_taken?.map((step, index) => <small key={`${step}-${index}`}>{step}</small>)}</div>)}</details>}</section>}
    {incident.logs_excerpt && <details className="log-details"><summary><FileText size={14}/> Captured log excerpt</summary><pre>{incident.logs_excerpt}</pre></details>}
    <div className="assessment-block">
      <div className="assessment-heading"><div><span className="micro-label">MEMORY ASSISTED REVIEW</span><h4>Agent assessment</h4></div><button className="button button-primary" onClick={onAnalyze} disabled={analysisBusy}>{analysisBusy ? <LoaderCircle className="spin" size={15}/> : <Sparkles size={15}/>} {analysisBusy ? "Recalling memory…" : "Analyze with memory"}</button></div>
      {!analysis && <p className="assessment-hint">Suspected causes remain hypotheses until an engineer verifies them. Recommendations are for review and are never executed.</p>}
      {analysis && <AnalysisView analysis={analysis}/>}
      {error && <div className="inline-alert alert-error" role="alert"><CircleAlert size={16}/><span>{error}</span></div>}
      {warning && <div className="inline-alert alert-warning" role="status"><TriangleAlert size={16}/><span>{warning}</span></div>}
      {notice && <div className={`inline-alert ${notice.includes("not confirmed") ? "alert-warning" : "alert-success"}`} role="status" aria-live="polite">{notice.includes("not confirmed") ? <TriangleAlert size={16}/> : <Check size={16}/>}<span>{notice}</span></div>}
    </div>
    <FeedbackForm incidentId={incident.id} existingOutcome={row.feedback_outcome} onSubmit={onFeedback} busy={feedbackBusy}/>
  </motion.section>;
}

function AnalysisView({ analysis }) {
  const hypotheses = analysis.analysis?.hypotheses || [];
  const recommendations = analysis.analysis?.recommended_steps || [];
  return <div className="analysis-view">
    <div className="analysis-meta"><span className="analysis-source"><span className={`source-dot ${analysis.memory_available ? "source-available" : ""}`}/>{analysis.memory_available ? "Hindsight memory available" : "Memory unavailable"}</span><span>{analysis.cold_start ? "Cold start" : "Historical context retrieved"}{analysis.used_fallback ? " · Runbook fallback" : ""}</span></div>
    {analysis.message && <p className="analysis-message">{analysis.message}</p>}
    <div className="analysis-section"><span className="micro-label">SUSPECTED CAUSES</span>{hypotheses.length ? hypotheses.map((item) => <div className="hypothesis" key={`${item.cause}-${item.evidence_incident_ids.join()}`}><div><StatusPill label="Suspected" kind="warning"/><strong>{item.cause}</strong></div><p>{item.reasoning}</p><small>Historical citations: {item.evidence_incident_ids.length ? item.evidence_incident_ids.join(", ") : "none"}</small></div>) : <p className="muted-caption">No cause hypothesis was returned. Review the runbook checks and incident evidence.</p>}</div>
    {recommendations.length > 0 && <div className="analysis-section"><span className="micro-label">RECOMMENDED CHECKS · ENGINEER REVIEW</span><ol className="recommendation-list">{recommendations.map((step, i) => <li key={`${step}-${i}`}><span>{String(i + 1).padStart(2, "0")}</span><p>{step}</p></li>)}</ol></div>}
    {analysis.warnings?.map((warning, i) => <div className="inline-alert alert-warning" key={`warn-${i}`}><TriangleAlert size={16}/><span>{warning}</span></div>)}
    {analysis.anti_runbook_warnings?.map((warning, i) => <div className="anti-runbook" key={`anti-${i}`}><TriangleAlert size={16}/><div><strong>Previously attempted fix</strong><p>{warning.message}</p>{warning.context?.map((context) => <small key={context}>{context}</small>)}</div></div>)}
    <div className="analysis-section evidence-section"><div className="evidence-title"><span className="micro-label">HINDSIGHT MEMORY EVIDENCE</span><span className="evidence-count">{analysis.evidence?.length || 0} recalled</span></div>{analysis.evidence?.length ? analysis.evidence.map((item, i) => <details className="evidence-item" key={item.memory_id || item.incident_id || i}><summary><span><Network size={14}/>{item.incident_id || item.memory_id || `Historical memory ${i + 1}`}</span><span>{typeof item.relevance === "number" ? `Relevance ${item.relevance.toFixed(2)}` : "Historical record"}</span></summary><p>{item.source_text || item.raw_text || item.text || "Source text was not returned."}</p><small>Historical evidence is separate from the agent’s suspected current cause.</small></details>) : <p className="muted-caption">No relevant historical evidence was recalled for this incident.</p>}</div>
  </div>;
}

function FeedbackForm({ incidentId, existingOutcome, onSubmit, busy }) {
  const [expanded, setExpanded] = useState(false);
  const [cause, setCause] = useState("");
  const [steps, setSteps] = useState("");
  const [outcome, setOutcome] = useState("resolved");
  const [notes, setNotes] = useState("");
  useEffect(() => { setExpanded(false); setCause(""); setSteps(""); setNotes(""); }, [incidentId, existingOutcome]);
  return <section className="feedback-section">
    <button className="feedback-toggle" type="button" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}><span><span className="micro-label">ENGINEER VERIFICATION</span><strong>{existingOutcome ? "Record another verification" : "Record verified outcome"}</strong></span><span className="feedback-toggle-icon">{expanded ? <X size={15}/> : <MessageSquareText size={16}/>}</span></button>
    <AnimatePresence initial={false}>{expanded && <motion.form className="feedback-form" onSubmit={(event) => { event.preventDefault(); onSubmit({ verified_cause: cause, steps_taken: steps.split("\n").map((value) => value.trim()).filter(Boolean), outcome, notes }); }} initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: .2 }}>
      <label>Verified cause<input required maxLength={10000} value={cause} onChange={(event) => setCause(event.target.value)} placeholder="What did the engineer confirm?"/></label>
      <label>Steps taken<textarea maxLength={20000} rows={3} value={steps} onChange={(event) => setSteps(event.target.value)} placeholder="One action per line"/></label>
      <div className="feedback-grid"><label>Outcome<select value={outcome} onChange={(event) => setOutcome(event.target.value)}><option value="resolved">Resolved</option><option value="failed">Failed</option><option value="partial">Partial</option></select></label><label>Engineer notes<textarea maxLength={20000} rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Context and impact"/></label></div>
      <div className="form-footer"><span>Feedback is stored through FastAPI and retained when Hindsight is available.</span><button className="button button-dark" type="submit" disabled={busy}>{busy ? <LoaderCircle size={15} className="spin"/> : <Check size={15}/>} Save verified feedback</button></div>
    </motion.form>}</AnimatePresence>
  </section>;
}

function IncidentDesk({ rows, memory, selectedId, setSelectedId, incident, feedbackHistory, analysis, analysisBusy, onAnalyze, onFeedback, feedbackBusy, actionError, notice }) {
  const selectedRow = rows.find((row) => row.incident.id === selectedId);
  return <motion.div className="page-content" key="incidents" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25 }}>
    <Snapshot rows={rows} memory={memory}/>
    <SectionHead index="01" title="Incident register" note="Verified history stays distinct from synthetic exercises."/>
    <div className="incident-layout"><IncidentList rows={rows} selectedId={selectedId} onSelect={setSelectedId}/><IncidentDetail row={selectedRow} incident={incident} feedbackHistory={feedbackHistory} analysis={analysis} analysisBusy={analysisBusy} onAnalyze={onAnalyze} onFeedback={onFeedback} feedbackBusy={feedbackBusy} error={actionError} warning={actionWarning} notice={notice}/></div>
  </motion.div>;
}

function ReplayLab({ rows }) {
  const [selected, setSelected] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const candidates = rows.filter((row) => row.feedback_outcome && !row.synthetic);
  const move = (index, direction) => setSelected((current) => { const copy = [...current]; const target = index + direction; if (target < 0 || target >= copy.length) return current; [copy[index], copy[target]] = [copy[target], copy[index]]; return copy; });
  const toggle = (id) => setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  async function run() { setBusy(true); setError(""); try { setResult(await api.replay(selected)); } catch (err) { setError(err.message); } finally { setBusy(false); } }
  const chartData = result ? result.memory_disabled.steps.map((step, i) => ({
    sequence: step.step,
    "Memory disabled": step.steps_to_verified_fix,
    "Memory enabled": result.memory_enabled.steps[i]?.steps_to_verified_fix ?? null,
  })) : [];
  return <motion.div className="page-content" key="replay" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25 }}>
    <div className="page-kicker"><span>EXPERIMENTAL WORKSPACE</span><span>02 / REPLAY</span></div>
    <SectionHead index="01" title="Replay lab" note="Replay the same ordered incidents with memory disabled and enabled."/>
    <div className="replay-intro"><div className="replay-symbol"><Activity size={21}/></div><div><strong>Compare what the agent recalled</strong><p>Only engineer-verified incidents are eligible. The replay uses an isolated memory bank; metrics are shown as observed.</p></div><div className="replay-count"><strong>{selected.length.toString().padStart(2, "0")}</strong><span>SELECTED</span></div></div>
    <div className="replay-picker panel"><div className="panel-heading"><div><span className="micro-label">VERIFIED INCIDENTS</span><h3>Build a sequence</h3></div><span className="helper-text">Choose records, then arrange their order.</span></div>
      {candidates.length ? <div className="sequence-list">{candidates.map(({ incident, feedback_outcome: outcome }) => { const index = selected.indexOf(incident.id); return <div className={`sequence-row ${index >= 0 ? "chosen" : ""}`} key={incident.id}><label className="sequence-check"><input type="checkbox" checked={index >= 0} onChange={() => toggle(incident.id)}/><span className="custom-check">{index >= 0 ? <Check size={12}/> : null}</span><span className="sequence-service"><strong>{incident.service}</strong><small>{incident.error}</small></span><StatusPill label={outcome} kind={outcome === "resolved" ? "success" : outcome === "failed" ? "danger" : "warning"}/></label>{index >= 0 && <div className="sequence-order"><span>{String(index + 1).padStart(2, "0")}</span><button onClick={() => move(index, -1)} disabled={index === 0} aria-label={`Move ${incident.service} earlier`}><ArrowUp size={14}/></button><button onClick={() => move(index, 1)} disabled={index === selected.length - 1} aria-label={`Move ${incident.service} later`}><ArrowDown size={14}/></button></div>}</div>; })}</div> : <div className="empty-list"><div className="empty-icon"><Activity size={18}/></div><strong>No verified incidents to replay</strong><p>Record an engineer-verified outcome before comparing memory conditions.</p></div>}
      <div className="replay-footer"><span className="muted-caption">Synthetic incidents are excluded.</span><button className="button button-dark" disabled={!selected.length || busy} onClick={run}>{busy ? <LoaderCircle size={15} className="spin"/> : <Activity size={15}/>} Run memory comparison</button></div>
      {error && <div className="inline-alert alert-error"><CircleAlert size={15}/>{error}</div>}
    </div>
    {result && <ReplayResult result={result} chartData={chartData}/>}
  </motion.div>;
}

function ReplayResult({ result, chartData }) {
  const variants = [result.memory_disabled, result.memory_enabled];
  return <section className="replay-results">
    <div className="run-id"><span className="section-index">RUN</span><span>{result.run_id}</span><i/><span>{result.incidents_replayed} INCIDENTS</span></div>
    <div className="variant-grid">{variants.map((variant) => { const cited = variant.steps.filter((item) => item.correct_prior_cause_cited === true).length; const measured = variant.steps.filter((item) => item.correct_prior_cause_cited !== null).length; return <article className="variant-card" key={variant.mode}><div className="variant-name"><span className={`variant-mark ${variant.mode === "memory_enabled" ? "mark-on" : ""}`}/><strong>{variant.mode === "memory_enabled" ? "Memory enabled" : "Memory disabled"}</strong><span>{variant.mode === "memory_enabled" ? "HINDSIGHT" : "BASELINE"}</span></div><strong className="variant-value">{cited} <small>of {measured} checks</small></strong><span className="variant-label">Correct prior-cause citations</span><div className="variant-foot">Memory {variant.mode === "memory_enabled" ? (variant.memory_available ? "available" : "unavailable") : "off for baseline"}</div></article>; })}</div>
    <div className="chart-card panel"><div className="panel-heading"><div><span className="micro-label">MEASURED FIX POSITION</span><h3>Learning curve</h3></div><span className="chart-unit">Recommendation position</span></div>{chartData.some((point) => point["Memory disabled"] !== null || point["Memory enabled"] !== null) ? <Suspense fallback={<div className="chart-empty"><LoaderCircle className="spin" size={18}/><p>Loading the replay chart…</p></div>}><ReplayChart chartData={chartData}/></Suspense> : <div className="chart-empty"><Activity size={18}/><p>No measured recommendation positions in this replay. The table still shows every observed step; values are never imputed.</p></div>}
      <div className="chart-legend"><span><i/>Memory disabled</span><span><i/>Memory enabled</span></div></div>
    <div className="table-wrap"><table><thead><tr><th>MODE</th><th>STEP</th><th>INCIDENT</th><th>CORRECT CITATION</th><th>FIX POSITION</th><th>VERIFIED CAUSE</th></tr></thead><tbody>{variants.flatMap((variant) => variant.steps.map((step) => <tr key={`${variant.mode}-${step.step}`}><td>{variant.mode === "memory_enabled" ? "Memory enabled" : "Memory disabled"}</td><td>{String(step.step).padStart(2, "0")}</td><td><code>{step.incident_id}</code></td><td>{step.correct_prior_cause_cited === null ? "Not measured" : step.correct_prior_cause_cited ? "Yes" : "No"}</td><td>{step.steps_to_verified_fix ?? "Not measured"}</td><td>{step.matched_verified_cause || "—"}</td></tr>))}</tbody></table></div>
    <details className="raw-result"><summary>Inspect complete replay response</summary><pre>{JSON.stringify(result, null, 2)}</pre></details>
  </section>;
}

function Learning({ memory, rows }) {
  const [stats, setStats] = useState(null);
  const [insightQuestion, setInsightQuestion] = useState("Which fixes failed most often?");
  const [insight, setInsight] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { Promise.allSettled([api.memoryOrigins(), api.outcomes()]).then((results) => setStats({ origins: results[0].status === "fulfilled" ? results[0].value : null, outcomes: results[1].status === "fulfilled" ? results[1].value : null })); }, [rows.length, memory?.feedback_records]);
  async function reflect(event) { event.preventDefault(); setBusy(true); setError(""); try { setInsight(await api.reflect(insightQuestion)); } catch (err) { setError(err.message); } finally { setBusy(false); } }
  const outcomeRows = stats?.outcomes?.outcomes ? Object.entries(stats.outcomes.outcomes).map(([outcome, count]) => ({ outcome, count })) : [];
  return <motion.div className="page-content" key="learning" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25 }}>
    <div className="page-kicker"><span>PERSISTENT OPERATIONAL MEMORY</span><span>03 / LEARNING</span></div>
    <SectionHead index="01" title="Learning & memory" note="Real engineer feedback and synthetic examples are reported separately."/>
    <div className="memory-grid"><Metric icon={MessageSquareText} label="Feedback records" value={number(memory?.feedback_records)} foot="Engineer submitted"/><Metric icon={Database} label="Real incidents retained" value={number(stats?.origins?.real_retained_in_hindsight)} foot="Confirmed Hindsight responses"/><Metric icon={Layers3} label="Synthetic retained" value={number(stats?.origins?.synthetic_retained_in_hindsight)} foot="Labeled exercises"/><Metric icon={Check} label="Total confirmed retains" value={number(memory?.retained_in_hindsight)} foot="Retain responses"/></div>
    <div className="data-note"><Database size={15}/> A retained count records successful Hindsight Retain responses. It is not a live bank inventory.</div>
    <div className="learning-columns"><section className="panel outcome-panel"><div className="panel-heading"><div><span className="micro-label">VERIFIED RECORDS</span><h3>Recorded outcomes</h3></div><span className="helper-text">Synthetic feedback excluded</span></div>{outcomeRows.length ? <div className="outcome-list">{outcomeRows.map(({ outcome, count }) => <div className="outcome-line" key={outcome}><span><StatusPill label={outcome} kind={outcome === "resolved" ? "success" : outcome === "failed" ? "danger" : "warning"}/></span><strong>{count}</strong><span>recorded</span></div>)}</div> : <p className="muted-caption">No verified outcomes have been recorded yet.</p>}
      <div className="table-wrap compact-table"><table><thead><tr><th>VERIFIED CAUSE</th><th>RECORDED</th><th>RESOLVED</th><th>FAILED</th></tr></thead><tbody>{stats?.outcomes?.by_resolution?.length ? stats.outcomes.by_resolution.map((item) => <tr key={item.verified_cause}><td>{item.verified_cause}</td><td>{item.display}</td><td>{item.resolved}</td><td>{item.failed}</td></tr>) : <tr><td colSpan="4">No engineer-verified causes yet.</td></tr>}</tbody></table></div>
    </section><section className="reflect-panel"><div className="reflect-heading"><span className="reflect-icon"><Sparkles size={17}/></span><div><span className="micro-label">HINDSIGHT REFLECT</span><h3>Ask the memory</h3></div></div><p>Explore patterns from retained operational history. If Reflect is unavailable, the API clearly labels its stored-feedback fallback.</p><form onSubmit={reflect}><label htmlFor="reflect-question">Question</label><textarea id="reflect-question" minLength="3" maxLength="2000" rows="3" value={insightQuestion} onChange={(event) => setInsightQuestion(event.target.value)}/><button className="button button-dark" type="submit" disabled={busy}>{busy ? <LoaderCircle size={15} className="spin"/> : <ArrowUpRight size={15}/>} Reflect on history</button></form>{error && <div className="inline-alert alert-error"><CircleAlert size={15}/>{error}</div>}{insight && <div className="insight-result"><div className="insight-source"><span className="source-dot source-available"/>{insight.source === "hindsight" ? "Hindsight Reflect" : "Stored-feedback fallback"}{insight.cached ? " · cached" : ""}</div><p>{insight.answer}</p><small>Updated {dateLabel(insight.cached_at)}</small></div>}</section></div>
    <SectionHead index="02" title="Outcomes by category" note="Counts are calculated from stored engineer feedback; no percentage is inferred."/>
    <div className="table-wrap panel category-table"><table><thead><tr><th>CATEGORY</th><th>RECORDED</th><th>RESOLVED</th><th>FAILED</th><th>PARTIAL</th></tr></thead><tbody>{stats?.outcomes?.by_category?.length ? stats.outcomes.by_category.map((item) => <tr key={item.category}><td>{item.category}</td><td>{item.recorded}</td><td>{item.resolved}</td><td>{item.failed}</td><td>{item.partial}</td></tr>) : <tr><td colSpan="5">No category totals are available yet.</td></tr>}</tbody></table></div>
  </motion.div>;
}

function App() {
  const [page, setPage] = useState(pageNames[0]);
  const [rows, setRows] = useState([]);
  const [memory, setMemory] = useState(null);
  const [health, setHealth] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [incident, setIncident] = useState(null);
  const [feedbackHistory, setFeedbackHistory] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [actionWarning, setActionWarning] = useState("");
  const [notice, setNotice] = useState("");
  const [fatalError, setFatalError] = useState("");

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setRefreshing(true);
    setFatalError("");
    const [healthResult, feedResult, memoryResult] = await Promise.allSettled([api.health(), api.incidents(), api.memory()]);
    setHealth(healthResult.status === "fulfilled");
    if (feedResult.status === "fulfilled") {
      const nextRows = feedResult.value;
      setRows(nextRows);
      setSelectedId((current) => current && nextRows.some((item) => item.incident.id === current) ? current : nextRows[0]?.incident.id || null);
    } else {
      const error = feedResult.reason;
      setFatalError(error instanceof ApiError ? error.message : "Could not load incidents.");
    }
    if (memoryResult.status === "fulfilled") setMemory(memoryResult.value);
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => { refresh(true); }, [refresh]);
  useEffect(() => {
    if (!selectedId) { setIncident(null); setFeedbackHistory([]); setAnalysis(null); return; }
    setIncident(null); setFeedbackHistory([]);
    setAnalysis(null); setActionError(""); setActionWarning(""); setNotice("");
    let alive = true;
    Promise.allSettled([api.incident(selectedId), api.feedbackHistory(selectedId)]).then(([incidentResult, feedbackResult]) => {
      if (!alive) return;
      if (incidentResult.status === "fulfilled") setIncident(incidentResult.value);
      else setActionError(incidentResult.reason.message);
      if (feedbackResult.status === "fulfilled") setFeedbackHistory(feedbackResult.value);
    });
    return () => { alive = false; };
  }, [selectedId]);

  async function analyze() {
    if (!selectedId) return;
    setAnalysisBusy(true); setActionError(""); setActionWarning(""); setNotice("");
    try { setAnalysis(await api.analyze(selectedId)); } catch (error) { setActionError(error.message); }
    finally { setAnalysisBusy(false); }
  }

  async function saveFeedback(payload) {
    if (!selectedId) return;
    setFeedbackBusy(true); setActionError(""); setActionWarning(""); setNotice("");
    try {
      const result = await api.feedback(selectedId, payload);
      setNotice(`Feedback ${result.duplicate ? "was already recorded" : "recorded"}. Hindsight Retain ${result.memory_retained ? "confirmed" : "not confirmed"}.`);
      if (result.warning) setActionWarning(result.warning);
      setFeedbackHistory(await api.feedbackHistory(selectedId));
      await refresh(true);
    } catch (error) { setActionError(error.message); }
    finally { setFeedbackBusy(false); }
  }

  const pageView = page === pageNames[0]
    ? <IncidentDesk rows={rows} memory={memory} selectedId={selectedId} setSelectedId={setSelectedId} incident={incident} feedbackHistory={feedbackHistory} analysis={analysis} analysisBusy={analysisBusy} onAnalyze={analyze} onFeedback={saveFeedback} feedbackBusy={feedbackBusy} actionError={actionError} notice={notice}/>
    : page === pageNames[1] ? <ReplayLab rows={rows}/> : <Learning memory={memory} rows={rows}/>;

  return <div className="app-shell"><Masthead page={page} setPage={setPage} health={health} counts={{ incidents: rows.length }} refresh={() => refresh(false)} refreshing={refreshing}/>
    <main>
      <div id="dashboard-panel" role="tabpanel" aria-labelledby={`dashboard-tab-${Math.max(0, pageNames.indexOf(page))}`} tabIndex={0}>
        <AnimatePresence mode="wait">{loading ? <motion.div className="loading-state" key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><LoaderCircle className="spin" size={20}/>Loading operational history…</motion.div> : fatalError ? <motion.div className="fatal-state" key="error" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><CircleAlert size={21}/><div><strong>Could not load the incident register</strong><p>{fatalError}</p><button className="button button-dark" onClick={() => refresh(false)}><RotateCw size={14}/> Try again</button></div></motion.div> : <React.Fragment key={page}>{pageView}</React.Fragment>}</AnimatePresence>
      </div>
    </main>
    <footer className="footer"><span><BrandMark/> INCIDENTMIND <i/> OPERATIONAL MEMORY</span><span>Recommendations require engineer review. No recovery actions are executed.</span><span>01—03&nbsp; / &nbsp;{page.toUpperCase()}</span></footer>
  </div>;
}

createRoot(document.getElementById("root")).render(<React.StrictMode><App/></React.StrictMode>);
