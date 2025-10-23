import { useState, useRef, useEffect } from 'react';
import { Box, CircularProgress, IconButton, Dialog } from '@mui/material';
import { ArrowUp, Paperclip, X } from 'lucide-react';
import { useAuth } from '@clerk/clerk-react';
import { useApp } from '../store';
import FileUpload from './FileUpload';

export default function QuestionBar() {
  const { getToken } = useAuth();
  const ready = useApp((s) => s.ready);
  const error = useApp((s) => s.error);
  const init = useApp((s) => s.init);
  const createDoc = useApp((s) => s.createDocumentAndThread);
  const input = useApp((s) => s.input);
  const setInput = useApp((s) => s.setInput);
  const askAI = useApp((s) => s.askAI);
  const doc = useApp((s) => s.document);
  const threadId = useApp((s) => s.threadId);
  const [isLoading, setIsLoading] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    (async () => {
      const token = await getToken();
      await init(token);
      await createDoc(token);
    })();
  }, [getToken, init, createDoc]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const scrollHeight = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = Math.min(scrollHeight, 120) + 'px';
    }
  }, [input]);

  const handleAsk = async () => {
    if (!input.trim() || isLoading) return;
    setIsLoading(true);
    const token = await getToken();
    await askAI(token);
    setIsLoading(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
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

  return (
    <>
      {/* File Upload Dialog */}
      <Dialog
        open={showUpload && !!threadId}
        onClose={() => setShowUpload(false)}
        maxWidth="sm"
        fullWidth
        PaperProps={{
          sx: {
            borderRadius: '12px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
          },
        }}
      >
        <Box sx={{ p: 3 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2.5 }}>
            <Box sx={{ fontSize: '16px', fontWeight: 700, color: '#111827' }}>
              Upload Files
            </Box>
            <IconButton
              size="small"
              onClick={() => setShowUpload(false)}
              sx={{
                width: 28,
                height: 28,
                '&:hover': { background: '#F3F4F6' },
              }}
            >
              <X size={16} color="#6B7280" />
            </IconButton>
          </Box>

          <FileUpload
            threadId={threadId}
            documentId={doc?.id}
            onUploadComplete={(files) => {
              console.log('Files uploaded:', files);
            }}
          />
        </Box>
      </Dialog>

      {/* Question Bar */}
      <Box
        sx={{
          borderTop: '1px solid #E5E7EB',
          background: 'white',
          boxShadow: '0 -4px 16px rgba(0, 0, 0, 0.04)',
        }}
      >
        {/* Input Area */}
        <Box sx={{ p: 3 }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 1.5,
              background: '#F9FAFB',
              border: '2px solid #E5E7EB',
              borderRadius: '16px',
              padding: '10px 14px',
              transition: 'all 0.2s ease',
              '&:focus-within': {
                borderColor: '#667eea',
                background: 'white',
              },
            }}
          >
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                height: '36px',
              }}
            >
              <IconButton
                size="small"
                onClick={() => setShowUpload(!showUpload)}
                disabled={isLoading}
                sx={{
                  width: 36,
                  height: 36,
                  borderRadius: '8px',
                  background: showUpload ? '#E0E7FF' : 'transparent',
                  color: showUpload ? '#667eea' : '#6B7280',
                  '&:hover': {
                    background: showUpload ? '#E0E7FF' : '#F3F4F6',
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
                placeholder="Ask AI to help with your document..."
                disabled={isLoading}
                style={{
                  width: '100%',
                  border: 'none',
                  outline: 'none',
                  resize: 'none',
                  fontSize: '15px',
                  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                  lineHeight: '20px',
                  padding: '8px 0',
                  minHeight: '20px',
                  maxHeight: '120px',
                  background: 'transparent',
                  color: '#111827',
                }}
              />
            </Box>

            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                height: '36px',
              }}
            >
              <IconButton
                size="small"
                onClick={handleAsk}
                disabled={!input.trim() || isLoading}
                sx={{
                  width: 36,
                  height: 36,
                  borderRadius: '8px',
                  background: input.trim() && !isLoading ? '#667eea' : '#F3F4F6',
                  color: input.trim() && !isLoading ? '#FFFFFF' : '#9CA3AF',
                  '&:hover': {
                    background: input.trim() && !isLoading ? '#5568D3' : '#F3F4F6',
                  },
                  '&:disabled': {
                    background: '#F3F4F6',
                    color: '#9CA3AF',
                  },
                }}
              >
                {isLoading ? <CircularProgress size={16} sx={{ color: '#9CA3AF' }} /> : <ArrowUp size={18} />}
              </IconButton>
            </Box>
          </Box>
        </Box>
      </Box>
    </>
  );
}