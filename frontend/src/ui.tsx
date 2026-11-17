import React from "react";
import { IconCheck, IconAlert, IconX, IconShield, IconClock } from "./icons";

export function cx(...a: (string | false | null | undefined)[]) {
  return a.filter(Boolean).join(" ");
}

export function money(amount?: string | number | null, currency?: string | null) {
  if (amount === null || amount === undefined || amount === "") return "—";
  const n = typeof amount === "string" ? parseFloat(amount) : amount;
  if (isNaN(n as number)) return String(amount);
  return `${currency ? currency + " " : ""}${(n as number).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
}

export const DECISION: Record<string, { label: string; Icon: any; bg: string; text: string; ring: string; dot: string; grad: string }> = {
  APPROVE: { label: "Approved", Icon: IconCheck, bg: "bg-approve-soft", text: "text-approve-ink", ring: "ring-approve-ring", dot: "bg-approve", grad: "from-emerald-500 to-teal-500" },
  HOLD: { label: "On hold", Icon: IconClock, bg: "bg-hold-soft", text: "text-hold-ink", ring: "ring-hold-ring", dot: "bg-hold", grad: "from-amber-500 to-orange-500" },
  REJECT: { label: "Rejected", Icon: IconX, bg: "bg-reject-soft", text: "text-reject-ink", ring: "ring-reject-ring", dot: "bg-reject", grad: "from-rose-500 to-red-500" },
  APPROVE_OVERRIDE: { label: "Approved (override)", Icon: IconCheck, bg: "bg-approve-soft", text: "text-approve-ink", ring: "ring-approve-ring", dot: "bg-approve", grad: "from-emerald-500 to-teal-500" },
  REJECT_OVERRIDE: { label: "Rejected (override)", Icon: IconX, bg: "bg-reject-soft", text: "text-reject-ink", ring: "ring-reject-ring", dot: "bg-reject", grad: "from-rose-500 to-red-500" },
};

export const SEV: Record<string, { tag: string; label: string }> = {
  high: { tag: "bg-reject-soft text-reject-ink ring-1 ring-reject-ring", label: "High" },
  medium: { tag: "bg-hold-soft text-hold-ink ring-1 ring-hold-ring", label: "Medium" },
  low: { tag: "bg-ink/[0.05] text-ink-soft ring-1 ring-line", label: "Low" },
};

export function Card({ children, className = "", hover = false, ...rest }: any) {
  return (
    <div className={cx("card", hover && "transition-all duration-200 ease-spring hover:shadow-md hover:-translate-y-0.5", className)} {...rest}>
      {children}
    </div>
  );
}

export function Button({ variant = "primary", className = "", children, ...rest }: any) {
  const v: Record<string, string> = {
    primary: "btn-primary", ghost: "btn-ghost", soft: "btn-soft", dark: "btn-dark",
    approve: "btn bg-approve text-white px-3.5 py-2 shadow-sm hover:brightness-95 active:scale-[0.98]",
    reject: "btn bg-reject text-white px-3.5 py-2 shadow-sm hover:brightness-95 active:scale-[0.98]",
  };
  return <button className={cx(v[variant], className)} {...rest}>{children}</button>;
}

export function Chip({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <span className={cx("chip", className)}>{children}</span>;
}

export function DecisionBadge({ decision, size = "sm" }: { decision: string; size?: "sm" | "lg" }) {
  const d = DECISION[decision] || DECISION.HOLD;
  const Icon = d.Icon;
  const lg = size === "lg";
  return (
    <span className={cx("inline-flex items-center gap-2 rounded-full font-semibold ring-1 whitespace-nowrap shrink-0", d.bg, d.text, d.ring,
      lg ? "px-3.5 py-1.5 text-sm" : "px-2.5 py-1 text-xs")}>
      <Icon size={lg ? 16 : 13} strokeWidth={2.5} />
      {d.label}
    </span>
  );
}

const EXPECTED_LABEL: Record<string, string> = { APPROVE: "Approve", HOLD: "Hold", REJECT: "Reject" };
/** For UNprocessed samples: shows the engineered target outcome, visually distinct from a real decision. */
export function ExpectedBadge({ decision }: { decision: string }) {
  const d = DECISION[decision] || DECISION.HOLD;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-[11px] font-semibold text-ink-soft whitespace-nowrap shrink-0 shadow-xs"
      title="Engineered to reach this decision">
      <span className={cx("h-1.5 w-1.5 rounded-full", d.dot)} />
      <span className="text-ink-faint font-medium">expects</span>
      {EXPECTED_LABEL[decision] || decision}
    </span>
  );
}

export function SeverityTag({ severity }: { severity: string }) {
  const s = SEV[severity] || SEV.low;
  return <span className={cx("chip !px-2 !py-0.5 !text-[10px] uppercase tracking-wide", s.tag)}>{s.label}</span>;
}

/** Stage status glyph used in the pipeline stepper. */
export function StatusGlyph({ status, index }: { status: string; index: number }) {
  const base = "relative z-10 flex items-center justify-center rounded-full shrink-0 transition-all duration-300 ease-spring";
  if (status === "pass")
    return <span className={cx(base, "w-8 h-8 bg-approve text-white shadow-sm")}><IconCheck size={16} strokeWidth={2.75} /></span>;
  if (status === "warn")
    return <span className={cx(base, "w-8 h-8 bg-hold text-white shadow-sm")}><IconAlert size={15} strokeWidth={2.5} /></span>;
  if (status === "fail")
    return <span className={cx(base, "w-8 h-8 bg-reject text-white shadow-sm")}><IconX size={15} strokeWidth={3} /></span>;
  if (status === "running")
    return <span className={cx(base, "w-8 h-8 bg-brand text-white animate-pulse-ring")}><span className="w-2 h-2 rounded-full bg-white animate-ping" /></span>;
  return <span className={cx(base, "w-8 h-8 bg-ink/[0.06] text-ink-ghost text-xs font-semibold tnum")}>{index}</span>;
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={cx("skeleton", className)} />;
}

export function EmptyState({ icon, title, hint }: { icon?: React.ReactNode; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-14 px-6">
      {icon && <div className="w-12 h-12 rounded-2xl bg-brand-soft text-brand-600 flex items-center justify-center mb-3 ring-1 ring-brand-100">{icon}</div>}
      <div className="text-sm font-semibold text-ink">{title}</div>
      {hint && <div className="text-sm text-ink-faint mt-1 max-w-xs">{hint}</div>}
    </div>
  );
}

export function Stat({ label, value, sub, icon, accent }: { label: string; value: React.ReactNode; sub?: string; icon?: React.ReactNode; accent?: boolean }) {
  return (
    <Card className="p-4 sm:p-5 relative overflow-hidden group">
      {accent && <div className="absolute -top-8 -right-8 w-24 h-24 rounded-full bg-brand/[0.07] blur-2xl" />}
      <div className="flex items-start justify-between relative">
        <div className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-faint">{label}</div>
        {icon && <div className="text-ink-ghost group-hover:text-brand-500 transition-colors">{icon}</div>}
      </div>
      <div className="mt-2 text-[26px] leading-none font-bold text-ink tnum">{value}</div>
      {sub && <div className="text-xs text-ink-faint mt-1.5">{sub}</div>}
    </Card>
  );
}

export function SectionLabel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={cx("text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint", className)}>{children}</div>;
}

export function Page({ children, className = "", wide = false }: { children: React.ReactNode; className?: string; wide?: boolean }) {
  return (
    <div className={cx("px-5 sm:px-8 py-7 sm:py-9 mx-auto animate-fade-in", wide ? "max-w-[1400px]" : "max-w-6xl", className)}>
      {children}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: string; subtitle?: string; actions?: React.ReactNode; eyebrow?: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-7">
      <div className="min-w-0">
        {eyebrow && <div className="mb-2">{eyebrow}</div>}
        <h1 className="text-[26px] sm:text-[30px] font-bold text-ink tracking-tight leading-tight">{title}</h1>
        {subtitle && <p className="text-ink-faint mt-1.5 text-[15px] max-w-2xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}
