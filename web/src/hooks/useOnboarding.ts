// web/src/hooks/useOnboarding.ts
import { useState, useEffect } from 'react';
import { useUser, useAuth } from '@clerk/clerk-react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface OnboardingStatus {
  registered: boolean;
  org_id: string | null;
  schema_name: string | null;
  vault_key_id: string | null;
}

interface OnboardingResult {
  isLoading: boolean;
  isRegistered: boolean;
  error: string | null;
  schemaName: string | null;
}

export function useOnboarding(): OnboardingResult {
  const { user } = useUser();
  const { getToken } = useAuth();
  const [isLoading, setIsLoading] = useState(true);
  const [isRegistered, setIsRegistered] = useState(false);
  const [schemaName, setSchemaName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const checkAndRegister = async () => {
      if (!user) {
        setIsLoading(false);
        return;
      }

      try {
        // Get auth token
        const token = await getToken();
        if (!token) {
          throw new Error('No authentication token available');
        }

        // Check onboarding status
        const statusRes = await fetch(`${API_URL}/onboarding/status`, {
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
        });

        if (!statusRes.ok) {
          throw new Error('Failed to check onboarding status');
        }

        const status: OnboardingStatus = await statusRes.json();

        if (status.registered) {
          setIsRegistered(true);
          setSchemaName(status.schema_name);
          setIsLoading(false);
          return;
        }

        // If not registered, register automatically
        console.log('New user detected, registering...');
        const registerRes = await fetch(`${API_URL}/onboarding/register`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
        });

        if (!registerRes.ok) {
          const errorData = await registerRes.json().catch(() => ({}));
          throw new Error(errorData.detail || 'Failed to register new member');
        }

        const result = await registerRes.json();
        console.log('Registration successful:', result);
        
        setIsRegistered(true);
        setSchemaName(result.schema_name);
        setIsLoading(false);
      } catch (err) {
        console.error('Onboarding error:', err);
        setError(err instanceof Error ? err.message : 'Unknown error');
        setIsLoading(false);
      }
    };

    checkAndRegister();
  }, [user, getToken]);

  return {
    isLoading,
    isRegistered,
    error,
    schemaName,
  };
}