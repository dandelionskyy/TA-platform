import { useState, useEffect } from 'react';
import { useAuthStore } from '../stores/authStore';
import { api } from '../services/api';
import RobotMonitor from '../components/robot/RobotMonitor';

interface Student {
  id: string;
  student_id: string;
  display_name: string;
  phone: string;
  is_active: boolean;
}

interface Message {
  id: string;
  role: string;
  content: string;
  context_source?: string;
  created_at: string;
}

interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export default function TeacherPage() {
  const { user, logout } = useAuthStore();
  const [students, setStudents] = useState<Student[]>([]);
  const [search, setSearch] = useState('');
  const [selectedStudent, setSelectedStudent] = useState<Student | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [selectedConv, setSelectedConv] = useState<string | null>(null);
  const [usage, setUsage] = useState<any>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark');

  useEffect(() => { searchStudents(); }, []);

  const toggleDark = () => {
    const next = !dark;
    setDark(next);
    localStorage.setItem('theme', next ? 'dark' : 'light');
    document.documentElement.classList.toggle('dark', next);
  };

  const searchStudents = async () => {
    try {
      const data = await api.getStudents(search);
      setStudents(data.students || []);
    } catch {}
  };

  const selectStudent = async (s: Student) => {
    setSelectedStudent(s);
    setSelectedConv(null);
    setMessages([]);
    try {
      const [convData, usageData] = await Promise.all([
        api.getStudentConversations(s.id),
        api.getStudentUsage(s.id),
      ]);
      setConversations(convData.conversations || []);
      setUsage(usageData);
    } catch {}
  };

  const selectConversation = async (convId: string) => {
    if (!selectedStudent) return;
    setSelectedConv(convId);
    try {
      const data = await api.getStudentMessages(selectedStudent.id, convId);
      setMessages(data.messages || []);
    } catch {}
  };

  return (
    <div className="flex h-screen bg-[var(--bg-secondary)]">
      {/* Sidebar */}
      <aside className={`${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0 fixed lg:relative z-30 w-[260px] h-full bg-[var(--bg-sidebar)] text-[var(--text-sidebar)] flex flex-col p-2.5 transition-transform duration-300`}>
        <div className="px-2.5 py-3 text-lg font-semibold border-b border-[var(--border-color)] mb-2">Teacher Panel</div>
        <div className="px-2.5 mb-3">
          <input type="text" value={search} onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && searchStudents()}
            placeholder="Search students..."
            className="w-full px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-white/50 outline-none text-sm" />
        </div>
        <div className="flex-1 overflow-y-auto">
          {students.map(s => (
            <button key={s.id} onClick={() => selectStudent(s)}
              className={`w-full text-left px-3 py-2.5 rounded-md text-sm hover:bg-white/10 transition-colors block ${selectedStudent?.id === s.id ? 'bg-white/15' : ''}`}>
              <div className="truncate">{s.display_name || s.student_id}</div>
              <div className="text-xs text-[var(--text-secondary)]">{s.student_id}</div>
            </button>
          ))}
        </div>
        <div className="border-t border-[var(--border-color)] pt-2.5 px-2.5 space-y-2">
          <button onClick={toggleDark} className="w-full py-2 rounded-md bg-transparent border border-[var(--text-secondary)] text-[var(--text-sidebar)] text-sm cursor-pointer hover:bg-white/10">{dark ? 'Light' : 'Dark'}</button>
          <button onClick={logout} className="w-full py-2 rounded-md text-sm text-red-400 hover:text-red-300 cursor-pointer">Logout</button>
        </div>
      </aside>
      {sidebarOpen && <div className="lg:hidden fixed inset-0 z-20 bg-black/50" onClick={() => setSidebarOpen(false)} />}

      {/* Main */}
      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        <div className="lg:hidden flex items-center gap-3 px-4 py-3 border-b border-[var(--border-color)] bg-[var(--bg-primary)]">
          <button onClick={() => setSidebarOpen(true)} className="text-xl cursor-pointer">&#9776;</button>
          <span className="font-semibold">Teacher Panel</span>
        </div>

        <div className="flex-1 p-4 md:p-6 space-y-6">
          {selectedStudent ? (
            <>
              {/* Student info + Usage */}
              <div className="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl p-5">
                <h2 className="text-xl font-semibold mb-1">{selectedStudent.display_name || selectedStudent.student_id}</h2>
                <p className="text-sm text-[var(--text-secondary)]">{selectedStudent.student_id} | {selectedStudent.phone}</p>
                {usage && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                    {[
                      ['Messages', usage.total_chat_messages],
                      ['Conversations', usage.total_conversations],
                      ['Logins', usage.total_login_count],
                      ['Robot Qs', usage.total_robot_questions],
                    ].map(([label, val]) => (
                      <div key={label} className="text-center p-3 rounded-lg bg-[var(--bg-secondary)]">
                        <div className="text-2xl font-bold text-[var(--accent-color)]">{val}</div>
                        <div className="text-xs text-[var(--text-secondary)] mt-1">{label}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Conversations */}
              <div className="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl p-5">
                <h3 className="font-semibold mb-3">Conversation History</h3>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {conversations.map(c => (
                    <button key={c.id} onClick={() => selectConversation(c.id)}
                      className={`w-full text-left px-4 py-3 rounded-lg text-sm hover:bg-[var(--bg-secondary)] transition-colors block ${selectedConv === c.id ? 'bg-[var(--bg-secondary)] ring-1 ring-[var(--accent-color)]' : ''}`}>
                      <div className="flex justify-between">
                        <span>{c.title || c.id.slice(0, 8)}</span>
                        <span className="text-xs text-[var(--text-secondary)]">{c.updated_at ? new Date(c.updated_at).toLocaleDateString() : ''}</span>
                      </div>
                    </button>
                  ))}
                  {conversations.length === 0 && <p className="text-sm text-[var(--text-secondary)]">No conversations yet</p>}
                </div>
              </div>

              {/* Messages */}
              {selectedConv && messages.length > 0 && (
                <div className="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl p-5">
                  <h3 className="font-semibold mb-3">Messages</h3>
                  <div className="space-y-4 max-h-[50vh] overflow-y-auto">
                    {messages.map(m => (
                      <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-sm ${
                          m.role === 'user'
                            ? 'bg-[var(--user-message-bg)] text-[var(--user-message-text)] rounded-br-sm'
                            : 'bg-[var(--bot-message-bg)] text-[var(--text-primary)] rounded-bl-sm'
                        }`}>
                          <p className="whitespace-pre-wrap">{m.content}</p>
                          <p className="text-[10px] mt-1 opacity-60">{new Date(m.created_at).toLocaleString()}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-[var(--text-secondary)]">
              <p>Select a student from the sidebar to view their activity</p>
            </div>
          )}

          {/* Robot Monitor */}
          <div className="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl p-5">
            <h3 className="font-semibold mb-3">Robot Status</h3>
            <RobotMonitor role="teacher" />
          </div>
        </div>
      </main>
    </div>
  );
}
