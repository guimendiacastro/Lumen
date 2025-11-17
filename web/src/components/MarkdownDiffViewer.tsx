import * as React from 'react';
import { Box } from '@mui/material';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from 'tiptap-markdown';

interface MarkdownDiffViewerProps {
  content: string;
}

export default function MarkdownDiffViewer({ content }: MarkdownDiffViewerProps) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [1, 2, 3, 4, 5, 6],
        },
        bulletList: {
          keepMarks: true,
          keepAttributes: false,
        },
        orderedList: {
          keepMarks: true,
          keepAttributes: false,
        },
      }),
      Markdown.configure({
        html: false,
        transformPastedText: false,
        transformCopiedText: false,
      }),
    ],
    content: content,
    editable: false, // Read-only
    editorProps: {
      attributes: {
        class: 'prose prose-sm focus:outline-none',
        style: 'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 14px; line-height: 1.6; color: #111827;',
      },
    },
  });

  // Update content when prop changes
  React.useEffect(() => {
    if (editor && content) {
      editor.commands.setContent(content);
    }
  }, [content, editor]);

  return (
    <Box
      sx={{
        height: '100%',
        overflow: 'auto',
        '& .ProseMirror': {
          outline: 'none',
          padding: 0,
          '& h1': {
            fontSize: '1.75em',
            fontWeight: 700,
            marginTop: '0.5em',
            marginBottom: '0.5em',
            lineHeight: 1.2,
            color: '#111827',
          },
          '& h2': {
            fontSize: '1.4em',
            fontWeight: 700,
            marginTop: '0.75em',
            marginBottom: '0.5em',
            lineHeight: 1.3,
            color: '#111827',
          },
          '& h3': {
            fontSize: '1.2em',
            fontWeight: 600,
            marginTop: '0.75em',
            marginBottom: '0.5em',
            lineHeight: 1.4,
            color: '#1F2937',
          },
          '& h4': {
            fontSize: '1.05em',
            fontWeight: 600,
            marginTop: '0.75em',
            marginBottom: '0.5em',
            lineHeight: 1.4,
            color: '#1F2937',
          },
          '& p': {
            marginTop: '0.5em',
            marginBottom: '0.5em',
            color: '#374151',
          },
          '& strong': {
            fontWeight: 700,
            color: '#111827',
          },
          '& em': {
            fontStyle: 'italic',
          },
          '& ul, & ol': {
            paddingLeft: '1.5em',
            marginTop: '0.5em',
            marginBottom: '0.5em',
            color: '#374151',
          },
          '& li': {
            marginTop: '0.25em',
            marginBottom: '0.25em',
          },
          '& blockquote': {
            borderLeft: '3px solid #E5E7EB',
            paddingLeft: '1em',
            marginLeft: 0,
            fontStyle: 'italic',
            color: '#6B7280',
          },
          '& code': {
            background: '#F3F4F6',
            padding: '0.2em 0.4em',
            borderRadius: '3px',
            fontSize: '0.9em',
            fontFamily: 'monospace',
            color: '#DC2626',
          },
          '& pre': {
            background: '#F3F4F6',
            padding: '1em',
            borderRadius: '6px',
            overflow: 'auto',
            marginTop: '0.5em',
            marginBottom: '0.5em',
            '& code': {
              background: 'none',
              padding: 0,
              color: '#374151',
            },
          },
          '& hr': {
            border: 'none',
            borderTop: '2px solid #E5E7EB',
            margin: '1.5em 0',
          },
        },
      }}
    >
      <EditorContent editor={editor} />
    </Box>
  );
}
