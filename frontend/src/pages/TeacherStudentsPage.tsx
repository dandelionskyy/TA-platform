import { DependencyList, useEffect, useState } from 'react';
import AcademicShell from '../components/shared/AcademicShell';
import ChatMessage from '../components/shared/ChatMessage';
import { useLanguage } from '../i18n/LanguageContext';
import { api } from '../services/api';

type Course = { id: string; name: string };
type Student = { id: string; student_id: string; display_name: string; is_active: boolean; courses: Course[] };
type Conversation = { id: string; title: string; course_id: string; created_at: string; updated_at: string; message_count: number; total_tokens: number; recorded_usage_count: number };
type Message = { id: string; role: string; content: string; created_at: string; token_count: number | null; prompt_tokens: number | null; completion_tokens: number | null; model_name: string | null; response_time_ms: number | null };
type Usage = {
  total_chat_messages: number; total_ai_responses: number; total_conversations: number;
  prompt_tokens: number; completion_tokens: number; total_tokens: number;
  recorded_usage_count: number; missing_usage_count: number; recorded_prompt_count: number; recorded_completion_count: number;
  first_active_at: string | null; last_active_at: string | null;
  models: { model_name: string | null; responses: number; total_tokens: number | null; recorded_usage_count: number }[];
};
type Page<T> = { total: number; page: number; page_size: number } & T;

// Ignore responses from a previous student/page after navigation or unmount.
function useLoad<T>(load: () => Promise<T>, dependencies: DependencyList) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setData(null); setError('');
    load().then(value => { if (active) setData(value); }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : 'Request failed');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [...dependencies, revision]);
  return { data, loading, error, retry: () => setRevision(value => value + 1) };
}

function LoadState({ loading, error, retry }: { loading: boolean; error: string; retry: () => void }) {
  const { text } = useLanguage();
  if (loading) return <p role="status" className="p-5 text-sm muted">{text('正在加载…', 'Loading…')}</p>;
  if (error) return <div role="alert" className="p-5 text-sm text-[var(--danger)]">{text('加载失败：', 'Unable to load: ')}{error} <button className="btn ml-3" onClick={retry}>{text('重试', 'Retry')}</button></div>;
  return null;
}

function Pager({ page, total, size, onChange, label }: { page: number; total: number; size: number; onChange: (value: number) => void; label: string }) {
  const { text, locale } = useLanguage();
  const pages = Math.max(1, Math.ceil(total / size));
  return <nav aria-label={label} className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border-color)] p-4 text-sm">
    <span className="muted">{text('共', 'Total')} {total.toLocaleString(locale)} · {text('第', 'Page')} {page} / {pages}</span>
    <div className="flex items-center gap-2">
      <button className="btn disabled:cursor-default disabled:opacity-40" disabled={page <= 1} onClick={() => onChange(page - 1)}>{text('上一页', 'Previous')}</button>
      <select aria-label={text('跳转页码', 'Go to page')} className="field !w-auto" value={page} onChange={e => onChange(Number(e.target.value))}>
        {Array.from({ length: pages }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1} / {pages}</option>)}
      </select>
      <button className="btn disabled:cursor-default disabled:opacity-40" disabled={page >= pages} onClick={() => onChange(page + 1)}>{text('下一页', 'Next')}</button>
    </div>
  </nav>;
}

function useFormat() {
  const { text, locale } = useLanguage();
  return {
    number: (n: number | null | undefined) => n == null ? text('未记录', 'Not recorded') : n.toLocaleString(locale),
    date: (value: string | null | undefined) => value ? new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`).toLocaleString(locale) : '—',
  };
}

export default function TeacherStudentsPage() {
  const { text } = useLanguage();
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [course, setCourse] = useState('');
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(50);
  const [student, setStudent] = useState<Student | null>(null);
  const courses = useLoad<{ courses: Course[] }>(() => api.getTeacherCourses(), []);
  const students = useLoad<Page<{ students: Student[] }>>(() => api.getStudents(query, page, size, course), [query, page, size, course]);
  useEffect(() => {
    if (students.data && page > Math.max(1, Math.ceil(students.data.total / size))) setPage(Math.max(1, Math.ceil(students.data.total / size)));
  }, [students.data, page, size]);
  return <AcademicShell role="teacher" eyebrow={text('教师工作台', 'Teacher workspace')} title={text('所有学生', 'All students')}
    description={text('浏览所管理课程的全部学生，查看课程问答历史和 AI 使用详情。', 'Browse every student in your courses and review course conversations and AI usage.')}>
    {student ? <StudentDetails key={student.id} student={student} onBack={() => setStudent(null)} /> : <section className="panel overflow-hidden">
      <form className="flex flex-wrap items-end gap-3 border-b border-[var(--border-color)] p-5" onSubmit={e => { e.preventDefault(); setQuery(search.trim()); setPage(1); }}>
        <label className="min-w-48 flex-1 text-sm">{text('姓名或学号', 'Name or student ID')}<input className="field mt-2" maxLength={100} placeholder={text('搜索学生', 'Search students')} value={search} onChange={e => setSearch(e.target.value)} /></label>
        <button className="btn-primary rounded-md px-4 py-2">{text('搜索', 'Search')}</button>
        <label className="min-w-48 flex-1 text-sm">{text('课程', 'Course')}<select className="field mt-2" value={course} onChange={e => { setCourse(e.target.value); setPage(1); }}><option value="">{text('全部课程', 'All courses')}</option>{courses.data?.courses.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label className="text-sm">{text('每页人数', 'Page size')}<select className="field mt-2" value={size} onChange={e => { setSize(Number(e.target.value)); setPage(1); }}>{[20, 50, 100].map(n => <option key={n} value={n}>{n}</option>)}</select></label>
        {(query || course) && <button type="button" className="btn" onClick={() => { setSearch(''); setQuery(''); setCourse(''); setPage(1); }}>{text('重置', 'Reset')}</button>}
      </form>
      {courses.error && <LoadState loading={false} error={courses.error} retry={courses.retry} />}
      <LoadState {...students} />
      {students.data && !students.loading && <>
        <div className="overflow-x-auto"><table className="w-full min-w-[580px] text-left text-sm">
          <thead className="bg-[var(--bg-secondary)] text-xs muted"><tr>{[text('学生', 'Student'), text('学号', 'Student ID'), text('课程', 'Courses'), text('状态', 'Status'), text('问答与用量', 'History and usage')].map(label => <th scope="col" key={label} className="px-5 py-3 font-medium">{label}</th>)}</tr></thead>
          <tbody className="divide-y divide-[var(--border-color)]">{students.data.students.map(s => <tr key={s.id} className="hover:bg-[var(--bg-secondary)]">
            <td className="px-5 py-4 font-medium">{s.display_name || s.student_id}</td><td className="px-5 py-4 tabular-nums muted">{s.student_id}</td>
            <td className="max-w-xs px-5 py-4"><div className="flex flex-wrap gap-1">{s.courses?.map(c => <span key={c.id} className="rounded bg-[var(--bg-secondary)] px-2 py-1 text-xs">{c.name}</span>)}</div></td>
            <td className="px-5 py-4 muted">{s.is_active ? text('正常', 'Active') : text('已停用', 'Inactive')}</td>
            <td className="px-5 py-4"><button className="btn whitespace-nowrap" onClick={() => setStudent(s)} aria-label={`${text('查看详情', 'View details')} ${s.student_id}`}>{text('查看详情', 'View details')} →</button></td>
          </tr>)}{!students.data.students.length && <tr><td colSpan={5} className="p-12 text-center muted">{text('当前条件下没有学生。', 'No students match these filters.')}</td></tr>}</tbody>
        </table></div>
        <Pager page={page} size={size} total={students.data.total} onChange={setPage} label={text('学生分页', 'Student pages')} />
      </>}
    </section>}
  </AcademicShell>;
}

function StudentDetails({ student, onBack }: { student: Student; onBack: () => void }) {
  const { text } = useLanguage(); const format = useFormat();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const usage = useLoad<Usage>(() => api.getStudentUsage(student.id), [student.id]);
  const conversations = useLoad<Page<{ conversations: Conversation[] }>>(() => api.getStudentConversations(student.id, page), [student.id, page]);
  const u = usage.data;
  const token = (count: number, value: number, responses: number) => count ? format.number(value) : responses ? text('未记录', 'Not recorded') : '0';
  return <>
    <button className="btn" onClick={onBack}>← {text('返回所有学生', 'Back to all students')}</button>
    <section className="panel p-5">
      <h2 className="text-xl font-semibold">{student.display_name || student.student_id}</h2><p className="mt-1 text-sm muted">{text('学号', 'Student ID')} {student.student_id} · {student.courses?.map(c => c.name).join(' / ')}</p>
      <LoadState {...usage} />
      {u && <>
        <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">{[
          [text('会话数', 'Conversations'), format.number(u.total_conversations)],
          [text('消息数', 'Messages'), format.number(u.total_chat_messages)],
          [text('AI 回复数', 'AI responses'), format.number(u.total_ai_responses)],
          [text('已记录总 Token', 'Recorded total tokens'), token(u.recorded_usage_count, u.total_tokens, u.total_ai_responses)],
        ].map(([label, value]) => <div className="rounded-md bg-[var(--bg-secondary)] p-4" key={label}><div className="text-2xl font-semibold break-words text-[var(--accent-color)]">{value}</div><div className="mt-1 text-xs muted">{label}</div></div>)}</div>
        <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">{[
          [text('输入 Token', 'Input tokens'), token(u.recorded_prompt_count, u.prompt_tokens, u.total_ai_responses)],
          [text('输出 Token', 'Output tokens'), token(u.recorded_completion_count, u.completion_tokens, u.total_ai_responses)],
          [text('首次课程问答', 'First course activity'), format.date(u.first_active_at)],
          [text('最近课程问答', 'Latest course activity'), format.date(u.last_active_at)],
        ].map(([label, value]) => <div key={label}><dt className="text-xs muted">{label}</dt><dd className="mt-1">{value}</dd></div>)}</dl>
        <p className="mt-4 text-xs leading-5 muted">{text('统计仅包含您管理课程的问答。Token 来自模型服务的实际返回，输入包含历史和资料上下文；耗时为单次回复等待时间。', 'Statistics cover conversations in your courses. Tokens come from provider usage; input includes history and reference context. Response time is the wait for one reply.')}</p>
        {!!u.missing_usage_count && <p className="mt-1 text-xs muted">{text('有', 'There are')} {u.missing_usage_count} {text('条 AI 回复未记录 Token，汇总未包含这些用量，无法追溯补算。', 'AI replies without token records. Totals exclude them; historical usage cannot be reconstructed.')}</p>}
        {!!u.models.length && <div className="mt-5 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="mb-2 text-left font-semibold">{text('模型使用情况', 'Model usage')}</caption><thead className="text-xs muted"><tr><th className="py-2">{text('模型', 'Model')}</th><th>{text('回复数', 'Replies')}</th><th>{text('有用量记录', 'Metered replies')}</th><th>{text('已记录 Token', 'Recorded tokens')}</th></tr></thead><tbody className="divide-y divide-[var(--border-color)]">{u.models.map(m => <tr key={m.model_name || 'unknown'}><td className="py-3 break-all">{m.model_name || text('未记录', 'Not recorded')}</td><td>{m.responses}</td><td>{m.recorded_usage_count}</td><td>{format.number(m.total_tokens)}</td></tr>)}</tbody></table></div>}
      </>}
    </section>
    <div className="grid items-start gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
      <section className="panel min-w-0 overflow-hidden">
        <h2 className="border-b border-[var(--border-color)] p-4 font-semibold">{text('会话历史', 'Conversation history')}</h2>
        <LoadState {...conversations} />
        {conversations.data && !conversations.loading && <>
          <div className="max-h-[600px] overflow-y-auto divide-y divide-[var(--border-color)]">{conversations.data.conversations.map(c => <button key={c.id} onClick={() => setSelected(c)} aria-pressed={c.id === selected?.id} className={`block w-full p-4 text-left hover:bg-[var(--bg-secondary)] ${c.id === selected?.id ? 'bg-[var(--accent-muted)]' : ''}`}>
            <div className="truncate text-sm font-medium">{c.title === 'New Chat' ? text('课程问答', 'Course conversation') : c.title}</div>
            <p className="mt-1 text-xs muted">{student.courses?.find(course => course.id === c.course_id)?.name}</p>
            <p className="mt-2 text-xs muted">{format.date(c.updated_at)}</p><p className="mt-1 text-xs muted">{c.message_count} {text('条消息', 'messages')} · {c.recorded_usage_count ? format.number(c.total_tokens) : '—'} Token</p>
          </button>)}{!conversations.data.total && <p className="p-8 text-sm muted">{text('暂无课程会话。', 'No course conversations yet.')}</p>}</div>
          <Pager page={page} total={conversations.data.total} size={20} onChange={value => { setPage(value); setSelected(null); }} label={text('会话分页', 'Conversation pages')} />
        </>}
      </section>
      {selected ? <MessageHistory key={selected.id} studentId={student.id} conversation={selected} /> : <section className="panel p-12 text-center text-sm muted">{text('选择一个会话查看消息和每次调用详情。', 'Select a conversation to view messages and per-response details.')}</section>}
    </div>
  </>;
}

function MessageHistory({ studentId, conversation }: { studentId: string; conversation: Conversation }) {
  const { text } = useLanguage(); const format = useFormat(); const [page, setPage] = useState(1);
  const messages = useLoad<Page<{ messages: Message[] }>>(() => api.getStudentMessages(studentId, conversation.id, page), [studentId, conversation.id, page]);
  return <section className="panel min-w-0 overflow-hidden">
    <header className="border-b border-[var(--border-color)] p-4"><h2 className="font-semibold">{text('消息与调用详情', 'Messages and usage details')}</h2><p className="mt-1 text-xs muted">{text('创建时间', 'Created')} {format.date(conversation.created_at)}</p></header>
    <LoadState {...messages} />
    {messages.data && !messages.loading && <>
      <div className="divide-y divide-[var(--border-color)]">{messages.data.messages.map(m => <article key={m.id} className="min-w-0 overflow-hidden p-4">
        <header className="mb-3 flex flex-wrap items-center gap-2 text-xs muted"><strong>{m.role === 'user' ? text('学生', 'Student') : 'AI'}</strong><time>{format.date(m.created_at)}</time></header>
        <ChatMessage role={m.role} content={m.content} />
        {m.role === 'assistant' && <dl className="mt-4 grid grid-cols-2 gap-3 rounded-md bg-[var(--bg-secondary)] p-3 text-xs sm:grid-cols-3">{[
          [text('模型', 'Model'), m.model_name || text('未记录', 'Not recorded')],
          [text('输入 Token', 'Input tokens'), format.number(m.prompt_tokens)],
          [text('输出 Token', 'Output tokens'), format.number(m.completion_tokens)],
          [text('总 Token', 'Total tokens'), format.number(m.token_count)],
          [text('响应耗时', 'Response time'), m.response_time_ms == null ? text('未记录', 'Not recorded') : `${(m.response_time_ms / 1000).toFixed(2)} ${text('秒', 's')}`],
        ].map(([label, value]) => <div key={label}><dt className="muted">{label}</dt><dd className="mt-1 break-all font-medium">{value}</dd></div>)}</dl>}
      </article>)}{!messages.data.total && <p className="p-8 text-sm muted">{text('暂无消息。', 'No messages yet.')}</p>}</div>
      <Pager page={page} size={50} total={messages.data.total} onChange={setPage} label={text('消息分页', 'Message pages')} />
    </>}
  </section>;
}
