const API_BASE = import.meta.env.VITE_API_BASE as string

async function json<T>(res: Response): Promise<T> {
  const text = await res.text()
  let data: any = null
  try { data = text ? JSON.parse(text) : null } catch { /* noop */ }
  if (!res.ok) {
    const msg = data?.detail ?? data?.message ?? res.statusText
    throw new Error(`HTTP ${res.status}: ${msg}`)
  }
  return data as T
}

export async function apiGet<T>(path: string) {
  const res = await fetch(`${API_BASE}${path}`, { method: 'GET' })
  return json<T>(res)
}
export async function apiPost<T>(path: string, body: unknown) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  return json<T>(res)
}
export async function apiPut<T>(path: string, body: unknown) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  return json<T>(res)
}

// typed calls
export type MeResp = { user_id: string; org_id: string; schema_name: string; vault_key_id: string }
export type DocOut = { id: string; title: string; content: string; mime: string }
export type ThreadOut = { id: string; title?: string | null; document_id?: string | null }
export type MessageOut = { id: string; thread_id: string; role: 'user'|'system'; text: string }
export type CompareOut = { request_id: string; providers: { id: string; provider: string; text: string; latencyMs?: number; ok?: boolean }[] }
export type SelectionOut = { selection_id: string; document_id: string; new_version: number }

export const api = {
  health: () => apiGet<{ok:boolean}>('/healthz'),
  me: () => apiGet<MeResp>('/me'),
  bootstrap: () => apiPost<{ok:boolean; schema:string}>('/bootstrap/member-schema', {}),
  createDoc: (title: string, content: string) => apiPost<{id:string}>('/documents', { title, content }),
  getDoc: (id: string) => apiGet<DocOut>(`/documents/${id}`),
  saveDoc: (id: string, content: string) => apiPut<{ok: boolean; version: number}>(`/documents/${id}`, { content }),
  createThread: (title?: string, document_id?: string | null) => apiPost<ThreadOut>('/threads', { title, document_id: document_id ?? null }),
  postMessage: (thread_id: string, text: string) => apiPost<MessageOut>(`/threads/${thread_id}/messages`, { text }),
  compare: (thread_id: string, message_id: string, system?: string) => apiPost<CompareOut>('/ai/compare', { thread_id, message_id, system }),
  applySelection: (args: {
    request_id: string; response_id: string; provider: 'openai'|'anthropic'|'xai';
    document_id: string; mode: 'append'|'replace'|'insert_at';
    insert_index?: number | null;
    replace_range?: { start: number; end: number } | null;
    selected_text_override?: string | null;
  }) => apiPost<SelectionOut>('/ai/selection', args),
}
