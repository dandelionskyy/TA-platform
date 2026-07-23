import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import RobotMonitor from '../components/robot/RobotMonitor';
import { LanguageToggle, useLanguage } from '../i18n/LanguageContext';
import { api } from '../services/api';
import { useAuthStore } from '../stores/authStore';

interface StudentUsage {
  user_id: string;
  student_id: string;
  display_name: string;
  total_chat_messages: number;
  total_conversations: number;
  total_login_count: number;
  last_active_at?: string | null;
}

export default function TAPage() {
  const { user, logout } = useAuthStore();
  const { text, locale } = useLanguage();
  const [dashboard, setDashboard] = useState<any>();
  const [students, setStudents] = useState<StudentUsage[]>([]);
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark');

  useEffect(() => {
    api.getTADashboard().then(setDashboard).catch(() => {});
    api.getTAStudents().then(data => setStudents(data.students || [])).catch(() => {});
  }, []);

  const toggleDark = () => {
    const next = !dark;
    setDark(next);
    localStorage.setItem('theme', next ? 'dark' : 'light');
    document.documentElement.classList.toggle('dark', next);
  };
  const metrics: [string, number][] = [
    [text('学生数', 'Students'), dashboard?.total_students || 0],
    [text('消息数', 'Messages'), dashboard?.total_messages || 0],
    [text('会话数', 'Conversations'), dashboard?.total_conversations || 0],
    [text('机器人提问', 'Robot questions'), dashboard?.total_robot_questions || 0],
  ];

  return <div className="app-shell">
    <aside className="sidebar hidden md:flex">
      <div className="sidebar-header"><div className="sidebar-brand">TA Platform</div><LanguageToggle /></div>
      <div className="px-2.5 py-3 text-xs text-[#9b9ca3]">{text('助教工作台', 'Teaching assistant workspace')}</div>
      <nav className="sidebar-scroll">
        <div className="sidebar-section-title">{text('工作区', 'Workspace')}</div>
        <Link to="/ta" className="sidebar-item active block">{text('工作概览', 'Overview')}</Link>
        <Link to="/ta/materials" className="sidebar-item block">{text('课程资料', 'Course materials')}</Link>
        <Link to="/ta/assignments" className="sidebar-item block">{text('作业批改', 'Grading queue')}</Link>
        <Link to="/ta/attendance" className="sidebar-item block">{text('考勤管理', 'Attendance')}</Link>
        <Link to="/ta/announcements" className="sidebar-item block">{text('课程通知', 'Announcements')}</Link>
        <Link to="/ta/messages" className="sidebar-item block">{text('师生沟通', 'Messages')}</Link>
        <div className="sidebar-section-title">{text('权限说明', 'Access policy')}</div>
        <p className="px-2.5 text-xs leading-5 text-[#9b9ca3]">{text('可以查看学生姓名和统计数据，但不能查看 AI 对话内容。', 'Student names and usage counts are visible; AI conversation content is restricted to teachers.')}</p>
      </nav>
      <div className="sidebar-footer">
        <button className="btn w-full border-white/20 bg-transparent text-sm text-white" onClick={toggleDark}>{dark ? text('浅色主题', 'Light theme') : text('深色主题', 'Dark theme')}</button>
        <button className="btn-danger mt-2 w-full text-sm" onClick={logout}>{text('退出登录', 'Log out')}</button>
        <div className="mt-2 truncate px-1 text-xs text-[#9b9ca3]">{user?.display_name || user?.student_id}</div>
      </div>
    </aside>
    <main className="workspace overflow-y-auto">
      <header className="mobile-header"><strong>{text('助教工作台', 'Teaching assistant workspace')}</strong><LanguageToggle /><Link className="btn ml-auto" to="/ta/messages">{text('消息', 'Messages')}</Link><button className="btn" onClick={logout}>{text('退出', 'Log out')}</button></header>
      <div className="mx-auto w-full max-w-6xl space-y-5 p-4 md:p-7">
        <div><p className="text-xs font-semibold uppercase tracking-[.14em] text-[var(--accent-color)]">{text('助教工作台', 'Teaching assistant')}</p><h1 className="mt-1 text-2xl font-semibold">{text('工作概览', 'Usage overview')}</h1><p className="mt-1 text-sm muted">{text('查看负责课程的学习活跃度，不接触学生 AI 对话内容。', 'Monitor assigned-course activity without opening student AI conversations.')}</p></div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{metrics.map(([label, value]) => <div className="panel metric" key={label}><div className="metric-value">{value}</div><div className="mt-1 text-xs muted">{label}</div></div>)}</div>
        <section className="panel overflow-hidden"><div className="flex items-center justify-between border-b border-[var(--border-color)] px-4 py-3"><h2 className="font-semibold">{text('学生活跃度', 'Student activity')}</h2><span className="text-xs muted">{text('仅显示统计', 'Counts only')}</span></div><div className="overflow-x-auto"><table className="w-full min-w-[620px] text-left text-sm"><thead className="bg-[var(--bg-secondary)] text-xs muted"><tr><th className="px-4 py-3 font-medium">{text('学生', 'Student')}</th><th className="px-4 py-3 font-medium">{text('消息', 'Messages')}</th><th className="px-4 py-3 font-medium">{text('会话', 'Conversations')}</th><th className="px-4 py-3 font-medium">{text('登录', 'Logins')}</th><th className="px-4 py-3 font-medium">{text('最近活跃', 'Last active')}</th></tr></thead><tbody>{students.map(student => <tr key={student.user_id} className="border-t border-[var(--border-color)]"><td className="px-4 py-3"><div className="font-medium">{student.display_name || student.student_id}</div><div className="text-xs muted">{student.student_id}</div></td><td className="px-4 py-3">{student.total_chat_messages}</td><td className="px-4 py-3">{student.total_conversations}</td><td className="px-4 py-3">{student.total_login_count}</td><td className="px-4 py-3 muted">{student.last_active_at ? new Date(student.last_active_at).toLocaleString(locale) : '—'}</td></tr>)}</tbody></table>{students.length === 0 && <p className="px-4 py-8 text-center text-sm muted">{text('暂无已分配学生。', 'No assigned students yet.')}</p>}</div></section>
        <section className="panel p-4"><h2 className="mb-3 font-semibold">{text('机器人状态', 'Robot status')}</h2><RobotMonitor role="ta" /></section>
      </div>
    </main>
  </div>;
}
