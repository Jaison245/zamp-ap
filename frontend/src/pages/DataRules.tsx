import React, { useEffect, useState } from "react";
import { api } from "../api";
import { Card, money, Page, PageHeader, Button, SectionLabel, Skeleton, cx } from "../ui";
import { IconRefresh, IconCheck, IconBuilding, IconSliders, Spinner } from "../icons";

const TOL_FIELDS: [string, string, boolean][] = [
  ["line_price_pct", "Line price", true],
  ["invoice_total_pct", "Invoice total", true],
  ["invoice_total_abs", "Invoice total (abs $)", false],
  ["cumulative_po_pct", "Cumulative PO", true],
];
const VSTATUS: Record<string, string> = {
  active: "bg-approve-soft text-approve-ink ring-approve-ring",
  blocked: "bg-reject-soft text-reject-ink ring-reject-ring",
  pending: "bg-hold-soft text-hold-ink ring-hold-ring",
};
const POSTATUS: Record<string, string> = {
  open: "bg-approve-soft text-approve-ink ring-approve-ring",
  partially_billed: "bg-hold-soft text-hold-ink ring-hold-ring",
  closed: "bg-ink/[0.05] text-ink-faint ring-line",
  cancelled: "bg-ink/[0.05] text-ink-faint ring-line",
};

export default function DataRules({ onReset }: { onReset: () => void }) {
  const [data, setData] = useState<any>(null);
  const [rules, setRules] = useState<any>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const load = () => { api.data().then(setData); api.getRules().then(setRules); };
  useEffect(() => { load(); }, []);

  async function saveRules() {
    setSaving(true);
    try { await api.putRules(rules); setSaved(true); setTimeout(() => setSaved(false), 1600); } finally { setSaving(false); }
  }
  async function doReset() {
    setResetting(true);
    try { await api.reset(); load(); onReset(); } finally { setResetting(false); }
  }
  const setTol = (key: string, val: string) => setRules({ ...rules, tolerances: { ...rules.tolerances, [key]: parseFloat(val) } });

  return (
    <Page wide>
      <PageHeader
        title="Data & rules"
        subtitle="The master data the engine checks against, and the policy knobs you can tune live."
        actions={<Button variant="dark" onClick={doReset} disabled={resetting}>{resetting ? <><Spinner size={15} /> Resetting</> : <><IconRefresh size={16} /> Reset demo data</>}</Button>}
      />

      {!data || !rules ? (
        <Card className="p-6"><Skeleton className="h-24 w-full" /></Card>
      ) : (
        <div className="space-y-5">
          {/* tolerances */}
          <Card className="p-5">
            <div className="flex items-start justify-between gap-4 mb-4">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-xl bg-brand-soft text-brand-600 flex items-center justify-center ring-1 ring-brand-100"><IconSliders size={18} /></div>
                <div>
                  <div className="font-semibold text-ink text-[15px]">Tolerance policy</div>
                  <div className="text-[12.5px] text-ink-faint">Editable live — re-run the same invoice to watch a decision flip.</div>
                </div>
              </div>
              <Button onClick={saveRules} disabled={saving} className="shrink-0">
                {saving ? <Spinner size={15} /> : saved ? <IconCheck size={16} strokeWidth={2.5} /> : null}{saved ? "Saved" : "Save"}
              </Button>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {TOL_FIELDS.map(([key, label, isPct]) => (
                <div key={key} className="rounded-xl border border-line bg-surface-2 p-3">
                  <label className="text-[11px] font-medium text-ink-faint">{label}</label>
                  <div className="flex items-baseline gap-2 mt-1.5">
                    <input type="number" step="0.005" value={rules.tolerances[key]} onChange={(e) => setTol(key, e.target.value)}
                      className="w-full bg-transparent text-lg font-bold text-ink tnum focus:outline-none" />
                    {isPct && <span className="text-[12px] font-semibold text-brand-600 tnum shrink-0">{(rules.tolerances[key] * 100).toFixed(1)}%</span>}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-2 text-[12px] text-ink-faint bg-brand-soft/50 rounded-lg px-3 py-2 border border-brand-100">
              <span className="text-brand-600 font-semibold">Tip</span> Set line price to 0.005 (0.5%) and re-run <span className="font-mono text-ink-soft">INV-ACME-001</span> → it flips APPROVE → HOLD.
            </div>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* vendors */}
            <Card className="overflow-hidden">
              <div className="px-5 py-3.5 border-b border-line flex items-center gap-2"><IconBuilding size={16} className="text-ink-faint" /><SectionLabel>Vendors</SectionLabel></div>
              <div className="divide-y divide-line max-h-[26rem] overflow-y-auto">
                {data.vendors.map((v: any) => (
                  <div key={v.vendor_id} className="px-5 py-3 flex items-center gap-3 hover:bg-surface-2 transition-colors">
                    <div className="w-9 h-9 rounded-xl bg-brand-soft text-brand-700 flex items-center justify-center font-bold text-[13px] shrink-0 ring-1 ring-brand-100">
                      {v.legal_name.slice(0, 2).toUpperCase()}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold text-ink text-[13.5px] truncate">{v.legal_name}</div>
                      <div className="text-[11px] text-ink-faint truncate">{v.country} · {v.currency}{v.aliases ? ` · aka ${v.aliases.split("|")[0]}` : ""}</div>
                    </div>
                    <span className={cx("chip !py-0.5 ring-1 capitalize shrink-0", VSTATUS[v.status])}>{v.status}</span>
                  </div>
                ))}
              </div>
            </Card>

            {/* POs */}
            <Card className="overflow-hidden">
              <div className="px-5 py-3.5 border-b border-line flex items-center gap-2"><IconSliders size={16} className="text-ink-faint" /><SectionLabel>Purchase orders · billed vs remaining</SectionLabel></div>
              <div className="divide-y divide-line max-h-[26rem] overflow-y-auto">
                {data.purchase_orders.map((p: any) => {
                  const pct = p.total ? Math.min(100, Math.max(0, (p.billed / p.total) * 100)) : 0;
                  const over = p.remaining < 0;
                  return (
                    <div key={p.po_number} className="px-5 py-3 hover:bg-surface-2 transition-colors">
                      <div className="flex items-center justify-between gap-2">
                        <div className="font-mono text-[13px] font-semibold text-ink">{p.po_number} <span className="text-ink-ghost font-sans font-normal">· {p.vendor_id}</span></div>
                        <span className={cx("chip !py-0.5 ring-1 shrink-0", POSTATUS[p.status])}>{p.status.replace("_", " ")}</span>
                      </div>
                      <div className="mt-2 h-1.5 rounded-full bg-ink/[0.06] overflow-hidden">
                        <div className={cx("h-full rounded-full transition-all duration-500", over ? "bg-reject" : "bg-brand-gradient")} style={{ width: `${pct}%` }} />
                      </div>
                      <div className="flex justify-between mt-1.5 text-[11px] tnum">
                        <span className="text-ink-faint">billed <span className="text-ink-soft font-medium font-mono">{money(p.billed, p.currency)}</span></span>
                        <span className={cx(over ? "text-reject font-medium" : "text-ink-faint")}>remaining <span className="font-mono">{money(p.remaining, p.currency)}</span></span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          </div>
        </div>
      )}
    </Page>
  );
}
