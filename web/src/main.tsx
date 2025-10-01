import React from 'react';
import ReactDOM from 'react-dom/client';
import { ClerkProvider, SignedIn, SignedOut, SignInButton } from '@clerk/clerk-react';
import { Box, Button, Typography, Container } from '@mui/material';
import { Sparkles, FileText, Zap, Shield } from 'lucide-react';
import App from './App';
import './index.css';

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string;
if (!clerkPubKey) {
  console.warn('VITE_CLERK_PUBLISHABLE_KEY is missing');
}

function SignInPage() {
  return (
    <Box
      sx={{
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        position: 'relative',
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        '&::before': {
          content: '""',
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'radial-gradient(circle at 20% 50%, rgba(120, 119, 198, 0.3), transparent 50%), radial-gradient(circle at 80% 80%, rgba(138, 43, 226, 0.15), transparent 50%)',
          pointerEvents: 'none',
        },
      }}
    >
      <Container maxWidth="lg">
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
            gap: 4,
            alignItems: 'center',
          }}
        >
          {/* Left side - Branding */}
          <Box sx={{ color: 'white', position: 'relative', zIndex: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 4 }}>
              <Box
                sx={{
                  width: 60,
                  height: 60,
                  borderRadius: '16px',
                  background: 'rgba(255, 255, 255, 0.2)',
                  backdropFilter: 'blur(10px)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 800,
                  fontSize: '28px',
                  border: '2px solid rgba(255, 255, 255, 0.3)',
                }}
              >
                L
              </Box>
              <Box>
                <Typography variant="h3" sx={{ fontWeight: 800, letterSpacing: '-1px' }}>
                  LUMEN
                </Typography>
                <Typography sx={{ fontSize: '12px', letterSpacing: '2px', opacity: 0.9, fontWeight: 600 }}>
                  AI-POWERED WORKSPACE
                </Typography>
              </Box>
            </Box>

            <Typography variant="h4" sx={{ fontWeight: 700, mb: 2, lineHeight: 1.3 }}>
              Your AI-Powered Document Assistant
            </Typography>
            <Typography sx={{ fontSize: '18px', mb: 4, opacity: 0.9, lineHeight: 1.6 }}>
              Collaborate with multiple AI models to draft, edit, and refine your documents with unprecedented speed and quality.
            </Typography>

            {/* Features */}
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {[
                { icon: Sparkles, text: 'Compare responses from OpenAI, Anthropic & xAI' },
                { icon: FileText, text: 'Real-time collaborative document editing' },
                { icon: Zap, text: 'Lightning-fast AI-powered drafting' },
                { icon: Shield, text: 'Secure and private by default' },
              ].map(({ icon: Icon, text }, idx) => (
                <Box
                  key={idx}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 2,
                    background: 'rgba(255, 255, 255, 0.1)',
                    backdropFilter: 'blur(10px)',
                    padding: 2,
                    borderRadius: '12px',
                    border: '1px solid rgba(255, 255, 255, 0.2)',
                  }}
                >
                  <Box
                    sx={{
                      width: 40,
                      height: 40,
                      borderRadius: '10px',
                      background: 'rgba(255, 255, 255, 0.2)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Icon size={20} />
                  </Box>
                  <Typography sx={{ fontSize: '15px', fontWeight: 500 }}>
                    {text}
                  </Typography>
                </Box>
              ))}
            </Box>
          </Box>

          {/* Right side - Sign In Card */}
          <Box
            sx={{
              position: 'relative',
              zIndex: 1,
            }}
          >
            <Box
              sx={{
                background: 'rgba(255, 255, 255, 0.95)',
                backdropFilter: 'blur(20px)',
                borderRadius: '24px',
                padding: 5,
                boxShadow: '0 20px 60px rgba(0, 0, 0, 0.3)',
                border: '1px solid rgba(255, 255, 255, 0.3)',
              }}
            >
              <Box sx={{ textAlign: 'center', mb: 4 }}>
                <Typography variant="h4" sx={{ fontWeight: 800, mb: 1, color: '#1a1a1a' }}>
                  Welcome Back
                </Typography>
                <Typography sx={{ color: '#666', fontSize: '15px' }}>
                  Sign in to access your AI workspace
                </Typography>
              </Box>

              <SignInButton mode="modal">
                <Button
                  variant="contained"
                  fullWidth
                  sx={{
                    py: 2,
                    borderRadius: '12px',
                    textTransform: 'none',
                    fontSize: '16px',
                    fontWeight: 700,
                    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                    boxShadow: '0 8px 24px rgba(102, 126, 234, 0.4)',
                    '&:hover': {
                      background: 'linear-gradient(135deg, #5568d3 0%, #6a3f8f 100%)',
                      boxShadow: '0 12px 32px rgba(102, 126, 234, 0.5)',
                      transform: 'translateY(-2px)',
                    },
                    transition: 'all 0.3s ease',
                  }}
                >
                  Sign In with Clerk
                </Button>
              </SignInButton>

              <Box sx={{ mt: 4, textAlign: 'center' }}>
                <Typography sx={{ fontSize: '13px', color: '#999', mb: 2 }}>
                  Trusted by professionals worldwide
                </Typography>
                <Box
                  sx={{
                    display: 'flex',
                    justifyContent: 'center',
                    gap: 3,
                    opacity: 0.6,
                  }}
                >
                  {['OpenAI', 'Anthropic', 'xAI'].map(provider => (
                    <Box
                      key={provider}
                      sx={{
                        px: 2,
                        py: 1,
                        background: 'rgba(0, 0, 0, 0.05)',
                        borderRadius: '8px',
                        fontSize: '12px',
                        fontWeight: 600,
                        color: '#666',
                      }}
                    >
                      {provider}
                    </Box>
                  ))}
                </Box>
              </Box>
            </Box>

            {/* Floating elements for visual interest */}
            <Box
              sx={{
                position: 'absolute',
                top: -20,
                right: -20,
                width: 100,
                height: 100,
                borderRadius: '50%',
                background: 'rgba(255, 255, 255, 0.1)',
                backdropFilter: 'blur(10px)',
                zIndex: -1,
              }}
            />
            <Box
              sx={{
                position: 'absolute',
                bottom: -30,
                left: -30,
                width: 150,
                height: 150,
                borderRadius: '50%',
                background: 'rgba(255, 255, 255, 0.1)',
                backdropFilter: 'blur(10px)',
                zIndex: -1,
              }}
            />
          </Box>
        </Box>
      </Container>
    </Box>
  );
}

function Root() {
  return (
    <ClerkProvider publishableKey={clerkPubKey}>
      <SignedIn>
        <App />
      </SignedIn>
      <SignedOut>
        <SignInPage />
      </SignedOut>
    </ClerkProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);