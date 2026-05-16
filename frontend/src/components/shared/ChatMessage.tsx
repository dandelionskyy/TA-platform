import { useEffect, useRef } from 'react';
import { marked } from 'marked';
import katex from 'katex';
import hljs from 'highlight.js';

interface Props {
  role: string;
  content: string;
}

export default function ChatMessage({ role, content }: Props) {
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (role !== 'assistant' || !contentRef.current) return;

    let html: string;
    try {
      // Pre-process LaTeX delimiters before markdown parsing
      let processed = content
        .replace(/\\\[/g, '$$')
        .replace(/\\\]/g, '$$')
        .replace(/\\\(/g, '$')
        .replace(/\\\)/g, '$');
      html = marked.parse(processed, { async: false }) as string;
    } catch {
      html = content;
    }
    contentRef.current.innerHTML = html;

    // Syntax highlighting
    contentRef.current.querySelectorAll('pre code').forEach((block) => {
      try {
        hljs.highlightElement(block as HTMLElement);
        const pre = block.parentElement;
        if (pre) {
          const btn = document.createElement('button');
          btn.className = 'copy-button';
          btn.textContent = 'Copy';
          btn.onclick = () => {
            navigator.clipboard.writeText((block as HTMLElement).textContent || '').then(() => {
              btn.textContent = 'Copied!';
              setTimeout(() => btn.textContent = 'Copy', 2000);
            });
          };
          pre.appendChild(btn);
        }
      } catch {}
    });

    // KaTeX rendering
    try {
      renderMathElements(contentRef.current);
    } catch {}
  }, [content, role]);

  const isUser = role === 'user';

  return (
    <div className={`message ${isUser ? 'user' : 'bot'}`}>
      {!isUser && <div className="bot-avatar">AI</div>}
      <div className="content" ref={isUser ? undefined : contentRef}>
        {isUser ? content : undefined}
      </div>
    </div>
  );
}

function renderMathElements(container: HTMLElement) {
  const delimiters = [
    { left: '$$', right: '$$', display: true },
    { left: '$', right: '$', display: false },
  ];
  const text = container.innerHTML;
  let result = text;
  for (const { left, right, display } of delimiters) {
    const regex = new RegExp(`\\${left}([^$]+?)\\${right}`, 'g');
    result = result.replace(regex, (_, formula: string) => {
      try {
        return katex.renderToString(formula.trim(), { displayMode: display, throwOnError: false });
      } catch {
        return _;
      }
    });
  }
  container.innerHTML = result;
}
