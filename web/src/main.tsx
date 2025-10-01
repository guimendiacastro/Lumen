import React from 'react'
import ReactDOM from 'react-dom/client'
import { ClerkProvider, SignedIn, SignedOut, SignInButton } from '@clerk/clerk-react'
import { Box, Button, Typography } from '@mui/material'
import App from './App'
import './index.css'

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string
if (!clerkPubKey) {
  console.warn('VITE_CLERK_PUBLISHABLE_KEY is missing')
}

function Root() {
  return (
    <ClerkProvider publishableKey={clerkPubKey}>
      <SignedIn>
        <App />
      </SignedIn>
      <SignedOut>
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center',
            height: '100vh',
            background: 'linear-gradient(135deg, #f5f7fa, #c3cfe2)',
          }}
        >
          <Box
            sx={{
              backgroundColor: 'white',
              padding: 4,
              borderRadius: 2,
              boxShadow: 3,
              textAlign: 'center',
              maxWidth: 400,
              width: '100%',
            }}
          >
            <Typography variant="h3" component="h1" gutterBottom>
              Welcome to LUMEN
            </Typography>
            <Typography variant="body1" gutterBottom>
              Please sign in to continue.
            </Typography>
            <Box mt={3}>
              <SignInButton mode="modal">
                <Button variant="contained" color="primary" size="large">
                  Sign In
                </Button>
              </SignInButton>
            </Box>
          </Box>
        </Box>
      </SignedOut>
    </ClerkProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
)
