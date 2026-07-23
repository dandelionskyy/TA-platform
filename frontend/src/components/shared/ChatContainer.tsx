import { useState, useEffect, useRef } from 'react';
import { api } from '../../services/api';
import ChatMessage from './ChatMessage';
import TypingIndicator from './TypingIndicator';
import SkeletonLoader from './SkeletonLoader';
import { useLanguage } from '../../i18n/LanguageContext';

interface Props {
  chatId: string;
  mode: string;
}

interface Message {
  id: string;
  role: string;
  content: string;
  createdAt: string;
}

export default function ChatContainer({ chatId, mode }: Props) {
  const { text } = useLanguage();
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const chatBoxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (chatId === 'general') {
      setMessages([]);
      return;
    }
    loadMessages();
  }, [chatId]);

  useEffect(() => {
    if (chatBoxRef.current) {
      chatBoxRef.current.scrollTop = chatBoxRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

  const loadMessages = async () => {
    setLoading(true);
    try {
      const data = await api.getMessages(chatId, 1);
      setMessages(data.messages || []);
    } catch {
      setMessages([]);
    } finally {
      setLoading(false);
    }
  };

  const addMessage = (text: string, sender: 'user' | 'assistant') => {
    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      role: sender === 'user' ? 'user' : 'assistant',
      content: text,
      createdAt: new Date().toISOString(),
    }]);
  };

  const showTyping = () => setIsTyping(true);
  const hideTyping = () => setIsTyping(false);

  // Expose methods to parent via window (for ChatInput)
  useEffect(() => {
    (window as any).__chatMethods = { addMessage, showTyping, hideTyping, loadMessages };
    return () => { delete (window as any).__chatMethods; };
  }, [chatId]);

  if (loading) return <SkeletonLoader />;

  const welcomeHTML = chatId === 'general';

  return (
    <div className="chat-box" ref={chatBoxRef}>
      {welcomeHTML && messages.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-full text-center px-5">
          <h1 className="text-[2.4em] text-[var(--text-primary)] mb-4 font-bold">
            <span className="typewriter">{text('AI 学习助教', 'AI Learning Assistant')}</span>
          </h1>
          <div className="flex gap-5 justify-center flex-wrap mt-5">
            {[
              { title: text('解释一个概念', 'Explain a concept'), desc: text('“什么是 P-N 结？”', '"What is a P-N junction?"') },
              { title: text('总结一个章节', 'Summarize a chapter'), desc: text('“请总结第三章的重点。”', '"Give me the key points of Chapter 3."') },
              { title: text('请求一个例子', 'Ask for examples'), desc: text('“请举例说明节点分析。”', '"Show me an example of nodal analysis."') },
            ].map((card, i) => (
              <div key={i}
                className="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl p-5 w-[220px] cursor-pointer
                  opacity-0 translate-y-5 animate-[slideInUp_0.4s_ease-out_forwards] hover:-translate-y-1 hover:shadow-lg transition-all"
                style={{ animationDelay: `${1.5 + i * 0.15}s` }}
                onClick={() => {
                  (window as any).__chatMethods?.addMessage(card.desc.replace(/"/g, ''), 'user');
                }}>
                <h4 className="text-[var(--text-primary)] mb-2.5">{card.title}</h4>
                <p className="text-sm text-[var(--text-secondary)]">{card.desc}</p>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <>
          {messages.map(msg => (
            <ChatMessage key={msg.id} role={msg.role} content={msg.content} />
          ))}
        </>
      )}
      {isTyping && <TypingIndicator />}
    </div>
  );
}
