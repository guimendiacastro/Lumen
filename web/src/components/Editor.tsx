import * as React from 'react';
import * as monaco from 'monaco-editor';
import { Box, Button, Chip } from '@mui/material';
import { Save, FileText, CheckCircle } from 'lucide-react';
import { useApp } from '../store';

export default function Editor() {
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const editorRef = React.useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const doc = useApp(s => s.document);
  const saveDoc = useApp(s => s.saveDoc);
  const setEditBuffer = useApp(s => s.setEditBuffer);
  const [isSaving, setIsSaving] = React.useState(false);
  const [saved, setSaved] = React.useState(false);
  const [editorHeight, setEditorHeight] = React.useState(600);

  React.useEffect(() => {
    if (!containerRef.current) return;
    
    editorRef.current = monaco.editor.create(containerRef.current, {
      value: doc?.content ?? '',
      language: 'markdown',
      automaticLayout: true,
      minimap: { enabled: false },
      fontSize: 14,
      lineHeight: 24,
      padding: { top: 16, bottom: 16 },
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      smoothScrolling: true,
      cursorBlinking: 'smooth',
      cursorSmoothCaretAnimation: 'on',
      renderLineHighlight: 'all',
      scrollBeyondLastLine: false,
      wordWrap: 'on',
      wrappingIndent: 'same',
      theme: 'vs',
    });

    const sub = editorRef.current.onDidChangeModelContent(() => {
      const v = editorRef.current?.getValue() ?? '';
      setEditBuffer(v);
      setSaved(false);
    });

    return () => {
      sub.dispose();
      editorRef.current?.dispose();
    };
  }, []);

  React.useEffect(() => {
    if (editorRef.current && doc) {
      const curr = editorRef.current.getValue();
      if (curr !== doc.content) {
        editorRef.current.setValue(doc.content);
        setSaved(true);
      }
    }
  }, [doc]);

  const onSave = async () => {
    if (!editorRef.current) return;
    setIsSaving(true);
    const text = editorRef.current.getValue();
    await saveDoc(text);
    setIsSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 120px)', maxHeight: 'calc(100vh - 120px)' }}>
      {/* Header */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          p: 3,
          pb: 2,
          borderBottom: '1px solid rgba(0, 0, 0, 0.05)',
          flexShrink: 0,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <FileText size={20} style={{ color: '#667eea' }} />
          <Box sx={{ fontSize: '18px', fontWeight: 700, color: '#1a1a1a' }}>
            Document Editor
          </Box>
          {saved && (
            <Chip
              icon={<CheckCircle size={14} />}
              label="Saved"
              size="small"
              sx={{
                ml: 1,
                height: '24px',
                background: 'rgba(16, 163, 127, 0.1)',
                color: '#10a37f',
                fontWeight: 600,
                fontSize: '11px',
                border: 'none',
                '& .MuiChip-icon': {
                  color: '#10a37f',
                },
              }}
            />
          )}
        </Box>
        <Button
          variant="contained"
          startIcon={isSaving ? null : <Save size={16} />}
          onClick={onSave}
          disabled={isSaving}
          sx={{
            borderRadius: '10px',
            textTransform: 'none',
            fontWeight: 600,
            fontSize: '13px',
            px: 2.5,
            py: 1,
            background: saved
              ? 'linear-gradient(135deg, #10a37f 0%, #0d8f6f 100%)'
              : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            boxShadow: '0 4px 12px rgba(102, 126, 234, 0.3)',
            transition: 'all 0.3s ease',
            '&:hover': {
              background: saved
                ? 'linear-gradient(135deg, #0d8f6f 0%, #0a7a5e 100%)'
                : 'linear-gradient(135deg, #5568d3 0%, #6a3f8f 100%)',
              boxShadow: '0 6px 16px rgba(102, 126, 234, 0.4)',
            },
            '&:disabled': {
              background: '#e0e0e0',
              color: '#999',
            },
          }}
        >
          {isSaving ? 'Saving...' : saved ? 'Saved' : 'Save Document'}
        </Button>
      </Box>

      {/* Document Info */}
      <Box
        sx={{
          px: 3,
          pt: 2,
          pb: 1.5,
          flexShrink: 0,
        }}
      >
        <Box sx={{ fontSize: '11px', color: '#667eea', fontWeight: 600, mb: 0.5, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          Currently Editing
        </Box>
        <Box sx={{ fontSize: '14px', fontWeight: 600, color: '#1a1a1a' }}>
          {doc?.title || 'Untitled Document'}
        </Box>
      </Box>

      {/* Monaco Editor */}
      <Box
        sx={{
          flex: '1 1 auto',
          mx: 3,
          mb: 3,
          minHeight: '400px',
          height: '100%',
          borderRadius: '16px',
          overflow: 'hidden',
          border: '1px solid rgba(0, 0, 0, 0.08)',
          boxShadow: 'inset 0 2px 8px rgba(0, 0, 0, 0.04)',
          background: '#fafafa',
        }}
      >
        <div ref={containerRef} style={{ height: '100%', width: '100%' }} />
      </Box>
    </Box>
  );
}