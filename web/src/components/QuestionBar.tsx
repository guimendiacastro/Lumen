import { useState, useRef, useEffect } from 'react';
import { Box, CircularProgress, IconButton, Typography, Collapse } from '@mui/material';
import { ArrowUp, Paperclip, CheckCircle2, ChevronDown, ChevronUp } from 'lucide-react';
import { useAuth } from '@clerk/clerk-react';
import { useApp } from '../store';
import FileChip from './FileChip';

export default function QuestionBar() {
  const { getToken } = useAuth();
  const ready = useApp((s) => s.ready);
  const error = useApp((s) => s.error);
  const init = useApp((s) => s.init);
  const input = useApp((s) => s.input);
  const setInput = useApp((s) => s.setInput);
  const askAI = useApp((s) => s.askAI);
  const createDocumentAndThread = useApp((s) => s.createDocumentAndThread);
  const addUploadedFile = useApp((s) => s.addUploadedFile);
  const threadId = useApp((s) => s.threadId);
  const uploadedFiles = useApp((s) => s.uploadedFiles);
  const removeUploadedFile = useApp((s) => s.removeUploadedFile);
  const loadFiles = useApp((s) => s.loadFiles);
  const interactionMode = useApp((s) => s.interactionMode);
  const setInteractionMode = useApp((s) => s.setInteractionMode);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const uploadedFilesRef = useRef(uploadedFiles);
  const hasPendingUploads = uploadedFiles.some(
    (f) => !f.use_direct_context && !f.indexed
  );
  const fileInputRef = useRef<HTMLInputElement>(null);
  const completionTimer = useRef<NodeJS.Timeout | null>(null);
  const hadUploadsRef = useRef(false);
  const [showCompletion, setShowCompletion] = useState(false);
  const [isFilesExpanded, setIsFilesExpanded] = useState(() => {
    const saved = localStorage.getItem('lumen-files-expanded');
    return saved !== null ? JSON.parse(saved) : true;
  });

  useEffect(() => {
    uploadedFilesRef.current = uploadedFiles;
  }, [uploadedFiles]);

  // Show a brief completion indicator when uploads finish
  useEffect(() => {
    if (isUploading || hasPendingUploads) {
      if (completionTimer.current) {
        clearTimeout(completionTimer.current);
        completionTimer.current = null;
      }
      setShowCompletion(false);
      if (uploadedFiles.length > 0) {
        hadUploadsRef.current = true;
      }
    } else if (hadUploadsRef.current && uploadedFiles.length > 0) {
      setShowCompletion(true);
      completionTimer.current = setTimeout(() => {
        setShowCompletion(false);
        completionTimer.current = null;
        hadUploadsRef.current = false;
      }, 2500);
    }
  }, [isUploading, hasPendingUploads, uploadedFiles.length]);

  useEffect(() => {
    return () => {
      if (completionTimer.current) {
        clearTimeout(completionTimer.current);
        completionTimer.current = null;
      }
    };
  }, []);

  useEffect(() => {
    (async () => {
      const token = await getToken();
      await init(token);
    })();
  }, [getToken, init]);

  // Load files when thread changes
  useEffect(() => {
    if (threadId) {
      (async () => {
        const token = await getToken();
        if (!token) {
          console.warn('[QuestionBar] No auth token available while loading files.');
          return;
        }
        await loadFiles(token);
      })();
    }
  }, [threadId, getToken, loadFiles]);

  // Poll for indexing status with exponential backoff
  useEffect(() => {
    if (!threadId) return;

    let pollInterval = 3000; // Start at 3 seconds
    const maxInterval = 30000; // Max 30 seconds
    let timeoutId: NodeJS.Timeout | null = null;
    let isActive = true;

    const pollIndexingStatus = async () => {
      if (!isActive) return;

      const filesNeedingPolling = uploadedFilesRef.current.filter(
        (f) => !f.use_direct_context && f.status === 'ready' && !f.indexed
      );

      if (filesNeedingPolling.length > 0) {
        const token = await getToken();
        if (!token) {
          console.warn('[QuestionBar] No auth token available while polling files.');
          return;
        }
        await loadFiles(token);

        // Exponential backoff: increase interval by 1.5x each time, max 30s
        pollInterval = Math.min(pollInterval * 1.5, maxInterval);
      } else {
        // No files to poll, reset interval for next time
        pollInterval = 3000;
      }

      // Continue polling loop regardless so new uploads trigger automatically
      if (isActive) {
        timeoutId = setTimeout(pollIndexingStatus, pollInterval);
      }
    };

    // Start polling immediately
    pollIndexingStatus();

    return () => {
      isActive = false;
      if (timeoutId) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
    };
  }, [threadId, getToken, loadFiles]); // Removed uploadedFiles from deps to prevent restart on every update

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const scrollHeight = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = Math.min(scrollHeight, 120) + 'px';
    }
  }, [input]);

  const handleAsk = async () => {
    if (!input.trim() || isLoading || hasPendingUploads || isUploading) return;
    setIsLoading(true);
    const token = await getToken();
    await askAI(token);
    setIsLoading(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!hasPendingUploads && !isUploading) {
        handleAsk();
      }
    }
  };

  const handleRemoveFile = async (fileId: string) => {
    const token = await getToken();
    if (!token) {
      console.warn('[QuestionBar] Tried to remove file without auth token.');
      return;
    }
    await removeUploadedFile(fileId, token);
  };

  const toggleFilesExpanded = () => {
    const newValue = !isFilesExpanded;
    setIsFilesExpanded(newValue);
    localStorage.setItem('lumen-files-expanded', JSON.stringify(newValue));
  };

  const ensureThreadExists = async () => {
    if (!threadId) {
      const token = await getToken();
      await createDocumentAndThread(token);
    }
  };

  const handleFileSelect = async () => {
    await ensureThreadExists();
    fileInputRef.current?.click();
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    setIsUploading(true);
    setUploadError(null);

    try {
      const token = await getToken();
      if (!token) {
        throw new Error('Not authenticated');
      }

      const currentThreadId = useApp.getState().threadId;
      const currentDocumentId = useApp.getState().document?.id;

      const uploadPromises = Array.from(files).map(async (file) => {
        const formData = new FormData();
        formData.append('file', file);
        if (currentThreadId) formData.append('thread_id', currentThreadId);
        if (currentDocumentId) formData.append('document_id', currentDocumentId);

        const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/files/upload`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
          },
          body: formData,
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || 'Upload failed');
        }

        return await response.json();
      });

      const results = await Promise.all(uploadPromises);
      results.forEach((file) => addUploadedFile(file));
    } catch (err: any) {
      console.error('Failed to upload files:', err);
      setUploadError(err.message || 'Failed to upload files');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  if (error) {
    return (
      <Box
        sx={{
          p: 2,
          background: '#FEE2E2',
          borderTop: '1px solid #FCA5A5',
        }}
      >
        <Box sx={{ fontSize: '13px', color: '#DC2626', fontWeight: 500, textAlign: 'center' }}>
          Error: {error}
        </Box>
      </Box>
    );
  }

  if (!ready) {
    return (
      <Box
        sx={{
          p: 3,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderTop: '1px solid #E5E7EB',
          background: 'white',
        }}
      >
        <CircularProgress size={24} />
      </Box>
    );
  }

  const showStatusPill = uploadError || isUploading || hasPendingUploads || showCompletion;

  const getStatusContent = () => {
    if (uploadError) {
      return {
        color: '#b04132',
        borderColor: 'rgba(176, 65, 50, 0.4)',
        background: 'rgba(176, 65, 50, 0.12)',
        icon: null,
        text: uploadError,
      };
    }

    if (isUploading) {
      return {
        color: 'var(--muted-ink)',
        borderColor: 'var(--sand-border)',
        background: 'var(--sand-soft)',
        icon: <CircularProgress size={14} sx={{ color: 'var(--muted-ink)' }} />,
        text: 'Uploading files…',
      };
    }

    if (hasPendingUploads) {
      return {
        color: 'var(--muted-ink)',
        borderColor: 'var(--sand-border)',
        background: 'var(--sand-soft)',
        icon: <CircularProgress size={14} sx={{ color: 'var(--muted-ink)' }} />,
        text: 'Processing files…',
      };
    }

    return {
      color: '#0d815f',
      borderColor: 'rgba(13,129,95,0.3)',
      background: 'rgba(13,129,95,0.12)',
      icon: <CheckCircle2 size={16} color="#0d815f" />,
      text: 'Files ready to use',
    };
  };

  const statusContent = getStatusContent();

  return (
    <Box
      sx={{
        width: '100%',
        background: 'var(--card)',
        border: '1px solid var(--sand-border)',
        borderRadius: '32px',
        boxShadow: '0 25px 70px rgba(51, 41, 32, 0.12)',
        px: { xs: 2, md: 4 },
        py: 3,
      }}
    >
        {/* Mode Toggle */}
        <Box
          sx={{
            display: 'flex',
            gap: 1,
            mb: 2,
            p: 0.5,
            background: 'var(--sand-soft)',
            borderRadius: '12px',
            width: 'fit-content',
          }}
        >
          <Box
            onClick={() => setInteractionMode('edit')}
            sx={{
              px: 2,
              py: 1,
              borderRadius: '10px',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              background: interactionMode === 'edit' ? 'white' : 'transparent',
              color: interactionMode === 'edit' ? 'var(--ink)' : 'var(--muted-ink)',
              boxShadow: interactionMode === 'edit' ? '0 2px 4px rgba(0,0,0,0.08)' : 'none',
              '&:hover': {
                background: interactionMode === 'edit' ? 'white' : 'rgba(255,255,255,0.5)',
              },
            }}
          >
            Edit Document
          </Box>
          <Box
            onClick={() => setInteractionMode('qa')}
            sx={{
              px: 2,
              py: 1,
              borderRadius: '10px',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              background: interactionMode === 'qa' ? 'white' : 'transparent',
              color: interactionMode === 'qa' ? 'var(--ink)' : 'var(--muted-ink)',
              boxShadow: interactionMode === 'qa' ? '0 2px 4px rgba(0,0,0,0.08)' : 'none',
              '&:hover': {
                background: interactionMode === 'qa' ? 'white' : 'rgba(255,255,255,0.5)',
              },
            }}
          >
            Ask Question
          </Box>
        </Box>

        {/* Uploaded Files Display */}
        {uploadedFiles.length > 0 && (
          <Box sx={{ mb: 1.5 }}>
            {/* Toggle Header */}
            <Box
              onClick={toggleFilesExpanded}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                mb: isFilesExpanded ? 1 : 0,
                cursor: 'pointer',
                padding: '6px 8px',
                borderRadius: '8px',
                transition: 'background 0.15s ease',
                '&:hover': {
                  background: 'var(--sand-soft)',
                },
              }}
            >
              <Paperclip size={14} color="var(--muted-ink)" />
              <Typography sx={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted-ink)' }}>
                {uploadedFiles.length} {uploadedFiles.length === 1 ? 'file' : 'files'}
              </Typography>
              {isFilesExpanded ? (
                <ChevronUp size={14} color="var(--muted-ink)" />
              ) : (
                <ChevronDown size={14} color="var(--muted-ink)" />
              )}
            </Box>

            {/* Collapsible File Chips */}
            <Collapse in={isFilesExpanded} timeout={300}>
              <Box
                sx={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 1,
                }}
              >
                {uploadedFiles.map((file) => (
                  <FileChip
                    key={file.file_id}
                    filename={file.filename}
                    fileId={file.file_id}
                    onRemove={handleRemoveFile}
                    useDirectContext={file.use_direct_context}
                    indexed={file.indexed}
                    chunkCount={file.chunk_count}
                  />
                ))}
              </Box>
            </Collapse>
          </Box>
        )}

        {showStatusPill && (
          <Box
            sx={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 0.75,
              mb: 1.5,
              padding: '6px 12px',
              borderRadius: '999px',
              background: statusContent.background,
              border: `1px solid ${statusContent.borderColor}`,
              color: statusContent.color,
              boxShadow: '0 6px 12px rgba(0,0,0,0.05)',
            }}
          >
            {statusContent.icon}
            <Typography sx={{ fontSize: '12px', fontWeight: 600 }}>
              {statusContent.text}
            </Typography>
          </Box>
        )}

        <Box
          sx={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 1.5,
            background: '#fff9f3',
            border: '1px solid var(--sand-border)',
            borderRadius: '26px',
            padding: '14px 18px',
            transition: 'all 0.2s ease',
            boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.4)',
            '&:focus-within': {
              borderColor: 'var(--accent)',
              boxShadow: '0 0 0 4px rgba(220, 141, 106, 0.12)',
            },
          }}
        >
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              height: '40px',
            }}
          >
            <IconButton
              size="small"
              onClick={handleFileSelect}
              disabled={isLoading}
              sx={{
                width: 40,
                height: 40,
                borderRadius: '14px',
                background: 'var(--sand)',
                color: 'var(--muted-ink)',
                '&:hover': {
                  background: 'var(--sand-soft)',
                },
                '&:disabled': {
                  opacity: 0.5,
                },
              }}
            >
              <Paperclip size={18} />
            </IconButton>
          </Box>

          <Box
            sx={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              minHeight: '36px',
            }}
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                interactionMode === 'qa'
                  ? 'Ask a question about your document...'
                  : 'How can AI help with your document?'
              }
              disabled={isLoading || hasPendingUploads || isUploading}
              style={{
                width: '100%',
                border: 'none',
                outline: 'none',
                resize: 'none',
                fontSize: '16px',
                fontFamily: '-apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif',
                lineHeight: '22px',
                padding: '8px 0',
                minHeight: '22px',
                maxHeight: '120px',
                background: 'transparent',
                color: 'var(--ink)',
              }}
            />
          </Box>

          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              height: '40px',
            }}
          >
            <IconButton
              size="small"
              onClick={handleAsk}
              disabled={!input.trim() || isLoading || hasPendingUploads || isUploading}
              sx={{
                width: 42,
                height: 42,
                borderRadius: '14px',
                background: input.trim() && !isLoading && !hasPendingUploads && !isUploading ? 'var(--accent)' : 'var(--sand-soft)',
                color: input.trim() && !isLoading && !hasPendingUploads && !isUploading ? '#FFFFFF' : 'var(--muted-ink)',
                '&:hover': {
                  background: input.trim() && !isLoading && !hasPendingUploads && !isUploading ? 'var(--accent-strong)' : 'var(--sand)',
                },
                '&:disabled': {
                  background: 'var(--sand-soft)',
                  color: 'var(--muted-ink)',
                  opacity: 0.6,
                },
              }}
            >
              {isLoading ? <CircularProgress size={16} sx={{ color: 'var(--muted-ink)' }} /> : <ArrowUp size={18} />}
            </IconButton>
          </Box>
        </Box>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".txt,.md,.pdf,.docx,.doc"
          style={{ display: 'none' }}
          onChange={(e) => handleUpload(e.target.files)}
        />
    </Box>
  );
}
