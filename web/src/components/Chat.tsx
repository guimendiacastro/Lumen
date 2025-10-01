import { Box, TextField, Button, Chip, CircularProgress } from '@mui/material';
import { Send, Sparkles } from 'lucide-react';
import { useApp } from '../store';
import { useEffect, useState } from 'react';

export default function Chat() {
  const ready = useApp(s => s.ready);
  const error = useApp(s => s.error);
  const init = useApp(s => s.init);
  const createDoc = useApp(s => s.createDocumentAndThread);
  const input = useApp(s => s.input);
  const setInput = useApp(s => s.setInput);
  const askAI = useApp(s => s.askAI);
  const doc = useApp(s => s.document);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    (async () => {
      await init();
      await createDoc();
    })();
  }, []);

  const handleAsk = async () => {
    setIsLoading(true);
    await askAI();
    setIsLoading(false);
  };

  if (error) {
    return (
      <Box sx={{ p: 3 }}>
        <Box
          sx={{
            background: 'linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%)',
            color: 'white',
            p: 2,
            borderRadius: '12px',
            fontSize: '14px',
          }}
        >
          ⚠️ {error}
        </Box>
      </Box>
    );
  }

  if (!ready || !doc) {
    return (
      <Box sx={{ p: 3, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
        <CircularProgress size={40} sx={{ color: '#667eea' }} />
        <Box sx={{ fontSize: '14px', color: '#666' }}>Initializing workspace...</Box>
      </Box>
    );
  }

  return (
    <Box sx={{ 
      display: 'flex', 
      flexDirection: 'column',
      height: 'calc(100vh - 120px)', 
      maxHeight: 'calc(100vh - 120px)',
      p: 3 
    }}>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            mb: 1,
          }}
        >
          <Sparkles size={20} style={{ color: '#667eea' }} />
          <Box sx={{ fontSize: '18px', fontWeight: 700, color: '#1a1a1a' }}>
            AI Assistant
          </Box>
        </Box>
        <Box sx={{ fontSize: '13px', color: '#666', lineHeight: 1.5 }}>
          Ask questions or request drafts for your document
        </Box>
      </Box>

      {/* Current Document Info */}
      <Box
        sx={{
          mb: 3,
          p: 2,
          background: 'linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%)',
          borderRadius: '12px',
          border: '1px solid rgba(102, 126, 234, 0.2)',
        }}
      >
        <Box sx={{ fontSize: '11px', color: '#667eea', fontWeight: 600, mb: 0.5, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          Active Document
        </Box>
        <Box sx={{ fontSize: '14px', fontWeight: 600, color: '#1a1a1a' }}>
          {doc.title}
        </Box>
      </Box>

      {/* Input Area */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <TextField
          fullWidth
          multiline
          rows={4}
          placeholder="Ask something about your document or request a new clause..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              handleAsk();
            }
          }}
          disabled={isLoading}
          sx={{
            '& .MuiOutlinedInput-root': {
              borderRadius: '16px',
              backgroundColor: 'white',
              fontSize: '14px',
              '& fieldset': {
                borderColor: 'rgba(0, 0, 0, 0.1)',
              },
              '&:hover fieldset': {
                borderColor: '#667eea',
              },
              '&.Mui-focused fieldset': {
                borderColor: '#667eea',
                borderWidth: '2px',
              },
            },
          }}
        />

        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box sx={{ fontSize: '12px', color: '#999' }}>
            Press ⌘+Enter to send
          </Box>
          <Button
            variant="contained"
            endIcon={isLoading ? <CircularProgress size={16} sx={{ color: 'white' }} /> : <Send size={16} />}
            onClick={handleAsk}
            disabled={!input.trim() || isLoading}
            sx={{
              borderRadius: '12px',
              textTransform: 'none',
              fontWeight: 600,
              px: 3,
              py: 1,
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              boxShadow: '0 4px 12px rgba(102, 126, 234, 0.4)',
              '&:hover': {
                background: 'linear-gradient(135deg, #5568d3 0%, #6a3f8f 100%)',
                boxShadow: '0 6px 16px rgba(102, 126, 234, 0.5)',
              },
              '&:disabled': {
                background: '#e0e0e0',
                color: '#999',
              },
            }}
          >
            {isLoading ? 'Processing...' : 'Ask AI'}
          </Button>
        </Box>
      </Box>

      {/* Suggestions */}
      <Box sx={{ mt: 3 }}>
        <Box sx={{ fontSize: '12px', color: '#666', mb: 1.5, fontWeight: 600 }}>
          Quick suggestions:
        </Box>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
          {[
            'Summarize this document',
            'Add a conclusion',
            'Improve clarity',
            'Draft introduction',
          ].map(suggestion => (
            <Chip
              key={suggestion}
              label={suggestion}
              onClick={() => setInput(suggestion)}
              size="small"
              sx={{
                borderRadius: '8px',
                border: '1px solid rgba(102, 126, 234, 0.3)',
                background: 'white',
                fontSize: '12px',
                fontWeight: 500,
                transition: 'all 0.2s ease',
                '&:hover': {
                  background: 'linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%)',
                  borderColor: '#667eea',
                  transform: 'translateY(-1px)',
                },
              }}
            />
          ))}
        </Box>
      </Box>
    </Box>
  );
}