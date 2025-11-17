import { useState } from 'react';
import { Box, IconButton, LinearProgress } from '@mui/material';
import { X, FileText, File, Check, Loader2 } from 'lucide-react';

interface FileChipProps {
  filename: string;
  fileId: string;
  onRemove: (fileId: string) => void;
  useDirectContext?: boolean;
  indexed?: boolean;
  chunkCount?: number;
}

export default function FileChip({ filename, fileId, onRemove, useDirectContext, indexed, chunkCount }: FileChipProps) {
  const [isHovered, setIsHovered] = useState(false);

  const getFileIcon = (name: string) => {
    const ext = name.split('.').pop()?.toLowerCase();
    if (ext === 'pdf' || ext === 'txt' || ext === 'md' || ext === 'doc' || ext === 'docx') {
      return <FileText size={14} />;
    }
    return <File size={14} />;
  };

  // Determine if file is still indexing
  const isIndexing = !useDirectContext && !indexed;
  const isReady = useDirectContext || indexed;

  return (
    <Box
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      sx={{
        display: 'inline-flex',
        flexDirection: 'column',
        gap: 0.5,
        background: 'var(--sand)',
        border: '1px solid var(--sand-border)',
        borderRadius: '12px',
        padding: '8px 12px',
        maxWidth: '220px',
        transition: 'all 0.2s ease',
        '&:hover': {
          background: '#fff',
          borderColor: 'var(--sand-border)',
          boxShadow: '0 10px 20px rgba(46,34,24,0.08)',
        },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, width: '100%' }}>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            color: 'var(--muted-ink)',
          }}
        >
          {getFileIcon(filename)}
        </Box>
        <Box
          sx={{
            fontSize: '13px',
            color: 'var(--ink)',
            fontWeight: 500,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            flex: 1,
          }}
        >
          {filename}
        </Box>

        {/* Status Icon */}
        <Box sx={{ display: 'flex', alignItems: 'center', marginLeft: 'auto' }}>
          {isReady ? (
            <Check size={14} color="#0d815f" />
          ) : (
            <Loader2 size={14} color="#bb5142" className="spinner" />
          )}
        </Box>

        {isHovered && (
          <IconButton
            size="small"
            onClick={() => onRemove(fileId)}
            sx={{
              width: 18,
              height: 18,
              padding: 0,
              marginLeft: 0.5,
              color: 'var(--muted-ink)',
              '&:hover': {
                background: 'var(--sand)',
                color: 'var(--ink)',
              },
            }}
          >
            <X size={12} />
          </IconButton>
        )}
      </Box>

      {/* Indexing Progress Bar */}
      {isIndexing && (
        <Box sx={{ width: '100%' }}>
          <LinearProgress
            sx={{
              height: 2,
              borderRadius: 1,
              backgroundColor: 'rgba(0,0,0,0.05)',
              '& .MuiLinearProgress-bar': {
                backgroundColor: '#bb5142',
              },
            }}
          />
          <Box sx={{ fontSize: '10px', color: 'var(--muted-ink)', mt: 0.5 }}>
            Indexing{chunkCount ? ` (${chunkCount} chunks)` : '...'}
          </Box>
        </Box>
      )}

      {/* Ready/Indexed Status */}
      {isReady && !useDirectContext && (
        <Box sx={{ fontSize: '10px', color: '#0d815f', fontWeight: 600 }}>
          Indexed ({chunkCount || 0} chunks)
        </Box>
      )}
    </Box>
  );
}
