import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { LanguageToggle, useLanguage } from '../i18n/LanguageContext';

export default function LoginPage() {
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login: doLogin } = useAuthStore();
  const { text } = useLanguage();
  const navigate = useNavigate();

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      await doLogin(login.trim(), password);
      const user = useAuthStore.getState().user;
      navigate(user?.role === 'teacher' ? '/teacher' : user?.role === 'ta' ? '/ta' : '/student', { replace: true });
    } catch (err: any) {
      setError(err.message || text('登录失败，请检查账号和密码。', 'Unable to sign in. Check your credentials.'));
    } finally { setLoading(false); }
  };

  return (
    <main className="auth-page">
      <section className="auth-panel">
        <header className="mb-7">
          <div className="flex items-start justify-between gap-3"><div><p className="mb-2 text-xs font-semibold uppercase tracking-[.16em] text-[var(--accent-color)]">TA Platform</p><h1 className="text-2xl font-semibold">{text('登录', 'Sign in')}</h1></div><LanguageToggle /></div>
          <p className="mt-2 text-sm muted">{text('使用学号或手机号登录。', 'Use your student ID or phone number.')}</p>
        </header>
        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="block text-sm font-medium">{text('学号或手机号', 'Student ID or phone')}
            <input className="auth-input mt-1.5" value={login} onChange={e => setLogin(e.target.value)} autoComplete="username" required />
          </label>
          <label className="block text-sm font-medium">{text('密码', 'Password')}
            <input className="auth-input mt-1.5" type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" required />
          </label>
          {error && <div className="auth-error" role="alert">{error}</div>}
          <button className="btn btn-primary w-full" type="submit" disabled={loading}>{loading ? text('登录中...', 'Signing in...') : text('登录', 'Sign in')}</button>
        </form>
        <p className="mt-6 text-center text-sm muted">{text('还没有学生账号？', 'New student?')} <Link className="text-[var(--accent-color)] hover:underline" to="/register">{text('注册账号', 'Create an account')}</Link></p>
      </section>
    </main>
  );
}
