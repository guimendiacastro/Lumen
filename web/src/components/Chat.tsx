// web/src/components/Chat.tsx - REPLACE entire file

import { Box, CircularProgress, IconButton } from '@mui/material';
import { ArrowUp, Paperclip, X } from 'lucide-react';
import { useApp } from '../store';
import { useEffect, useState, useRef } from 'react';
import FileUpload from './FileUpload';

export default function Chat() {
  const ready = useApp(s => s.ready);
  const error = useApp(s => s.error);
  const init = useApp(s => s.init);
  const createDoc = useApp(s => s.createDocumentAndThread);
  const input = useApp(s => s.input);
  const setInput = useApp(s => s.setInput);
  const askAI = useApp(s => s.askAI);
  const doc = useApp(s => s.document);
  const threadId = useApp(s => s.threadId);
  const [isLoading, setIsLoading] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    (async () => {
      await init();
      await createDoc();
    })();
  }, []);

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
    await askAI();
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
          width: 'calc(100% - 96px)',
          maxWidth: '800px',
          zIndex: 1000,
        }}
      >
        <Box
          sx={{
            background: '#FEF2F2',
            border: '1px solid #FCA5A5',
            color: '#991B1B',
            p: 2,
            borderRadius: '8px',
            fontSize: '14px',
            fontWeight: 500,
          }}
        >
          {error}
        </Box>
      </Box>
    );
  }

  if (!ready || !doc) {
    return (
      <Box
        sx={{
          position: 'fixed',
          bottom: 24,
          left: '50%',
          transform: 'translateX(-50%)',
          width: 'calc(100% - 96px)',
          maxWidth: '800px',
          zIndex: 1000,
        }}
      >
        <Box
          sx={{
            background: '#FFFFFF',
            border: '1px solid #E5E7EB',
            borderRadius: '12px',
            p: 2,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 2,
          }}
        >
          <CircularProgress size={20} sx={{ color: '#6B7280' }} />
          <Box sx={{ fontSize: '14px', color: '#6B7280', fontWeight: 500 }}>
            Initializing...
          </Box>
        </Box>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        position: 'fixed',
        bottom: 24,
        left: '50%',
        transform: 'translateX(-50%)',
        width: 'calc(100% - 96px)',
        maxWidth: '800px',
        zIndex: 1000,
      }}
    >
      {/* File Upload Panel - Shows above chat input when active */}
      {showUpload && (
        <Box
          sx={{
            background: '#FFFFFF',
            border: '1px solid #E5E7EB',
            borderRadius: '12px',
            boxShadow: '0 4px 16px rgba(0, 0, 0, 0.08)',
            mb: 2,
            p: 2,
          }}
        >
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Box sx={{ fontSize: '14px', fontWeight: 600, color: '#111827' }}>
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
            threadId={threadId || undefined}
            documentId={doc?.id}
            onUploadComplete={(files) => {
              console.log('Files uploaded:', files);
              // Optionally close the upload panel after successful upload
              // setShowUpload(false);
            }}
          />
        </Box>
      )}

      {/* Chat Input Box */}
      <Box
        sx={{
          background: '#FFFFFF',
          border: '1px solid #E5E7EB',
          borderRadius: '12px',
          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.08)',
        }}
      >
        <Box sx={{ display: 'flex', gap: 1.5, p: 1.5, alignItems: 'flex-end' }}>
          {/* File Upload Button */}
          <IconButton
            onClick={() => setShowUpload(!showUpload)}
            disabled={isLoading}
            sx={{
              width: '44px',
              height: '44px',
              minWidth: '44px',
              minHeight: '44px',
              borderRadius: '8px',
              background: showUpload ? '#F3F4F6' : 'transparent',
              color: showUpload ? '#111827' : '#6B7280',
              '&:hover': {
                background: '#F3F4F6',
              },
              '&:disabled': {
                color: '#D1D5DB',
              },
            }}
          >
            <Paperclip size={20} />
          </IconButton>

          {/* Text Input */}
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask LUMEN..."
            disabled={isLoading}
            style={{
              flex: 1,
              minHeight: '44px',
              maxHeight: '120px',
              padding: '12px 14px',
              border: 'none',
              borderRadius: '8px',
              fontSize: '15px',
              fontWeight: 400,
              color: '#111827',
              outline: 'none',
              resize: 'none',
              fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
              background: 'transparent',
              lineHeight: '1.5',
            }}
          />

          {/* Send Button */}
          <Box
            component="button"
            onClick={handleAsk}
            disabled={!input.trim() || isLoading}
            sx={{
              width: '44px',
              height: '44px',
              minWidth: '44px',
              minHeight: '44px',
              borderRadius: '8px',
              border: 'none',
              background: input.trim() && !isLoading ? '#000000' : '#F3F4F6',
              color: input.trim() && !isLoading ? '#FFFFFF' : '#9CA3AF',
              cursor: input.trim() && !isLoading ? 'pointer' : 'not-allowed',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.15s ease',
              '&:hover': {
                background: input.trim() && !isLoading ? '#1F2937' : '#F3F4F6',
              },
            }}
          >
            {isLoading ? (
              <CircularProgress size={18} sx={{ color: '#FFFFFF' }} />
            ) : (
              <ArrowUp size={20} strokeWidth={2.5} />
            )}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}