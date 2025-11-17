// web/src/components/ThreadSidebar.tsx
import {
  Box,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Typography,
  IconButton,
  TextField,
  CircularProgress,
  Divider,
  Button,
} from '@mui/material';
import { X, Plus, Edit2, Check } from 'lucide-react';
import { useState, useEffect } from 'react';
import { useApp } from '../store';
import { useAuth, UserButton } from '@clerk/clerk-react';
import { formatDistanceToNow } from 'date-fns';
import { motion, AnimatePresence } from 'framer-motion';

const SIDEBAR_WIDTH = 280;

export function ThreadSidebar() {
  const { getToken } = useAuth();
  const isSidebarOpen = useApp((s) => s.isSidebarOpen);
  const toggleSidebar = useApp((s) => s.toggleSidebar);
  const threads = useApp((s) => s.threads);
  const currentThreadId = useApp((s) => s.threadId);
  const isLoadingThreads = useApp((s) => s.isLoadingThreads);
  const loadThreads = useApp((s) => s.loadThreads);
  const switchThread = useApp((s) => s.switchThread);
  const createNewThread = useApp((s) => s.createNewThread);
  const updateThreadTitle = useApp((s) => s.updateThreadTitle);

  const [editingThreadId, setEditingThreadId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  // Load threads when sidebar opens
  useEffect(() => {
    if (isSidebarOpen) {
      const fetchThreads = async () => {
        const token = await getToken();
        loadThreads(token);
      };
      fetchThreads();
    }
  }, [isSidebarOpen, getToken, loadThreads]);

  const handleSwitchThread = async (threadId: string) => {
    try {
      const token = await getToken();
      await switchThread(threadId, token);
      toggleSidebar(); // Close sidebar after switching
    } catch (error) {
      console.error('Error switching thread:', error);
    }
  };

  const handleCreateThread = async () => {
    const token = await getToken();
    await createNewThread(token);
  };

  const handleStartEdit = (threadId: string, currentTitle?: string | null) => {
    setEditingThreadId(threadId);
    setEditTitle(currentTitle || 'Untitled');
  };

  const handleSaveEdit = async () => {
    if (!editingThreadId || !editTitle.trim()) {
      setEditingThreadId(null);
      return;
    }

    const token = await getToken();
    await updateThreadTitle(editingThreadId, editTitle.trim(), token);
    setEditingThreadId(null);
    setEditTitle('');
  };

  const handleCancelEdit = () => {
    setEditingThreadId(null);
    setEditTitle('');
  };

  return (
    <Drawer
      anchor="left"
      open={isSidebarOpen}
      onClose={toggleSidebar}
      variant="persistent"
      sx={{
        width: isSidebarOpen ? SIDEBAR_WIDTH : 0,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: SIDEBAR_WIDTH,
          boxSizing: 'border-box',
          borderRight: 'none',
          bgcolor: 'var(--sand)',
          backgroundImage: 'linear-gradient(180deg, rgba(255,255,255,0.95), rgba(248,245,238,0.9))',
          paddingBottom: 2,
        },
      }}
    >
      {/* Header */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          px: 2,
          py: 2,
          borderBottom: '1px solid var(--sand-border)',
        }}
      >
        <Typography variant="h6" sx={{ fontWeight: 600, color: 'var(--ink)' }}>
          Conversations
        </Typography>
        <IconButton size="small" onClick={toggleSidebar}>
          <X size={20} />
        </IconButton>
      </Box>

      {/* New Thread Button */}
      <Box sx={{ px: 2, py: 2 }}>
        <Button
          fullWidth
          variant="contained"
          startIcon={<Plus size={18} />}
          onClick={handleCreateThread}
          sx={{
            textTransform: 'none',
            borderRadius: 2,
            py: 1,
            background: 'var(--accent)',
            boxShadow: '0 10px 25px rgba(220, 141, 106, 0.35)',
            '&:hover': {
              background: 'var(--accent-strong)',
              boxShadow: '0 12px 28px rgba(192, 103, 66, 0.4)',
            },
          }}
        >
          New Conversation
        </Button>
      </Box>

      <Divider sx={{ borderColor: 'var(--sand-border)' }} />

      {/* Thread List */}
      <Box sx={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
        {isLoadingThreads ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress size={32} />
          </Box>
        ) : threads.length === 0 ? (
          <Box sx={{ px: 3, py: 4 }}>
            <Typography variant="body2" color="text.secondary" align="center">
              No conversations yet. Create your first one!
            </Typography>
          </Box>
        ) : (
          <List sx={{ px: 1, py: 1 }}>
            <AnimatePresence>
              {threads.map((thread) => (
                <motion.div
                  key={thread.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  transition={{ duration: 0.2 }}
                >
                  <ListItem
                    disablePadding
                    sx={{
                      mb: 0.5,
                      borderRadius: 2,
                      overflow: 'hidden',
                    }}
                  >
                    {editingThreadId === thread.id ? (
                      // Edit Mode
                      <Box
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 1,
                          width: '100%',
                          px: 1.5,
                          py: 1,
                        }}
                      >
                        <TextField
                          size="small"
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleSaveEdit();
                            if (e.key === 'Escape') handleCancelEdit();
                          }}
                          autoFocus
                          fullWidth
                          sx={{ flex: 1 }}
                        />
                        <IconButton size="small" onClick={handleSaveEdit}>
                          <Check size={16} />
                        </IconButton>
                        <IconButton size="small" onClick={handleCancelEdit}>
                          <X size={16} />
                        </IconButton>
                      </Box>
                    ) : (
                      // View Mode
                      <ListItemButton
                        selected={thread.id === currentThreadId}
                        onClick={() => handleSwitchThread(thread.id)}
                        sx={{
                          borderRadius: 2,
                          mx: 0.5,
                          border: '1px solid transparent',
                          '&.Mui-selected': {
                            bgcolor: '#FFFFFF',
                            borderColor: 'var(--sand-border)',
                            boxShadow: '0 14px 30px rgba(0,0,0,0.08)',
                            '&:hover': {
                              bgcolor: '#FFFFFF',
                            },
                          },
                          '&:hover': {
                            bgcolor: 'rgba(255,255,255,0.8)',
                            borderColor: 'var(--sand-border)',
                          },
                        }}
                      >
                        <ListItemText
                          primary={
                            <Box
                              sx={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                gap: 1,
                              }}
                            >
                              <Typography
                                variant="body2"
                                sx={{
                                  fontWeight: thread.id === currentThreadId ? 600 : 400,
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                  flex: 1,
                                }}
                              >
                                {thread.title || 'Untitled Conversation'}
                              </Typography>
                              <IconButton
                                size="small"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleStartEdit(thread.id, thread.title);
                                }}
                                sx={{ opacity: 0.6, '&:hover': { opacity: 1 } }}
                              >
                                <Edit2 size={14} />
                              </IconButton>
                            </Box>
                          }
                          secondary={
                            (thread.updated_at || thread.created_at) && (
                              <Typography variant="caption" color="text.secondary">
                                {formatDistanceToNow(new Date(thread.updated_at || thread.created_at!), {
                                  addSuffix: true,
                                })}
                              </Typography>
                            )
                          }
                        />
                      </ListItemButton>
                    )}
                  </ListItem>
                </motion.div>
              ))}
            </AnimatePresence>
          </List>
        )}
      </Box>

      {/* User Profile at Bottom */}
      <Box
        sx={{
          borderTop: '1px solid var(--sand-border)',
          px: 2,
          py: 2,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <UserButton
          afterSignOutUrl="/"
          appearance={{
            elements: {
              avatarBox: {
                width: 40,
                height: 40,
                boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
              },
            },
          }}
        />
      </Box>
    </Drawer>
  );
}
