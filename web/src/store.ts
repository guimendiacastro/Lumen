import { create } from 'zustand'
import { api } from './lib/api'
import type { DocOut, CompareOut } from './lib/api'

type ProviderId = 'openai'|'anthropic'|'xai'
type AnswerCard = { id: string; provider: ProviderId; text: string; latencyMs?: number; ok?: boolean }

type State = {
  ready: boolean
  error?: string
  document?: DocOut
  threadId?: string
  messages: { id: string; role: 'user'|'system'|'assistant'; text: string }[]
  input: string
  answers: AnswerCard[]
  activeProvider?: ProviderId
  lastRequestId?: string
  editBuffer: string            // live text from editor (unsaved)
}

type Actions = {
  init: () => Promise<void>
  createDocumentAndThread: () => Promise<void>
  setInput: (v: string) => void
  setEditBuffer: (v: string) => void
  askAI: () => Promise<void>
  pickAnswer: (card: AnswerCard & { text?: string }, mode?: 'append'|'replace'|'insert_at') => Promise<void>
  refreshDoc: () => Promise<void>
  saveDoc: (content: string) => Promise<void>
}

export const useApp = create<State & Actions>((set, get) => ({
  ready: false,
  messages: [],
  input: '',
  answers: [],
  editBuffer: '',

  async init() {
    try {
      await api.health()
      await api.me()
      await api.bootstrap()
      set({ ready: true })
    } catch (e: any) {
      set({ error: e.message || 'init failed' })
    }
  },

  async createDocumentAndThread() {
    const title = 'Untitled Document'
    const content = '# New Document\n\nType here…'
    const { id } = await api.createDoc(title, content)
    const thread = await api.createThread('Chat for: ' + title, id)
    const doc = await api.getDoc(id)
    set({ document: doc, threadId: thread.id, messages: [], editBuffer: doc.content })
  },

  setInput(v) { set({ input: v }) },
  setEditBuffer(v) { set({ editBuffer: v }) },

  async askAI() {
    const { threadId, input, messages, document, editBuffer } = get()
    if (!threadId || !input.trim() || !document) return

    // 1) auto-save the latest editor content so backend snapshot is fresh
    if (typeof editBuffer === 'string' && editBuffer !== document.content) {
      await api.saveDoc(document.id, editBuffer)
      const fresh = await api.getDoc(document.id)
      set({ document: fresh })  // keep local in sync
    }

    // 2) post the user message and fan-out
    const m = await api.postMessage(threadId, input)
    const cmp: CompareOut = await api.compare(threadId, m.id)
    const answers: AnswerCard[] = cmp.providers.map(p => ({
      id: p.id, provider: p.provider as any, text: p.text, latencyMs: p.latencyMs, ok: p.ok
    }))
    set({
      messages: [...messages, { id: m.id, role: 'user', text: input }],
      input: '',
      answers,
      lastRequestId: (cmp as any).request_id
    })
  },

  async pickAnswer(card, mode = 'append') {
    const st = get()
    if (!st.document || !st.lastRequestId) return

    const override = card.text && card.text.length > 0 ? card.text : undefined

    await api.applySelection({
      request_id: st.lastRequestId,
      response_id: card.id,
      provider: card.provider,
      document_id: st.document.id,
      mode,
      selected_text_override: override ?? null,
    })
    const fresh = await api.getDoc(st.document.id)
    set({ document: fresh, editBuffer: fresh.content, answers: [], activeProvider: card.provider })
  },

  async refreshDoc() {
    const { document } = get()
    if (!document) return
    const fresh = await api.getDoc(document.id)
    set({ document: fresh, editBuffer: fresh.content })
  },

  async saveDoc(content) {
    const { document } = get()
    if (!document) return
    await api.saveDoc(document.id, content)
    const fresh = await api.getDoc(document.id)
    set({ document: fresh, editBuffer: fresh.content })
  },
}))
