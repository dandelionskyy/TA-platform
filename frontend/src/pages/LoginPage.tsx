import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';

export default function LoginPage() {
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login: doLogin } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await doLogin(login, password);
      const user = useAuthStore.getState().user;
      if (user?.role === 'teacher') navigate('/teacher');
      else if (user?.role === 'ta') navigate('/ta');
      else navigate('/student');
    } catch (err: any) {
      setError(err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="gradient-bg min-h-screen flex items-center justify-center p-4">
      <div className="glass-card w-full max-w-md p-8 md:p-10">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">TA Platform</h1>
          <p className="text-white/70 text-sm">Smart Teaching Assistant System</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <input
              type="text"
              value={login}
              onChange={e => setLogin(e.target.value)}
              placeholder="Student ID / Phone number"
              className="w-full px-4 py-3 rounded-xl bg-white/20 border border-white/30 text-white placeholder-white/60 outline-none focus:border-white/60 focus:bg-white/25 transition-all"
              required
            />
          </div>
          <div>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Password"
              className="w-full px-4 py-3 rounded-xl bg-white/20 border border-white/30 text-white placeholder-white/60 outline-none focus:border-white/60 focus:bg-white/25 transition-all"
              required
            />
          </div>
          {error && (
            <div className="text-red-300 text-sm bg-red-500/20 rounded-lg px-4 py-2">{error}</div>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl bg-white text-purple-700 font-semibold hover:bg-white/90 disabled:opacity-50 transition-all cursor-pointer"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
        <p className="text-center mt-6 text-white/70 text-sm">
          Don't have an account?{' '}
          <Link to="/register" className="text-white underline hover:text-white/90">Register</Link>
        </p>
      </div>
    </div>
  );
}
