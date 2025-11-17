// web/src/components/ChatHistory.tsx
import { Box, IconButton, Paper, List, ListItem, ListItemButton, ListItemText, Typography } from '@mui/material';
import { MessageSquare } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useApp } from '../store';
import { motion, AnimatePresence } from 'framer-motion';

export function ChatHistory() {
  const messages = useApp((s) => s.messages);
  const [isOpen, setIsOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const MENU_WIDTH = 320;

  // Filter to only show user messages (questions)
  const userQuestions = messages.filter((m) => m.role === 'user');

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const left = Math.max(rect.right - MENU_WIDTH, 16) + window.scrollX;
      const top = rect.bottom + 8 + window.scrollY;
      setMenuPosition({ top, left });
    }
  }, [isOpen]);

  const handleQuestionClick = (index: number) => {
    // Close the dropdown
    setIsOpen(false);

    // Could add scroll-to functionality here if needed
    console.log('Selected question:', userQuestions[index].text);
  };

  return (
    <Box sx={{ position: 'relative' }}>
      {/* Floating Button */}
      <IconButton
        ref={buttonRef}
        onClick={() => setIsOpen(!isOpen)}
        sx={{
          width: 48,
          height: 48,
          bgcolor: 'var(--card)',
          color: 'var(--ink)',
          border: '1px solid var(--sand-border)',
          boxShadow: '0 12px 30px rgba(0,0,0,0.12)',
          '&:hover': {
            bgcolor: 'var(--sand)',
            boxShadow: '0 16px 32px rgba(0,0,0,0.15)',
          },
          transition: 'all 0.2s ease',
        }}
      >
        <MessageSquare size={20} />
      </IconButton>

      {/* Dropdown Menu */}
      {createPortal(
        <AnimatePresence>
          {isOpen && (
            <motion.div
              ref={dropdownRef}
              initial={{ opacity: 0, scale: 0.95, y: -10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: -10 }}
              transition={{ duration: 0.15, ease: 'easeOut' }}
              style={{
                position: 'absolute',
                top: menuPosition.top,
                left: menuPosition.left,
                zIndex: 2000,
              }}
            >
              <Paper
                elevation={8}
                sx={{
                  width: MENU_WIDTH,
                  maxHeight: 400,
                  overflow: 'hidden',
                  borderRadius: 3,
                  bgcolor: 'var(--card)',
                  border: '1px solid var(--sand-border)',
                  boxShadow: '0 20px 50px rgba(0,0,0,0.18)',
                }}
              >
                {/* Header */}
                <Box
                  sx={{
                    px: 2,
                    py: 1.5,
                    borderBottom: 1,
                    borderColor: 'divider',
                    bgcolor: 'background.default',
                  }}
                >
                  <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                    Your Questions
                  </Typography>
                  {userQuestions.length > 0 && (
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                      {userQuestions.length} {userQuestions.length === 1 ? 'question' : 'questions'}
                    </Typography>
                  )}
                </Box>

                {/* Questions List */}
                <Box
                  sx={{
                    maxHeight: 340,
                    overflowY: 'auto',
                    '&::-webkit-scrollbar': {
                      width: '6px',
                    },
                    '&::-webkit-scrollbar-track': {
                      background: 'transparent',
                    },
                    '&::-webkit-scrollbar-thumb': {
                      background: '#d0d0d0',
                      borderRadius: '3px',
                    },
                    '&::-webkit-scrollbar-thumb:hover': {
                      background: '#b0b0b0',
                    },
                  }}
                >
                  {userQuestions.length === 0 ? (
                    <Box sx={{ px: 3, py: 4, textAlign: 'center' }}>
                      <Typography variant="body2" color="text.secondary">
                        No questions yet. Start by asking something below.
                      </Typography>
                    </Box>
                  ) : (
                    <List disablePadding>
                      {userQuestions.map((question, index) => (
                        <ListItem key={question.id} disablePadding>
                          <ListItemButton
                            onClick={() => handleQuestionClick(index)}
                            sx={{
                              py: 1.5,
                              px: 2,
                              '&:hover': {
                                bgcolor: 'action.hover',
                              },
                            }}
                          >
                            <ListItemText
                              primary={
                                <Typography
                                  variant="body2"
                                  sx={{
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    display: '-webkit-box',
                                    WebkitLineClamp: 2,
                                    WebkitBoxOrient: 'vertical',
                                    lineHeight: 1.4,
                                  }}
                                >
                                  {index + 1}. {question.text}
                                </Typography>
                              }
                            />
                          </ListItemButton>
                        </ListItem>
                      ))}
                    </List>
                  )}
                </Box>
              </Paper>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body
      )}
    </Box>
  );
}
