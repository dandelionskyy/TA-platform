import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import { LanguageToggle, useLanguage } from '../../i18n/LanguageContext';

type Role = 'student' | 'ta' | 'teacher';

interface Props {
  role: Role;
  eyebrow: string;
  title: string;
  description?: string;
  children: React.ReactNode;
}

export default function AcademicShell({ role, eyebrow, title, description, children }: Props) {
  const { user, logout } = useAuthStore();
  const { text, locale } = useLanguage();
  const [dark, setDark] = useStateTheme();
  const links = role === 'student' ? [
    { label: text('学习概览', 'Overview'), to: '/student', end: true },
    { label: text('AI 助教', 'AI Assistant'), to: '/student/chat' },
    { label: text('BRIDGE 学习助手', 'BRIDGE tutor'), to: '/bridge' },
    { label: text('我的作业', 'My assignments'), to: '/student/assignments' },
    { label: text('签到考勤', 'Attendance'), to: '/student/attendance' },
    { label: text('课程通知', 'Announcements'), to: '/student/announcements' },
    { label: text('师生沟通', 'Messages'), to: '/student/messages' },
  ] : role === 'ta' ? [
    { label: text('工作概览', 'Overview'), to: '/ta', end: true },
    { label: text('课程资料', 'Course materials'), to: '/ta/materials' },
    { label: text('作业批改', 'Grading queue'), to: '/ta/assignments' },
    { label: text('考勤管理', 'Attendance'), to: '/ta/attendance' },
    { label: text('课程通知', 'Announcements'), to: '/ta/announcements' },
    { label: text('师生沟通', 'Messages'), to: '/ta/messages' },
  ] : [
    { label: text('教学概览', 'Overview'), to: '/teacher', end: true },
    { label: text('课程资料', 'Course materials'), to: '/teacher/materials' },
    { label: text('BRIDGE 管理', 'BRIDGE administration'), to: '/teacher/bridge' },
    { label: text('作业管理', 'Assignments'), to: '/teacher/assignments' },
    { label: text('考勤管理', 'Attendance'), to: '/teacher/attendance' },
    { label: text('课程通知', 'Announcements'), to: '/teacher/announcements' },
    { label: text('师生沟通', 'Messages'), to: '/teacher/messages' },
  ];
  const roleLabel = role === 'student' ? text('学生工作台', 'Student workspace') : role === 'ta' ? text('助教工作台', 'Teaching assistant workspace') : text('教师工作台', 'Teacher workspace');

  return (
    <div className="app-shell">
      <aside className="sidebar hidden md:flex">
        <div className="sidebar-header">
          <div className="sidebar-brand">TA Platform</div><LanguageToggle />
        </div>
        <div className="px-2.5 py-3 text-xs text-[#9b9ca3]">{roleLabel}</div>
        <nav className="sidebar-scroll px-1">
          <div className="sidebar-section-title">{text('工作区', 'Workspace')}</div>
          {links.map(link => <NavLink key={link.to} to={link.to} end={link.end} className={({ isActive }) => `sidebar-item block ${isActive ? 'active' : ''}`}>{link.label}</NavLink>)}
          <div className="sidebar-section-title border-t border-white/10">{text('课程工具', 'Course tools')}</div>
          <div className="px-2.5 py-2 text-xs leading-5 text-[#9b9ca3]">{text('课程、作业、考勤和通知按课程隔离，所有操作都会记录。', 'Courses, assignments, attendance and announcements are scoped to each course.')}</div>
        </nav>
        <div className="sidebar-footer">
          <button className="btn w-full border-white/20 bg-transparent text-sm text-white" onClick={() => setDark(!dark)}>{dark ? text('浅色主题', 'Light theme') : text('深色主题', 'Dark theme')}</button>
          <button className="btn-danger mt-2 w-full text-sm" onClick={logout}>{text('退出登录', 'Log out')}</button>
          <div className="mt-2 truncate px-1 text-xs text-[#9b9ca3]">{user?.display_name || user?.student_id}</div>
        </div>
      </aside>
      <main className="workspace overflow-y-auto">
        <header className="mobile-header sticky top-0 z-10">
          <strong>TA Platform</strong>
          <span className="ml-auto text-xs muted">{user?.display_name || user?.student_id}</span>
          <LanguageToggle /><button className="btn text-xs" onClick={logout}>{text('退出', 'Log out')}</button>
        </header>
        <nav className="flex gap-1 overflow-x-auto border-b border-[var(--border-color)] bg-[var(--bg-primary)] px-3 py-2 md:hidden">
          {links.map(link => <NavLink key={link.to} to={link.to} end={link.end} className={({ isActive }) => `whitespace-nowrap rounded-md px-3 py-2 text-xs ${isActive ? 'bg-[var(--accent-muted)] font-medium text-[var(--accent-color)]' : 'muted'}`}>{link.label}</NavLink>)}
        </nav>
        <div className="mx-auto w-full max-w-7xl space-y-6 p-4 md:p-7">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[.14em] text-[var(--accent-color)]">{eyebrow}</p>
              <h1 className="mt-1 text-2xl font-semibold tracking-tight md:text-3xl">{title}</h1>
              {description && <p className="mt-1 max-w-2xl text-sm muted">{description}</p>}
            </div>
            <div className="hidden rounded-md border border-[var(--border-color)] bg-[var(--card-bg)] px-3 py-2 text-xs muted md:block">{new Date().toLocaleDateString(locale, { weekday: 'long', month: 'long', day: 'numeric' })}</div>
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}

function useStateTheme(): [boolean, (value: boolean) => void] {
  const [dark, setDarkState] = React.useState(() => localStorage.getItem('theme') === 'dark');
  const setDark = (value: boolean) => {
    setDarkState(value);
    localStorage.setItem('theme', value ? 'dark' : 'light');
    document.documentElement.classList.toggle('dark', value);
  };
  return [dark, setDark];
}
