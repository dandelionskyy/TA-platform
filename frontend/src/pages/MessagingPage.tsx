import { FormEvent, useEffect, useRef, useState } from 'react';
import AcademicShell from '../components/shared/AcademicShell';
import { useLanguage } from '../i18n/LanguageContext';
import { api } from '../services/api';
import { useAuthStore } from '../stores/authStore';

type Role = 'student' | 'ta' | 'teacher';

interface ContactUser { id: string; student_id: string; display_name: string; role: Role; }
interface Contact { course_id: string; course_name: string; user: ContactUser; can_message: boolean; accepted: boolean; }
interface Thread { id: string; course_id: string; course_name: string; other_user: ContactUser; last_message: string; last_message_at?: string | null; unread_count: number; }
interface DirectMessage { id: string; sender_id: string; content: string; created_at: string; }
interface Permission { course_id: string; student: ContactUser; accepted: boolean; }
interface Course { id: string; name: string; }

function displayName(person?: ContactUser | null) { return person?.display_name || person?.student_id || ''; }

export default function MessagingPage({ role }: { role: Role }) {
  const { user } = useAuthStore();
  const { text, locale } = useLanguage();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeThread, setActiveThread] = useState<Thread | null>(null);
  const [messages, setMessages] = useState<DirectMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [courses, setCourses] = useState<Course[]>([]);
  const [permissionCourseId, setPermissionCourseId] = useState('');
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  const loadDirectory = async () => {
    const [contactData, threadData] = await Promise.all([api.getMessageContacts(), api.getMessageThreads()]);
    setContacts(contactData.contacts || []);
    setThreads(threadData.threads || []);
  };
  const openThread = async (thread: Thread) => {
    setError('');
    try {
      const data = await api.getMessageThread(thread.id);
      setActiveThread(data.thread);
      setMessages(data.messages || []);
      setThreads(current => current.map(item => item.id === thread.id ? { ...item, unread_count: 0 } : item));
    } catch (caught: any) { setError(caught?.message || text('无法加载对话。', 'Unable to load the conversation.')); }
  };
  const startConversation = async (contact: Contact) => {
    if (!contact.can_message) return;
    setError('');
    try {
      const thread = await api.createMessageThread(contact.course_id, contact.user.id);
      await loadDirectory();
      await openThread(thread);
    } catch (caught: any) { setError(caught?.message || text('无法创建对话。', 'Unable to start the conversation.')); }
  };

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        await loadDirectory();
        if (role === 'teacher') {
          const data = await api.getCourses();
          const next = data.courses || [];
          setCourses(next);
          setPermissionCourseId(next[0]?.id || '');
        }
      } catch (caught: any) { setError(caught?.message || text('消息列表加载失败。', 'Unable to load messages.')); }
      finally { setLoading(false); }
    };
    load();
  }, [role]);

  useEffect(() => {
    if (!permissionCourseId || role !== 'teacher') { setPermissions([]); return; }
    api.getMessagePermissions(permissionCourseId).then(data => setPermissions(data.permissions || [])).catch((caught: any) => setError(caught?.message || text('权限列表加载失败。', 'Unable to load permissions.')));
  }, [permissionCourseId, role]);

  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const data = await api.getMessageThreads();
        setThreads(data.threads || []);
        if (activeThread) {
          const detail = await api.getMessageThread(activeThread.id);
          setActiveThread(detail.thread);
          setMessages(detail.messages || []);
        }
      } catch { /* Keep the last successful state during transient polling failures. */ }
    }, 5000);
    return () => window.clearInterval(timer);
  }, [activeThread?.id]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages.length]);

  const send = async (event: FormEvent) => {
    event.preventDefault();
    const content = draft.trim();
    if (!activeThread || !content || sending) return;
    setSending(true); setError('');
    try {
      await api.sendDirectMessage(activeThread.id, content);
      setDraft('');
      const detail = await api.getMessageThread(activeThread.id);
      setActiveThread(detail.thread); setMessages(detail.messages || []);
      await loadDirectory();
    } catch (caught: any) { setError(caught?.message || text('消息发送失败。', 'Unable to send the message.')); }
    finally { setSending(false); }
  };

  const changePermission = async (permission: Permission) => {
    const next = !permission.accepted;
    setPermissions(current => current.map(item => item.student.id === permission.student.id ? { ...item, accepted: next } : item));
    try {
      await api.updateMessagePermission(permission.course_id, permission.student.id, next);
      await loadDirectory();
    } catch (caught: any) {
      setPermissions(current => current.map(item => item.student.id === permission.student.id ? permission : item));
      setError(caught?.message || text('消息权限更新失败。', 'Unable to update message permission.'));
    }
  };

  const roleName = (value: Role) => value === 'teacher' ? text('教师', 'Teacher') : value === 'ta' ? text('助教', 'Teaching assistant') : text('学生', 'Student');
  const title = text('师生沟通', 'Course messages');
  const description = text('按课程与教师、助教和学生直接沟通，消息记录会同步保存在平台中。', 'Message teachers, assistants and students by course. Conversation history stays synchronized in the platform.');

  return <AcademicShell role={role} eyebrow={roleName(role)} title={title} description={description}>
    {error && <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
    <div className={`grid min-h-[650px] gap-4 ${role === 'teacher' ? 'xl:grid-cols-[280px_minmax(0,1fr)_300px]' : 'xl:grid-cols-[300px_minmax(0,1fr)]'}`}>
      <aside className="panel min-h-0 overflow-hidden">
        <div className="border-b border-[var(--border-color)] px-4 py-3"><h2 className="font-semibold">{text('最近消息', 'Recent messages')}</h2><p className="mt-1 text-xs muted">{text('每 5 秒自动同步', 'Synced every 5 seconds')}</p></div>
        <div className="max-h-72 overflow-y-auto border-b border-[var(--border-color)]">
          {threads.map(thread => <button key={thread.id} onClick={() => openThread(thread)} className={`block w-full border-b border-[var(--border-color)] px-4 py-3 text-left last:border-0 ${activeThread?.id === thread.id ? 'bg-[var(--accent-muted)]' : 'hover:bg-[var(--bg-secondary)]'}`}><div className="flex items-center justify-between gap-2"><span className="truncate text-sm font-medium">{displayName(thread.other_user)}</span>{thread.unread_count > 0 && <span className="min-w-5 rounded-full bg-[var(--accent-color)] px-1.5 py-0.5 text-center text-[10px] text-white">{thread.unread_count}</span>}</div><p className="mt-1 truncate text-xs muted">{thread.last_message || text('暂无消息', 'No messages yet')}</p><p className="mt-1 truncate text-[10px] muted">{thread.course_name}</p></button>)}
          {!loading && threads.length === 0 && <p className="px-4 py-8 text-center text-sm muted">{text('暂无对话记录', 'No conversations yet')}</p>}
        </div>
        <div className="px-4 py-3"><h3 className="text-xs font-semibold uppercase tracking-[.1em] muted">{text('课程联系人', 'Course contacts')}</h3></div>
        <div className="max-h-72 overflow-y-auto">
          {contacts.map(contact => <button key={`${contact.course_id}-${contact.user.id}`} onClick={() => startConversation(contact)} disabled={!contact.can_message} className="block w-full border-t border-[var(--border-color)] px-4 py-3 text-left hover:bg-[var(--bg-secondary)] disabled:cursor-not-allowed disabled:opacity-50"><div className="flex items-center justify-between gap-2"><span className="text-sm font-medium">{displayName(contact.user)}</span><span className="text-[10px] muted">{roleName(contact.user.role)}</span></div><div className="mt-1 flex items-center justify-between gap-2"><span className="truncate text-xs muted">{contact.course_name}</span>{!contact.can_message && <span className="text-[10px] text-amber-700">{text('暂不接收', 'Not accepting')}</span>}</div></button>)}
          {!loading && contacts.length === 0 && <p className="px-4 py-8 text-center text-sm muted">{text('当前课程暂无可联系成员', 'No contacts are available in your courses')}</p>}
        </div>
      </aside>

      <section className="panel flex min-h-[560px] min-w-0 flex-col overflow-hidden">
        {activeThread ? <>
          <header className="border-b border-[var(--border-color)] px-5 py-4"><div className="flex items-center justify-between gap-3"><div><h2 className="font-semibold">{displayName(activeThread.other_user)}</h2><p className="mt-1 text-xs muted">{activeThread.course_name} · {roleName(activeThread.other_user.role)}</p></div><span className="rounded-md bg-[var(--bg-secondary)] px-2 py-1 text-xs muted">{text('平台消息', 'Platform message')}</span></div></header>
          <div className="flex-1 space-y-3 overflow-y-auto bg-[var(--bg-secondary)]/40 px-4 py-5 md:px-6">
            {messages.map(message => { const mine = message.sender_id === user?.id; return <div key={message.id} className={`flex ${mine ? 'justify-end' : 'justify-start'}`}><div className={`max-w-[82%] rounded-md px-3.5 py-2.5 text-sm leading-6 shadow-sm ${mine ? 'bg-[var(--accent-color)] text-white' : 'border border-[var(--border-color)] bg-[var(--card-bg)]'}`}><p className="whitespace-pre-wrap break-words">{message.content}</p><p className={`mt-1 text-[10px] ${mine ? 'text-white/70' : 'muted'}`}>{new Date(message.created_at).toLocaleString(locale)}</p></div></div>; })}
            {messages.length === 0 && <div className="flex h-full items-center justify-center text-sm muted">{text('发送第一条消息开始沟通', 'Send the first message to begin')}</div>}
            <div ref={endRef} />
          </div>
          <form onSubmit={send} className="border-t border-[var(--border-color)] p-3"><div className="flex items-end gap-2"><textarea className="field min-h-12 flex-1 resize-none" rows={2} maxLength={10000} value={draft} onChange={event => setDraft(event.target.value)} placeholder={text('输入消息...', 'Type a message...')} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} /><button className="btn-primary min-h-12 rounded-md px-4 text-sm" disabled={!draft.trim() || sending}>{sending ? text('发送中', 'Sending') : text('发送', 'Send')}</button></div></form>
        </> : <div className="flex flex-1 items-center justify-center px-6 text-center"><div><div className="mx-auto flex h-12 w-12 items-center justify-center rounded-md border border-[var(--border-color)] bg-[var(--bg-secondary)] text-lg font-semibold text-[var(--accent-color)]">信</div><h2 className="mt-4 font-semibold">{text('选择一位课程联系人', 'Choose a course contact')}</h2><p className="mt-1 text-sm muted">{text('已有对话会保留在左侧，方便继续沟通。', 'Existing conversations stay on the left so you can continue at any time.')}</p></div></div>}
      </section>

      {role === 'teacher' && <aside className="panel min-h-0 overflow-hidden"><div className="border-b border-[var(--border-color)] px-4 py-3"><h2 className="font-semibold">{text('学生消息权限', 'Student message permissions')}</h2><p className="mt-1 text-xs muted">{text('决定是否接收学生主动发送的消息', 'Choose which students may message you')}</p></div><div className="p-3"><select className="field w-full" value={permissionCourseId} onChange={event => setPermissionCourseId(event.target.value)}><option value="">{text('选择课程', 'Select course')}</option>{courses.map(course => <option key={course.id} value={course.id}>{course.name}</option>)}</select></div><div className="max-h-[540px] overflow-y-auto border-t border-[var(--border-color)]">{permissions.map(permission => <div key={permission.student.id} className="flex items-center justify-between gap-3 border-b border-[var(--border-color)] px-4 py-3"><div className="min-w-0"><p className="truncate text-sm font-medium">{displayName(permission.student)}</p><p className="mt-1 text-xs muted">{permission.student.student_id}</p></div><label className="flex cursor-pointer items-center gap-2 text-xs"><input type="checkbox" checked={permission.accepted} onChange={() => changePermission(permission)} /><span>{permission.accepted ? text('接收', 'Accept') : text('拒绝', 'Block')}</span></label></div>)}{permissionCourseId && permissions.length === 0 && <p className="px-4 py-8 text-center text-sm muted">{text('该课程暂无学生', 'No students in this course')}</p>}</div></aside>}
    </div>
  </AcademicShell>;
}
