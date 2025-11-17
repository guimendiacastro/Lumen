// web/src/components/Chat.tsx
import { Box, CircularProgress, IconButton } from '@mui/material';
import { ArrowUp, Paperclip } from 'lucide-react';
import { useAuth } from '@clerk/clerk-react';
import { useApp } from '../store';
import { useEffect, useState, useRef } from 'react';
import FileUpload from './FileUpload';

export default function Chat() {
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
          position: 'fixed',
          bottom: 24,
          left: '50%',
          transform: 'translateX(-50%)',
          background: '#FEE2E2',
          color: '#991B1B',
          px: 3,
          py: 2,
          borderRadius: '8px',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.1)',
          zIndex: 1000,
        }}
      >
        Error: {error}
      </Box>
    );
  }

  if (!ready) {
    return (
      <Box
        sx={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <CircularProgress size={32} />
      </Box>
    );
  }

  return (
    <Box
      sx={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <Box
        sx={{
          p: 2,
          borderBottom: '1px solid #E5E7EB',
        }}
      >
        <Box
          sx={{
            fontSize: '12px',
            fontWeight: 600,
            color: '#6B7280',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
          }}
        >
          Chat
        </Box>
        <Box sx={{ fontSize: '15px', fontWeight: 600, color: '#111827', mt: 0.5 }}>
          {doc?.title || 'Untitled'}
        </Box>
      </Box>

      {/* Messages Area */}
      <Box
        sx={{
          flex: 1,
          overflowY: 'auto',
          p: 2,
        }}
      >
        {/* Messages would go here */}
      </Box>

      {/* File Upload Section */}
      {showUpload && threadId && (
        <Box sx={{ px: 2, pb: 1 }}>
          <FileUpload
            threadId={threadId}
            documentId={doc?.id}
          />
        </Box>
      )}

      {/* Input Area */}
      <Box
        sx={{
          p: 2,
          borderTop: '1px solid #E5E7EB',
        }}
      >
        <Box
          sx={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: 1,
            background: 'white',
            border: '2px solid #E5E7EB',
            borderRadius: '12px',
            padding: '8px 12px',
            '&:focus-within': {
              borderColor: '#667eea',
            },
            transition: 'border-color 0.2s',
          }}
        >
          <IconButton
            size="small"
            onClick={() => setShowUpload(!showUpload)}
            sx={{
              width: 32,
              height: 32,
              color: '#6B7280',
              '&:hover': { background: '#F3F4F6' },
            }}
          >
            <Paperclip size={18} />
          </IconButton>

          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask AI for help..."
            disabled={isLoading}
            style={{
              flex: 1,
              border: 'none',
              outline: 'none',
              resize: 'none',
              fontSize: '14px',
              fontFamily: 'inherit',
              lineHeight: '20px',
              padding: '6px 0',
              minHeight: '20px',
              maxHeight: '120px',
              background: 'transparent',
            }}
          />

          <IconButton
            size="small"
            onClick={handleAsk}
            disabled={!input.trim() || isLoading}
            sx={{
              width: 32,
              height: 32,
              background: input.trim() && !isLoading ? '#000000' : '#F3F4F6',
              color: input.trim() && !isLoading ? '#FFFFFF' : '#9CA3AF',
              '&:hover': {
                background: input.trim() && !isLoading ? '#1F2937' : '#F3F4F6',
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
  );
}
