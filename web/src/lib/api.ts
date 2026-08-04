/**
 * lib/api.ts — the single place that turns a `fetch` call into a typed,
 * truthful result.
 *
 * Every mutation caller needs to tell "the server said yes" from "the
 * server said no" from "we never heard back," without re-implementing
 * `res.ok` / `res.json()` / try-catch at each call site. Product invariant
 * #2 (docs/superpowers/plans/2026-07-30-comprehensive-product-unification.md):
 * the UI renders backend truth and never treats a non-2xx response as
 * success. This module owns ONLY that HTTP-decoding/error-normalization
 * concern — it knows nothing about projects, shots, or pipelines.
 * Feature-specific request shapes and endpoints stay next to their callers
 * (e.g. `usePipelineState.ts`'s `approveShotPlan`, `PromptEditor.tsx`'s
 * `handleSave`), built on top of the helpers below.
 */

export interface ApiSuccess<T> {
  ok: true
  status: number
  data: T
}

export interface ApiFailure {
  ok: false
  /** HTTP status, or 0 when the request never reached a server (network
   *  failure, CORS, offline, aborted). */
  status: number
  /** Human-readable, safe-to-surface message: the parsed body's own
   *  `error` string when it has one, else `res.statusText`/`HTTP <code>`,
   *  else the thrown error's message. Never undefined/empty on failure --
   *  callers can always show or log SOMETHING truthful. */
  error: string
  /** The parsed JSON error body, when the response had one (many
   *  endpoints in this product reply `{"error": "..."}` or
   *  `{"success": false, ...}` on failure). `undefined` when the body was
   *  absent, non-JSON, or unreadable -- callers that only need the
   *  message should use `error` above instead of poking at this. */
  body?: unknown
}

export type ApiResult<T> = ApiSuccess<T> | ApiFailure

const NETWORK_ERROR = 'Network error -- the request never reached the server.'

/** Best-effort JSON parse. An empty body (204, HEAD-shaped 200) or a
 *  non-JSON body (proxy error page, HTML 500) must not throw. */
async function tryParseJson(res: Response): Promise<unknown> {
  const text = await res.text().catch(() => '')
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

function errorMessageFrom(body: unknown, res: Response): string {
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    const message = (body as Record<string, unknown>).error
    if (typeof message === 'string' && message.trim()) return message
  }
  return res.statusText || `HTTP ${res.status}`
}

/**
 * Perform `fetch` and normalize the outcome into `ApiResult<T>`. Never
 * throws and never rejects: a network failure resolves to
 * `{ok: false, status: 0, error}` exactly like a non-2xx HTTP response
 * resolves to `{ok: false, status, error, body}`, so every caller can use
 * the SAME `if (!result.ok)` branch regardless of where the failure
 * happened. This is the low-level primitive -- prefer the verb helpers
 * below for a JSON request/response body.
 */
export async function apiRequest<T = unknown>(
  input: string,
  init?: RequestInit,
): Promise<ApiResult<T>> {
  let res: Response
  try {
    res = await fetch(input, init)
  } catch (err) {
    return {
      ok: false,
      status: 0,
      error: err instanceof Error && err.message ? err.message : NETWORK_ERROR,
    }
  }
  const body = await tryParseJson(res)
  if (!res.ok) {
    return { ok: false, status: res.status, error: errorMessageFrom(body, res), body }
  }
  return { ok: true, status: res.status, data: body as T }
}

function jsonInit(method: string, body?: unknown): RequestInit {
  return body === undefined
    ? { method }
    : { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export function apiGet<T = unknown>(url: string): Promise<ApiResult<T>> {
  return apiRequest<T>(url)
}

export function apiPost<T = unknown>(url: string, body?: unknown): Promise<ApiResult<T>> {
  return apiRequest<T>(url, jsonInit('POST', body))
}

export function apiPut<T = unknown>(url: string, body?: unknown): Promise<ApiResult<T>> {
  return apiRequest<T>(url, jsonInit('PUT', body))
}

export function apiPatch<T = unknown>(url: string, body?: unknown): Promise<ApiResult<T>> {
  return apiRequest<T>(url, jsonInit('PATCH', body))
}

export function apiDelete<T = unknown>(url: string): Promise<ApiResult<T>> {
  return apiRequest<T>(url, { method: 'DELETE' })
}
