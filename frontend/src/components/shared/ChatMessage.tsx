import { useEffect, useRef } from 'react';
import { marked } from 'marked';
import katex from 'katex';
import hljs from 'highlight.js';
import DOMPurify from 'dompurify';
import { useLanguage } from '../../i18n/LanguageContext';

interface Props {
  role: string;
  content: string;
}

export default function ChatMessage({ role, content }: Props) {
  const contentRef = useRef<HTMLDivElement>(null);
  const { text } = useLanguage();

  useEffect(() => {
    if (role !== 'assistant' || !contentRef.current) return;

    let html: string;
    try {
      // Protect LaTeX from Markdown emphasis parsing, then restore rendered KaTeX.
      const mathFragments: string[] = [];
      const preserveMath = (formula: string, displayMode: boolean) => {
        const token = `MATHPLACEHOLDER${mathFragments.length}END`;
        mathFragments.push(katex.renderToString(formula.trim(), { displayMode, throwOnError: false }));
        return token;
      };
      let processed = content
        .replace(/\\\[/g, '$$')
        .replace(/\\\]/g, '$$')
        .replace(/\\\(/g, '$')
        .replace(/\\\)/g, '$')
        .replace(/\$\$([\s\S]+?)\$\$/g, (_, formula: string) => preserveMath(formula, true))
        .replace(/\$([^$\n]+?)\$/g, (_, formula: string) => preserveMath(formula, false));
      html = marked.parse(processed, { async: false }) as string;
      mathFragments.forEach((fragment, index) => {
        html = html.replace(`MATHPLACEHOLDER${index}END`, fragment);
      });
    } catch {
      html = marked.parse(content, { async: false }) as string;
    }
    // Assistant text can include user-supplied material. Sanitize the final
    // Markdown and KaTeX HTML before adding it to the document.
    contentRef.current.innerHTML = DOMPurify.sanitize(html, {
      FORBID_TAGS: ['img', 'iframe', 'form', 'audio', 'video'],
    });

    // Syntax highlighting
    contentRef.current.querySelectorAll('pre code').forEach((block) => {
      try {
        hljs.highlightElement(block as HTMLElement);
        const pre = block.parentElement;
        if (pre) {
          const btn = document.createElement('button');
          btn.className = 'copy-button';
          btn.textContent = text('复制', 'Copy');
          btn.onclick = () => {
            navigator.clipboard.writeText((block as HTMLElement).textContent || '').then(() => {
              btn.textContent = text('已复制', 'Copied!');
              setTimeout(() => btn.textContent = text('复制', 'Copy'), 2000);
            });
          };
          pre.appendChild(btn);
        }
      } catch {}
    });

  }, [content, role, text]);

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
