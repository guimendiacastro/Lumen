import { Box, CircularProgress, Typography } from '@mui/material';
import { UserButton } from '@clerk/clerk-react';
import { useOnboarding } from './hooks/useOnboarding';
import Answers from './components/Answers';
import Editor from './components/Editor';
import QuestionBar from './components/QuestionBar';

export default function App() {
  const { isLoading, isRegistered, error, schemaName } = useOnboarding();

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
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Top Bar */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          px: 4,
          py: 2.5,
          borderBottom: '1px solid #E5E7EB',
          background: 'white',
          zIndex: 10,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Box
            sx={{
              width: 36,
              height: 36,
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 800,
              fontSize: '18px',
              color: 'white',
            }}
          >
            L
          </Box>
          <Box>
            <Typography sx={{ fontSize: '18px', fontWeight: 800, lineHeight: 1 }}>
              LUMEN
            </Typography>
            {schemaName && (
              <Typography sx={{ fontSize: '10px', color: '#9CA3AF', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                {schemaName}
              </Typography>
            )}
          </Box>
        </Box>

        <UserButton
          afterSignOutUrl="/"
          appearance={{
            elements: {
              avatarBox: {
                width: 36,
                height: 36,
              },
            },
          }}
        />
      </Box>

      {/* Main Content */}
      <Box sx={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left: AI Answers */}
        <Box
          sx={{
            flex: 1,
            borderRight: '1px solid #E5E7EB',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            background: '#FAFAFA',
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
            overflow: 'hidden' 
          }}
        >
          <Editor />
        </Box>
      </Box>

      {/* Bottom: Question Bar */}
      <QuestionBar />
    </Box>
  );
}