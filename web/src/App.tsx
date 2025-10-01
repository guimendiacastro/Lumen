import { Box, Paper, Stack } from '@mui/material';
import Chat from './components/Chat';
import Answers from './components/Answers';
import Editor from './components/Editor';

export default function App() {
  return (
    <Box sx={{ padding: 2, backgroundColor: '#f5f5f5', minHeight: '100vh' }}>
      <Stack spacing={2} direction={{ xs: 'column', md: 'row' }}>
        <Paper elevation={3} sx={{ padding: 2, flex: 1 }}>
          <Chat />
        </Paper>
        <Paper elevation={3} sx={{ padding: 2, flex: 1 }}>
          <Answers />
        </Paper>
        <Paper elevation={3} sx={{ padding: 2, flex: 1 }}>
          <Editor />
        </Paper>
      </Stack>
    </Box>
  );
}
