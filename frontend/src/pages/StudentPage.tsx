import { useState, useEffect, useRef } from 'react';
import { useAuthStore } from '../stores/authStore';
import { api } from '../services/api';
import ChatContainer from '../components/shared/ChatContainer';
import ChatInput from '../components/shared/ChatInput';
import RobotMonitor from '../components/robot/RobotMonitor';

interface Conversation {
  id: string;
  title: string;
  course_id?: string;
  chapter_index?: number;
  created_at: string;
  updated_at: string;
}

interface CourseConfig {
  chapters: string[];
  path: string;
}

// Course configuration — editable, mirrors original assistant.html
const COURSES: Record<string, CourseConfig> = {
  'Transistors & Optoelectronics': {
    chapters: ['Chapter 1','Chapter 2','Chapter 3','Chapter 4','Chapter 5','Chapter 6','Chapter 7','Chapter 8','Chapter 9','Chapter 10','Chapter 11'],
    path: 'Semiconductor Physics',
  },
};

export default function StudentPage() {
  const { user, logout } = useAuthStore();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeChatId, setActiveChatId] = useState('general');
  const [activeMode, setActiveMode] = useState<string>('general');
  const [pptSrc, setPptSrc] = useState('');
  const [showPpt, setShowPpt] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark');
  const chatKeyRef = useRef(0);

  useEffect(() => { loadConversations(); }, []);

  const loadConversations = async () => {
    try {
      const data = await api.getConversations(1);
      setConversations(data.conversations || []);
    } catch {}
  };

  const toggleDark = () => {
    const next = !dark;
    setDark(next);
    localStorage.setItem('theme', next ? 'dark' : 'light');
    document.documentElement.classList.toggle('dark', next);
  };

  const switchToChat = (chatId: string, courseName?: string, chapterIdx?: number) => {
    setActiveChatId(chatId);
    chatKeyRef.current++;
    if (chatId === 'general') {
      setShowPpt(false);
      setPptSrc('');
      setActiveMode('general');
    } else if (courseName && chapterIdx !== undefined) {
      const course = COURSES[courseName];
      if (course) {
        setShowPpt(true);
        setPptSrc(`/static/ppt/${course.path}/chapter_${chapterIdx + 1}.pdf`);
        const slug = course.path.replace(/\s+/g, '-');
        setActiveMode(`${slug}-ch${chapterIdx}`);
      }
    }
    setSidebarOpen(false);
  };

  const handleNewConversation = (convId: string) => {
    setActiveChatId(convId);
    setActiveMode('chatbot');
    setShowPpt(false);
    setPptSrc('');
    chatKeyRef.current++;
    loadConversations();
  };

  return (
    <div className="flex h-screen bg-[var(--bg-secondary)]">
      {/* Sidebar */}
      <aside className={`${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0 fixed lg:relative z-30 w-[260px] h-full bg-[var(--bg-sidebar)] text-[var(--text-sidebar)] flex flex-col p-2.5 transition-transform duration-300`}>
        <div className="flex items-center justify-between px-2.5 py-2 border-b border-[var(--border-color)] mb-2.5">
          <div className="text-lg font-semibold px-2">TA Platform</div>
          <button onClick={() => switchToChat('general')}
            className="bg-transparent border border-[var(--text-secondary)] text-[var(--text-sidebar)] px-3 py-1 rounded-md cursor-pointer text-lg hover:bg-white/10 transition-colors">
            +
          </button>
        </div>

        {/* Conversations */}
        <div className="flex-1 overflow-y-auto">
          <div className="px-3 py-2 text-xs text-[var(--text-secondary)] uppercase tracking-wider">Recent Chats</div>
          {conversations.slice(0, 10).map(conv => (
            <button key={conv.id}
              onClick={() => { setActiveChatId(conv.id); setActiveMode('chatbot'); setShowPpt(false); setPptSrc(''); chatKeyRef.current++; }}
              className={`w-full text-left px-3 py-2.5 rounded-md text-sm hover:bg-white/10 transition-colors truncate block ${activeChatId === conv.id ? 'bg-white/15' : ''}`}>
              {conv.title || conv.id.slice(0, 8)}
            </button>
          ))}
        </div>

        {/* Courses */}
        <div className="flex-1 overflow-y-auto border-t border-[var(--border-color)]">
          <div className="px-3 py-2 text-xs text-[var(--text-secondary)] uppercase tracking-wider">Courses</div>
          {Object.entries(COURSES).map(([name, course]) => {
            const slug = course.path.replace(/\s+/g, '-');
            return (
              <details key={name} className="mb-1">
                <summary className="px-3 py-2.5 rounded-md text-sm hover:bg-white/10 cursor-pointer transition-colors">{name}</summary>
                <div className="ml-4">
                  {course.chapters.map((ch, i) => {
                    const chId = `${slug}-ch${i}`;
                    return (
                      <button key={i}
                        onClick={() => switchToChat(chId, name, i)}
                        className={`w-full text-left px-3 py-2 rounded-md text-sm hover:bg-white/10 transition-colors block relative overflow-hidden
                          ${activeChatId === chId ? 'bg-white/15 text-[var(--text-sidebar)]' : 'text-[var(--text-secondary)]'}`}>
                        <span className={`absolute left-0 top-0 h-full w-[3px] bg-[var(--accent-color)] transition-transform duration-300 ${activeChatId === chId ? 'translate-x-0' : '-translate-x-full'}`} />
                        {ch}
                      </button>
                    );
                  })}
                </div>
              </details>
            );
          })}
        </div>

        {/* Robot status — compact sidebar card */}
        <div className="border-t border-[var(--border-color)] pt-2 px-1">
          <div className="text-xs text-[var(--text-secondary)] uppercase tracking-wider px-2 mb-1">Robot</div>
          <RobotMonitor role="student" />
        </div>

        {/* Bottom bar */}
        <div className="border-t border-[var(--border-color)] pt-2.5 px-2.5 space-y-2">
          <button onClick={toggleDark} className="w-full py-2 rounded-md bg-transparent border border-[var(--text-secondary)] text-[var(--text-sidebar)] text-sm cursor-pointer hover:bg-white/10 transition-colors">
            {dark ? 'Light Mode' : 'Dark Mode'}
          </button>
          <div className="flex items-center gap-2 px-2 pb-1">
            <span className="text-sm text-[var(--text-secondary)] truncate flex-1">{user?.display_name || user?.student_id}</span>
            <button onClick={logout} className="text-xs text-red-400 hover:text-red-300 cursor-pointer">Logout</button>
          </div>
        </div>
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && <div className="lg:hidden fixed inset-0 z-20 bg-black/50" onClick={() => setSidebarOpen(false)} />}

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Mobile header */}
        <div className="lg:hidden flex items-center gap-3 px-4 py-3 border-b border-[var(--border-color)] bg-[var(--bg-primary)]">
          <button onClick={() => setSidebarOpen(true)} className="text-xl cursor-pointer">&#9776;</button>
          <span className="font-semibold">TA Platform</span>
        </div>

        {/* Content area */}
        <div className="flex-1 flex min-h-0">
          {showPpt && pptSrc && (
            <div className="hidden md:flex flex-1 border-r border-[var(--border-color)] p-5 min-w-0">
              <iframe src={pptSrc} className="w-full h-full border-0 rounded-lg" title="PPT Viewer" />
            </div>
          )}
          <div className={`flex-1 flex flex-col min-w-0 ${!showPpt ? 'max-w-3xl mx-auto w-full' : ''}`}>
            <ChatContainer key={chatKeyRef.current} chatId={activeChatId} mode={activeMode} />
            <ChatInput chatId={activeChatId} mode={activeMode} onNewConversation={handleNewConversation} />
          </div>
        </div>
      </main>
    </div>
  );
}
