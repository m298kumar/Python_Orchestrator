import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { getAuthStatus, login as apiLogin } from '../api/client';

interface AuthContextType {
  isAuthenticated: boolean;
  authEnabled: boolean;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  error: string | null;
}

const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  authEnabled: false,
  loading: true,
  login: async () => {},
  logout: () => {},
  error: null,
});

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authEnabled, setAuthEnabled] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function check() {
      try {
        const res = await getAuthStatus();
        const enabled = res.data.auth_enabled;
        setAuthEnabled(enabled);
        if (!enabled) {
          setIsAuthenticated(true);
        } else {
          const token = localStorage.getItem('stlc_token');
          setIsAuthenticated(!!token);
        }
      } catch {
        setIsAuthenticated(true);
      } finally {
        setLoading(false);
      }
    }
    check();
  }, []);

  const login = async (username: string, password: string) => {
    setError(null);
    try {
      const res = await apiLogin(username, password);
      localStorage.setItem('stlc_token', res.data.access_token);
      setIsAuthenticated(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Login failed';
      setError(msg);
      throw err;
    }
  };

  const logout = () => {
    localStorage.removeItem('stlc_token');
    setIsAuthenticated(false);
  };

  return (
    <AuthContext.Provider
      value={{ isAuthenticated, authEnabled, loading, login, logout, error }}
    >
      {children}
    </AuthContext.Provider>
  );
}
