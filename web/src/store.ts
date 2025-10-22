// web/src/store.ts
import { create } from 'zustand';
import { api } from './lib/api';
import type { DocOut, CompareOut } from './lib/api';

type ProviderId = 'openai' | 'anthropic' | 'xai';
type AnswerCard = {
  id: string;
  provider: ProviderId;
  text: string;
  latencyMs?: number;
  ok?: boolean;
};

type State = {
  ready: boolean;
  error?: string;
  document?: DocOut;
  threadId?: string;
  messages: { id: string; role: 'user' | 'system' | 'assistant'; text: string }[];
  input: string;
  answers: AnswerCard[];
  activeProvider?: ProviderId;
  lastRequestId?: string;
  editBuffer: string; // live text from editor (unsaved)
};

type Actions = {
  init: (token?: string | null) => Promise<void>;
  createDocumentAndThread: (token?: string | null) => Promise<void>;
  setInput: (v: string) => void;
  setEditBuffer: (v: string) => void;
  askAI: (token?: string | null) => Promise<void>;
  pickAnswer: (
    card: AnswerCard & { text?: string },
    mode?: 'append' | 'replace' | 'insert_at',
    token?: string | null
  ) => Promise<void>;
  refreshDoc: (token?: string | null) => Promise<void>;
  saveDoc: (content: string, token?: string | null) => Promise<void>;
};

export const useApp = create<State & Actions>((set, get) => ({
  ready: false,
  messages: [],
  input: '',
  answers: [],
  editBuffer: '',

  async init(token?: string | null) {
    try {
      await api.health(token);
      await api.me(token);
      await api.bootstrap(token);
      set({ ready: true });
    } catch (e: any) {
      set({ error: e.message || 'init failed' });
    }
  },

  async createDocumentAndThread(token?: string | null) {
    const title = 'Untitled Document';
    const content = '# New Document\n\nType here…';
    const { id } = await api.createDoc(title, content, token);
    const thread = await api.createThread('Chat for: ' + title, id, token);
    const doc = await api.getDoc(id, token);
    set({
      document: doc,
      threadId: thread.id,
      messages: [],
      editBuffer: doc.content,
    });
  },

  setInput(v) {
    set({ input: v });
  },

  setEditBuffer(v) {
    set({ editBuffer: v });
  },

  async askAI(token?: string | null) {
    const { threadId, input, messages, document, editBuffer } = get();
    if (!threadId || !input.trim() || !document) return;

    // 1) auto-save the latest editor content so backend snapshot is fresh
    if (typeof editBuffer === 'string' && editBuffer !== document.content) {
      await api.saveDoc(document.id, editBuffer, token);
      const fresh = await api.getDoc(document.id, token);
      set({ document: fresh }); // keep local in sync
    }

    // 2) post the user message and fan-out
    const m = await api.postMessage(threadId, input, token);
    const cmp: CompareOut = await api.compare(threadId, m.id, token);
    const answers: AnswerCard[] = cmp.providers.map((p) => ({
      id: p.id,
      provider: p.provider as any,
      text: p.text,
      latencyMs: p.latencyMs,
      ok: p.ok,
    }));
    set({
      messages: [...messages, { id: m.id, role: 'user', text: input }],
      input: '',
      answers,
      lastRequestId: (cmp as any).request_id,
    });
  },

  // FIXED: Pass provider and document_id to the API
  async pickAnswer(card, mode = 'append', token?: string | null) {
    const st = get();
    if (!st.document || !st.lastRequestId) return;

    const override = card.text && card.text.length > 0 ? card.text : undefined;
    
    // Pass provider and document_id to fix the 422 error
    await api.selection(
      st.lastRequestId, 
      card.id, 
      card.provider,        // Provider field required by backend
      st.document.id,       // Document ID required by backend
      mode, 
      override, 
      token
    );

    // Refresh doc to show applied changes
    const fresh = await api.getDoc(st.document.id, token);
    set({ document: fresh, editBuffer: fresh.content });
  },

  async refreshDoc(token?: string | null) {
    const st = get();
    if (!st.document) return;
    const fresh = await api.getDoc(st.document.id, token);
    set({ document: fresh, editBuffer: fresh.content });
  },

  async saveDoc(content: string, token?: string | null) {
    const st = get();
    if (!st.document) return;
    await api.saveDoc(st.document.id, content, token);
    const fresh = await api.getDoc(st.document.id, token);
    set({ document: fresh, editBuffer: fresh.content });
  },
}));