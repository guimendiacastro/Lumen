import { Box } from '@mui/material';
import Chat from './components/Chat';
import Answers from './components/Answers';
import Editor from './components/Editor';

export default function App() {
  return (
    <Box
      sx={{
        height: '100vh',
        background: '#FAFAFA',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Minimal Header */}
      <Box
        sx={{
          background: '#FFFFFF',
          borderBottom: '1px solid #E5E7EB',
          height: '64px',
          display: 'flex',
          alignItems: 'center',
          px: 4,
          flexShrink: 0,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Box
            sx={{
              width: 32,
              height: 32,
              borderRadius: '6px',
              background: '#000000',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
              color: 'white',
              fontSize: '16px',
              letterSpacing: '-0.5px',
            }}
          >
            L
          </Box>
          <Box sx={{ fontSize: '20px', fontWeight: 600, color: '#111827', letterSpacing: '-0.3px' }}>
            LUMEN
          </Box>
        </Box>
      </Box>

      {/* Main Content Area - Fixed Height */}
      <Box
        sx={{
          flex: 1,
          display: 'flex',
          px: 3,
          py: 3,
          gap: 3,
          maxWidth: '1800px',
          width: '100%',
          margin: '0 auto',
          overflow: 'hidden',
          minHeight: 0, // Critical for flexbox scrolling
        }}
      >
        {/* AI Responses Panel - Scrollable */}
        <Box
          sx={{
            width: '480px',
            background: '#FFFFFF',
            border: '1px solid #E5E7EB',
            borderRadius: '8px',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            minHeight: 0, // Critical for flexbox scrolling
          }}
        >
          <Answers />
        </Box>

        {/* Document Editor Panel - Scrollable */}
        <Box
          sx={{
            flex: 1,
            background: '#FFFFFF',
            border: '1px solid #E5E7EB',
            borderRadius: '8px',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            minHeight: 0, // Critical for flexbox scrolling
          }}
        >
          <Editor />
        </Box>
      </Box>

      {/* Floating Chat Input */}
      <Chat />
    </Box>
  );
}