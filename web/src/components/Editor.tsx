import * as React from 'react';
import { Box, Button } from '@mui/material';
import { Check } from 'lucide-react';
import { useAuth } from '@clerk/clerk-react';
import { useApp } from '../store';
import RichTextEditor from './RichTextEditor';

export default function Editor() {
  const { getToken } = useAuth();
  const doc = useApp((s) => s.document);
  const saveDoc = useApp((s) => s.saveDoc);
  const setEditBuffer = useApp((s) => s.setEditBuffer);
  const [isSaving, setIsSaving] = React.useState(false);
  const [saved, setSaved] = React.useState(false);
  const [editorContent, setEditorContent] = React.useState(doc?.content ?? '');

  // Update editor content when document changes
  React.useEffect(() => {
    if (doc?.content) {
      setEditorContent(doc.content);
    }
  }, [doc?.content]);

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
          borderBottom: '1px solid #E5E7EB',
          px: 4,
          py: 2.5,
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
              color: '#6B7280',
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
            }}
          >
            Document
          </Box>
          <Box sx={{ fontSize: '15px', fontWeight: 600, color: '#111827', mt: 0.5 }}>
            {doc?.title || 'Untitled'}
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
            background: saved ? '#ECFDF5' : '#000000',
            color: saved ? '#059669' : '#FFFFFF',
            border: saved ? '1px solid #D1FAE5' : 'none',
            '&:hover': {
              background: saved ? '#ECFDF5' : '#1F2937',
            },
            '&:disabled': {
              background: saved ? '#ECFDF5' : '#F3F4F6',
              color: saved ? '#059669' : '#9CA3AF',
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
          background: '#FFFFFF',
        }}
      >
        <RichTextEditor value={editorContent} onChange={handleEditorChange} />
      </Box>
    </Box>
  );
}