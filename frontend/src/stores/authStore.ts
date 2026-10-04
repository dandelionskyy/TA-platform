import { create } from 'zustand';
import { api } from '../services/api';

interface User {
  id: string;
  student_id: string;
  phone: string;
  display_name: string;
  role: string;
  is_active: boolean;
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  loading: boolean;
  login: (login: string, password: string) => Promise<void>;
  register: (data: { student_id: string; phone: string; password: string; sms_code: string; display_name?: string }) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
}

// An anonymous BRIDGE token must not survive an account change on a shared browser.
function clearBridgeSessions() {
  for (const key of Object.keys(localStorage)) {
    if (key.startsWith('bridge-session:')) localStorage.removeItem(key);
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: !!localStorage.getItem('access_token'),
  loading: false,

  login: async (login: string, password: string) => {
    const result = await api.login(login, password);
    clearBridgeSessions();
    localStorage.setItem('access_token', result.tokens.access_token);
    localStorage.setItem('refresh_token', result.tokens.refresh_token);
    const theme = localStorage.getItem('theme');
    if (theme) document.documentElement.classList.toggle('dark', theme === 'dark');
    set({ user: result.user, isAuthenticated: true });
  },

  register: async (data) => {
    const result = await api.register(data);
    clearBridgeSessions();
    localStorage.setItem('access_token', result.tokens.access_token);
    localStorage.setItem('refresh_token', result.tokens.refresh_token);
    set({ user: result.user, isAuthenticated: true });
  },

  logout: () => {
    clearBridgeSessions();
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    set({ user: null, isAuthenticated: false });
  },

  checkAuth: async () => {
    try {
      const user = await api.getMe();
      set({ user, isAuthenticated: true });
    } catch {
      clearBridgeSessions();
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      set({ user: null, isAuthenticated: false });
    }
  },
}));
