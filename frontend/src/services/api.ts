export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

export async function checkApi(): Promise<boolean> {
  try {
    const response = await fetch(`${apiBaseUrl}/health`, { signal: AbortSignal.timeout(8000) });
    return response.ok;
  } catch { return false; }
}

export async function api<T>(path: string, body?: unknown, options: { signal?: AbortSignal; timeoutMs?: number } = {}): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  if (options.signal?.aborted) controller.abort();
  const timeout = setTimeout(abort, options.timeoutMs ?? 65000);
  try {
    const response = await fetch(`${apiBaseUrl}${path}`, {
      method: body === undefined ? "GET" : "POST", signal: controller.signal,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload?.detail;
      const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map(e => e.msg).join(" ") : detail?.message;
      throw new Error(message || "The request could not be completed. Please retry.");
    }
    if (payload === null) throw new Error("The response could not be read. Please retry.");
    return payload as T;
  } catch (error) {
    if (options.signal?.aborted) throw new Error("Request cancelled.");
    if (controller.signal.aborted) throw new Error("The request took too long. Your entries are kept; please retry.");
    if (error instanceof TypeError) throw new Error("Unable to connect. Check your connection and retry.");
    throw error;
  } finally { clearTimeout(timeout); options.signal?.removeEventListener("abort", abort); }
}

export function readStored<T>(key: string, fallback: T): T {
  try { return JSON.parse(localStorage.getItem(key) || "null") ?? fallback; } catch { return fallback; }
}
export function storeLocal(key: string, value: unknown): boolean {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { return false; }
}
