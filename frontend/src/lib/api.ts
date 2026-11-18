// Same-origin API client. Adds the CSRF double-submit header and maps errors to stable codes.
export class ApiError extends Error {
  constructor(public status: number, public code: string, public data: Record<string, unknown> = {}) {
    super(code);
  }
}

function csrf(): string {
  if (typeof document === "undefined") return "";
  const m = document.cookie.match(/(?:^|; )fp_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function ensureCsrf() {
  if (!csrf()) await fetch("/api/health", { credentials: "same-origin" });
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; form?: FormData; raw?: boolean } = {}): Promise<T> {
  const method = opts.method || (opts.body || opts.form ? "POST" : "GET");
  if (method !== "GET") await ensureCsrf();
  const headers: Record<string, string> = { "x-csrf-token": csrf() };
  if (opts.body !== undefined) headers["content-type"] = "application/json";
  const res = await fetch(`/api${path}`, {
    method, headers, credentials: "same-origin",
    body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
  });
  if (!res.ok) {
    let detail: any = {};
    try { detail = (await res.json()).detail ?? {}; } catch { /* non-JSON */ }
    throw new ApiError(res.status, detail.code || `http_${res.status}`, detail);
  }
  if (opts.raw) return res as unknown as T;
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("json") ? res.json() : res.text()) as Promise<T>;
}

export async function download(path: string, filename: string) {
  const res = await api<Response>(path, { raw: true });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
