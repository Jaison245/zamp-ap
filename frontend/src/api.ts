export type Code = {
  code: string; outcome: "REJECT" | "HOLD" | "INFO"; severity: string;
  routing: string; routing_label: string; message: string; evidence?: string; detail?: string;
};
export type StageEvent = {
  type: "stage" | "decision" | "error";
  stage?: number; name?: string; status?: "running" | "pass" | "warn" | "fail";
  duration_ms?: number; detail?: any; codes?: Code[]; notes?: string[];
  run_id?: number; result?: RunResult; cost_usd?: number; message?: string;
};
export type RunResult = {
  decision: "APPROVE" | "HOLD" | "REJECT"; codes: Code[]; routing?: string;
  top_reason?: string; explanation: string; vendor_email?: string;
  posting?: any; side_effects?: string[]; extraction: any; po_table: any[];
  vendor?: { name: string; id: string }; amount?: string; currency?: string; invoice_number?: string;
};

const J = async (r: Response) => {
  if (!r.ok) throw new Error(await r.text());
  return r.json();
};

export const api = {
  health: () => fetch("/api/health").then(J),
  samples: () => fetch("/api/samples").then(J),
  createRunSample: (sample_id: string) => {
    const fd = new FormData();
    fd.append("sample_id", sample_id);
    return fetch("/api/runs", { method: "POST", body: fd }).then(J);
  },
  createRunUpload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch("/api/runs", { method: "POST", body: fd }).then(J);
  },
  getRun: (id: number) => fetch(`/api/runs/${id}`).then(J),
  listRuns: () => fetch("/api/runs").then(J),
  dashboard: () => fetch("/api/dashboard").then(J),
  review: () => fetch("/api/review").then(J),
  reviewAction: (id: number, action: string, comment: string) =>
    fetch(`/api/review/${id}`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, comment }) }).then(J),
  data: () => fetch("/api/data").then(J),
  getRules: () => fetch("/api/rules").then(J),
  putRules: (rules: any) => fetch("/api/rules", { method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rules) }).then(J),
  reset: () => fetch("/api/reset", { method: "POST" }).then(J),
  pdfUrl: (id: number) => `/api/runs/${id}/pdf`,
  samplePdfUrl: (id: string) => `/api/samples/${id}/pdf`,
};
