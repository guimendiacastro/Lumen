import { useState } from 'react';
import { Box, Button, CircularProgress, Tabs, Tab, Chip } from '@mui/material';
import { Replace, Sparkles, TrendingUp, TrendingDown } from 'lucide-react';
import { useAuth } from '@clerk/clerk-react';
import { useApp } from '../store';
import { formatDiffWithContext, getDiffStats } from '../utils/diff';
import { renderMarkdownLine } from '../utils/markdown-renderer';
import { ChatHistory } from './ChatHistory';

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
  const baselineDocument = useApp((s) => s.baselineDocument);
  const isLoadingAnswers = useApp((s) => s.isLoadingAnswers);
  const pickAnswer = useApp((s) => s.pickAnswer);
  const answersMode = useApp((s) => s.answersMode);
  const [activeTab, setActiveTab] = useState(0);
  const [applying, setApplying] = useState<string | null>(null);

  // Use baseline document for diff comparison if available, otherwise use current document
  const diffBaseDocument = baselineDocument || document;

  const handlePick = async (card: any) => {
    setApplying(card.id);
    try {
      const token = await getToken();
      await pickAnswer(card, 'replace', token);
    } finally {
      setApplying(null);
    }
  };

  // Loading state
  if (isLoadingAnswers) {
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
        <CircularProgress size={48} sx={{ mb: 3, color: '#667eea' }} />
        <Box sx={{ fontSize: '18px', fontWeight: 600, color: '#6B7280', mb: 1 }}>
          Getting AI Responses
        </Box>
        <Box sx={{ fontSize: '14px', color: '#9CA3AF', maxWidth: '400px' }}>
          Asking multiple AI models for their suggestions...
        </Box>
      </Box>
    );
  }

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

  // Helper to detect if document is just a placeholder
  const isPlaceholderDocument = (content: string): boolean => {
    const stripped = content.trim();
    const placeholders = ['# New Document', 'Type here', 'Start typing', 'Enter text', 'Untitled'];
    if (stripped.length < 100) {
      return placeholders.some(p => stripped.toLowerCase().includes(p.toLowerCase()));
    }
    return false;
  };

  // Only show diff if answers were generated in edit mode and the original document is not a placeholder
  const shouldShowDiff = answersMode === 'edit' && diffBaseDocument && !isPlaceholderDocument(diffBaseDocument.content);

  // Compute diff and stats using baseline document
  // Use 1 line of context to reduce showing unrelated changes
  const diffText = shouldShowDiff && currentAnswer
    ? formatDiffWithContext(diffBaseDocument.content, currentAnswer.text, 1)
    : currentAnswer?.text || '';

  const stats = shouldShowDiff && currentAnswer
    ? getDiffStats(diffBaseDocument.content, currentAnswer.text)
    : { added: 0, removed: 0, modified: 0 };

  return (
    <Box
      sx={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        background: 'transparent',
        position: 'relative',
      }}
    >
      {/* Header with Tabs */}
      <Box
        sx={{
          borderBottom: '1px solid var(--sand-border)',
          background: 'transparent',
          px: { xs: 2, md: 3 },
          display: 'flex',
          alignItems: 'center',
          gap: 2,
        }}
      >
        <Tabs
          value={activeTab}
          onChange={(_, newValue) => setActiveTab(newValue)}
          sx={{
            minHeight: '60px',
            flex: 1,
            '& .MuiTabs-indicator': {
              height: '3px',
              borderRadius: '3px 3px 0 0',
              backgroundColor: 'var(--accent)',
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
        <Box sx={{ flexShrink: 0 }}>
          <ChatHistory />
        </Box>
      </Box>

      {/* Diff Stats Bar */}
      {shouldShowDiff && stats.modified > 0 && (
        <Box sx={{ display: 'flex', gap: 2, px: { xs: 3, md: 5 }, py: 2.5, background: 'var(--sand-soft)', borderBottom: '1px solid var(--sand-border)' }}>
          <Chip
            icon={<TrendingUp size={16} />}
            label={`+${stats.added} lines`}
            size="small"
            sx={{
              background: 'rgba(13, 129, 95, 0.08)',
              color: '#0d815f',
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
          px: { xs: 3, md: 5 },
          py: 4,
          background: 'transparent',
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
          {answersMode === 'qa' ? 'Answer' : shouldShowDiff ? 'Document Changes' : 'Suggested Document'}
        </Box>
        <Box
          sx={{
            fontSize: '14px',
            lineHeight: 1.6,
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            background: 'rgba(250, 246, 238, 0.7)',
            border: '1px solid var(--sand-border)',
            borderRadius: '16px',
            p: 2.5,
            overflowX: 'auto',
            '& .diff-line': {
              padding: '4px 8px',
              borderRadius: '3px',
              marginBottom: '2px',
            },
          }}
        >
          {shouldShowDiff ? (
            // Show diff view when document is not placeholder
            diffText.split('\n').map((line, idx) => {
            let color = 'var(--ink)';
            let background = 'transparent';
            let fontWeight = 400;

            if (line.startsWith('+')) {
              color = '#0d815f';
              background = 'rgba(13,129,95,0.08)';
              fontWeight = 500;
            } else if (line.startsWith('-')) {
              color = '#bb5142';
              background = 'rgba(187, 81, 66, 0.08)';
              fontWeight = 500;
            } else if (line.startsWith('  ')) {
              color = 'var(--muted-ink)';
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
                {line.startsWith('+') || line.startsWith('-') || line.startsWith('  ') ? (
                  <>
                    <Box component="span" sx={{ opacity: 0.5, marginRight: '8px' }}>
                      {line[0]}
                    </Box>
                    {renderMarkdownLine(line)}
                  </>
                ) : (
                  line || ' '
                )}
              </Box>
            );
          })
          ) : (
            // Show full document preview when original is placeholder
            currentAnswer?.text.split('\n').map((line, idx) => (
              <Box
                key={idx}
                sx={{
                  padding: '4px 0',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {renderMarkdownLine('  ' + line)}
              </Box>
            ))
          )}
        </Box>
      </Box>

      {/* Action Button - Compact floating style (only if answers are from edit mode) */}
      {answersMode === 'edit' && (
        <Box
          sx={{
            position: 'absolute',
            bottom: 20,
            right: 20,
            zIndex: 10,
          }}
        >
          <Button
            startIcon={isApplying ? <CircularProgress size={14} sx={{ color: 'white' }} /> : <Replace size={16} />}
            onClick={() => handlePick(currentAnswer)}
            disabled={isApplying}
            variant="contained"
            sx={{
              py: 1,
              px: 2,
              borderRadius: '12px',
              textTransform: 'none',
              fontWeight: 600,
              fontSize: '13px',
              background: providerColor === '#6B7280' ? 'var(--accent)' : providerColor,
              color: 'white',
              boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
              '&:hover': {
                background: providerColor === '#6B7280' ? 'var(--accent-strong)' : providerColor,
                opacity: 0.9,
                boxShadow: '0 6px 24px rgba(0,0,0,0.2)',
              },
              '&:disabled': {
                background: '#F3F4F6',
                color: '#9CA3AF',
                boxShadow: 'none',
              },
            }}
          >
            Replace
          </Button>
        </Box>
      )}
    </Box>
  );
}
