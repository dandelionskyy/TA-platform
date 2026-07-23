import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import RobotMonitor from '../components/robot/RobotMonitor';
import ChatContainer from '../components/shared/ChatContainer';
import ChatInput from '../components/shared/ChatInput';
import { LanguageToggle, useLanguage } from '../i18n/LanguageContext';
import { api } from '../services/api';
import { useAuthStore } from '../stores/authStore';

interface Conversation { id: string; title: string; course_id?: string; chapter_index?: number; chapter_id?: string; updated_at: string; }
interface Material { id: string; filename: string; mime_type?: string; size_bytes: number; preview_kind: 'pdf' | 'image' | 'text' | 'office' | 'download'; processing_status: string; }
interface Chapter { id: string; title: string; description: string; sort_order: number; materials: Material[]; legacy?: boolean; }
interface Course { id: string; name: string; description?: string; knowledge_base_path?: string; chapters: Chapter[]; }

export default function StudentPage() {
  const { user, logout } = useAuthStore();
  const { text } = useLanguage();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [activeChatId, setActiveChatId] = useState('general');
  const [activeMode, setActiveMode] = useState('chatbot');
  const [activeCourse, setActiveCourse] = useState<Course>();
  const [activeChapter, setActiveChapter] = useState<Chapter>();
  const [activeMaterial, setActiveMaterial] = useState<Material>();
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewText, setPreviewText] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark');
  const chatKey = useRef(0);
  const previewUrlRef = useRef('');

  const loadConversations = async () => { try { const data = await api.getConversations(1); setConversations(data.conversations || []); } catch {} };
  useEffect(() => {
    loadConversations();
    api.getCourses().then(data => setCourses(data.courses || [])).catch(() => setCourses([]));
    return () => { if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current); };
  }, []);

  const clearPreview = () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = '';
    setPreviewUrl(''); setPreviewText(''); setPreviewError('');
  };
  const showMaterial = async (material?: Material) => {
    clearPreview(); setActiveMaterial(material);
    if (!material) return;
    if (material.preview_kind === 'office' || material.preview_kind === 'download') return;
    setPreviewLoading(true);
    try {
      const blob = await api.getCourseMaterialFile(material.id);
      if (material.preview_kind === 'text') {
        setPreviewText(await blob.text());
      } else {
        const url = URL.createObjectURL(blob);
        previewUrlRef.current = url; setPreviewUrl(url);
      }
    } catch (caught: any) { setPreviewError(caught?.message || text('资料加载失败。', 'Unable to load material.')); }
    finally { setPreviewLoading(false); }
  };
  const downloadMaterial = async (material: Material) => {
    try {
      const blob = await api.getCourseMaterialFile(material.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = material.filename; document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (caught: any) { setPreviewError(caught?.message || text('资料下载失败。', 'Unable to download material.')); }
  };

  const toggleDark = () => { const next = !dark; setDark(next); localStorage.setItem('theme', next ? 'dark' : 'light'); document.documentElement.classList.toggle('dark', next); };
  const chooseGeneral = () => {
    setActiveChatId('general'); setActiveMode('chatbot'); setActiveCourse(undefined); setActiveChapter(undefined); setActiveMaterial(undefined); clearPreview(); chatKey.current += 1; setSidebarOpen(false);
  };
  const enterChapter = (course: Course, chapter: Chapter, conversationId = 'general') => {
    setActiveChatId(conversationId); setActiveCourse(course); setActiveChapter(chapter);
    const slug = (course.knowledge_base_path || course.name).replace(/\s+/g, '-');
    setActiveMode(`${slug}-ch${chapter.sort_order}`);
    chatKey.current += 1; setSidebarOpen(false);
    showMaterial(chapter.materials[0]);
  };
  const chooseConversation = (conversation: Conversation) => {
    if (conversation.course_id) {
      const course = courses.find(item => item.id === conversation.course_id);
      const chapter = course?.chapters.find(item => item.id === conversation.chapter_id)
        || course?.chapters.find(item => item.sort_order === conversation.chapter_index);
      if (course && chapter) { enterChapter(course, chapter, conversation.id); return; }
    }
    clearPreview(); setActiveCourse(undefined); setActiveChapter(undefined); setActiveMaterial(undefined); setActiveMode('chatbot'); setActiveChatId(conversation.id); chatKey.current += 1; setSidebarOpen(false);
  };
  const bindConversation = (id: string) => { setActiveChatId(id); loadConversations(); };

  return <div className="app-shell">
    <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
      <div className="sidebar-header"><div className="sidebar-brand">TA Platform</div><LanguageToggle /><button className="btn border-white/20 bg-transparent text-white" onClick={chooseGeneral} title={text('新建会话', 'New conversation')}>+</button></div>
      <div className="sidebar-scroll">
        <div className="sidebar-section-title">{text('工作区', 'Workspace')}</div>
        <Link to="/student" className="sidebar-item active block">{text('学习概览', 'Overview')}</Link>
        <Link to="/student/chat" className="sidebar-item block">{text('AI 助教', 'AI Assistant')}</Link>
        <Link to="/student/assignments" className="sidebar-item block">{text('我的作业', 'My assignments')}</Link>
        <Link to="/student/attendance" className="sidebar-item block">{text('签到考勤', 'Attendance')}</Link>
        <Link to="/student/announcements" className="sidebar-item block">{text('课程通知', 'Announcements')}</Link>
        <Link to="/student/messages" className="sidebar-item block">{text('师生沟通', 'Messages')}</Link>
        <div className="sidebar-section-title border-t border-white/10">{text('我的课程', 'My courses')}</div>
        {courses.length === 0 && <p className="px-2.5 py-2 text-xs text-[#9b9ca3]">{text('教师分配的课程会显示在这里。', 'Courses assigned by your teacher appear here.')}</p>}
        {courses.map(course => <details key={course.id} className="mb-1" open={activeCourse?.id === course.id || undefined}><summary className="sidebar-item cursor-pointer list-none"><span className="block truncate font-medium">{course.name}</span><span className="mt-0.5 block text-[10px] text-[#9b9ca3]">{course.chapters.length} {text('个章节', 'chapters')}</span></summary><div>{course.chapters.map((chapter, index) => <button key={chapter.id} className={`sidebar-subitem ${activeChapter?.id === chapter.id ? 'active' : ''}`} onClick={() => enterChapter(course, chapter)}><span className="block truncate">{index + 1}. {chapter.title}</span><span className="ml-2 text-[10px] opacity-60">{chapter.materials.length}</span></button>)}{course.chapters.length === 0 && <p className="px-4 py-2 text-[11px] text-[#9b9ca3]">{text('教师还没有发布章节', 'No chapters published')}</p>}</div></details>)}
        <div className="sidebar-section-title border-t border-white/10">{text('最近 AI 会话', 'Recent AI chats')}</div>
        {conversations.slice(0, 15).map(conversation => <button key={conversation.id} className={`sidebar-item ${activeChatId === conversation.id ? 'active' : ''}`} onClick={() => chooseConversation(conversation)}>{conversation.title === 'New Chat' ? text('新会话', 'New Chat') : conversation.title || text('未命名会话', 'Untitled conversation')}</button>)}
      </div>
      <div className="sidebar-footer"><div className="mb-2 text-xs text-[#9b9ca3]">{text('机器人状态', 'Robot status')}</div><RobotMonitor role="student" compact /><div className="mt-3 flex items-center gap-2"><button className="btn flex-1 border-white/20 bg-transparent text-xs text-white" onClick={toggleDark}>{dark ? text('浅色主题', 'Light theme') : text('深色主题', 'Dark theme')}</button><button className="btn-danger text-xs" onClick={logout}>{text('退出登录', 'Log out')}</button></div><div className="mt-2 truncate px-1 text-xs text-[#9b9ca3]">{user?.display_name || user?.student_id}</div></div>
    </aside>
    {sidebarOpen && <button aria-label={text('关闭导航', 'Close navigation')} className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setSidebarOpen(false)} />}
    <main className="workspace min-h-0">
      <header className="mobile-header"><button className="btn" onClick={() => setSidebarOpen(true)} aria-label={text('打开导航', 'Open navigation')}>☰</button><strong className="truncate">{activeChapter?.title || 'TA Platform'}</strong><LanguageToggle /><button className="btn ml-auto" onClick={chooseGeneral} title={text('新建会话', 'New conversation')}>+</button></header>
      {activeChapter && activeCourse ? <div className="grid min-h-0 flex-1 grid-rows-[minmax(300px,46vh)_minmax(560px,1fr)] md:grid-cols-[minmax(340px,48%)_minmax(380px,1fr)] md:grid-rows-1">
        <section className="flex min-h-0 flex-col border-b border-[var(--border-color)] bg-[var(--bg-secondary)] md:border-b-0 md:border-r">
          <header className="border-b border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-3"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="text-xs font-medium text-[var(--accent-color)]">{activeCourse.name}</p><h1 className="mt-0.5 truncate font-semibold">{activeChapter.title}</h1></div>{activeMaterial && <button className="btn shrink-0 px-3 py-1.5 text-xs" onClick={() => downloadMaterial(activeMaterial)}>{text('下载', 'Download')}</button>}</div>{activeChapter.description && <p className="mt-1 line-clamp-2 text-xs muted">{activeChapter.description}</p>}</header>
          <nav className="flex gap-1 overflow-x-auto border-b border-[var(--border-color)] bg-[var(--bg-primary)] px-3 py-2">{activeChapter.materials.map((material, index) => <button key={material.id} onClick={() => showMaterial(material)} className={`max-w-48 shrink-0 truncate rounded-md px-3 py-1.5 text-xs ${activeMaterial?.id === material.id ? 'bg-[var(--accent-muted)] font-medium text-[var(--accent-color)]' : 'muted hover:bg-[var(--bg-secondary)]'}`}>{index + 1}. {material.filename}</button>)}{activeChapter.materials.length === 0 && <span className="px-2 py-1.5 text-xs muted">{text('本章节暂无课件', 'No materials in this chapter')}</span>}</nav>
          <div className="min-h-0 flex-1 overflow-auto p-3">{previewLoading ? <div className="flex h-full items-center justify-center text-sm muted">{text('正在加载课件...', 'Loading material...')}</div> : previewError ? <div className="flex h-full items-center justify-center px-6 text-center text-sm text-rose-600">{previewError}</div> : !activeMaterial ? <div className="flex h-full items-center justify-center px-6 text-center"><div><p className="font-medium">{text('本章节暂未上传课件', 'No material has been uploaded')}</p><p className="mt-1 text-sm muted">{text('仍可在右侧向 AI 询问本章节内容。', 'You can still ask the AI about this chapter on the right.')}</p></div></div> : activeMaterial.preview_kind === 'pdf' && previewUrl ? <iframe title={activeMaterial.filename} src={previewUrl} className="h-full min-h-[420px] w-full border-0 bg-white" /> : activeMaterial.preview_kind === 'image' && previewUrl ? <div className="flex min-h-full items-center justify-center"><img src={previewUrl} alt={activeMaterial.filename} className="max-h-full max-w-full object-contain" /></div> : activeMaterial.preview_kind === 'text' ? <pre className="whitespace-pre-wrap break-words rounded-md bg-[var(--card-bg)] p-4 text-sm leading-6">{previewText}</pre> : <div className="flex h-full items-center justify-center px-6 text-center"><div><p className="font-medium">{activeMaterial.filename}</p><p className="mt-2 text-sm muted">{text('浏览器不能直接预览该格式，请下载后打开。资料文字已在后台提取，可直接在右侧向 AI 提问。', 'This format cannot be previewed in the browser. Download it to open locally; extracted text is available to the AI on the right.')}</p><button className="btn-primary mt-4 rounded-md px-4 py-2 text-sm" onClick={() => downloadMaterial(activeMaterial)}>{text('下载课件', 'Download material')}</button></div></div>}</div>
        </section>
        <section className="flex min-h-0 flex-col bg-[var(--bg-primary)]"><div className="border-b border-[var(--border-color)] px-5 py-3"><span className="font-medium">{text('章节 AI 助手', 'Chapter AI assistant')}</span><span className="ml-2 text-xs muted">{text('回答会优先参考左侧章节资料', 'Answers prioritize the chapter materials')}</span></div><ChatContainer key={chatKey.current} chatId={activeChatId} mode={activeMode} /><ChatInput chatId={activeChatId} mode={activeMode} courseId={activeCourse.id} chapterIndex={activeChapter.sort_order} chapterId={activeChapter.legacy ? undefined : activeChapter.id} onNewConversation={bindConversation} /></section>
      </div> : <section className="mx-auto flex min-h-0 w-full max-w-4xl flex-1 flex-col"><div className="border-b border-[var(--border-color)] bg-[var(--bg-primary)] px-5 py-3"><span className="font-medium">{activeChatId === 'general' ? text('AI 助教', 'AI Assistant') : text('会话', 'Conversation')}</span><span className="ml-2 text-xs muted">{text('从左侧课程目录选择章节，可结合课件提问。', 'Choose a chapter from the course directory to ask with its materials.')}</span></div><ChatContainer key={chatKey.current} chatId={activeChatId} mode={activeMode} /><ChatInput chatId={activeChatId} mode={activeMode} onNewConversation={bindConversation} /></section>}
    </main>
  </div>;
}
