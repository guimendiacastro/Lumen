import type { ReactElement } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Box } from '@mui/material';

/**
 * Renders a markdown line as formatted JSX elements using react-markdown
 * Handles all standard markdown syntax
 */
export function renderMarkdownLine(line: string): ReactElement {
  // Remove the diff prefix (+, -, or spaces) to check the content
  const diffPrefix = line.substring(0, 1);
  let content = line;

  if (diffPrefix === '+' || diffPrefix === '-' || diffPrefix === ' ') {
    content = line.substring(1);
  }

  return (
    <Box
      component="span"
      sx={{
        display: 'inline',
        '& > *': {
          display: 'inline',
          margin: 0,
          padding: 0,
        },
        '& h1, & h2, & h3, & h4, & h5, & h6': {
          fontSize: 'inherit',
          fontWeight: 700,
          display: 'inline',
        },
        '& h1': { fontSize: '1.4em' },
        '& h2': { fontSize: '1.25em' },
        '& h3': { fontSize: '1.1em' },
        '& p': {
          display: 'inline',
          margin: 0,
        },
        '& strong': {
          fontWeight: 700,
        },
        '& em': {
          fontStyle: 'italic',
        },
        '& code': {
          background: '#F3F4F6',
          padding: '0.1em 0.3em',
          borderRadius: '3px',
          fontSize: '0.9em',
          fontFamily: 'monospace',
          color: '#DC2626',
        },
        '& ul, & ol': {
          display: 'inline',
          padding: 0,
          margin: 0,
          listStyle: 'none',
        },
        '& li': {
          display: 'inline',
        },
        '& li::before': {
          marginRight: '8px',
          opacity: 0.7,
        },
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Force inline rendering for all elements
          p: ({ children }) => <>{children}</>,
          h1: ({ children }) => <strong style={{ fontSize: '1.4em' }}>{children}</strong>,
          h2: ({ children }) => <strong style={{ fontSize: '1.25em' }}>{children}</strong>,
          h3: ({ children }) => <strong style={{ fontSize: '1.1em' }}>{children}</strong>,
          h4: ({ children }) => <strong style={{ fontSize: '1em' }}>{children}</strong>,
          h5: ({ children }) => <strong style={{ fontSize: '1em' }}>{children}</strong>,
          h6: ({ children }) => <strong style={{ fontSize: '1em' }}>{children}</strong>,
          ul: ({ children }) => <>{children}</>,
          ol: ({ children }) => <>{children}</>,
          li: ({ children }) => <>{children}</>,
        }}
      >
        {content}
      </ReactMarkdown>
    </Box>
  );
}
