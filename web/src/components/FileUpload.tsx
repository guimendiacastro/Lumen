import { useState, useRef, useEffect } from 'react';
import { Box, CircularProgress, IconButton, LinearProgress } from '@mui/material';
import { Upload, X, File, Check, AlertCircle, Loader2 } from 'lucide-react';
import { useAuth } from '@clerk/clerk-react';
import { useApp } from '../store';
import type { FileUploadResponse } from '../lib/api';

interface FileWithStatus extends FileUploadResponse {
  indexed?: boolean;
  chunk_count_actual?: number;
  polling?: boolean;
}

interface FileUploadProps {
  threadId?: string;
  documentId?: string;
  onUploadComplete?: (files: FileUploadResponse[]) => void;
}

export default function FileUpload({ threadId, documentId, onUploadComplete }: FileUploadProps) {
  const { getToken } = useAuth();
  const addUploadedFile = useApp((s) => s.addUploadedFile);
  const [uploading, setUploading] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<FileWithStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadedFilesRef = useRef<FileWithStatus[]>(uploadedFiles);

  useEffect(() => {
    uploadedFilesRef.current = uploadedFiles;
  }, [uploadedFiles]);

  // Poll for indexing status with exponential backoff
  useEffect(() => {
    let pollInterval = 3000; // Start at 3 seconds
    const maxInterval = 30000; // Max 30 seconds
    let timeoutId: NodeJS.Timeout | null = null;
    let isActive = true;

    const pollIndexingStatus = async () => {
      if (!isActive) return;

      const filesNeedingPolling = uploadedFilesRef.current.filter(
        (f) => !f.use_direct_context && f.status === 'ready' && !f.indexed
      );

      if (filesNeedingPolling.length === 0) {
        pollInterval = 3000; // Reset when no files to poll
      }

      if (filesNeedingPolling.length > 0) {
        try {
          const token = await getToken();
          if (!token) return;

          for (const file of filesNeedingPolling) {
            const response = await fetch(
              `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/files/${file.file_id}/status`,
              {
                headers: {
                  Authorization: `Bearer ${token}`,
                },
              }
            );

            if (response.ok) {
              const status = await response.json();
              setUploadedFiles((prev) =>
                prev.map((f) =>
                  f.file_id === file.file_id
                    ? {
                        ...f,
                        indexed: status.indexed,
                        chunk_count_actual: status.chunk_count,
                        polling: !status.indexed,
                      }
                    : f
                )
              );
            }
          }

          // Exponential backoff: increase interval by 1.5x each time, max 30s
          pollInterval = Math.min(pollInterval * 1.5, maxInterval);
        } catch (err) {
          console.error('Failed to poll indexing status:', err);
        }
      }

      // Keep polling regardless of whether there was work this cycle
      if (isActive) {
        timeoutId = setTimeout(pollIndexingStatus, pollInterval);
      }
    };

    // Start polling immediately
    pollIndexingStatus();

    return () => {
      isActive = false;
      if (timeoutId) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
    };
  }, [getToken]); // Removed uploadedFiles from deps to prevent restart on every update

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    setUploading(true);
    setError(null);

    try {
      const token = await getToken();
      if (!token) {
        throw new Error('Not authenticated');
      }

      const uploadPromises = Array.from(files).map(async (file) => {
        const formData = new FormData();
        formData.append('file', file);
        if (threadId) formData.append('thread_id', threadId);
        if (documentId) formData.append('document_id', documentId);

        const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/files/upload`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
          },
          body: formData,
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || 'Upload failed');
        }

        return await response.json();
      });

      const results = await Promise.all(uploadPromises);
      setUploadedFiles((prev) => [...prev, ...results]);

      // Add each file to global state
      results.forEach((file) => addUploadedFile(file));

      onUploadComplete?.(results);
    } catch (err: any) {
      setError(err.message || 'Failed to upload files');
    } finally {
      setUploading(false);
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleUpload(e.dataTransfer.files);
    }
  };

  const removeFile = async (fileId: string) => {
    try {
      const token = await getToken();
      if (!token) {
        throw new Error('Not authenticated');
      }

      await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/files/${fileId}/delete`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      setUploadedFiles((prev) => prev.filter((f) => f.file_id !== fileId));
    } catch (err) {
      console.error('Failed to delete file:', err);
    }
  };

  return (
    <Box sx={{ width: '100%' }}>
      {/* Upload Area */}
      <Box
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        sx={{
          border: dragActive ? '2px dashed var(--accent)' : '2px dashed var(--sand-border)',
          borderRadius: '20px',
          p: 3,
          textAlign: 'center',
          background: dragActive ? 'rgba(220,141,106,0.08)' : 'var(--card)',
          cursor: 'pointer',
          transition: 'all 0.2s ease',
          '&:hover': {
            borderColor: 'var(--accent)',
            background: '#fff9f5',
          },
          boxShadow: dragActive ? '0 20px 48px rgba(220,141,106,0.25)' : 'inset 0 1px 0 rgba(255,255,255,0.6)',
        }}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={(e) => handleUpload(e.target.files)}
          style={{ display: 'none' }}
          accept=".txt,.md,.pdf,.docx,.doc"
        />

        {uploading ? (
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 2, py: 1 }}>
            <CircularProgress size={18} sx={{ color: '#667eea' }} />
            <Box sx={{ fontSize: '13px', color: '#6B7280', fontWeight: 500 }}>
              Uploading...
            </Box>
          </Box>
        ) : (
          <>
            <Upload size={28} color="#c7784a" style={{ marginBottom: '8px' }} />
            <Box sx={{ fontSize: '15px', fontWeight: 600, color: 'var(--ink)', mb: 0.5 }}>
              Drop files or click to upload
            </Box>
            <Box sx={{ fontSize: '12px', color: 'var(--muted-ink)' }}>
              PDF, DOCX, TXT, MD up to 30MB
            </Box>
          </>
        )}
      </Box>

      {/* Error Message */}
      {error && (
        <Box
          sx={{
            mt: 2,
            p: 2,
            background: 'rgba(176, 65, 50, 0.08)',
            border: '1px solid rgba(176, 65, 50, 0.4)',
            borderRadius: '12px',
            display: 'flex',
            alignItems: 'center',
            gap: 1,
          }}
        >
          <AlertCircle size={16} color="#DC2626" />
          <Box sx={{ fontSize: '13px', color: '#b04132', fontWeight: 500 }}>
            {error}
          </Box>
        </Box>
      )}

      {/* Uploaded Files List */}
      {uploadedFiles.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Box
            sx={{
              fontSize: '12px',
              fontWeight: 600,
              color: 'var(--muted-ink)',
              mb: 1,
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
            }}
          >
            Uploaded Files ({uploadedFiles.length})
          </Box>

          {uploadedFiles.map((file) => (
            <Box
              key={file.file_id}
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                p: 2,
                mb: 1.5,
                background: 'var(--card)',
                border: '1px solid var(--sand-border)',
                borderRadius: '18px',
                boxShadow: '0 14px 36px rgba(46,34,24,0.08)',
                '&:hover': {
                  borderColor: 'var(--accent)',
                },
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flex: 1, minWidth: 0 }}>
                <Box
                  sx={{
                    width: 36,
                    height: 36,
                    borderRadius: '10px',
                    background: 'var(--sand)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <File size={16} color="#a0765b" />
                </Box>

                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Box
                    sx={{
                      fontSize: '13px',
                      fontWeight: 600,
                      color: 'var(--ink)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {file.filename}
                  </Box>
                  <Box sx={{ fontSize: '11px', color: 'var(--muted-ink)', mt: 0.5 }}>
                    {formatFileSize(file.size_bytes)}
                    {file.use_direct_context ? (
                      <Box component="span" sx={{ ml: 1, color: '#0d815f', fontWeight: 600 }}>
                        • Direct Context
                      </Box>
                    ) : file.indexed ? (
                      <Box component="span" sx={{ ml: 1, color: '#0d815f', fontWeight: 600 }}>
                        • Indexed ({file.chunk_count_actual || 0} chunks)
                      </Box>
                    ) : (
                      <Box component="span" sx={{ ml: 1, color: '#bb5142', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
                        <Loader2 size={10} color="#bb5142" className="spinner" />
                        • Indexing...
                      </Box>
                    )}
                  </Box>

                  {/* Indexing Progress Bar */}
                  {!file.use_direct_context && !file.indexed && (
                    <Box sx={{ mt: 1 }}>
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
                      <Box sx={{ fontSize: '10px', color: 'var(--muted-ink)', mt: 0.5, fontStyle: 'italic' }}>
                        Azure is chunking and indexing your document...
                      </Box>
                    </Box>
                  )}
                </Box>
              </Box>

              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                {file.status === 'ready' && (file.use_direct_context || file.indexed) && (
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.5,
                      px: 1.5,
                      py: 0.5,
                      background: 'rgba(13,129,95,0.12)',
                      borderRadius: '999px',
                    }}
                  >
                    <Check size={10} color="#0d815f" />
                    <Box sx={{ fontSize: '10px', fontWeight: 600, color: '#0d815f' }}>
                      Ready
                    </Box>
                  </Box>
                )}

                {file.status === 'ready' && !file.use_direct_context && !file.indexed && (
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.5,
                      px: 1.5,
                      py: 0.5,
                      background: 'rgba(187,81,66,0.12)',
                      borderRadius: '999px',
                    }}
                  >
                    <CircularProgress size={10} sx={{ color: '#bb5142' }} />
                    <Box sx={{ fontSize: '10px', fontWeight: 600, color: '#bb5142' }}>
                      Indexing
                    </Box>
                  </Box>
                )}

                <IconButton
                  size="small"
                  onClick={() => removeFile(file.file_id)}
                  sx={{
                    width: 20,
                    height: 20,
                    color: 'var(--muted-ink)',
                    '&:hover': { background: 'var(--sand)', color: 'var(--ink)' },
                  }}
                >
                  <X size={12} />
                </IconButton>
              </Box>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
