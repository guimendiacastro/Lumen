import { Box, Button } from '@mui/material';
import { Sparkles, Brain, Zap, ArrowRight } from 'lucide-react';
import { useApp } from '../store';
import { extractDraftOnly } from '../lib/extract';
import { useState } from 'react';

const providerConfig = {
  openai: { name: 'GPT-4', icon: Sparkles, color: '#10A37F' },
  anthropic: { name: 'Claude', icon: Brain, color: '#D97757' },
  xai: { name: 'Grok', icon: Zap, color: '#5865F2' },
};

export default function Answers() {
  const answers = useApp(s => s.answers);
  const pick = useApp(s => s.pickAnswer);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const useAsDoc = async (a: any) => {
    const draft = extractDraftOnly(a.text);
    await pick({ ...a, text: draft }, 'replace');
  };

  if (answers.length === 0) {
    return (
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          p: 4,
          textAlign: 'center',
        }}
      >
        <Box
          sx={{
            width: 56,
            height: 56,
            borderRadius: '12px',
            background: '#F9FAFB',
            border: '1px solid #E5E7EB',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            mb: 2,
          }}
        >
          <Sparkles size={28} style={{ color: '#6B7280' }} />
        </Box>
        <Box sx={{ fontSize: '15px', fontWeight: 600, color: '#111827', mb: 1 }}>
          No responses yet
        </Box>
        <Box sx={{ fontSize: '14px', color: '#6B7280', lineHeight: 1.5, maxWidth: '280px' }}>
          Ask a question to compare AI responses
        </Box>
      </Box>
    );
  }

  const selectedAnswer = answers[selectedIndex] || answers[0];
  const draft = extractDraftOnly(selectedAnswer.text);
  const config = providerConfig[selectedAnswer.provider] || {
    name: selectedAnswer.provider,
    icon: Brain,
    color: '#6B7280'
  };
  const Icon = config.icon;

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      {/* Header with model selector */}
      <Box
        sx={{
          borderBottom: '1px solid #E5E7EB',
          p: 2,
        }}
      >
        <Box sx={{ fontSize: '12px', fontWeight: 600, color: '#6B7280', mb: 1.5, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          AI Response
        </Box>
        
        {/* Model Tabs */}
        <Box sx={{ display: 'flex', gap: 1 }}>
          {answers.map((answer, idx) => {
            const cfg = providerConfig[answer.provider] || { name: answer.provider, icon: Brain, color: '#6B7280' };
            const TabIcon = cfg.icon;
            const isSelected = selectedIndex === idx;
            
            return (
              <Box
                key={answer.id}
                component="button"
                onClick={() => setSelectedIndex(idx)}
                sx={{
                  flex: 1,
                  padding: '8px 12px',
                  border: '1px solid',
                  borderColor: isSelected ? '#000000' : '#E5E7EB',
                  borderRadius: '6px',
                  background: isSelected ? '#000000' : '#FFFFFF',
                  color: isSelected ? '#FFFFFF' : '#6B7280',
                  fontWeight: 600,
                  fontSize: '13px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 0.75,
                  transition: 'all 0.15s ease',
                  '&:hover': {
                    borderColor: isSelected ? '#000000' : '#9CA3AF',
                    background: isSelected ? '#1F2937' : '#F9FAFB',
                  },
                }}
              >
                <TabIcon size={14} />
                {cfg.name}
              </Box>
            );
          })}
        </Box>
      </Box>

      {/* Content Area */}
      <Box
        sx={{
          flex: 1,
          overflowY: 'auto',
          p: 3,
          fontSize: '15px',
          lineHeight: '1.7',
          color: '#374151',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
          whiteSpace: 'pre-wrap',
          '&::-webkit-scrollbar': {
            width: '6px',
          },
          '&::-webkit-scrollbar-track': {
            background: 'transparent',
          },
          '&::-webkit-scrollbar-thumb': {
            background: '#E5E7EB',
            borderRadius: '3px',
          },
          '&::-webkit-scrollbar-thumb:hover': {
            background: '#D1D5DB',
          },
        }}
      >
        {draft}
      </Box>

      {/* Action Button */}
      <Box
        sx={{
          borderTop: '1px solid #E5E7EB',
          p: 2,
        }}
      >
        <Button
          onClick={() => useAsDoc(selectedAnswer)}
          fullWidth
          endIcon={<ArrowRight size={18} />}
          sx={{
            borderRadius: '8px',
            textTransform: 'none',
            fontWeight: 600,
            fontSize: '14px',
            py: 1.5,
            background: '#000000',
            color: '#FFFFFF',
            border: 'none',
            '&:hover': {
              background: '#1F2937',
            },
            transition: 'all 0.15s ease',
          }}
        >
          Use this response
        </Button>
      </Box>
    </Box>
  );
}