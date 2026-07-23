import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { api } from '../services/api';
import { LanguageToggle, useLanguage } from '../i18n/LanguageContext';

export default function RegisterPage() {
  const [form, setForm] = useState({ student_id: '', phone: '', password: '', sms_code: '', display_name: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const { register } = useAuthStore();
  const { text } = useLanguage();
  const navigate = useNavigate();
  const update = (field: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) => setForm(prev => ({ ...prev, [field]: event.target.value }));

  const sendCode = async () => {
    if (!/^1\d{10}$/.test(form.phone)) { setError(text('请输入有效的中国大陆手机号。', 'Enter a valid mainland China phone number.')); return; }
    setSending(true); setError('');
    try {
      await api.sendSms(form.phone);
      setCooldown(60);
      const timer = window.setInterval(() => setCooldown(value => { if (value <= 1) { window.clearInterval(timer); return 0; } return value - 1; }), 1000);
    } catch (err: any) { setError(err.message || text('验证码发送失败。', 'Unable to send code.')); }
    finally { setSending(false); }
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setError(''); setLoading(true);
    try { await register(form); navigate('/student', { replace: true }); }
    catch (err: any) { setError(err.message || text('注册失败。', 'Registration failed.')); }
    finally { setLoading(false); }
  };

  return (
    <main className="auth-page">
      <section className="auth-panel">
        <header className="mb-6"><div className="flex items-start justify-between gap-3"><div><p className="mb-2 text-xs font-semibold uppercase tracking-[.16em] text-[var(--accent-color)]">TA Platform</p><h1 className="text-2xl font-semibold">{text('创建学生账号', 'Create student account')}</h1></div><LanguageToggle /></div><p className="mt-2 text-sm muted">{text('教师和助教账号由教学团队创建。', 'Teacher and TA accounts are issued by the teaching team.')}</p></header>
        <form onSubmit={submit} className="space-y-3.5">
          <label className="block text-sm font-medium">{text('学号', 'Student ID')}<input className="auth-input mt-1.5" value={form.student_id} onChange={update('student_id')} required /></label>
          <label className="block text-sm font-medium">{text('姓名', 'Display name')} <span className="muted font-normal">({text('可选', 'optional')})</span><input className="auth-input mt-1.5" value={form.display_name} onChange={update('display_name')} /></label>
          <label className="block text-sm font-medium">{text('手机号', 'Phone number')}<input className="auth-input mt-1.5" inputMode="tel" value={form.phone} onChange={update('phone')} required /></label>
          <div className="flex gap-2"><label className="min-w-0 flex-1 text-sm font-medium">{text('验证码', 'Verification code')}<input className="auth-input mt-1.5" value={form.sms_code} onChange={update('sms_code')} required /></label><button className="btn mt-6 shrink-0" type="button" onClick={sendCode} disabled={sending || cooldown > 0}>{cooldown ? `${cooldown}s` : sending ? text('发送中', 'Sending') : text('发送验证码', 'Send code')}</button></div>
          <label className="block text-sm font-medium">{text('密码', 'Password')}<input className="auth-input mt-1.5" type="password" minLength={6} value={form.password} onChange={update('password')} autoComplete="new-password" required /></label>
          {error && <div className="auth-error" role="alert">{error}</div>}
          <button className="btn btn-primary w-full" type="submit" disabled={loading}>{loading ? text('创建中...', 'Creating account...') : text('创建账号', 'Create account')}</button>
        </form>
        <p className="mt-5 text-center text-sm muted">{text('已经注册？', 'Already registered?')} <Link className="text-[var(--accent-color)] hover:underline" to="/login">{text('登录', 'Sign in')}</Link></p>
      </section>
    </main>
  );
}
