import * as React from 'react';
import * as monaco from 'monaco-editor';
import { Box, Button } from '@mui/material';
import { Check } from 'lucide-react';
import { useAuth } from '@clerk/clerk-react';
import { useApp } from '../store';

export default function Editor() {
  const { getToken } = useAuth();
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const editorRef = React.useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const doc = useApp((s) => s.document);
  const saveDoc = useApp((s) => s.saveDoc);
  const setEditBuffer = useApp((s) => s.setEditBuffer);
  const [isSaving, setIsSaving] = React.useState(false);
  const [saved, setSaved] = React.useState(false);

  React.useEffect(() => {
    if (!containerRef.current) return;

    editorRef.current = monaco.editor.create(containerRef.current, {
      value: doc?.content ?? '',
      language: 'markdown',
      automaticLayout: true,
      minimap: { enabled: false },
      fontSize: 15,
      lineHeight: 26,
      padding: { top: 24, bottom: 24 },
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      smoothScrolling: true,
      cursorBlinking: 'smooth',
      cursorSmoothCaretAnimation: 'on',
      renderLineHighlight: 'none',
      scrollBeyondLastLine: false,
      wordWrap: 'on',
      wrappingIndent: 'same',
      theme: 'vs',
      lineNumbers: 'off',
      glyphMargin: false,
      folding: false,
      lineDecorationsWidth: 0,
      lineNumbersMinChars: 0,
      renderWhitespace: 'none',
      overviewRulerBorder: false,
      hideCursorInOverviewRuler: true,
      scrollbar: {
        vertical: 'visible',
        horizontal: 'visible',
        verticalScrollbarSize: 6,
        horizontalScrollbarSize: 6,
      },
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
  }, [setEditBuffer]);

  React.useEffect(() => {
    if (doc && editorRef.current) {
      const currentValue = editorRef.current.getValue();
      if (currentValue !== doc.content) {
        editorRef.current.setValue(doc.content);
      }
    }
  }, [doc?.content]);

  const handleSave = async () => {
    const content = editorRef.current?.getValue();
    if (!content) return;
    setIsSaving(true);
    try {
      const token = await getToken();
      await saveDoc(content, token);
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

      {/* Monaco Editor Container with padding */}
      <Box
        sx={{
          flex: 1,
          overflow: 'hidden',
          background: '#FFFFFF',
          px: 4,
          py: 2,
        }}
      >
        <Box
          ref={containerRef}
          sx={{
            height: '100%',
            '& .monaco-editor': {
              '& .monaco-scrollable-element > .scrollbar > .slider': {
                background: '#E5E7EB !important',
                borderRadius: '3px',
              },
              '& .monaco-scrollable-element > .scrollbar > .slider:hover': {
                background: '#D1D5DB !important',
              },
            },
          }}
        />
      </Box>
    </Box>
  );
}