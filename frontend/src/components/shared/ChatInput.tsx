import { useState, useRef } from 'react';
import { api } from '../../services/api';

interface Props {
  chatId: string;
  mode: string;
  onNewConversation?: (convId: string) => void;
}

export default function ChatInput({ chatId, mode, onNewConversation }: Props) {
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim() || sending) return;

    const userMessage = text.trim();
    setText('');
    setSending(true);

    const chatMethods = (window as any).__chatMethods;
    chatMethods?.addMessage(userMessage, 'user');
    chatMethods?.showTyping();

    const formData = new FormData();
    formData.append('message', userMessage);
    formData.append('mode', mode);
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
      chatMethods?.addMessage('Sorry, an error occurred: ' + (err.message || 'Unknown error'), 'assistant');
    } finally {
      setSending(false);
      setFile(null);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFile(e.target.files?.[0] || null);
  };

  return (
    <div className="px-5 py-4 border-t border-[var(--border-color)] bg-[var(--bg-primary)]">
      {file && (
        <div className="flex items-center gap-2.5 mb-2 px-3 py-2 rounded-lg bg-[var(--bg-secondary)] text-sm">
          <span className="flex-1 truncate text-[var(--text-secondary)]">{file.name}</span>
          <button onClick={() => { setFile(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}
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
        <input type="text" value={text} onChange={e => setText(e.target.value)}
          placeholder={chatId === 'general' ? 'Ask me anything...' : 'Ask about the content...'}
          className="flex-1 px-4 py-2.5 bg-transparent text-base outline-none text-[var(--text-primary)]"
          disabled={sending} autoComplete="off" />
        <button type="submit" disabled={!text.trim() || sending}
          className="px-3 py-2 bg-transparent text-[var(--accent-color)] rounded-full cursor-pointer text-xl hover:bg-[var(--border-color)] hover:scale-110 transition-all disabled:text-[var(--text-secondary)] disabled:cursor-not-allowed">
          &#10148;
        </button>
      </form>
    </div>
  );
}
