import { Box, Button, Chip } from '@mui/material';
import { Brain, Clock, FileText, Plus } from 'lucide-react';
import { useApp } from '../store';
import { extractDraftOnly } from '../lib/extract';

const providerColors = {
  openai: { bg: '#10a37f', light: 'rgba(16, 163, 127, 0.1)', name: 'OpenAI' },
  anthropic: { bg: '#d97757', light: 'rgba(217, 119, 87, 0.1)', name: 'Anthropic' },
  xai: { bg: '#5865f2', light: 'rgba(88, 101, 242, 0.1)', name: 'xAI' },
};

export default function Answers() {
  const answers = useApp(s => s.answers);
  const pick = useApp(s => s.pickAnswer);

  const useAsDoc = async (a: any) => {
    const draft = extractDraftOnly(a.text);
    await pick({ ...a, text: draft }, 'replace');
  };

  return (
    <Box sx={{ 
      display: 'flex', 
      flexDirection: 'column',
      height: 'calc(100vh - 120px)', 
      maxHeight: 'calc(100vh - 120px)',
      overflow: 'hidden'
    }}>
      {/* Header */}
      <Box sx={{ p: 3, pb: 2, flexShrink: 0 }}>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            mb: 1,
          }}
        >
          <Brain size={20} style={{ color: '#667eea' }} />
          <Box sx={{ fontSize: '18px', fontWeight: 700, color: '#1a1a1a' }}>
            AI Responses
          </Box>
          {answers.length > 0 && (
            <Chip
              label={`${answers.length} models`}
              size="small"
              sx={{
                ml: 'auto',
                height: '24px',
                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                color: 'white',
                fontWeight: 600,
                fontSize: '11px',
              }}
            />
          )}
        </Box>
        <Box sx={{ fontSize: '13px', color: '#666', lineHeight: 1.5 }}>
          Compare responses from multiple AI models
        </Box>
      </Box>

      {/* Scrollable content area */}
      <Box sx={{ flex: '1 1 auto', overflowY: 'auto', px: 3, pb: 3 }}>
        {/* Empty State */}
        {answers.length === 0 && (
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              py: 6,
              px: 3,
              textAlign: 'center',
            }}
          >
            <Box
              sx={{
                width: 80,
                height: 80,
                borderRadius: '50%',
                background: 'linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                mb: 2,
              }}
            >
              <Brain size={36} style={{ color: '#667eea' }} />
            </Box>
            <Box sx={{ fontSize: '16px', fontWeight: 600, color: '#1a1a1a', mb: 1 }}>
              No responses yet
            </Box>
            <Box sx={{ fontSize: '13px', color: '#666', maxWidth: '280px' }}>
              Ask a question in the chat to see AI-generated responses from multiple models
            </Box>
          </Box>
        )}

        {/* Answer Cards */}
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {answers.map((a) => {
            const draft = extractDraftOnly(a.text);
            const providerInfo = providerColors[a.provider] || { bg: '#666', light: 'rgba(0,0,0,0.05)', name: a.provider };

            return (
              <Box
                key={a.id}
                sx={{
                  border: '1px solid rgba(0, 0, 0, 0.08)',
                  borderRadius: '16px',
                  overflow: 'hidden',
                  transition: 'all 0.3s ease',
                  background: 'white',
                  '&:hover': {
                    boxShadow: '0 8px 24px rgba(0, 0, 0, 0.12)',
                    transform: 'translateY(-2px)',
                  },
                }}
              >
                {/* Card Header */}
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    p: 2,
                    background: providerInfo.light,
                    borderBottom: '1px solid rgba(0, 0, 0, 0.05)',
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    <Box
                      sx={{
                        width: 32,
                        height: 32,
                        borderRadius: '8px',
                        background: providerInfo.bg,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: 'white',
                        fontWeight: 700,
                        fontSize: '14px',
                      }}
                    >
                      {providerInfo.name.charAt(0)}
                    </Box>
                    <Box>
                      <Box sx={{ fontSize: '14px', fontWeight: 700, color: '#1a1a1a' }}>
                        {providerInfo.name}
                      </Box>
                      {a.latencyMs && (
                        <Box
                          sx={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 0.5,
                            fontSize: '11px',
                            color: '#666',
                          }}
                        >
                          <Clock size={12} />
                          {a.latencyMs}ms
                        </Box>
                      )}
                    </Box>
                  </Box>
                  {a.ok && (
                    <Chip
                      label="✓ Success"
                      size="small"
                      sx={{
                        height: '22px',
                        background: 'rgba(16, 163, 127, 0.1)',
                        color: '#10a37f',
                        fontWeight: 600,
                        fontSize: '11px',
                        border: 'none',
                      }}
                    />
                  )}
                </Box>

                {/* Card Content */}
                <Box
                  sx={{
                    p: 2,
                    maxHeight: '240px',
                    overflowY: 'auto',
                    fontSize: '13px',
                    lineHeight: 1.6,
                    color: '#333',
                    fontFamily: 'monospace',
                    whiteSpace: 'pre-wrap',
                    background: '#fafafa',
                    '&::-webkit-scrollbar': {
                      width: '6px',
                    },
                    '&::-webkit-scrollbar-track': {
                      background: 'transparent',
                    },
                    '&::-webkit-scrollbar-thumb': {
                      background: 'rgba(0, 0, 0, 0.2)',
                      borderRadius: '3px',
                    },
                  }}
                >
                  {draft}
                </Box>

                {/* Card Actions */}
                <Box
                  sx={{
                    display: 'flex',
                    gap: 1,
                    p: 2,
                    borderTop: '1px solid rgba(0, 0, 0, 0.05)',
                    background: 'white',
                  }}
                >
                  <Button
                    startIcon={<FileText size={16} />}
                    onClick={() => useAsDoc(a)}
                    sx={{
                      flex: 1,
                      borderRadius: '10px',
                      textTransform: 'none',
                      fontWeight: 600,
                      fontSize: '13px',
                      py: 1,
                      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                      color: 'white',
                      '&:hover': {
                        background: 'linear-gradient(135deg, #5568d3 0%, #6a3f8f 100%)',
                      },
                    }}
                  >
                    Replace
                  </Button>
                  <Button
                    startIcon={<Plus size={16} />}
                    onClick={() => pick({ ...a, text: draft }, 'append')}
                    variant="outlined"
                    sx={{
                      flex: 1,
                      borderRadius: '10px',
                      textTransform: 'none',
                      fontWeight: 600,
                      fontSize: '13px',
                      py: 1,
                      borderColor: 'rgba(0, 0, 0, 0.2)',
                      color: '#1a1a1a',
                      '&:hover': {
                        borderColor: '#667eea',
                        background: 'rgba(102, 126, 234, 0.05)',
                      },
                    }}
                  >
                    Append
                  </Button>
                </Box>
              </Box>
            );
          })}
        </Box>
      </Box>
    </Box>
  );
}