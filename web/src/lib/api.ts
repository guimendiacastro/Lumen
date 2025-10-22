// web/src/lib/api.ts
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function json<T>(res: Response): Promise<T> {
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* noop */
  }
  if (!res.ok) {
    const msg = data?.detail ?? data?.message ?? res.statusText;
    throw new Error(`HTTP ${res.status}: ${msg}`);
  }
  return data as T;
}

export async function apiGet<T>(path: string, token?: string | null) {
  const headers: HeadersInit = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'GET',
    headers,
  });
  return json<T>(res);
}

export async function apiPost<T>(path: string, body: unknown, token?: string | null) {
  const headers: HeadersInit = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  return json<T>(res);
}

export async function apiPut<T>(path: string, body: unknown, token?: string | null) {
  const headers: HeadersInit = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(body),
  });
  return json<T>(res);
}

// File upload function (uses FormData, not JSON)
export async function apiPostFormData<T>(path: string, formData: FormData, token?: string | null) {
  const headers: HeadersInit = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers,
    body: formData,
  });
  return json<T>(res);
}

// Typed responses
export type MeResp = {
  user_id: string;
  org_id: string;
  schema_name: string;
  vault_key_id: string;
};

export type DocOut = {
  id: string;
  title: string;
  content: string;
  mime: string;
};

export type ThreadOut = {
  id: string;
  title?: string | null;
  document_id?: string | null;
};

export type MessageOut = {
  id: string;
  thread_id: string;
  role: 'user' | 'system';
  text: string;
};

export type CompareOut = {
  request_id: string;
  providers: {
    id: string;
    provider: string;
    text: string;
    latencyMs?: number;
    ok?: boolean;
  }[];
};

export type SelectionOut = {
  selection_id: string;
  document_id: string;
  new_version: number;
};

// File upload types
export type FileUploadResponse = {
  file_id: string;
  filename: string;
  size_bytes: number;
  use_direct_context: boolean;
  chunk_count: number;
  status: string;
};

export type FileMetadata = {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  use_direct_context: boolean;
  chunk_count: number;
  created_at: string;
};

// API methods with token parameter
export const api = {
  health: (token?: string | null) => apiGet<{ ok: boolean }>('/healthz', token),
  me: (token?: string | null) => apiGet<MeResp>('/me', token),
  bootstrap: (token?: string | null) =>
    apiPost<{ ok: boolean; schema: string }>('/bootstrap/member-schema', {}, token),
  createDoc: (title: string, content: string, token?: string | null) =>
    apiPost<{ id: string }>('/documents', { title, content }, token),
  getDoc: (id: string, token?: string | null) => apiGet<DocOut>(`/documents/${id}`, token),
  saveDoc: (id: string, content: string, token?: string | null) =>
    apiPut<{ ok: boolean; version: number }>(`/documents/${id}`, { content }, token),
  createThread: (title?: string, document_id?: string | null, token?: string | null) =>
    apiPost<ThreadOut>('/threads', { title, document_id: document_id ?? null }, token),
  postMessage: (threadId: string, content: string, token?: string | null) =>
    apiPost<MessageOut>(`/threads/${threadId}/messages`, { text: content }, token),
  compare: (threadId: string, messageId: string, token?: string | null) =>
    apiPost<CompareOut>('/ai/compare', { thread_id: threadId, message_id: messageId }, token),
  
  // FIXED: Added provider and documentId parameters
  selection: (
    requestId: string,
    responseId: string,
    provider: 'openai' | 'anthropic' | 'xai',
    documentId: string,
    mode: 'append' | 'replace' | 'insert_at',
    textOverride?: string,
    token?: string | null
  ) =>
    apiPost<SelectionOut>(
      '/ai/selection',
      {
        request_id: requestId,
        response_id: responseId,
        provider: provider,
        document_id: documentId,
        mode,
        selected_text_override: textOverride,
      },
      token
    ),
  
  uploadFile: (
    file: File,
    documentId?: string | null,
    threadId?: string | null,
    token?: string | null
  ) => {
    const formData = new FormData();
    formData.append('file', file);
    if (documentId) formData.append('document_id', documentId);
    if (threadId) formData.append('thread_id', threadId);
    return apiPostFormData<FileUploadResponse>('/files/upload', formData, token);
  },
  getFiles: (documentId?: string | null, threadId?: string | null, token?: string | null) => {
    const params = new URLSearchParams();
    if (documentId) params.append('document_id', documentId);
    if (threadId) params.append('thread_id', threadId);
    return apiGet<{ files: FileMetadata[] }>(`/files?${params}`, token);
  },
};