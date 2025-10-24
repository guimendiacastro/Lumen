import * as React from 'react';
import { useEditor, EditorContent, Editor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from 'tiptap-markdown';
import { Box } from '@mui/material';

interface RichTextEditorProps {
  value: string;
  onChange: (value: string) => void;
}

// Helper to safely get markdown content
function getMarkdownContent(editor: Editor): string {
  const storage = editor.storage as any;
  if (storage.markdown?.getMarkdown) {
    return storage.markdown.getMarkdown();
  }
  // Fallback to plain text if markdown storage not available
  return editor.getText();
}

export default function RichTextEditor({ value, onChange }: RichTextEditorProps) {
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
        transformPastedText: true,
        transformCopiedText: true,
      }),
    ],
    content: value,
    editorProps: {
      attributes: {
        class: 'prose prose-sm sm:prose lg:prose-lg xl:prose-2xl focus:outline-none',
        style: 'min-height: 100%; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 15px; line-height: 1.73; color: #111827;',
      },
    },
    onUpdate: ({ editor }) => {
      // Get the content as markdown
      const markdown = getMarkdownContent(editor);
      onChange(markdown);
    },
  });

  // Update editor content when value prop changes externally
  React.useEffect(() => {
    if (editor && value !== getMarkdownContent(editor)) {
      editor.commands.setContent(value);
    }
  }, [value, editor]);

  return (
    <Box
      sx={{
        height: '100%',
        overflow: 'auto',
        background: '#FFFFFF',
        '& .ProseMirror': {
          outline: 'none',
          minHeight: '100%',
          '& h1': {
            fontSize: '2em',
            fontWeight: 700,
            marginTop: '0.67em',
            marginBottom: '0.67em',
            lineHeight: 1.2,
          },
          '& h2': {
            fontSize: '1.5em',
            fontWeight: 700,
            marginTop: '0.83em',
            marginBottom: '0.83em',
            lineHeight: 1.3,
          },
          '& h3': {
            fontSize: '1.25em',
            fontWeight: 600,
            marginTop: '1em',
            marginBottom: '1em',
            lineHeight: 1.4,
          },
          '& h4': {
            fontSize: '1.1em',
            fontWeight: 600,
            marginTop: '1.33em',
            marginBottom: '1.33em',
            lineHeight: 1.4,
          },
          '& p': {
            marginTop: '0.5em',
            marginBottom: '0.5em',
          },
          '& strong': {
            fontWeight: 700,
          },
          '& em': {
            fontStyle: 'italic',
          },
          '& ul, & ol': {
            paddingLeft: '1.5em',
            marginTop: '0.5em',
            marginBottom: '0.5em',
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
          },
          '& pre': {
            background: '#F3F4F6',
            padding: '1em',
            borderRadius: '6px',
            overflow: 'auto',
            '& code': {
              background: 'none',
              padding: 0,
            },
          },
          '& hr': {
            border: 'none',
            borderTop: '2px solid #E5E7EB',
            margin: '2em 0',
          },
        },
        '&::-webkit-scrollbar': {
          width: '6px',
          height: '6px',
        },
        '&::-webkit-scrollbar-track': {
          background: 'transparent',
        },
        '&::-webkit-scrollbar-thumb': {
          background: '#E5E7EB',
          borderRadius: '3px',
          '&:hover': {
            background: '#D1D5DB',
          },
        },
      }}
    >
      <EditorContent editor={editor} />
    </Box>
  );
}
