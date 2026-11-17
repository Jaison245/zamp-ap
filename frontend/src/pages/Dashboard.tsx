import React, { useEffect, useState } from "react";
import { api } from "../api";
import { Card, DecisionBadge, money, Page, PageHeader, Stat, SectionLabel, Skeleton, EmptyState, cx } from "../ui";
import { IconRefresh, IconZap, IconTrend, IconClock, IconDollar, IconReceipt, IconLayers, IconArrowRight } from "../icons";

const MIX = { APPROVE: { c: "bg-approve", t: "Approved" }, HOLD: { c: "bg-hold", t: "Held" }, REJECT: { c: "bg-reject", t: "Rejected" } } as const;
const REJECT_CODES = new Set(["NOT_AN_INVOICE", "VENDOR_BLOCKED", "DUPLICATE_INVOICE", "WRONG_ADDRESSEE", "DUPLICATE_FILE"]);

export default function Dashboard({ onOpen }: { onOpen: (id: number) => void }) {
  const [kpi, setKpi] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const load = () => { api.dashboard().then(setKpi); api.listRuns().then(setRuns); };
  useEffect(load, []);

  const done = runs.filter((r) => r.status === "done");

  return (
    <Page wide>
      <PageHeader
        title="Dashboard"
        subtitle="Throughput, decision mix and the exceptions that actually need a human."
        actions={<button onClick={load} className="btn-soft !py-2 !px-3"><IconRefresh size={16} /> Refresh</button>}
      />

      {!kpi ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">{Array.from({ length: 4 }).map((_, i) => <Card key={i} className="p-5"><Skeleton className="h-3 w-20" /><Skeleton className="h-7 w-16 mt-3" /></Card>)}</div>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Stat accent label="Processed" value={kpi.total_processed} sub="invoices run" icon={<IconReceipt size={18} />} />
            <Stat label="Auto-approval" value={`${kpi.auto_approval_rate}%`} sub={`${kpi.decision_mix.APPROVE || 0} approved straight through`} icon={<IconZap size={18} />} />
            <Stat label="Needs review" value={kpi.on_hold} sub="held for a human" icon={<IconLayers size={18} />} />
            <Stat label="Approved value" value={money(kpi.total_value)} sub="posted to AP" icon={<IconTrend size={18} />} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mt-5">
            {/* decision mix + speed */}
            <Card className="p-5 lg:col-span-1">
              <SectionLabel>Decision mix</SectionLabel>
              <div className="flex h-3 rounded-full overflow-hidden bg-ink/[0.05] mt-3">
                {(["APPROVE", "HOLD", "REJECT"] as const).map((k) => {
                  const v = kpi.decision_mix[k] || 0;
                  const pct = kpi.total_processed ? (v / kpi.total_processed) * 100 : 0;
                  return v ? <div key={k} className={cx(MIX[k].c, "transition-all duration-500")} style={{ width: `${pct}%` }} title={`${k}: ${v}`} /> : null;
                })}
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-2 mt-3.5">
                {(["APPROVE", "HOLD", "REJECT"] as const).map((k) => (
                  <span key={k} className="flex items-center gap-1.5 text-[12.5px]">
                    <span className={cx("w-2.5 h-2.5 rounded-full", MIX[k].c)} />
                    <span className="text-ink-soft">{MIX[k].t}</span>
                    <span className="font-semibold text-ink tnum">{kpi.decision_mix[k] || 0}</span>
                  </span>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-3 mt-5 pt-4 border-t border-line">
                <div>
                  <div className="flex items-center gap-1.5 text-[11px] text-ink-faint"><IconClock size={13} /> Avg time</div>
                  <div className="text-lg font-bold text-ink tnum mt-0.5">{(kpi.avg_ms / 1000).toFixed(1)}s</div>
                </div>
                <div>
                  <div className="flex items-center gap-1.5 text-[11px] text-ink-faint"><IconDollar size={13} /> Avg cost</div>
                  <div className="text-lg font-bold text-ink tnum mt-0.5">{kpi.total_processed ? `$${(kpi.avg_cost || 0).toFixed(2)}` : "—"}</div>
                </div>
              </div>
            </Card>

            {/* top reasons */}
            <Card className="p-5 lg:col-span-2">
              <SectionLabel>Top hold &amp; reject reasons</SectionLabel>
              {kpi.top_hold_reasons.length === 0 ? (
                <div className="text-[13px] text-ink-faint mt-4">No exceptions yet.</div>
              ) : (
                <div className="space-y-3.5 mt-4">
                  {kpi.top_hold_reasons.map(([code, n]: [string, number], i: number) => {
                    const max = Math.max(1, ...kpi.top_hold_reasons.map((r: any) => r[1]));
                    const isReject = REJECT_CODES.has(code);
                    return (
                      <div key={code} className="flex items-center gap-3">
                        <span className="font-mono text-[11.5px] text-ink-soft w-[150px] shrink-0 truncate" title={code}>{code}</span>
                        <div className="flex-1 h-2.5 rounded-full bg-ink/[0.05] overflow-hidden">
                          <div className={cx("h-full rounded-full origin-left", isReject ? "bg-gradient-to-r from-reject to-rose-400" : "bg-gradient-to-r from-hold to-amber-400")}
                            style={{ width: `${(n / max) * 100}%`, transition: "width .7s cubic-bezier(.22,1,.36,1)", transitionDelay: `${i * 60}ms` }} />
                        </div>
                        <span className="text-[12px] font-semibold text-ink tnum w-4 text-right shrink-0">{n}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </Card>
          </div>

          {/* runs table */}
          <Card className="mt-5 overflow-hidden">
            <div className="px-5 py-3.5 border-b border-line flex items-center justify-between">
              <SectionLabel>Recent runs</SectionLabel>
              <span className="text-[12px] text-ink-faint">{done.length} total</span>
            </div>
            {done.length === 0 ? (
              <EmptyState icon={<IconReceipt size={22} />} title="No runs yet" hint="Process a sample from New run to populate the dashboard." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="text-left text-ink-faint text-[11px] uppercase tracking-wide">
                      <th className="px-5 py-2.5 font-semibold">Vendor</th>
                      <th className="font-semibold">Invoice</th>
                      <th className="font-semibold text-right">Amount</th>
                      <th className="font-semibold">Decision</th>
                      <th className="font-semibold">Top reason</th>
                      <th className="font-semibold text-right pr-5">Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {done.map((r) => (
                      <tr key={r.id} onClick={() => onOpen(r.id)} className="border-t border-line hover:bg-brand-soft/40 cursor-pointer transition-colors group">
                        <td className="px-5 py-3 font-medium text-ink">{r.vendor || "—"}</td>
                        <td className="font-mono text-[12px] text-ink-faint">{r.invoice_number || "—"}</td>
                        <td className="font-mono text-[12px] text-ink-soft tnum text-right">{money(r.amount, r.currency)}</td>
                        <td><DecisionBadge decision={r.decision} /></td>
                        <td className="font-mono text-[11.5px] text-ink-faint">{r.top_reason || "—"}</td>
                        <td className="text-[12px] text-ink-faint tnum text-right pr-5">
                          <span className="inline-flex items-center gap-1.5">
                            {r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : "—"}
                            <IconArrowRight size={14} className="text-ink-ghost opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </Page>
  );
}
