import { Box, CircularProgress, Typography, IconButton } from '@mui/material';
import { Menu } from 'lucide-react';
import { useOnboarding } from './hooks/useOnboarding';
import Answers from './components/Answers';
import Editor from './components/Editor';
import QuestionBar from './components/QuestionBar';
import { ThreadSidebar } from './components/ThreadSidebar';
import { useApp } from './store';

export default function App() {
  const { isLoading, error } = useOnboarding();
  const toggleSidebar = useApp((s) => s.toggleSidebar);

  // Show loading state
  if (isLoading) {
    return (
      <Box
        sx={{
          height: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          color: 'white',
        }}
      >
        <CircularProgress size={48} sx={{ color: 'white', mb: 3 }} />
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          Setting up your workspace...
        </Typography>
        <Typography sx={{ mt: 1, opacity: 0.9, fontSize: '14px' }}>
          Creating your secure environment
        </Typography>
      </Box>
    );
  }

  // Show error state
  if (error) {
    return (
      <Box
        sx={{
          height: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#FEE2E2',
          padding: 4,
        }}
      >
        <Box
          sx={{
            maxWidth: 500,
            background: 'white',
            borderRadius: '16px',
            padding: 4,
            boxShadow: '0 4px 24px rgba(0, 0, 0, 0.1)',
            textAlign: 'center',
          }}
        >
          <Typography variant="h5" sx={{ fontWeight: 700, color: '#DC2626', mb: 2 }}>
            Setup Error
          </Typography>
          <Typography sx={{ color: '#6B7280', mb: 3 }}>
            {error}
          </Typography>
          <Typography sx={{ fontSize: '13px', color: '#9CA3AF' }}>
            Please contact support or try refreshing the page.
          </Typography>
        </Box>
      </Box>
    );
  }

  // Main app
  return (
    <Box sx={{ height: '100vh', display: 'flex', overflow: 'hidden', background: 'var(--sand)' }}>
      {/* Thread Sidebar */}
      <ThreadSidebar />

      {/* Main Container */}
      <Box
        sx={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
          overflow: 'hidden',
        }}
      >
        <Box
          sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}
        >
          {/* Floating Menu Button */}
          <IconButton
            onClick={toggleSidebar}
            sx={{
              position: 'absolute',
              top: 20,
              left: 20,
              zIndex: 100,
              width: 44,
              height: 44,
              borderRadius: '12px',
              border: '1px solid var(--sand-border)',
              background: 'var(--card)',
              color: 'var(--ink)',
              boxShadow: '0 4px 20px rgba(0,0,0,0.08)',
              '&:hover': {
                background: 'var(--sand-soft)',
                boxShadow: '0 6px 24px rgba(0,0,0,0.12)',
              },
            }}
          >
            <Menu size={20} />
          </IconButton>

          {/* Main Content */}
          <Box
            sx={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              px: { xs: 2, lg: 4 },
              py: 3,
              gap: 3,
            }}
          >
            <Box
              sx={{
                flex: 1,
                display: 'flex',
                gap: 2,
                overflow: 'hidden',
                minHeight: 0,
              }}
            >
              {/* Left: AI Answers */}
              <Box
                sx={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  overflow: 'hidden',
                  borderRadius: '28px',
                  border: '1px solid var(--sand-border)',
                  background: 'var(--card)',
                  boxShadow: '0 20px 60px rgba(51, 41, 32, 0.08)',
                  minHeight: 0,
                }}
              >
                <Answers />
              </Box>

              {/* Right: Document Editor */}
              <Box
                sx={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  overflow: 'hidden',
                  borderRadius: '28px',
                  border: '1px solid var(--sand-border)',
                  background: 'var(--card)',
                  boxShadow: '0 20px 60px rgba(51, 41, 32, 0.08)',
                  minHeight: 0,
                }}
              >
                <Editor />
              </Box>
            </Box>

            {/* Bottom: Question Bar */}
            <Box sx={{ flexShrink: 0 }}>
              <QuestionBar />
            </Box>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
