import * as React from 'react';
import { Box, Button } from '@mui/material';
import { Check } from 'lucide-react';
import { useAuth } from '@clerk/clerk-react';
import { useApp } from '../store';
import RichTextEditor from './RichTextEditor';

export default function Editor() {
  const { getToken } = useAuth();
  const doc = useApp((s) => s.document);
  const threadId = useApp((s) => s.threadId);
  const threads = useApp((s) => s.threads);
  const saveDoc = useApp((s) => s.saveDoc);
  const setEditBuffer = useApp((s) => s.setEditBuffer);
  const [isSaving, setIsSaving] = React.useState(false);
  const [saved, setSaved] = React.useState(false);
  const [editorContent, setEditorContent] = React.useState(doc?.content ?? '');

  // Get current thread title
  const currentThread = threads.find(t => t.id === threadId);
  const displayTitle = currentThread?.title || doc?.title || 'Untitled';

  // Update editor content when document changes
  React.useEffect(() => {
    if (doc?.content) {
      setEditorContent(doc.content);
    }
  }, [doc?.content, doc?.id]);

  const handleEditorChange = (content: string) => {
    setEditorContent(content);
    setEditBuffer(content);
    setSaved(false);
  };

  const handleSave = async () => {
    if (!editorContent) return;
    setIsSaving(true);
    try {
      const token = await getToken();
      await saveDoc(editorContent, token);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <Box
        sx={{
          borderBottom: '1px solid var(--sand-border)',
          px: { xs: 3, md: 5 },
          py: 3,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          }}
      >
        <Box>
          <Box
            sx={{
              fontSize: '12px',
              fontWeight: 600,
              color: 'var(--muted-ink)',
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
            }}
          >
            Document
          </Box>
          <Box sx={{ fontSize: '18px', fontWeight: 600, color: 'var(--ink)', mt: 0.5 }}>
            {displayTitle}
          </Box>
        </Box>

        <Button
          startIcon={saved ? <Check size={16} /> : null}
          onClick={handleSave}
          disabled={isSaving || saved}
          sx={{
            borderRadius: '6px',
            textTransform: 'none',
            fontWeight: 600,
            fontSize: '13px',
            px: 2,
            py: 1,
            background: saved ? 'rgba(13,129,95,0.12)' : 'var(--accent)',
            color: saved ? '#0d815f' : '#FFFFFF',
            border: saved ? '1px solid rgba(13,129,95,0.3)' : 'none',
            '&:hover': {
              background: saved ? 'rgba(13,129,95,0.2)' : 'var(--accent-strong)',
            },
            '&:disabled': {
              background: saved ? 'rgba(13,129,95,0.12)' : '#F3F4F6',
              color: saved ? '#0d815f' : '#9CA3AF',
            },
            transition: 'all 0.15s ease',
          }}
        >
          {isSaving ? 'Saving...' : saved ? 'Saved' : 'Save'}
        </Button>
      </Box>

      {/* Rich Text Editor Container */}
      <Box
        sx={{
          flex: 1,
          overflow: 'hidden',
          background: 'var(--card)',
        }}
      >
        <RichTextEditor value={editorContent} onChange={handleEditorChange} />
      </Box>
    </Box>
  );
}
