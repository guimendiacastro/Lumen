// web/src/components/Answers.tsx
import { useState } from 'react';
import { Box, Button, CircularProgress, Tabs, Tab } from '@mui/material';
import { Plus, Replace, Sparkles } from 'lucide-react';
import { useAuth } from '@clerk/clerk-react';
import { useApp } from '../store';

const PROVIDER_LABELS: Record<string, string> = {
  openai: 'GPT-4',
  anthropic: 'Claude',
  xai: 'Grok',
};

const PROVIDER_COLORS: Record<string, string> = {
  openai: '#10A37F',
  anthropic: '#D97706',
  xai: '#000000',
};

export default function Answers() {
  const { getToken } = useAuth();
  const answers = useApp((s) => s.answers);
  const pickAnswer = useApp((s) => s.pickAnswer);
  const [activeTab, setActiveTab] = useState(0);
  const [applying, setApplying] = useState<string | null>(null);

  const handlePick = async (card: any, mode: 'append' | 'replace') => {
    setApplying(card.id);
    try {
      const token = await getToken();
      await pickAnswer(card, mode, token);
    } finally {
      setApplying(null);
    }
  };

  // Empty state
  if (answers.length === 0) {
    return (
      <Box
        sx={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#9CA3AF',
          px: 4,
          textAlign: 'center',
        }}
      >
        <Sparkles size={48} color="#D1D5DB" style={{ marginBottom: '16px' }} />
        <Box sx={{ fontSize: '18px', fontWeight: 600, color: '#6B7280', mb: 1 }}>
          Ask AI for Help
        </Box>
        <Box sx={{ fontSize: '14px', color: '#9CA3AF', maxWidth: '400px' }}>
          Type your question below to get responses from multiple AI models
        </Box>
      </Box>
    );
  }

  const currentAnswer = answers[activeTab];
  const isApplying = applying === currentAnswer?.id;
  const providerColor = PROVIDER_COLORS[currentAnswer?.provider] || '#6B7280';

  return (
    <Box
      sx={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Header with Tabs */}
      <Box
        sx={{
          borderBottom: '1px solid #E5E7EB',
          background: 'white',
        }}
      >
        <Tabs
          value={activeTab}
          onChange={(_, newValue) => setActiveTab(newValue)}
          sx={{
            px: 2,
            minHeight: '56px',
            '& .MuiTabs-indicator': {
              height: '3px',
              borderRadius: '3px 3px 0 0',
            },
          }}
        >
          {answers.map((answer, index) => {
            const color = PROVIDER_COLORS[answer.provider];
            return (
              <Tab
                key={answer.id}
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box
                      sx={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: answer.ok ? color : '#EF4444',
                      }}
                    />
                    <Box sx={{ fontWeight: 600 }}>
                      {PROVIDER_LABELS[answer.provider] || answer.provider}
                    </Box>
                    {answer.latencyMs && (
                      <Box sx={{ fontSize: '11px', color: '#9CA3AF', fontWeight: 500 }}>
                        {answer.latencyMs}ms
                      </Box>
                    )}
                  </Box>
                }
                sx={{
                  textTransform: 'none',
                  fontSize: '14px',
                  minHeight: '56px',
                  '&.Mui-selected': {
                    color: color,
                  },
                }}
              />
            );
          })}
        </Tabs>
      </Box>

      {/* Answer Content */}
      <Box
        sx={{
          flex: 1,
          overflowY: 'auto',
          p: 3,
          background: 'white',
        }}
      >
        <Box
          sx={{
            fontSize: '15px',
            lineHeight: 1.7,
            color: '#374151',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
          }}
        >
          {currentAnswer?.text}
        </Box>
      </Box>

      {/* Action Buttons */}
      <Box
        sx={{
          p: 3,
          borderTop: '1px solid #E5E7EB',
          background: '#FAFAFA',
          display: 'flex',
          gap: 2,
        }}
      >
        <Button
          startIcon={isApplying ? <CircularProgress size={14} /> : <Plus size={18} />}
          onClick={() => handlePick(currentAnswer, 'append')}
          disabled={isApplying}
          variant="outlined"
          sx={{
            flex: 1,
            py: 1.5,
            borderRadius: '10px',
            textTransform: 'none',
            fontWeight: 600,
            fontSize: '14px',
            borderColor: '#E5E7EB',
            color: '#374151',
            '&:hover': {
              background: '#F9FAFB',
              borderColor: '#D1D5DB',
            },
            '&:disabled': {
              background: '#F3F4F6',
              color: '#9CA3AF',
            },
          }}
        >
          Append to Document
        </Button>
        <Button
          startIcon={isApplying ? <CircularProgress size={14} /> : <Replace size={18} />}
          onClick={() => handlePick(currentAnswer, 'replace')}
          disabled={isApplying}
          variant="contained"
          sx={{
            flex: 1,
            py: 1.5,
            borderRadius: '10px',
            textTransform: 'none',
            fontWeight: 600,
            fontSize: '14px',
            background: providerColor,
            color: 'white',
            boxShadow: 'none',
            '&:hover': {
              background: providerColor,
              opacity: 0.9,
              boxShadow: 'none',
            },
            '&:disabled': {
              background: '#F3F4F6',
              color: '#9CA3AF',
            },
          }}
        >
          Replace Document
        </Button>
      </Box>
    </Box>
  );
}