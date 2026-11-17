import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Card, ExpectedBadge, money, Page, SectionLabel, Skeleton, cx } from "../ui";
import { IconUpload, IconFile, IconScan, IconArrowRight, IconSparkle, IconShield, IconLayers, IconFingerprint, IconCheck, IconZap, Spinner } from "../icons";

const STATS = [
  { v: "11", l: "pipeline stages" },
  { v: "100%", l: "eval decision accuracy" },
  { v: "~1s", l: "to a decision" },
];

const TAG_COLOR: Record<string, string> = {
  happy_path: "bg-approve-soft text-approve-ink ring-approve-ring",
  tolerance: "bg-brand-50 text-brand-700 ring-brand-100",
  split_billing: "bg-sky-50 text-sky-700 ring-sky-100",
  overrun: "bg-reject-soft text-reject-ink ring-reject-ring",
  scanned: "bg-violet-50 text-violet-700 ring-violet-100",
  implied_PO: "bg-hold-soft text-hold-ink ring-hold-ring",
  duplicate: "bg-orange-50 text-orange-700 ring-orange-100",
  fraud: "bg-reject-soft text-reject-ink ring-reject-ring",
  bank_change: "bg-reject-soft text-reject-ink ring-reject-ring",
  injection: "bg-reject-soft text-reject-ink ring-reject-ring",
  blocked_vendor: "bg-reject-soft text-reject-ink ring-reject-ring",
  not_an_invoice: "bg-ink/[0.05] text-ink-soft ring-line",
};
const tags = (t: string) => t.split(/[/+]/).map((x) => x.trim().replace(/\s+/g, "_")).filter(Boolean);

export default function NewRun({ onStart }: { onStart: (id: number) => void }) {
  const [samples, setSamples] = useState<any[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { api.samples().then(setSamples).catch(() => setSamples([])); }, []);

  async function runSample(id: string) {
    setBusy(id);
    try { const { run_id } = await api.createRunSample(id); onStart(run_id); } finally { setBusy(null); }
  }
  async function runUpload(file: File) {
    setBusy("upload");
    try { const { run_id } = await api.createRunUpload(file); onStart(run_id); } finally { setBusy(null); }
  }

  return (
    <Page>
      {/* HERO — also the drag-drop target */}
      <div
        className={cx("relative overflow-hidden rounded-3xl text-white mb-9 border shadow-xl transition-all duration-200 ease-spring",
          drag ? "border-fuchsia2/60 ring-2 ring-fuchsia2/40 scale-[1.004]" : "border-white/10")}
        style={{ background: "linear-gradient(180deg,#171327 0%,#0d0b1a 100%)" }}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDrag(false); }}
        onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) runUpload(f); }}
      >
        <div className="absolute inset-0 bg-aurora" />
        <div className="absolute inset-0 bg-grid [background-size:26px_26px] opacity-[0.12]" />
        <div className="pointer-events-none absolute -top-24 -right-10 w-80 h-80 rounded-full bg-fuchsia2/20 blur-3xl animate-float" />
        {drag && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 bg-[#0d0b1a]/80 backdrop-blur-sm">
            <IconUpload size={30} className="text-fuchsia-300" />
            <span className="font-semibold">Drop to process</span>
          </div>
        )}

        <div className="relative px-6 sm:px-10 py-9 sm:py-12 grid lg:grid-cols-[1.35fr_1fr] gap-8 lg:gap-6 items-center">
          <div>
            <div className="inline-flex items-center gap-1.5 rounded-full bg-white/10 text-violet-100 ring-1 ring-white/15 px-2.5 py-1 text-[11px] font-semibold backdrop-blur mb-4">
              <IconSparkle size={13} /> Autonomous accounts-payable · powered by Claude
            </div>
            <h1 className="text-[32px] sm:text-[44px] font-bold leading-[1.04] tracking-tight">
              From messy invoice<br className="hidden sm:block" /> to <span className="text-gradient-anim animate-gradient-pan">audited decision</span>
            </h1>
            <p className="text-slate-300/90 mt-4 text-[15px] sm:text-base max-w-xl leading-relaxed">
              Claude reads any PDF — digital or scanned. Deterministic code does the math and makes the call: approve, hold or reject. Every number grounded, every decision explained.
            </p>

            <div className="flex flex-wrap gap-3 mt-7">
              <button disabled={!samples?.length || !!busy} onClick={() => samples && runSample(samples[0].id)}
                className="btn bg-white text-ink px-5 py-3 shadow-lg hover:shadow-xl hover:-translate-y-0.5 active:translate-y-0 disabled:opacity-50">
                {busy === samples?.[0]?.id ? <Spinner size={16} /> : <IconZap size={17} className="text-brand-600" />} Run the live demo
              </button>
              <button disabled={!!busy} onClick={() => fileRef.current?.click()}
                className="btn bg-white/10 text-white ring-1 ring-white/20 px-5 py-3 backdrop-blur hover:bg-white/15">
                <IconUpload size={17} /> Upload a PDF
              </button>
            </div>

            <div className="flex flex-wrap gap-x-8 gap-y-3 mt-8 pt-6 border-t border-white/10">
              {STATS.map((s) => (
                <div key={s.l}>
                  <div className="text-xl font-bold tnum leading-none">{s.v}</div>
                  <div className="text-[11.5px] text-slate-400 mt-1">{s.l}</div>
                </div>
              ))}
            </div>
          </div>

          {/* floating decision preview */}
          <div className="relative hidden lg:flex justify-center items-center">
            <div className="pointer-events-none absolute w-64 h-64 rounded-full bg-brand-500/20 blur-3xl" />
            <div className="relative w-full max-w-[310px] rounded-2xl bg-white/[0.07] border border-white/15 backdrop-blur-xl p-4 shadow-2xl rotate-[1.5deg] animate-float">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-400/15 text-emerald-300 ring-1 ring-emerald-400/30 px-2.5 py-1 text-[11px] font-semibold">
                  <IconCheck size={13} strokeWidth={3} /> Approved
                </span>
                <span className="text-[10px] text-slate-400 tnum">1.1s · $0.00</span>
              </div>
              <div className="mt-3 text-2xl font-bold tnum">GBP 14,544.00</div>
              <div className="text-[12px] text-slate-400">Acme Supplies Ltd · <span className="font-mono">INV-ACME-001</span></div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {["PRICE_WITHIN_TOLERANCE", "3-WAY MATCHED"].map((c) => (
                  <span key={c} className="rounded-md bg-emerald-400/10 text-emerald-300 ring-1 ring-emerald-400/20 px-1.5 py-0.5 text-[10px] font-semibold font-mono">{c}</span>
                ))}
              </div>
              <div className="mt-4 pt-3 border-t border-white/10 flex items-center gap-[3px]">
                {Array.from({ length: 11 }).map((_, i) => (
                  <span key={i} className={cx("h-1.5 flex-1 rounded-full", i < 10 ? "bg-emerald-400/70" : "bg-brand-400/70")} />
                ))}
                <span className="ml-2 text-[10px] text-slate-400 shrink-0">11/11</span>
              </div>
            </div>
          </div>
        </div>
        <input ref={fileRef} type="file" accept="application/pdf" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) runUpload(f); }} />
      </div>

      <div className="flex items-end justify-between mb-4">
        <div>
          <SectionLabel>Sample invoices</SectionLabel>
          <p className="text-[12.5px] text-ink-faint mt-1">Each is engineered to exercise a specific decision path — the badge shows its expected outcome.</p>
        </div>
        <span className="chip bg-ink/[0.04] text-ink-faint ring-1 ring-line shrink-0">{samples ? `${samples.length} scenarios` : ""}</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {!samples && Array.from({ length: 6 }).map((_, i) => (
          <Card key={i} className="p-5"><Skeleton className="h-5 w-32" /><Skeleton className="h-4 w-24 mt-2" /><Skeleton className="h-6 w-full mt-4" /><Skeleton className="h-8 w-full mt-4" /></Card>
        ))}
        {samples?.map((s, i) => {
          const scanned = s.kind === "scanned";
          return (
            <Card key={s.id} hover className="p-5 flex flex-col animate-fade-up" style={{ animationDelay: `${i * 40}ms` }}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-start gap-3 min-w-0">
                  <div className={cx("w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ring-1",
                    scanned ? "bg-violet-50 text-violet-600 ring-violet-100" : "bg-brand-soft text-brand-600 ring-brand-100")}>
                    {scanned ? <IconScan size={18} /> : <IconFile size={18} />}
                  </div>
                  <div className="min-w-0">
                    <div className="font-semibold text-ink text-[15px] truncate">{s.id}</div>
                    <div className="text-[13px] text-ink-faint truncate">{s.vendor}</div>
                  </div>
                </div>
                <ExpectedBadge decision={s.expected_decision} />
              </div>

              <div className="flex flex-wrap gap-1.5 mt-3.5">
                <span className={cx("chip !py-0.5 ring-1", scanned ? "bg-violet-50 text-violet-700 ring-violet-100" : "bg-ink/[0.05] text-ink-soft ring-line")}>{s.kind}</span>
                {tags(s.tag).map((t) => (
                  <span key={t} className={cx("chip !py-0.5 ring-1", TAG_COLOR[t] || "bg-ink/[0.05] text-ink-soft ring-line")}>{t}</span>
                ))}
              </div>

              <div className="flex items-center justify-between mt-4 pt-3.5 border-t border-line">
                <span className="font-mono text-[13px] font-medium text-ink-soft tnum">{money(s.total, s.currency)}</span>
                <button disabled={!!busy} onClick={() => runSample(s.id)}
                  className="btn-primary !px-3.5 !py-2 !text-[13px] group/btn">
                  {busy === s.id ? <Spinner size={15} /> : <>Process <IconArrowRight size={15} className="transition-transform group-hover/btn:translate-x-0.5" /></>}
                </button>
              </div>
            </Card>
          );
        })}
      </div>
    </Page>
  );
}
