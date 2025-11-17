// web/src/components/MessageBubble.tsx
import { Box, Typography, Paper } from '@mui/material';
import { User, Bot } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import type { MessageOut } from '../lib/api';

type MessageBubbleProps = {
  message: MessageOut;
};

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  if (isSystem) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', my: 2 }}>
        <Typography
          variant="caption"
          sx={{
            color: 'text.secondary',
            fontStyle: 'italic',
            px: 2,
            py: 0.5,
            borderRadius: 1,
            bgcolor: 'action.hover',
          }}
        >
          {message.text}
        </Typography>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: isUser ? 'row-reverse' : 'row',
        gap: 1.5,
        mb: 2,
        px: 2,
      }}
    >
      {/* Avatar */}
      <Box
        sx={{
          width: 32,
          height: 32,
          borderRadius: '50%',
          bgcolor: isUser ? 'primary.main' : 'secondary.main',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          mt: 0.5,
        }}
      >
        {isUser ? (
          <User size={18} color="white" />
        ) : (
          <Bot size={18} color="white" />
        )}
      </Box>

      {/* Message Content */}
      <Box sx={{ maxWidth: '70%', minWidth: 0 }}>
        <Paper
          elevation={1}
          sx={{
            px: 2,
            py: 1.5,
            borderRadius: 2,
            bgcolor: isUser ? 'primary.light' : 'grey.100',
            color: isUser ? 'primary.contrastText' : 'text.primary',
          }}
        >
          <Typography
            variant="body1"
            sx={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              lineHeight: 1.5,
            }}
          >
            {message.text}
          </Typography>
        </Paper>

        {/* Timestamp */}
        {message.ts && (
          <Typography
            variant="caption"
            sx={{
              display: 'block',
              mt: 0.5,
              px: 1,
              color: 'text.secondary',
              textAlign: isUser ? 'right' : 'left',
            }}
          >
            {formatDistanceToNow(new Date(message.ts), { addSuffix: true })}
          </Typography>
        )}
      </Box>
    </Box>
  );
}
