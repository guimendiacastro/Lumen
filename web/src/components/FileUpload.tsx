// web/src/components/FileUpload.tsx
import { useState, useRef } from 'react';
import { Box, CircularProgress, IconButton } from '@mui/material';
import { Upload, X, File, Check, AlertCircle } from 'lucide-react';
import { useAuth } from '@clerk/clerk-react';
import type { FileUploadResponse } from '../lib/api';

interface FileUploadProps {
  threadId?: string;
  documentId?: string;
  onUploadComplete?: (files: FileUploadResponse[]) => void;
  onClose?: () => void;
}

export default function FileUpload({ threadId, documentId, onUploadComplete, onClose }: FileUploadProps) {
  const { getToken } = useAuth();
  const [uploading, setUploading] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<FileUploadResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
      // Get auth token
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

      // Call delete API
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
          border: dragActive ? '2px dashed #000' : '2px dashed #E5E7EB',
          borderRadius: '8px',
          p: 3,
          textAlign: 'center',
          background: dragActive ? '#F9FAFB' : '#FAFAFA',
          cursor: 'pointer',
          transition: 'all 0.2s ease',
          '&:hover': {
            borderColor: '#9CA3AF',
            background: '#F9FAFB',
          },
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
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 2 }}>
            <CircularProgress size={20} sx={{ color: '#6B7280' }} />
            <Box sx={{ fontSize: '14px', color: '#6B7280', fontWeight: 500 }}>
              Uploading and processing...
            </Box>
          </Box>
        ) : (
          <>
            <Upload size={32} color="#9CA3AF" style={{ marginBottom: '12px' }} />
            <Box sx={{ fontSize: '14px', fontWeight: 600, color: '#111827', mb: 0.5 }}>
              Drop files here or click to upload
            </Box>
            <Box sx={{ fontSize: '12px', color: '#6B7280' }}>
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
            background: '#FEF2F2',
            border: '1px solid #FCA5A5',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            gap: 1,
          }}
        >
          <AlertCircle size={16} color="#DC2626" />
          <Box sx={{ fontSize: '13px', color: '#DC2626', fontWeight: 500 }}>
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
              color: '#6B7280',
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
                mb: 1,
                background: '#FFFFFF',
                border: '1px solid #E5E7EB',
                borderRadius: '6px',
                '&:hover': {
                  borderColor: '#D1D5DB',
                },
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flex: 1, minWidth: 0 }}>
                <Box
                  sx={{
                    width: 32,
                    height: 32,
                    borderRadius: '6px',
                    background: '#F3F4F6',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <File size={16} color="#6B7280" />
                </Box>

                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Box
                    sx={{
                      fontSize: '13px',
                      fontWeight: 600,
                      color: '#111827',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {file.filename}
                  </Box>
                  <Box sx={{ fontSize: '11px', color: '#6B7280', mt: 0.25 }}>
                    {formatFileSize(file.size_bytes)}
                    {file.use_direct_context ? (
                      <Box component="span" sx={{ ml: 1, color: '#059669', fontWeight: 600 }}>
                        • Direct Context
                      </Box>
                    ) : (
                      <Box component="span" sx={{ ml: 1, color: '#2563EB', fontWeight: 600 }}>
                        • RAG ({file.chunk_count} chunks)
                      </Box>
                    )}
                  </Box>
                </Box>
              </Box>

              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                {file.status === 'ready' && (
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.5,
                      px: 1.5,
                      py: 0.5,
                      background: '#ECFDF5',
                      borderRadius: '4px',
                    }}
                  >
                    <Check size={12} color="#059669" />
                    <Box sx={{ fontSize: '11px', fontWeight: 600, color: '#059669' }}>
                      Ready
                    </Box>
                  </Box>
                )}

                <IconButton
                  size="small"
                  onClick={() => removeFile(file.file_id)}
                  sx={{
                    width: 24,
                    height: 24,
                    '&:hover': { background: '#F3F4F6' },
                  }}
                >
                  <X size={14} color="#6B7280" />
                </IconButton>
              </Box>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}