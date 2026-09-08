import { useEffect, useState, useRef } from 'react';
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

interface ActiveFile {
  id: string;
  filename: string;
  mime_type?: string;
  size_bytes: number;
  processing_status: string;
  page_count?: number;
}

interface GuidedQuestion {
  question: string;
  options: string[];
}

export default function ChatInput({ chatId, mode, courseId, chapterIndex, chapterId, onNewConversation }: Props) {
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [activeFile, setActiveFile] = useState<ActiveFile | null>(null);
  const [removingFile, setRemovingFile] = useState(false);
  const [guidedMode, setGuidedMode] = useState(() => localStorage.getItem('guided_mode') === 'true');
  const [guidedQuestion, setGuidedQuestion] = useState<GuidedQuestion | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const previousChatIdRef = useRef(chatId);
  const { text: tr, language } = useLanguage();

  useEffect(() => {
    let cancelled = false;
    const previousChatId = previousChatIdRef.current;
    previousChatIdRef.current = chatId;
    if (previousChatId !== 'general') setGuidedQuestion(null);
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (chatId === 'general') {
      setActiveFile(null);
      return () => { cancelled = true; };
    }
    setActiveFile(null);
    api.getConversationFile(chatId)
      .then(result => { if (!cancelled) setActiveFile(result.file); })
      .catch(() => { if (!cancelled) setActiveFile(null); });
    return () => { cancelled = true; };
  }, [chatId]);

  const sendUserMessage = async (userMessage: string) => {
    if (!userMessage.trim() || sending) return;
    setInputText('');
    setSending(true);
    setGuidedQuestion(null);

    const chatMethods = (window as any).__chatMethods;
    chatMethods?.addMessage(userMessage, 'user');
    chatMethods?.showTyping();

    const formData = new FormData();
    formData.append('message', userMessage);
    formData.append('mode', mode);
    formData.append('guided_mode', String(guidedMode));
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
      setGuidedQuestion(result.guided_question);
      setActiveFile(result.active_file);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      if (onNewConversation && chatId === 'general') {
        onNewConversation(result.conversation_id);
      }
    } catch (err: any) {
      chatMethods?.hideTyping();
      chatMethods?.addMessage(tr('抱歉，发生了错误：', 'Sorry, an error occurred: ') + (err.message || tr('未知错误', 'Unknown error')), 'assistant');
    } finally {
      setSending(false);
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    void sendUserMessage(inputText.trim());
  };

  const toggleGuidedMode = () => {
    const next = !guidedMode;
    setGuidedMode(next);
    localStorage.setItem('guided_mode', String(next));
    if (!next) setGuidedQuestion(null);
  };

  const chooseGuidedOption = (option: string) => {
    if (!guidedQuestion || sending) return;
    const requestMessage = `${guidedQuestion.question}\n\n${tr('我的选择：', 'My choice: ')}${option}`;
    void sendUserMessage(requestMessage);
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

  const removeReferenceFile = async () => {
    if (chatId === 'general' || !activeFile || removingFile) return;
    setRemovingFile(true);
    try {
      await api.removeConversationFile(chatId);
      setActiveFile(null);
    } catch (err: any) {
      const chatMethods = (window as any).__chatMethods;
      chatMethods?.addMessage(tr('无法移除参考文件：', 'Could not remove the reference file: ') + (err.message || tr('未知错误', 'Unknown error')), 'assistant');
    } finally {
      setRemovingFile(false);
    }
  };

  return (
    <div className="px-5 py-4 border-t border-[var(--border-color)] bg-[var(--bg-primary)]">
      <div className="mb-2 flex min-h-7 items-center justify-between gap-3">
        <div className="min-w-0">
          <span className="text-sm font-medium text-[var(--text-primary)]">{tr('引导模式', 'Guided mode')}</span>
          <span className="ml-2 hidden text-xs muted sm:inline">{tr('通过选项逐步深入学习', 'Continue learning with suggested choices')}</span>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={guidedMode}
          aria-label={tr('切换引导模式', 'Toggle guided mode')}
          onClick={toggleGuidedMode}
          disabled={sending}
          className={`relative h-5 w-9 shrink-0 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${guidedMode ? 'bg-[var(--accent-color)]' : 'bg-[var(--border-color)]'}`}
        >
          <span className={`absolute left-0 top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${guidedMode ? 'translate-x-[18px]' : 'translate-x-0.5'}`} />
        </button>
      </div>
      {guidedMode && guidedQuestion && (
        <div className="mb-3 border-l-2 border-[var(--accent-color)] bg-[var(--bg-secondary)] px-3 py-2.5">
          <p className="mb-2 text-sm font-medium text-[var(--text-primary)]">{guidedQuestion.question}</p>
          <div className="flex flex-wrap gap-2">
            {guidedQuestion.options.map(option => (
              <button
                key={option}
                type="button"
                disabled={sending}
                onClick={() => chooseGuidedOption(option)}
                className="rounded-md border border-[var(--border-color)] bg-[var(--bg-primary)] px-3 py-1.5 text-left text-sm text-[var(--text-secondary)] transition-colors hover:border-[var(--accent-color)] hover:text-[var(--accent-color)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {option}
              </button>
            ))}
          </div>
        </div>
      )}
      {(file || activeFile) && (
        <div className="flex items-center gap-2.5 mb-2 px-3 py-2 rounded-lg bg-[var(--bg-secondary)] text-sm">
          <span className="text-xs font-medium text-[var(--accent-color)]">
            {file ? (activeFile ? tr('替换为', 'Replace with') : tr('待发送', 'To attach')) : tr('当前参考', 'Current reference')}
          </span>
          <span className="flex-1 truncate text-[var(--text-secondary)]">{file?.name || activeFile?.filename}</span>
          {!file && activeFile?.processing_status === 'no_text' ? (
            <span className="text-xs text-amber-600">{tr('未提取到文字', 'No text extracted')}</span>
          ) : null}
          {!file && activeFile?.page_count ? <span className="text-xs muted">{tr(`${activeFile.page_count} 页`, `${activeFile.page_count} pages`)}</span> : null}
          <button type="button" disabled={removingFile} onClick={() => {
            if (file) {
              setFile(null);
              if (fileInputRef.current) fileInputRef.current.value = '';
            } else {
              void removeReferenceFile();
            }
          }} title={tr(file ? '取消附件' : '移除当前参考文件', file ? 'Cancel attachment' : 'Remove current reference file')}
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
