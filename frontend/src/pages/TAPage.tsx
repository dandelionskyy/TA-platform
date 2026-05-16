import { useState, useEffect } from 'react';
import { useAuthStore } from '../stores/authStore';
import { api } from '../services/api';
import RobotMonitor from '../components/robot/RobotMonitor';

interface StudentUsage {
  user_id: string;
  student_id: string;
  display_name: string;
  total_chat_messages: number;
  total_conversations: number;
  last_active_at: string | null;
  total_login_count: number;
  total_robot_questions: number;
}

export default function TAPage() {
  const { user, logout } = useAuthStore();
  const [dashboard, setDashboard] = useState<any>(null);
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark');

  useEffect(() => {
    api.getTADashboard().then(setDashboard).catch(() => {});
  }, []);

  const toggleDark = () => {
    const next = !dark;
    setDark(next);
    localStorage.setItem('theme', next ? 'dark' : 'light');
    document.documentElement.classList.toggle('dark', next);
  };

  return (
    <div className="flex h-screen bg-[var(--bg-secondary)]">
      {/* Simple TA sidebar */}
      <aside className="hidden md:flex w-[220px] bg-[var(--bg-sidebar)] text-[var(--text-sidebar)] flex-col p-2.5">
        <div className="px-2.5 py-3 text-lg font-semibold border-b border-[var(--border-color)] mb-4">TA Panel</div>
        <div className="flex-1" />
        <button onClick={toggleDark} className="w-full py-2 mb-2 rounded-md bg-transparent border border-[var(--text-secondary)] text-[var(--text-sidebar)] text-sm cursor-pointer hover:bg-white/10">{dark ? 'Light' : 'Dark'}</button>
        <button onClick={logout} className="w-full py-2 rounded-md text-sm text-red-400 hover:text-red-300 cursor-pointer">Logout</button>
      </aside>

      <main className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
        {/* Mobile header */}
        <div className="md:hidden flex items-center justify-between">
          <h1 className="text-lg font-semibold">TA Panel</h1>
          <button onClick={logout} className="text-sm text-red-400">Logout</button>
        </div>

        {/* Dashboard stats */}
        {dashboard && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              ['Students', dashboard.total_students],
              ['Total Messages', dashboard.total_messages],
              ['Conversations', dashboard.total_conversations],
              ['Robot Questions', dashboard.total_robot_questions],
            ].map(([label, val]) => (
              <div key={label} className="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl p-5 text-center">
                <div className="text-3xl font-bold text-[var(--accent-color)]">{val}</div>
                <div className="text-sm text-[var(--text-secondary)] mt-2">{label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Note about permissions */}
        <div className="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl p-5">
          <h2 className="font-semibold mb-2">Usage Overview</h2>
          <p className="text-sm text-[var(--text-secondary)]">
            As a Teaching Assistant, you can view aggregate usage statistics (time and frequency).
            Detailed conversation content is accessible only to teachers.
          </p>
        </div>

        {/* Robot Monitor */}
        <div className="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl p-5">
          <h3 className="font-semibold mb-3">Robot Status</h3>
          <RobotMonitor role="ta" />
        </div>
      </main>
    </div>
  );
}
