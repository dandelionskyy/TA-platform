import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { api } from '../services/api';
import RobotMonitor from '../components/robot/RobotMonitor';
import CourseMemberManager from '../components/shared/CourseMemberManager';
import { LanguageToggle, useLanguage } from '../i18n/LanguageContext';

interface Course {
  id: string;
  name: string;
}

export default function TeacherPage() {
  const { user, logout } = useAuthStore();
  const { text } = useLanguage();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark');
  const [dashboard, setDashboard] = useState<any>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [newCourse, setNewCourse] = useState('');
  const [member, setMember] = useState({
    role: 'ta' as 'ta' | 'student',
    student_id: '',
    phone: '',
    password: '',
    display_name: '',
    course_id: '',
  });
  const [memberMessage, setMemberMessage] = useState('');

  useEffect(() => {
    api.getTeacherDashboard().then(setDashboard).catch(() => {});
    api.getTeacherCourses().then(data => setCourses(data.courses || [])).catch(() => {});
  }, []);

  const toggleDark = () => {
    const next = !dark;
    setDark(next);
    localStorage.setItem('theme', next ? 'dark' : 'light');
    document.documentElement.classList.toggle('dark', next);
  };

  const createCourse = async () => {
    if (!newCourse.trim()) return;
    try {
      const course = await api.createCourse({ name: newCourse.trim() });
      setCourses(current => [...current, course]);
      setNewCourse('');
    } catch {}
  };

  const provisionMember = async () => {
    if (!member.student_id || !member.phone || !member.password) {
      setMemberMessage(text('学号、手机号和密码为必填项。', 'Student ID, phone and password are required.'));
      return;
    }
    try {
      const created = await api.provisionUser(member);
      if (member.course_id) {
        if (member.role === 'ta') await api.assignTA(member.course_id, created.id);
        else await api.enrollStudent(member.course_id, created.id);
      }
      setMember({ role: member.role, student_id: '', phone: '', password: '', display_name: '', course_id: member.course_id });
      setMemberMessage(text('账号已创建并分配课程。', 'Account created and assigned.'));
    } catch (error: any) {
      setMemberMessage(error.message || text('无法创建账号。', 'Unable to create account.'));
    }
  };

  const metricLabels: [string, number][] = [
    [text('学生数', 'Students'), dashboard?.total_students || 0],
    [text('今日消息', 'Messages today'), dashboard?.total_messages_today || 0],
    [text('会话数', 'Conversations'), dashboard?.total_conversations || 0],
    [text('机器人提问', 'Robot questions'), dashboard?.total_robot_questions || 0],
  ];

  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <div className="sidebar-brand">TA Platform</div>
          <LanguageToggle />
        </div>
        <div className="px-2.5 py-3 text-xs text-[#9b9ca3]">{text('教师工作台', 'Teacher workspace')}</div>
        <div className="flex-1 overflow-y-auto">
          <div className="px-2.5 pb-2 pt-1 text-[11px] uppercase tracking-[.08em] text-[#9b9ca3]">{text('工作区', 'Workspace')}</div>
          <Link to="/teacher" className="block rounded-md px-3 py-2 text-sm text-white hover:bg-white/10">{text('教学概览', 'Overview')}</Link>
          <Link to="/teacher/materials" className="block rounded-md px-3 py-2 text-sm text-white hover:bg-white/10">{text('课程资料', 'Course materials')}</Link>
          <Link to="/teacher/assignments" className="block rounded-md px-3 py-2 text-sm text-white hover:bg-white/10">{text('作业管理', 'Assignments')}</Link>
          <Link to="/teacher/attendance" className="block rounded-md px-3 py-2 text-sm text-white hover:bg-white/10">{text('考勤管理', 'Attendance')}</Link>
          <Link to="/teacher/announcements" className="block rounded-md px-3 py-2 text-sm text-white hover:bg-white/10">{text('课程通知', 'Announcements')}</Link>
          <Link to="/teacher/messages" className="block rounded-md px-3 py-2 text-sm text-white hover:bg-white/10">{text('师生沟通', 'Messages')}</Link>
          <Link to="/teacher/students" className="block rounded-md px-3 py-2 text-sm text-white hover:bg-white/10">{text('所有学生', 'All students')}</Link>
        </div>
        <div className="sidebar-footer">
          <button onClick={toggleDark} className="btn w-full border-white/20 bg-transparent text-sm text-white">{dark ? text('浅色主题', 'Light theme') : text('深色主题', 'Dark theme')}</button>
          <button onClick={logout} className="btn-danger mt-2 w-full text-sm">{text('退出登录', 'Log out')}</button>
          <div className="mt-2 truncate px-1 text-xs text-[#9b9ca3]">{user?.display_name || user?.student_id}</div>
        </div>
      </aside>

      {sidebarOpen && <button aria-label={text('关闭导航', 'Close navigation')} className="fixed inset-0 z-20 bg-black/50 lg:hidden" onClick={() => setSidebarOpen(false)} />}

      <main className="workspace overflow-y-auto">
        <header className="mobile-header">
          <button onClick={() => setSidebarOpen(true)} className="btn" aria-label={text('打开导航', 'Open navigation')}>☰</button>
          <span className="font-semibold">{text('教师工作台', 'Teacher workspace')}</span>
          <LanguageToggle />
          <button className="btn ml-auto" onClick={logout}>{text('退出', 'Log out')}</button>
        </header>
        <div className="flex-1 space-y-6 p-4 md:p-7">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {metricLabels.map(([label, value]) => <div className="panel metric" key={label}><div className="metric-value">{value}</div><div className="mt-1 text-xs muted">{label}</div></div>)}
          </div>

          <section className="panel p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-semibold">{text('课程管理', 'Courses')}</h2>
                <p className="mt-1 text-sm muted">{text('学生和助教按课程进行权限隔离。', 'Students and assistants are scoped to a course.')}</p>
              </div>
              <div className="flex gap-2">
                <input className="field max-w-xs" value={newCourse} onChange={event => setNewCourse(event.target.value)} placeholder={text('课程名称', 'Course name')} />
                <button className="btn-primary rounded-md px-3 py-2 text-sm" onClick={createCourse}>{text('添加课程', 'Add course')}</button>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {courses.map(course => <span key={course.id} className="rounded-md bg-[var(--bg-secondary)] px-3 py-2 text-sm">{course.name}</span>)}
              {courses.length === 0 && <span className="text-sm muted">{text('暂无课程。', 'No courses yet.')}</span>}
            </div>
          </section>

          <CourseMemberManager courses={courses} />

          <section className="panel p-5">
            <h2 className="font-semibold">{text('创建账号并分配课程', 'Issue access')}</h2>
            <p className="mt-1 text-sm muted">{text('助教可以由教师创建；学生优先通过注册后在上方批量加入课程。', 'Create TA accounts here; students should register first and be added in bulk above.')}</p>
            <div className="mt-4 grid gap-2 md:grid-cols-3">
              <select className="field" value={member.role} onChange={event => setMember({ ...member, role: event.target.value as 'ta' | 'student' })}>
                <option value="ta">{text('助教', 'Teaching assistant')}</option>
                <option value="student">{text('学生（手动创建）', 'Student (manual creation)')}</option>
              </select>
              <select className="field" value={member.course_id} onChange={event => setMember({ ...member, course_id: event.target.value })}>
                <option value="">{text('不分配课程', 'No course assignment')}</option>
                {courses.map(course => <option value={course.id} key={course.id}>{course.name}</option>)}
              </select>
              <input className="field" placeholder={text('姓名', 'Display name')} value={member.display_name} onChange={event => setMember({ ...member, display_name: event.target.value })} />
              <input className="field" placeholder={text('学号', 'Student ID')} value={member.student_id} onChange={event => setMember({ ...member, student_id: event.target.value })} />
              <input className="field" placeholder={text('手机号', 'Phone')} value={member.phone} onChange={event => setMember({ ...member, phone: event.target.value })} />
              <input className="field" placeholder={text('临时密码', 'Temporary password')} type="password" value={member.password} onChange={event => setMember({ ...member, password: event.target.value })} />
            </div>
            <div className="mt-3 flex items-center gap-3">
              <button className="btn-primary rounded-md px-3 py-2 text-sm" onClick={provisionMember}>{text('创建账号', 'Create account')}</button>
              {memberMessage && <span className="text-sm muted">{memberMessage}</span>}
            </div>
          </section>

          <Link to="/teacher/students" className="panel block p-5"><h2 className="font-semibold">{text('所有学生', 'All students')} →</h2><p className="mt-1 text-sm muted">{text('查看完整学生目录、问答历史、Token 用量和模型详情。', 'Browse all students, chat history, token usage and model details.')}</p></Link>

          <section className="panel p-5"><h3 className="mb-3 font-semibold">{text('机器人状态', 'Robot status')}</h3><RobotMonitor role="teacher" /></section>
        </div>
      </main>
    </div>
  );
}
