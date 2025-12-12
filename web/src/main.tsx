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

export function SignInPage() {
  return (
    <Box
      sx={{
        minHeight: '100vh',
        background:
          'radial-gradient(circle at 16% 24%, rgba(220, 141, 106, 0.18), transparent 32%), radial-gradient(circle at 82% 12%, rgba(192, 103, 66, 0.14), transparent 26%), linear-gradient(135deg, #fdf8f1 0%, #f3e9dc 42%, #f8f5ee 100%)',
        color: 'var(--ink)',
        position: 'relative',
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        px: { xs: 2, md: 4 },
        py: { xs: 4, md: 8 },
      }}
    >
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          background:
            'radial-gradient(circle at 50% 65%, rgba(255, 255, 255, 0.5), transparent 36%), radial-gradient(circle at 12% 90%, rgba(220, 141, 106, 0.08), transparent 24%)',
          pointerEvents: 'none',
        }}
      />
      <Container maxWidth="lg" sx={{ position: 'relative', zIndex: 1 }}>
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: '1.05fr 0.95fr' },
            gap: { xs: 2.5, md: 3 },
            alignItems: 'stretch',
          }}
        >
          <Box
            sx={{
              background: 'var(--card)',
              borderRadius: '28px',
              border: '1px solid var(--sand-border)',
              boxShadow: '0 22px 60px rgba(51, 41, 32, 0.12)',
              p: { xs: 3, md: 4 },
              display: 'flex',
              flexDirection: 'column',
              gap: 2.5,
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            <Box
              sx={{
                position: 'absolute',
                inset: 0,
                background:
                  'radial-gradient(circle at 20% 10%, rgba(220, 141, 106, 0.12), transparent 30%), radial-gradient(circle at 90% 70%, rgba(192, 103, 66, 0.08), transparent 26%)',
                pointerEvents: 'none',
              }}
            />
            <Box sx={{ position: 'relative', zIndex: 1, display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <Box
                sx={{
                  width: 52,
                  height: 52,
                  borderRadius: '14px',
                  background: 'var(--card)',
                  border: '1px solid var(--sand-border)',
                  boxShadow: '0 14px 36px rgba(51, 41, 32, 0.12)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 800,
                  fontSize: '22px',
                  color: 'var(--accent-strong)',
                }}
              >
                L
              </Box>
              <Box>
                <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '-0.5px' }}>
                  Lumen
                </Typography>
                <Typography sx={{ fontSize: '12px', letterSpacing: '1.5px', textTransform: 'uppercase', color: 'var(--muted-ink)', fontWeight: 600 }}>
                  Document Intelligence
                </Typography>
              </Box>
            </Box>

            <Box sx={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              <Typography variant="h3" sx={{ fontWeight: 800, lineHeight: 1.05, letterSpacing: '-0.6px' }}>
                A calm place to ask and write.
              </Typography>
              <Typography sx={{ color: 'var(--muted-ink)', fontSize: '16px', maxWidth: 520 }}>
                Keep chat and docs side-by-side. Sign in to pick up where you left off.
              </Typography>
            </Box>

            <Box
              sx={{
                position: 'relative',
                zIndex: 1,
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' },
                gap: 1,
              }}
            >
              {[
                { icon: Sparkles, text: 'Multi-model answers' },
                { icon: FileText, text: 'Document-aware replies' },
                { icon: Shield, text: 'Clerk-secured' },
              ].map(({ icon: Icon, text }) => (
                <Box
                  key={text}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1,
                    padding: 1.5,
                    borderRadius: '14px',
                    background: 'var(--sand-soft)',
                    border: '1px solid var(--sand-border)',
                    boxShadow: '0 10px 26px rgba(51, 41, 32, 0.08)',
                  }}
                >
                  <Box
                    sx={{
                      width: 32,
                      height: 32,
                      borderRadius: '10px',
                      background: 'var(--card)',
                      border: '1px solid var(--sand-border)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: 'var(--accent-strong)',
                      flexShrink: 0,
                    }}
                  >
                    <Icon size={18} />
                  </Box>
                  <Typography sx={{ fontWeight: 600, fontSize: '13px', color: 'var(--muted-ink)' }}>{text}</Typography>
                </Box>
              ))}
            </Box>
          </Box>

          {/* Sign In Card */}
          <Box
            sx={{
              background: 'rgba(255, 253, 249, 0.92)',
              backdropFilter: 'blur(10px)',
              borderRadius: '24px',
              padding: { xs: 3, md: 4 },
              boxShadow: '0 22px 60px rgba(51, 41, 32, 0.14)',
              border: '1px solid var(--sand-border)',
              position: 'relative',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              gap: 2,
              alignSelf: 'center',
            }}
          >
            <Box
              sx={{
                position: 'absolute',
                inset: 0,
                background:
                  'radial-gradient(circle at 80% 0%, rgba(220, 141, 106, 0.12), transparent 35%), radial-gradient(circle at 10% 80%, rgba(192, 103, 66, 0.08), transparent 30%)',
                pointerEvents: 'none',
              }}
            />
            <Box sx={{ position: 'relative', zIndex: 1 }}>
              <Typography variant="h4" sx={{ fontWeight: 800, mb: 1 }}>
                Sign in
              </Typography>
              <Typography sx={{ color: 'var(--muted-ink)' }}>
                Continue to Lumen with your account.
              </Typography>
            </Box>

            <SignInButton mode="modal">
              <Button
                variant="contained"
                fullWidth
                sx={{
                  py: 2,
                  borderRadius: '14px',
                  textTransform: 'none',
                  fontSize: '16px',
                  fontWeight: 800,
                  background: 'linear-gradient(135deg, #dc8d6a 0%, #c06742 100%)',
                  boxShadow: '0 12px 28px rgba(192, 103, 66, 0.4)',
                  color: '#fffdf9',
                  '&:hover': {
                    background: 'linear-gradient(135deg, #c06742 0%, #a75131 100%)',
                    boxShadow: '0 14px 34px rgba(192, 103, 66, 0.45)',
                    transform: 'translateY(-1px)',
                  },
                  transition: 'all 0.25s ease',
                }}
              >
                Enter with Clerk
              </Button>
            </SignInButton>

            <Box
              sx={{
                position: 'relative',
                zIndex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 1.5,
                color: 'var(--muted-ink)',
                fontSize: '13px',
                flexWrap: 'wrap',
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                <Box sx={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)' }} />
                Secure by Clerk
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                <Box sx={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)' }} />
                Private by default
              </Box>
            </Box>
          </Box>
        </Box>
      </Container>
    </Box>
  );
}

export function Root() {
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
