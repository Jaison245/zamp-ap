import React, { useEffect, useRef, useState } from "react";
import { api, Code, RunResult, StageEvent } from "../api";
import { Card, DecisionBadge, money, SeverityTag, StatusGlyph, cx, SectionLabel } from "../ui";
import {
  IconNewRun, IconCopy, IconCheck, IconClock, IconDollar, IconShield, IconChevronDown, Spinner,
} from "../icons";

const STAGE_NAMES = [
  "Intake", "Pre-processing", "Extraction (Claude)", "Verify extraction", "Normalisation",
  "Vendor validation", "Duplicate detection", "PO matching", "Line match (2/3-way)",
  "Decision engine", "Explain & act",
];
type Stage = { stage: number; name: string; status: string; duration_ms?: number; detail?: any; notes?: string[]; codes?: Code[] };
const initStages = (): Stage[] => STAGE_NAMES.map((name, i) => ({ stage: i, name, status: "pending" }));

export default function LiveRun({ runId, replay = false, onNew }: { runId: number; replay?: boolean; onNew?: () => void }) {
  const [stages, setStages] = useState<Stage[]>(initStages());
  const [result, setResult] = useState<RunResult | null>(null);
  const [open, setOpen] = useState<number | null>(2);
  const [elapsed, setElapsed] = useState(0);
  const [cost, setCost] = useState<number | null>(null);
  const [pdfLoaded, setPdfLoaded] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (replay) {
      api.getRun(runId).then((r: any) => {
        const map = initStages();
        (r.events || []).forEach((ev: any) => {
          if (typeof ev.stage === "number" && ev.status !== "running")
            map[ev.stage] = { ...map[ev.stage], status: ev.status, duration_ms: ev.duration_ms, detail: ev.detail, notes: ev.notes, codes: ev.codes };
        });
        setStages(map); setResult(r.result); setElapsed(r.duration_ms || 0); setCost(r.cost_usd); setOpen(9);
      });
      return;
    }
    setStages(initStages()); setResult(null); setElapsed(0); setCost(null);
    const t0 = Date.now();
    const timer = setInterval(() => setElapsed(Date.now() - t0), 90);
    const es = new EventSource(`/api/runs/${runId}/stream`);
    esRef.current = es;
    es.onmessage = (m) => {
      let ev: StageEvent;
      try { ev = JSON.parse(m.data); } catch { return; }
      if (ev.type === "stage" && typeof ev.stage === "number") {
        setStages((prev) => prev.map((s) => s.stage === ev.stage
          ? { ...s, status: ev.status!, duration_ms: ev.duration_ms, detail: ev.detail, notes: ev.notes, codes: ev.codes } : s));
        if (ev.status !== "running") setOpen(ev.stage!);
      } else if (ev.type === "decision") {
        setResult(ev.result!); if (ev.cost_usd) setCost(ev.cost_usd); clearInterval(timer);
      } else if (ev.type === "error") {
        setStages((prev) => prev.map((s) => s.status === "running" ? { ...s, status: "fail" } : s));
        clearInterval(timer);
      }
    };
    es.addEventListener("end", () => { es.close(); clearInterval(timer); });
    es.onerror = () => { es.close(); clearInterval(timer); };
    return () => { es.close(); clearInterval(timer); };
  }, [runId, replay]);

  const done = !!result;
  const completed = stages.filter((s) => s.status !== "pending" && s.status !== "running").length;
  const progress = Math.round((completed / stages.length) * 100);

  return (
    <div className="px-4 sm:px-7 py-6 animate-fade-in">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold tracking-tight">{replay ? "Run replay" : "Live run"}</h1>
          <span className="chip bg-ink/[0.05] text-ink-soft ring-1 ring-line tnum">#{runId}</span>
        </div>
        <button onClick={onNew} className="btn-soft !py-2 !px-3"><IconNewRun size={16} /> New run</button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-12 gap-4 xl:h-[calc(100vh-9.5rem)]">
        {/* Document */}
        <Card className="xl:col-span-4 overflow-hidden flex flex-col h-[400px] lg:h-[460px] xl:h-full !shadow-md">
          <div className="px-4 h-11 flex items-center justify-between border-b border-line shrink-0">
            <span className="text-[13px] font-semibold text-ink-soft">Source document</span>
            <span className="text-[11px] text-ink-faint">PDF</span>
          </div>
          <div className="relative flex-1 bg-surface-2">
            {!pdfLoaded && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-ink-faint">
                <Spinner size={22} className="text-brand-500" />
                <span className="text-[12px]">Loading document…</span>
              </div>
            )}
            <iframe title="invoice" src={api.pdfUrl(runId) + "#toolbar=0&view=FitH"} onLoad={() => setPdfLoaded(true)}
              className={cx("absolute inset-0 w-full h-full transition-opacity duration-300", pdfLoaded ? "opacity-100" : "opacity-0")} />
          </div>
        </Card>

        {/* Pipeline */}
        <Card className="xl:col-span-4 flex flex-col h-[520px] lg:h-[460px] xl:h-full !shadow-md">
          <div className="px-4 h-11 flex items-center justify-between border-b border-line shrink-0">
            <span className="text-[13px] font-semibold text-ink-soft">Pipeline</span>
            <span className="inline-flex items-center gap-1.5 text-[11px] text-ink-faint tnum">
              <IconClock size={13} /> {(elapsed / 1000).toFixed(1)}s{!done && "…"}
            </span>
          </div>
          <div className="h-[3px] bg-ink/[0.05] shrink-0">
            <div className="h-full bg-brand-gradient transition-all duration-300 ease-spring" style={{ width: `${progress}%` }} />
          </div>
          <div className="p-3 overflow-y-auto flex-1">
            {stages.map((s, i) => {
              const isOpen = open === s.stage;
              const active = s.status !== "pending";
              return (
                <div key={s.stage} className="relative">
                  {i < stages.length - 1 && <div className={cx("absolute left-[19px] top-9 bottom-0 w-px", s.status === "pending" ? "bg-line" : "bg-line-strong")} />}
                  <button onClick={() => setOpen(isOpen ? null : s.stage)}
                    className={cx("w-full flex items-center gap-3 px-2 py-1.5 rounded-xl text-left transition-colors", active ? "hover:bg-ink/[0.03]" : "opacity-55")}>
                    <StatusGlyph status={s.status} index={s.stage} />
                    <span className="flex-1 min-w-0">
                      <span className="text-[13.5px] font-semibold text-ink block leading-tight">{s.name}</span>
                      {s.notes && s.notes.length > 0 && (
                        <span className="block text-[11px] text-ink-faint truncate mt-0.5">{s.notes.slice(0, 3).join(" · ")}</span>
                      )}
                    </span>
                    {typeof s.duration_ms === "number" && active && <span className="text-[10.5px] font-mono text-ink-ghost tnum shrink-0">{s.duration_ms}ms</span>}
                    {active && s.detail && <IconChevronDown size={14} className={cx("text-ink-ghost transition-transform shrink-0", isOpen && "rotate-180")} />}
                  </button>
                  {isOpen && active && s.detail && (
                    <div className="ml-11 mb-2 mt-1 rounded-xl bg-surface-2 border border-line p-3 text-xs animate-scale-in origin-top">
                      <StageDetail stage={s} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Card>

        {/* Decision */}
        <div className="lg:col-span-2 xl:col-span-4 xl:h-full xl:overflow-y-auto">
          {done ? <DecisionCard result={result!} cost={cost} elapsed={elapsed} />
            : <Card className="h-full min-h-[320px] flex flex-col items-center justify-center text-center p-8 !shadow-md relative overflow-hidden">
                <div className="absolute inset-0 bg-mesh pointer-events-none" />
                <div className="relative">
                  <div className="w-14 h-14 rounded-2xl bg-brand-soft flex items-center justify-center mx-auto mb-4 ring-1 ring-brand-100">
                    <Spinner size={26} className="text-brand-600" />
                  </div>
                  <div className="text-ink font-semibold">Deciding…</div>
                  <div className="text-ink-faint text-[13px] mt-1 max-w-[220px]">The model reads the document — code makes the call.</div>
                </div>
              </Card>}
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: any }) {
  if (v === null || v === undefined || v === "") return null;
  return <div className="flex justify-between gap-3 py-0.5"><span className="text-ink-faint">{k}</span><span className="font-medium text-ink-soft text-right break-all">{String(v)}</span></div>;
}

function Tick({ ok }: { ok: boolean }) {
  return <span className={cx("inline-flex items-center justify-center w-4 h-4 rounded-full text-white shrink-0", ok ? "bg-approve" : "bg-reject")}>{ok ? <IconCheck size={11} strokeWidth={3} /> : "✕"}</span>;
}

function StageDetail({ stage }: { stage: Stage }) {
  const d = stage.detail || {};
  if (stage.stage === 2) {
    const f = d.fields || {};
    return (
      <div className="space-y-0.5">
        <Row k="type" v={d.document_type} /><Row k="legibility" v={d.legibility} />
        <Row k="invoice #" v={f.invoice_number} /><Row k="vendor" v={f.vendor} />
        <Row k="total" v={f.total} /><Row k="PO ref" v={f.po_reference} /><Row k="mode" v={d.mode} />
        {d.suspicious_instructions?.length > 0 && (
          <div className="mt-2 rounded-lg bg-reject-soft border border-reject-ring p-2.5 text-reject-ink">
            <div className="font-semibold mb-1 flex items-center gap-1.5"><IconShield size={13} /> Instruction aimed at the AI — reported, not followed</div>
            <div className="italic text-[11px] opacity-90">"{d.suspicious_instructions[0]}"</div>
          </div>
        )}
      </div>
    );
  }
  if (stage.stage === 3) {
    return (
      <div className="space-y-2.5">
        {d.grounding?.length > 0 && <div>
          <div className="font-semibold text-ink-faint mb-1.5 uppercase tracking-wide text-[10px]">Grounding — quote found in PDF</div>
          <div className="space-y-1">{d.grounding.map((g: any, i: number) => (
            <div key={i} className="flex items-center gap-2"><Tick ok={g.ok} /><span className="text-ink-soft">{g.field}</span></div>))}</div>
        </div>}
        {d.double_read && <Row k="double-read disagreements" v={d.double_read.disagree?.join(", ") || "none"} />}
        {d.reconciliation?.length > 0 && <div>
          <div className="font-semibold text-ink-faint mb-1.5 uppercase tracking-wide text-[10px]">Arithmetic reconciliation</div>
          <div className="space-y-1">{d.reconciliation.map((c: any, i: number) => (
            <div key={i} className="flex items-center gap-2"><Tick ok={c.ok} /><span className="text-ink-soft flex-1">{c.name}</span><span className="text-ink-ghost font-mono text-[10px] tnum">{c.detail}</span></div>))}</div>
        </div>}
      </div>
    );
  }
  if (stage.stage === 7 && d.candidates?.length > 0) {
    return (
      <div className="space-y-0.5">
        <Row k="matched PO" v={d.po} /><Row k="inferred" v={String(d.inferred)} />
        <div className="font-semibold text-ink-faint mt-2 mb-1 uppercase tracking-wide text-[10px]">Candidates</div>
        {d.candidates.map((c: any) => (
          <div key={c.po_number} className="flex justify-between"><span className="font-mono text-ink-soft">{c.po_number}</span><span className="font-mono text-ink-ghost tnum">score {c.score} · rem {c.remaining}</span></div>))}
      </div>
    );
  }
  if (stage.stage === 8 && d.rows?.length > 0) return <PoTable rows={d.rows} compact />;
  if (stage.stage === 9 && stage.codes) {
    return <div className="space-y-1.5">{stage.codes.map((c) => (
      <div key={c.code} className="flex items-center gap-2">
        <span className={cx("chip !px-1.5 !py-0.5 !text-[9px] uppercase", c.outcome === "REJECT" ? "bg-reject-soft text-reject-ink" : c.outcome === "HOLD" ? "bg-hold-soft text-hold-ink" : "bg-approve-soft text-approve-ink")}>{c.outcome}</span>
        <span className="font-mono text-ink-soft text-[11px]">{c.code}</span>
      </div>))}</div>;
  }
  return <div className="space-y-0.5">{Object.entries(d).filter(([k]) => !["rows", "candidates", "grounding", "reconciliation", "fields"].includes(k)).map(([k, v]) => <Row key={k} k={k} v={typeof v === "object" ? JSON.stringify(v) : v} />)}</div>;
}

function PoTable({ rows, compact = false }: { rows: any[]; compact?: boolean }) {
  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-[11.5px]">
        <thead>
          <tr className="text-ink-ghost text-left">
            <th className="font-medium py-1 px-1">Line</th><th className="font-medium">Inv</th><th className="font-medium">PO</th>
            {!compact && <th className="font-medium">Recv</th>}<th className="font-medium">Δ%</th><th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line">
              <td className="py-1.5 px-1 pr-2 text-ink-soft">{r.description}</td>
              <td className="font-mono text-ink-soft tnum whitespace-nowrap">{r.inv_qty}×{r.inv_unit}</td>
              <td className="font-mono text-ink-faint tnum whitespace-nowrap">{r.po_qty ?? "—"}×{r.po_unit ?? "—"}</td>
              {!compact && <td className="font-mono text-ink-faint tnum">{r.received ?? "—"}</td>}
              <td className={cx("font-mono tnum", r.status === "fail" ? "text-reject font-semibold" : "text-ink-faint")}>{r.variance_pct ?? "—"}</td>
              <td><span className={r.status === "ok" ? "text-approve" : r.status === "warn" ? "text-hold" : "text-reject"}>{r.status === "ok" ? "✓" : r.status === "warn" ? "!" : "✕"}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DecisionCard({ result, cost, elapsed }: { result: RunResult; cost: number | null; elapsed: number }) {
  const [copied, setCopied] = useState(false);
  const info = result.codes.filter((c) => c.outcome === "INFO");
  const flags = result.codes.filter((c) => c.outcome !== "INFO");
  return (
    <Card className="!shadow-md overflow-hidden animate-fade-up">
      {/* header band */}
      <div className="relative p-5 border-b border-line bg-surface-2">
        <div className="flex items-center justify-between">
          <DecisionBadge decision={result.decision} size="lg" />
          {result.routing && <span className="chip bg-ink/[0.05] text-ink-soft ring-1 ring-line">→ {result.routing}</span>}
        </div>
        <div className="mt-3.5 flex items-end justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[28px] leading-none font-bold text-ink tnum">{money(result.amount, result.currency)}</div>
            <div className="text-[13px] text-ink-faint mt-1.5 truncate">{result.vendor?.name} · <span className="font-mono">{result.invoice_number}</span></div>
          </div>
          <div className="flex items-center gap-3 text-[11px] text-ink-faint shrink-0">
            <span className="inline-flex items-center gap-1 tnum"><IconClock size={12} />{(elapsed / 1000).toFixed(1)}s</span>
            {cost != null && <span className="inline-flex items-center gap-1 tnum"><IconDollar size={12} />{cost}</span>}
          </div>
        </div>
      </div>

      <div className="p-5 space-y-4">
        <p className="text-[13.5px] leading-relaxed text-ink-soft bg-brand-soft/50 rounded-xl p-3.5 border border-brand-100">{result.explanation}</p>

        <div className="space-y-2">
          {flags.map((c) => (
            <div key={c.code} className="rounded-xl border border-line p-3 hover:border-line-strong transition-colors">
              <div className="flex items-center gap-2">
                <SeverityTag severity={c.severity} />
                <span className="font-mono text-[11.5px] font-semibold text-ink">{c.code}</span>
                <span className="ml-auto text-[10.5px] text-ink-faint">{c.routing_label}</span>
              </div>
              <div className="text-[12.5px] text-ink-soft mt-1.5">{c.message}</div>
              {c.evidence && <div className="text-[10.5px] text-ink-ghost mt-1.5 font-mono break-all bg-ink/[0.03] rounded px-2 py-1">{c.evidence}</div>}
            </div>
          ))}
          {info.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-0.5">
              {info.map((c) => (
                <span key={c.code} className="chip bg-approve-soft text-approve-ink ring-1 ring-approve-ring !py-0.5" title={c.message}>
                  <IconCheck size={12} strokeWidth={3} /> {c.code}
                </span>))}
            </div>
          )}
        </div>

        {result.po_table?.length > 0 && (
          <div>
            <SectionLabel className="mb-1.5">Invoice vs PO</SectionLabel>
            <div className="rounded-xl border border-line p-2.5"><PoTable rows={result.po_table} /></div>
          </div>
        )}

        {result.vendor_email && (
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <SectionLabel>Vendor email · draft</SectionLabel>
              <button onClick={() => { navigator.clipboard?.writeText(result.vendor_email!); setCopied(true); setTimeout(() => setCopied(false), 1200); }}
                className="inline-flex items-center gap-1 text-[12px] text-brand-600 font-semibold hover:text-brand-700">
                {copied ? <><IconCheck size={13} /> Copied</> : <><IconCopy size={13} /> Copy</>}
              </button>
            </div>
            <pre className="whitespace-pre-wrap text-[11.5px] leading-relaxed text-ink-soft bg-surface-2 rounded-xl p-3.5 border border-line max-h-48 overflow-auto font-sans">{result.vendor_email}</pre>
          </div>
        )}

        {result.posting && (
          <details className="group">
            <summary className="flex items-center gap-1.5 cursor-pointer list-none">
              <IconChevronDown size={14} className="text-ink-ghost transition-transform group-open:rotate-180" />
              <SectionLabel>ERP posting · on approve</SectionLabel>
            </summary>
            <pre className="text-[10.5px] text-slate-200 bg-ink rounded-xl p-3.5 mt-2 overflow-auto max-h-56 font-mono leading-relaxed">{JSON.stringify(result.posting, null, 2)}</pre>
          </details>
        )}
      </div>
    </Card>
  );
}
