import React, { useEffect, useState } from "react";
import { api } from "./api";
import { cx } from "./ui";
import {
  IconNewRun, IconDashboard, IconReview, IconSliders, IconMenu, IconX, LogoMark, IconGitBranch,
} from "./icons";
import NewRun from "./pages/NewRun";
import LiveRun from "./pages/LiveRun";
import Dashboard from "./pages/Dashboard";
import Review from "./pages/Review";
import DataRules from "./pages/DataRules";

type View = "new" | "live" | "dashboard" | "review" | "data";

const NAV: { key: View; label: string; Icon: any }[] = [
  { key: "new", label: "New run", Icon: IconNewRun },
  { key: "dashboard", label: "Dashboard", Icon: IconDashboard },
  { key: "review", label: "Review queue", Icon: IconReview },
  { key: "data", label: "Data & rules", Icon: IconSliders },
];
const TITLES: Record<View, string> = { new: "New run", live: "Live run", dashboard: "Dashboard", review: "Review queue", data: "Data & rules" };

export default function App() {
  const [view, setView] = useState<View>("new");
  const [runId, setRunId] = useState<number | null>(null);
  const [replay, setReplay] = useState(false);
  const [health, setHealth] = useState<any>(null);
  const [drawer, setDrawer] = useState(false);

  useEffect(() => { api.health().then(setHealth).catch(() => {}); }, []);

  function go(v: View) { setView(v); setDrawer(false); }
  function startRun(id: number) { setRunId(id); setReplay(false); setView("live"); setDrawer(false); }
  function openRun(id: number) { setRunId(id); setReplay(true); setView("live"); setDrawer(false); }

  const Sidebar = (
    <div className="h-full w-[248px] bg-sidebar text-slate-300 flex flex-col relative overflow-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-48 bg-[radial-gradient(75%_60%_at_25%_0%,rgba(168,85,247,0.28),transparent)]" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-[radial-gradient(80%_70%_at_80%_100%,rgba(217,70,239,0.14),transparent)]" />
      <div className="px-5 pt-5 pb-4 relative">
        <div className="flex items-center gap-2.5">
          <LogoMark size={34} />
          <div>
            <div className="text-white font-bold text-[15px] tracking-tight leading-none">Zamp AP</div>
            <div className="text-[11px] text-slate-500 mt-1">Invoice Intelligence</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-3 space-y-1 relative">
        {NAV.map((n) => {
          const active = view === n.key;
          return (
            <button key={n.key} onClick={() => go(n.key)}
              className={cx("nav-item w-full", active ? "bg-white/[0.08] text-white" : "text-slate-400 hover:text-slate-100 hover:bg-white/[0.04]")}>
              {active && <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r-full bg-brand-gradient" />}
              <n.Icon size={18} className={active ? "text-white" : "text-slate-500"} />
              {n.label}
            </button>
          );
        })}
        {view === "live" && (
          <div className="nav-item w-full bg-white/[0.08] text-white mt-1">
            <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r-full bg-brand-gradient" />
            <span className="relative flex h-2.5 w-2.5 ml-[3px] mr-[7px]">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-400 opacity-60" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-brand-400" />
            </span>
            {replay ? "Run replay" : "Live run"}{runId ? ` #${runId}` : ""}
          </div>
        )}
      </nav>

      <div className="px-4 py-4 border-t border-white/[0.06] relative">
        <div className="rounded-xl bg-white/[0.04] ring-1 ring-white/[0.06] p-3 space-y-2">
          <div className="flex items-center gap-2 text-[12px]">
            <span className={cx("h-2 w-2 rounded-full", health ? "bg-emerald-400 shadow-[0_0_8px] shadow-emerald-400/60" : "bg-rose-400")} />
            <span className="text-slate-300 font-medium">{health ? "API connected" : "API offline"}</span>
          </div>
          {health && (
            <div className="flex items-center justify-between text-[11px] text-slate-500">
              <span className="inline-flex items-center gap-1.5">
                <IconGitBranch size={13} className="text-slate-600" />
                extractor
              </span>
              <span className={cx("chip !px-2 !py-0.5 !text-[10px]", health.extractor === "claude" ? "bg-brand-500/20 text-brand-200" : "bg-white/[0.06] text-slate-300")}>
                {health.extractor}
              </span>
            </div>
          )}
          <div className="text-[10.5px] text-slate-600 pt-1 border-t border-white/[0.05] leading-relaxed">
            The model reads · code decides
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="h-screen flex bg-canvas text-ink font-sans overflow-hidden">
      {/* desktop sidebar */}
      <aside className="hidden lg:block shrink-0">{Sidebar}</aside>

      {/* mobile drawer */}
      {drawer && (
        <div className="lg:hidden fixed inset-0 z-50 flex">
          <div className="absolute inset-0 bg-ink/40 backdrop-blur-[2px] animate-fade-in" onClick={() => setDrawer(false)} />
          <div className="relative animate-[fade-up_0.25s_ease] shadow-xl">{Sidebar}</div>
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        {/* mobile top bar */}
        <header className="lg:hidden glass sticky top-0 z-40 border-b border-line flex items-center justify-between px-4 h-14">
          <div className="flex items-center gap-2.5">
            <LogoMark size={26} />
            <span className="font-bold text-ink text-sm">Zamp AP</span>
          </div>
          <button onClick={() => setDrawer(true)} className="btn-ghost !px-2 !py-2" aria-label="Open menu">
            <IconMenu size={22} />
          </button>
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="min-h-full">
            {view === "new" && <NewRun onStart={startRun} />}
            {view === "live" && runId != null && (
              <LiveRun runId={runId} replay={replay} key={`${runId}-${replay}`} onNew={() => go("new")} />
            )}
            {view === "dashboard" && <Dashboard onOpen={openRun} />}
            {view === "review" && <Review onOpen={openRun} />}
            {view === "data" && <DataRules onReset={() => {}} />}
          </div>
        </main>
      </div>
    </div>
  );
}
