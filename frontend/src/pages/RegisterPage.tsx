import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { api } from '../services/api';

export default function RegisterPage() {
  const [form, setForm] = useState({ student_id: '', phone: '', password: '', sms_code: '', display_name: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [sendingSms, setSendingSms] = useState(false);
  const [smsCooldown, setSmsCooldown] = useState(0);
  const { register } = useAuthStore();
  const navigate = useNavigate();

  const updateField = (field: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm(prev => ({ ...prev, [field]: e.target.value }));
  };

  const handleSendSms = async () => {
    if (!form.phone || form.phone.length < 11) {
      setError('Please enter a valid phone number');
      return;
    }
    setSendingSms(true);
    setError('');
    try {
      await api.sendSms(form.phone);
      setSmsCooldown(60);
      const timer = setInterval(() => {
        setSmsCooldown(prev => {
          if (prev <= 1) { clearInterval(timer); return 0; }
          return prev - 1;
        });
      }, 1000);
    } catch (err: any) {
      setError(err.message || 'Failed to send SMS');
    } finally {
      setSendingSms(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await register(form);
      navigate('/student');
    } catch (err: any) {
      setError(err.message || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="gradient-bg min-h-screen flex items-center justify-center p-4">
      <div className="glass-card w-full max-w-md p-8 md:p-10">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Create Account</h1>
          <p className="text-white/70 text-sm">Register for TA Platform</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <input type="text" value={form.student_id} onChange={updateField('student_id')}
            placeholder="Student ID" className="w-full px-4 py-3 rounded-xl bg-white/20 border border-white/30 text-white placeholder-white/60 outline-none focus:border-white/60 focus:bg-white/25 transition-all" required />
          <input type="text" value={form.display_name} onChange={updateField('display_name')}
            placeholder="Display Name (optional)" className="w-full px-4 py-3 rounded-xl bg-white/20 border border-white/30 text-white placeholder-white/60 outline-none focus:border-white/60 focus:bg-white/25 transition-all" />
          <input type="text" value={form.phone} onChange={updateField('phone')}
            placeholder="Phone Number" className="w-full px-4 py-3 rounded-xl bg-white/20 border border-white/30 text-white placeholder-white/60 outline-none focus:border-white/60 focus:bg-white/25 transition-all" required />
          <div className="flex gap-2">
            <input type="text" value={form.sms_code} onChange={updateField('sms_code')}
              placeholder="SMS Code" className="flex-1 px-4 py-3 rounded-xl bg-white/20 border border-white/30 text-white placeholder-white/60 outline-none focus:border-white/60 focus:bg-white/25 transition-all" required />
            <button type="button" onClick={handleSendSms} disabled={smsCooldown > 0 || sendingSms}
              className="px-4 py-3 rounded-xl bg-white/30 text-white text-sm font-medium hover:bg-white/40 disabled:opacity-50 transition-all whitespace-nowrap cursor-pointer">
              {smsCooldown > 0 ? `${smsCooldown}s` : sendingSms ? '...' : 'Get Code'}
            </button>
          </div>
          <input type="password" value={form.password} onChange={updateField('password')}
            placeholder="Password (6+ characters)" className="w-full px-4 py-3 rounded-xl bg-white/20 border border-white/30 text-white placeholder-white/60 outline-none focus:border-white/60 focus:bg-white/25 transition-all" required minLength={6} />
          {error && (
            <div className="text-red-300 text-sm bg-red-500/20 rounded-lg px-4 py-2">{error}</div>
          )}
          <button type="submit" disabled={loading}
            className="w-full py-3 rounded-xl bg-white text-purple-700 font-semibold hover:bg-white/90 disabled:opacity-50 transition-all cursor-pointer">
            {loading ? 'Creating account...' : 'Register'}
          </button>
        </form>
        <p className="text-center mt-6 text-white/70 text-sm">
          Already have an account?{' '}
          <Link to="/login" className="text-white underline hover:text-white/90">Sign In</Link>
        </p>
      </div>
    </div>
  );
}
