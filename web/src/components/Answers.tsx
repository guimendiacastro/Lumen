import { useState } from 'react';
import { Box, Button, CircularProgress, Tabs, Tab, Chip } from '@mui/material';
import { Replace, Sparkles, TrendingUp, TrendingDown } from 'lucide-react';
import { useAuth } from '@clerk/clerk-react';
import { useApp } from '../store';
import { formatDiffWithContext, getDiffStats } from '../utils/diff';

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
  const document = useApp((s) => s.document);
  const pickAnswer = useApp((s) => s.pickAnswer);
  const [activeTab, setActiveTab] = useState(0);
  const [applying, setApplying] = useState<string | null>(null);

  const handlePick = async (card: any) => {
    setApplying(card.id);
    try {
      const token = await getToken();
      await pickAnswer(card, 'replace', token);
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
  
  // Compute diff and stats
  const diffText = document && currentAnswer
    ? formatDiffWithContext(document.content, currentAnswer.text, 3)
    : currentAnswer?.text || '';
  
  const stats = document && currentAnswer
    ? getDiffStats(document.content, currentAnswer.text)
    : { added: 0, removed: 0, modified: 0 };

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
          px: 1,
        }}
      >
        <Tabs
          value={activeTab}
          onChange={(_, newValue) => setActiveTab(newValue)}
          sx={{
            minHeight: '60px',
            '& .MuiTabs-indicator': {
              height: '3px',
              borderRadius: '3px 3px 0 0',
            },
          }}
        >
          {answers.map((answer) => {
            const color = PROVIDER_COLORS[answer.provider];
            return (
              <Tab
                key={answer.id}
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 0.5 }}>
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
                  minHeight: '60px',
                  px: 3,
                  '&.Mui-selected': {
                    color: color,
                  },
                }}
              />
            );
          })}
        </Tabs>
      </Box>

      {/* Diff Stats Bar */}
      {document && stats.modified > 0 && (
        <Box
          sx={{
            display: 'flex',
            gap: 2,
            px: 3,
            py: 2.5,
            background: '#F9FAFB',
            borderBottom: '1px solid #E5E7EB',
          }}
        >
          <Chip
            icon={<TrendingUp size={16} />}
            label={`+${stats.added} lines`}
            size="small"
            sx={{
              background: '#ECFDF5',
              color: '#059669',
              fontWeight: 600,
              fontSize: '12px',
            }}
          />
          <Chip
            icon={<TrendingDown size={16} />}
            label={`-${stats.removed} lines`}
            size="small"
            sx={{
              background: '#FEF2F2',
              color: '#DC2626',
              fontWeight: 600,
              fontSize: '12px',
            }}
          />
          <Box
            sx={{
              fontSize: '12px',
              color: '#6B7280',
              display: 'flex',
              alignItems: 'center',
              ml: 'auto',
            }}
          >
            {stats.modified} changes detected
          </Box>
        </Box>
      )}

      {/* Diff Content */}
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
            fontSize: '13px',
            fontWeight: 600,
            color: '#6B7280',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
            mb: 2,
          }}
        >
          Document Changes
        </Box>
        <Box
          sx={{
            fontSize: '13px',
            lineHeight: 1.6,
            fontFamily: 'Monaco, "Courier New", Consolas, monospace',
            background: '#F9FAFB',
            border: '1px solid #E5E7EB',
            borderRadius: '8px',
            p: 2.5,
            overflowX: 'auto',
            '& .diff-line': {
              padding: '2px 4px',
              borderRadius: '2px',
            },
          }}
        >
          {diffText.split('\n').map((line, idx) => {
            let color = '#374151';
            let background = 'transparent';
            let fontWeight = 400;
            
            if (line.startsWith('+')) {
              color = '#059669';
              background = '#ECFDF5';
              fontWeight = 500;
            } else if (line.startsWith('-')) {
              color = '#DC2626';
              background = '#FEF2F2';
              fontWeight = 500;
            } else if (line.startsWith('  ')) {
              color = '#9CA3AF';
            }
            
            return (
              <Box
                key={idx}
                className="diff-line"
                sx={{
                  color,
                  background,
                  fontWeight,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {line || ' '}
              </Box>
            );
          })}
        </Box>
      </Box>

      {/* Action Button */}
      <Box
        sx={{
          p: 3,
          borderTop: '1px solid #E5E7EB',
          background: '#FAFAFA',
          display: 'flex',
          justifyContent: 'center',
        }}
      >
        <Button
          startIcon={isApplying ? <CircularProgress size={14} /> : <Replace size={18} />}
          onClick={() => handlePick(currentAnswer)}
          disabled={isApplying}
          variant="contained"
          sx={{
            minWidth: '220px',
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