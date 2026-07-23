import { useState, useRef } from 'react';
import { api } from '../../services/api';
import { useLanguage } from '../../i18n/LanguageContext';

interface Props {
  chatId: string;
  mode: string;
  courseId?: string;
  chapterIndex?: number;
  chapterId?: string;
  onNewConversation?: (convId: string) => void;
}

export default function ChatInput({ chatId, mode, courseId, chapterIndex, chapterId, onNewConversation }: Props) {
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { text: tr, language } = useLanguage();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || sending) return;

    const userMessage = inputText.trim();
    setInputText('');
    setSending(true);

    const chatMethods = (window as any).__chatMethods;
    chatMethods?.addMessage(userMessage, 'user');
    chatMethods?.showTyping();

    const formData = new FormData();
    formData.append('message', userMessage);
    formData.append('mode', mode);
    if (courseId) formData.append('course_id', courseId);
    if (chapterIndex !== undefined) formData.append('chapter_index', String(chapterIndex));
    if (chapterId) formData.append('chapter_id', chapterId);
    if (chatId !== 'general') {
      formData.append('conversation_id', chatId);
    }
    if (file) {
      formData.append('file', file);
    }

    try {
      const result = await api.sendMessage(formData);
      chatMethods?.hideTyping();
      chatMethods?.addMessage(result.response, 'assistant');
      if (onNewConversation && chatId === 'general') {
        onNewConversation(result.conversation_id);
      }
    } catch (err: any) {
      chatMethods?.hideTyping();
      chatMethods?.addMessage(tr('抱歉，发生了错误：', 'Sorry, an error occurred: ') + (err.message || tr('未知错误', 'Unknown error')), 'assistant');
    } finally {
      setSending(false);
      setFile(null);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFile(e.target.files?.[0] || null);
  };

  const startVoiceInput = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return;
    const recognition = new SpeechRecognition();
    recognition.lang = language === 'zh' ? 'zh-CN' : 'en-US';
    recognition.interimResults = false;
    recognition.onresult = (event: any) => setInputText((event.results?.[0]?.[0]?.transcript || '').trim());
    recognition.start();
  };

  return (
    <div className="px-5 py-4 border-t border-[var(--border-color)] bg-[var(--bg-primary)]">
      {file && (
        <div className="flex items-center gap-2.5 mb-2 px-3 py-2 rounded-lg bg-[var(--bg-secondary)] text-sm">
          <span className="flex-1 truncate text-[var(--text-secondary)]">{file.name}</span>
          <button type="button" onClick={() => { setFile(null); if (fileInputRef.current) fileInputRef.current.value = ''; }} title={tr('移除附件', 'Remove attachment')}
            className="bg-none border-none text-[var(--text-secondary)] cursor-pointer text-lg">&times;</button>
        </div>
      )}
      <form onSubmit={handleSubmit} className="flex items-center bg-[var(--bg-secondary)] rounded-[25px] px-1 py-1">
        <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden"
          accept=".pdf,.pptx,.docx,.png,.jpg,.jpeg,.gif,.webp" />
        <button type="button" onClick={() => fileInputRef.current?.click()}
          className="px-3 py-2 bg-transparent text-[var(--text-secondary)] rounded-full cursor-pointer text-xl hover:bg-[var(--border-color)] hover:scale-110 transition-all">
          &#128206;
        </button>
        <button type="button" onClick={startVoiceInput} title={tr('语音输入', 'Voice input')}
          className="px-3 py-2 bg-transparent text-[var(--text-secondary)] rounded-full cursor-pointer text-base hover:bg-[var(--border-color)] transition-all">
          &#127908;
        </button>
        <input type="text" value={inputText} onChange={e => setInputText(e.target.value)}
          placeholder={courseId ? tr('询问本章节课件内容...', 'Ask about this chapter...') : chatId === 'general' ? tr('请输入你的问题...', 'Ask me anything...') : tr('继续当前会话...', 'Continue this conversation...')}
          className="flex-1 px-4 py-2.5 bg-transparent text-base outline-none text-[var(--text-primary)]"
          disabled={sending} autoComplete="off" />
        <button type="submit" disabled={!inputText.trim() || sending}
          className="px-3 py-2 bg-transparent text-[var(--accent-color)] rounded-full cursor-pointer text-xl hover:bg-[var(--border-color)] hover:scale-110 transition-all disabled:text-[var(--text-secondary)] disabled:cursor-not-allowed">
          &#10148;
        </button>
      </form>
    </div>
  );
}
