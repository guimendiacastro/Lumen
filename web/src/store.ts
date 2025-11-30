// web/src/store.ts
import { create } from 'zustand';
import { api } from './lib/api';
import type { DocOut, CompareOut, FileUploadResponse, ThreadOut, MessageOut } from './lib/api';

type ProviderId = 'openai' | 'anthropic' | 'xai';
type AnswerCard = {
  id: string;
  provider: ProviderId;
  text: string;
  latencyMs?: number;
  ok?: boolean;
};

// Unified file type for display
type FileItem = {
  file_id: string;
  filename: string;
  size_bytes: number;
  status: string;
  use_direct_context: boolean;
  chunk_count: number;
  indexed?: boolean;
  library_scope?: 'direct' | 'rag';
  indexed_at?: string | null;
  attached_at?: string | null;
  last_status_note?: string | null;
};

type InteractionMode = 'edit' | 'qa';

type State = {
  ready: boolean;
  error?: string;
  document?: DocOut;
  baselineDocument?: DocOut; // snapshot of document before asking AI (for diff comparison)
  threadId?: string;
  threads: ThreadOut[]; // list of all threads
  messages: MessageOut[]; // messages for current thread
  input: string;
  answers: AnswerCard[];
  activeProvider?: ProviderId;
  lastRequestId?: string;
  editBuffer: string; // live text from editor (unsaved)
  uploadedFiles: FileItem[]; // files uploaded in current thread
  isSidebarOpen: boolean; // thread sidebar visibility
  isLoadingThreads: boolean;
  isLoadingMessages: boolean;
  isLoadingAnswers: boolean; // loading state for AI responses
  interactionMode: InteractionMode; // toggle between edit and Q&A mode
  answersMode?: InteractionMode; // mode that was used to generate current answers
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
  addUploadedFile: (file: FileUploadResponse) => void;
  removeUploadedFile: (fileId: string, token?: string | null) => Promise<void>;
  loadFiles: (token?: string | null) => Promise<void>;
  // Thread management actions
  loadThreads: (token?: string | null) => Promise<void>;
  switchThread: (threadId: string, token?: string | null) => Promise<void>;
  createNewThread: (token?: string | null) => Promise<void>;
  updateThreadTitle: (threadId: string, title: string, token?: string | null) => Promise<void>;
  toggleSidebar: () => void;
  loadCurrentThreadMessages: (token?: string | null) => Promise<void>;
  setInteractionMode: (mode: InteractionMode) => void;
};

export const useApp = create<State & Actions>((set, get) => ({
  ready: false,
  threads: [],
  messages: [],
  input: '',
  answers: [],
  editBuffer: '',
  uploadedFiles: [],
  isSidebarOpen: false,
  isLoadingThreads: false,
  isLoadingMessages: false,
  isLoadingAnswers: false,
  interactionMode: 'edit',

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
      uploadedFiles: [],
      baselineDocument: undefined, // Clear baseline for new thread
    });
  },

  setInput(v) {
    set({ input: v });
  },

  setEditBuffer(v) {
    set({ editBuffer: v });
  },

  async askAI(token?: string | null) {
    let { threadId, input, messages, document, editBuffer, interactionMode } = get();
    if (!input.trim()) return;

    // Lazy thread creation: if no thread exists, create one now
    if (!threadId || !document) {
      await get().createDocumentAndThread(token);
      // Re-fetch state after thread creation
      const state = get();
      threadId = state.threadId;
      document = state.document;
      messages = state.messages;
      editBuffer = state.editBuffer;
    }

    if (!threadId || !document) return; // Safety check

    // Clear old answers and set loading state immediately
    set({ isLoadingAnswers: true, answers: [], answersMode: undefined });

    try {
      // 1) auto-save the latest editor content so backend snapshot is fresh
      if (typeof editBuffer === 'string' && editBuffer !== document.content) {
        await api.saveDoc(document.id, editBuffer, token);
        const fresh = await api.getDoc(document.id, token);
        set({ document: fresh }); // keep local in sync
      }

      // Preserve baseline document AFTER auto-save (with user's manual edits included)
      // This ensures the diff only shows LLM's proposed changes, not the user's edits
      // In Q&A mode, we don't need baseline for diff
      const currentDoc = get().document;
      const baselineDocument = interactionMode === 'edit' && currentDoc ? { ...currentDoc } : undefined;

      // 2) post the user message and fan-out
      const m = await api.postMessage(threadId, input, token);

      console.log('[askAI] Calling /ai/compare endpoint...');
      const startTime = Date.now();
      const cmp: CompareOut = await api.compare(threadId, m.id, token, interactionMode);
      const elapsed = Date.now() - startTime;
      console.log(`[askAI] /ai/compare completed in ${elapsed}ms`);

      const answers: AnswerCard[] = cmp.providers.map((p) => ({
        id: p.id,
        provider: p.provider as any,
        text: p.text,
        latencyMs: p.latencyMs,
        ok: p.ok,
      }));

      // Add user message to chat history
      const userMessage: MessageOut = {
        id: m.id,
        thread_id: threadId,
        role: 'user',
        text: input,
        ts: new Date().toISOString(),
      };

      set({
        messages: [...messages, userMessage],
        input: '',
        answers,
        answersMode: interactionMode, // Store the mode used to generate these answers
        baselineDocument, // Store the baseline for diff comparison (only in edit mode)
        lastRequestId: (cmp as any).request_id,
        isLoadingAnswers: false,
      });
    } catch (error: any) {
      console.error('[askAI] Error:', error);
      set({
        isLoadingAnswers: false,
        error: error.message || 'Failed to get AI responses'
      });
      // Show error to user for 5 seconds then clear
      setTimeout(() => {
        set({ error: undefined });
      }, 5000);
    }
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

    // Refresh doc to show applied changes and set it as the new baseline
    const fresh = await api.getDoc(st.document.id, token);
    set({
      document: fresh,
      editBuffer: fresh.content,
      baselineDocument: { ...fresh } // Set fresh document as baseline for next question
    });
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

  addUploadedFile(file: FileUploadResponse) {
    const { uploadedFiles } = get();
    const fileItem: FileItem = {
      file_id: file.file_id,
      filename: file.filename,
      size_bytes: file.size_bytes,
      status: file.status,
      use_direct_context: file.use_direct_context,
      chunk_count: file.chunk_count,
      indexed: file.indexed,
      library_scope: file.library_scope,
    };
    set({ uploadedFiles: [...uploadedFiles, fileItem] });
  },

  async removeUploadedFile(fileId: string, token?: string | null) {
    const { threadId, uploadedFiles } = get();
    if (!threadId) return;
    await api.detachThreadFile(threadId, fileId, token);
    set({ uploadedFiles: uploadedFiles.filter((f) => f.file_id !== fileId) });
  },

  async loadFiles(token?: string | null) {
    const { threadId } = get();
    if (!threadId) return;
    if (!token) {
      console.warn('[store.loadFiles] Missing auth token, skipping file fetch');
      return;
    }
    const files = await api.getFiles(threadId, token);
    const fileItems: FileItem[] = files.map((f) => ({
      file_id: f.id,
      filename: f.filename,
      size_bytes: f.size_bytes,
      status: f.status,
      use_direct_context: f.use_direct_context,
      chunk_count: f.chunk_count,
      indexed: f.indexed,
      library_scope: f.library_scope,
      indexed_at: f.indexed_at,
      attached_at: f.attached_at,
      last_status_note: f.last_status_note,
    }));
    set({ uploadedFiles: fileItems });
  },

  async loadThreads(token?: string | null) {
    set({ isLoadingThreads: true });
    try {
      const threads = await api.listThreads(50, 0, token);
      set({ threads, isLoadingThreads: false });
    } catch (e: any) {
      console.error('Failed to load threads:', e);
      set({ isLoadingThreads: false });
    }
  },

  async switchThread(threadId: string, token?: string | null) {
    set({ isLoadingMessages: true });
    try {
      const threadData = await api.getThread(threadId, token);

      // Map backend response (sanitized) to frontend (text)
      const messages: MessageOut[] = (threadData.messages || []).map((m: any) => ({
        id: m.id,
        thread_id: threadId,
        role: m.role,
        text: m.sanitized, // backend uses 'sanitized', frontend expects 'text'
        ts: m.ts,
      }));

      const document = threadData.document_id ? await api.getDoc(threadData.document_id, token) : undefined;

      set({
        threadId: threadData.id,
        messages,
        document,
        editBuffer: document?.content || '',
        isLoadingMessages: false,
        answers: [], // Clear previous answers when switching
        uploadedFiles: [], // Clear files initially
        baselineDocument: undefined, // Clear baseline when switching threads
      });

      // Load files for this thread (don't block on error)
      try {
        await get().loadFiles(token);
      } catch (fileError) {
        console.warn('Failed to load files for thread:', fileError);
        // Continue anyway - files are optional
      }
    } catch (e: any) {
      console.error('[store.switchThread] Failed to switch thread:', e);
      set({ isLoadingMessages: false });
    }
  },

  async createNewThread(token?: string | null) {
    await get().createDocumentAndThread(token);
    await get().loadThreads(token);
  },

  async updateThreadTitle(threadId: string, title: string, token?: string | null) {
    try {
      await api.updateThread(threadId, title, token);
      // Update local thread list
      const { threads } = get();
      set({
        threads: threads.map((t) => (t.id === threadId ? { ...t, title } : t)),
      });
    } catch (e: any) {
      console.error('Failed to update thread title:', e);
    }
  },

  toggleSidebar() {
    set((state) => ({ isSidebarOpen: !state.isSidebarOpen }));
  },

  async loadCurrentThreadMessages(token?: string | null) {
    const { threadId } = get();
    if (!threadId) return;
    set({ isLoadingMessages: true });
    try {
      const result = await api.getMessages(threadId, token);
      set({ messages: result.messages, isLoadingMessages: false });
    } catch (e: any) {
      console.error('Failed to load messages:', e);
      set({ isLoadingMessages: false });
    }
  },

  setInteractionMode(mode: InteractionMode) {
    // Don't clear answers - let them stay visible until next message is sent
    // Only clear baseline since it's mode-specific
    set({ interactionMode: mode, baselineDocument: undefined });
  },
}));
