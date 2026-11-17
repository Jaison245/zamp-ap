import React, { useEffect, useState } from "react";
import { api } from "../api";
import { Card, money, Page, PageHeader, Button, EmptyState, SeverityTag, cx } from "../ui";
import { IconRefresh, IconReview, IconCheck, IconArrowRight, Spinner } from "../icons";

export default function Review({ onOpen }: { onOpen: (id: number) => void }) {
  const [items, setItems] = useState<any[] | null>(null);
  const [comment, setComment] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const load = () => { api.review().then(setItems); };
  useEffect(() => { load(); }, []);

  async function act(id: number, action: string) {
    setBusy(id);
    try { await api.reviewAction(id, action, comment[id] || ""); await load(); } finally { setBusy(null); }
  }

  return (
    <Page>
      <PageHeader
        title="Review queue"
        subtitle="Exceptions the engine held for a human. Every override is written to the audit trail."
        actions={<button onClick={load} className="btn-soft !py-2 !px-3"><IconRefresh size={16} /> Refresh</button>}
      />

      {!items ? (
        <Card className="p-6"><div className="skeleton h-20 w-full rounded-xl" /></Card>
      ) : items.length === 0 ? (
        <Card><EmptyState icon={<IconCheck size={24} />} title="Queue is clear" hint="No invoices are waiting for review right now." /></Card>
      ) : (
        <div className="space-y-4">
          {items.map((it, i) => (
            <Card key={it.id} className="p-5 animate-fade-up" style={{ animationDelay: `${i * 50}ms` }}>
              <div className="flex items-start justify-between gap-3">
                <button onClick={() => onOpen(it.id)} className="text-left group min-w-0">
                  <div className="font-semibold text-ink group-hover:text-brand-600 transition-colors inline-flex items-center gap-1.5">
                    {it.vendor} · <span className="font-mono text-[14px]">{it.invoice_number}</span>
                    <IconArrowRight size={14} className="text-ink-ghost opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                  <div className="text-[13px] text-ink-faint mt-0.5">{money(it.amount, it.currency)} · route to {it.routing || "AP clerk"}</div>
                </button>
                <span className="chip bg-ink/[0.05] text-ink-faint ring-1 ring-line tnum shrink-0">#{it.id}</span>
              </div>

              <div className="flex flex-wrap items-center gap-1.5 mt-3">
                {(it.codes || []).filter((c: any) => c.outcome !== "INFO").map((c: any) => (
                  <span key={c.code} className="inline-flex items-center gap-1.5">
                    <SeverityTag severity={c.severity} />
                    <span className="font-mono text-[11px] text-ink-soft">{c.code}</span>
                  </span>
                ))}
              </div>

              <p className="text-[13.5px] text-ink-soft mt-3 leading-relaxed">{it.explanation}</p>

              <div className="mt-4 flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                <input value={comment[it.id] || ""} onChange={(e) => setComment({ ...comment, [it.id]: e.target.value })}
                  placeholder="Add a comment (logged to audit trail)…" className="input flex-1" />
                <div className="flex items-center gap-2">
                  <Button variant="approve" disabled={busy === it.id} onClick={() => act(it.id, "approve")}>
                    {busy === it.id ? <Spinner size={15} /> : <IconCheck size={15} strokeWidth={2.5} />} Approve
                  </Button>
                  <Button variant="reject" disabled={busy === it.id} onClick={() => act(it.id, "reject")}>Reject</Button>
                  <Button variant="soft" disabled={busy === it.id} onClick={() => act(it.id, "request_info")}>Request info</Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </Page>
  );
}
