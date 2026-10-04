import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import BridgeAvatar, { normalizeAvatarState, type AvatarState } from '../components/bridge/BridgeAvatar';
import BridgeEvidence from '../components/bridge/BridgeEvidence';
import { LanguageToggle, useLanguage } from '../i18n/LanguageContext';
import { bridgeApi, BridgeApiError, type BridgeModule, type BridgeSession, type BridgeSource, type BridgeTutorReply, type GroundingStatus } from '../services/bridgeApi';
import { useAuthStore } from '../stores/authStore';
import '../styles/bridge.css';

interface ChatLine {
  id: number;
  kind: 'student' | 'assistant' | 'notice';
  content: string;
  reply?: BridgeTutorReply;
  welcomeLanguage?: 'en' | 'zh';
  groundingStatus?: GroundingStatus;
  sources?: BridgeSource[];
}

function sessionKey(moduleId: string) { return `bridge-session:${moduleId}`; }
function cachedSession(moduleId: string): BridgeSession | null {
  try {
    const value = localStorage.getItem(sessionKey(moduleId));
    if (!value) return null;
    const result = JSON.parse(value) as BridgeSession;
    if (result.module_id === moduleId && result.session_token && Date.parse(result.expires_at) > Date.now() + 60000) return result;
  } catch { /* An expired or malformed token is replaced below. */ }
  localStorage.removeItem(sessionKey(moduleId));
  return null;
}

function stageLabel(stage: string, language: 'en' | 'zh'): string {
  const stages: Record<string, [string, string]> = {
    greeting: ['开始学习', 'Greeting'], diagnosis: ['了解已有知识', 'Diagnosis'],
    probing: ['探究想法', 'Probing'], hinting: ['提示', 'Hinting'],
    struggle: ['独立思考', 'Try it yourself'], check: ['用自己的话解释', 'Explain it back'],
    explain: ['完整解释', 'Explanation'], celebrate: ['学习进展', 'Progress'],
  };
  return stages[stage.toLowerCase()]?.[language === 'zh' ? 0 : 1] || stage.replace(/_/g, ' ');
}

function safeName(value?: string): string {
  const name = (value || '').normalize('NFKC').replace(/[\p{Cc}\p{Cf}]/gu, '').replace(/\s+/g, ' ').trim();
  return Array.from(name).length <= 40 ? name : '';
}

function namedAssistantLines(lines: ChatLine[], name: string): Set<number> {
  const named = new Set<number>();
  if (!name) return named;
  let assistantTurn = 0;
  let lastNamedTurn = -4;
  let priorStage = '';
  for (const line of lines) {
    if (line.kind !== 'assistant') continue;
    const stage = line.reply?.stage || '';
    const greeting = !!line.welcomeLanguage && line.content.startsWith(line.welcomeLanguage === 'zh' ? '你好！' : 'Hello!');
    const transition = ['check', 'celebrate', 'struggle'].includes(stage) && stage !== priorStage
      && line.reply?.grounding_status === 'GROUNDED';
    if ((greeting || transition) && assistantTurn - lastNamedTurn >= 3) {
      named.add(line.id);
      lastNamedTurn = assistantTurn;
    }
    priorStage = stage;
    assistantTurn++;
  }
  return named;
}

export default function BridgeStudentPage() {
  const { language, text } = useLanguage();
  const user = useAuthStore(state => state.user);
  const [preferredName, setPreferredName] = useState('');
  const [modules, setModules] = useState<BridgeModule[]>([]);
  const [moduleId, setModuleId] = useState('');
  const [loadingModules, setLoadingModules] = useState(true);
  const [sessionAttempt, setSessionAttempt] = useState(0);
  const [moduleError, setModuleError] = useState('');
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [queued, setQueued] = useState<string | null>(null);
  const [retryMessage, setRetryMessage] = useState<string | null>(null);
  const [thinkingHint, setThinkingHint] = useState('');
  const [avatar, setAvatar] = useState<AvatarState>('questioning');
  const [assessmentLocked, setAssessmentLocked] = useState(false);
  const [sessionReady, setSessionReady] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(() => localStorage.getItem('bridge-reduced-motion') === 'true');
  const [online, setOnline] = useState(() => navigator.onLine);
  const sessionRef = useRef<BridgeSession | null>(null);
  const creatingRef = useRef<Promise<BridgeSession> | null>(null);
  const inFlightRef = useRef<AbortController | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const seqRef = useRef(0);
  const module = modules.find(entry => entry.id === moduleId);
  const accountName = user?.role === 'student' && safeName(user.display_name) !== safeName(user.student_id)
    ? safeName(user.display_name) : '';
  const studentName = safeName(preferredName) || accountName;
  const personalizedLines = namedAssistantLines(lines, studentName);

  const nextId = () => ++seqRef.current;
  const append = (kind: ChatLine['kind'], content: string, reply?: BridgeTutorReply) => {
    setLines(current => [...current, { id: nextId(), kind, content, reply }]);
  };

  const loadModules = useCallback(async () => {
    setLoadingModules(true); setModuleError('');
    try {
      const available = await bridgeApi.listPublicModules();
      setModules(available);
      setModuleId(current => available.some(item => item.id === current) ? current : available[0]?.id || '');
    } catch {
      setModuleError(language === 'zh' ? '暂时无法获取课程模块，请稍后重试。' : 'The module list is unavailable. Please try again.');
    } finally { setLoadingModules(false); }
  }, [language]);

  useEffect(() => { void loadModules(); }, [loadModules]);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => { window.removeEventListener('online', update); window.removeEventListener('offline', update); };
  }, []);
  useEffect(() => {
    let cancelled = false;
    const cached = moduleId ? cachedSession(moduleId) : null;
    sessionRef.current = cached;
    creatingRef.current = null;
    setLines([]); setQueued(null); setRetryMessage(null); setAvatar('questioning');
    setAssessmentLocked(cached?.lock_status || false);
    setSessionReady(!!cached);
    inFlightRef.current?.abort();
    inFlightRef.current = null;
    if (cached) {
      setLines([{ id: nextId(), kind: 'notice', content: language === 'zh' ? '匿名学习进度已恢复。你可以继续提问。' : 'Your anonymous learning progress is available. You can continue asking questions.' }]);
    } else if (moduleId) {
      const opening = bridgeApi.createSession(moduleId, language);
      creatingRef.current = opening;
      opening.then(session => {
        if (cancelled) { void bridgeApi.deleteSession(session.session_token).catch(() => undefined); return; }
        sessionRef.current = session;
        localStorage.setItem(sessionKey(moduleId), JSON.stringify(session));
        setAssessmentLocked(session.lock_status); setAvatar(normalizeAvatarState(session.avatar_state));
        setLines([{ id: nextId(), kind: 'assistant', content: session.welcome, welcomeLanguage: session.language,
          groundingStatus: session.grounding_status || 'INSUFFICIENT EVIDENCE', sources: session.sources || [] }]);
        setSessionReady(true); setModuleError('');
      }).catch(() => { if (!cancelled) setModuleError(language === 'zh' ? '无法开始学习会话。请重试。' : 'Could not start a learning session. Please retry.'); })
        .finally(() => { if (!cancelled) creatingRef.current = null; });
    }
    return () => { cancelled = true; };
  }, [moduleId, sessionAttempt]);
  useEffect(() => {
    const still = reducedMotion || window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    chatEndRef.current?.scrollIntoView({ block: 'end', behavior: still ? 'auto' : 'smooth' });
  }, [lines, thinkingHint, reducedMotion]);
  useEffect(() => () => inFlightRef.current?.abort(), []);

  const ensureSession = async (): Promise<BridgeSession> => {
    if (!moduleId) throw new BridgeApiError(404, 'No active module');
    if (sessionRef.current && Date.parse(sessionRef.current.expires_at) > Date.now() + 60000) return sessionRef.current;
    if (!creatingRef.current) {
      creatingRef.current = bridgeApi.createSession(moduleId, language).then(session => {
        sessionRef.current = session;
        localStorage.setItem(sessionKey(moduleId), JSON.stringify(session));
        setAssessmentLocked(session.lock_status);
        return session;
      }).finally(() => { creatingRef.current = null; });
    }
    return creatingRef.current;
  };

  const send = async (content: string, showStudent = true) => {
    const message = content.trim();
    if (!message || busy || !moduleId || !sessionReady) return;
    if (showStudent) append('student', message);
    setDraft(''); setRetryMessage(null);
    if (!navigator.onLine) { setQueued(message); setOnline(false); return; }
    setQueued(null); setBusy(true); setAvatar('thinking');
    setThinkingHint(text('正在查看课程资料…', 'Checking the module materials…'));
    const controller = new AbortController();
    inFlightRef.current = controller;
    const timers = [
      window.setTimeout(() => setThinkingHint(text('仍在思考，请稍候…', 'Still thinking…')), 5000),
      window.setTimeout(() => setThinkingHint(text('所需时间比平时长，正在继续尝试…', 'This is taking longer than usual. Still working…')), 10000),
      window.setTimeout(() => setThinkingHint(text('遇到延迟。你可以继续等待，或取消后试一个更简单的问题。', 'There is a delay. You can keep waiting, or cancel and try a simpler question.')), 20000),
      window.setTimeout(() => controller.abort(), 45000),
    ];
    try {
      const session = await ensureSession();
      let reply: BridgeTutorReply;
      try { reply = await bridgeApi.tutor(session.session_token, message, language, controller.signal); }
      catch (error) {
        if (!(error instanceof BridgeApiError) || error.status !== 401) throw error;
        localStorage.removeItem(sessionKey(moduleId)); sessionRef.current = null;
        const fresh = await ensureSession();
        reply = await bridgeApi.tutor(fresh.session_token, message, language, controller.signal);
      }
      append('assistant', reply.response, reply);
      setAvatar(normalizeAvatarState(reply.avatar_state));
      setAssessmentLocked(reply.lock_status);
    } catch (error) {
      if (controller.signal.aborted && inFlightRef.current !== controller) return;
      setAvatar('uncertain');
      const status = error instanceof BridgeApiError ? error.status : -1;
      const note = status === 429 || status === 503
        ? text('助教现在较忙。请稍后重试。', 'The assistant is busy. Please try again shortly.')
        : status === 403 || status === 404
          ? text('该课程模块暂时不可用。请刷新模块列表。', 'This module is unavailable. Please refresh the module list.')
          : status === 0 || !navigator.onLine
            ? text('连接中断。消息未确认送达，请重试。', 'Connection lost. Delivery was not confirmed; please retry.')
            : controller.signal.aborted
              ? text('处理时间过长。请尝试更简短的问题，或重试。', 'This took too long. Try a shorter question, or retry.')
              : text('暂时无法回答。请稍后重试。', 'I cannot respond right now. Please try again.');
      append('notice', note);
      setRetryMessage(message);
    } finally {
      timers.forEach(window.clearTimeout);
      if (inFlightRef.current === controller) inFlightRef.current = null;
      setThinkingHint(''); setBusy(false);
    }
  };

  useEffect(() => {
    if (online && queued && !busy) void send(queued, false);
  }, [online, queued, busy]);

  const resetSession = async () => {
    if (busy) return;
    setBusy(true);
    const previous = sessionRef.current;
    sessionRef.current = null;
    localStorage.removeItem(sessionKey(moduleId));
    setSessionReady(false); setLines([]); setRetryMessage(null); setQueued(null); setAvatar('thinking'); setAssessmentLocked(false);
    if (previous) try { await bridgeApi.deleteSession(previous.session_token); } catch { /* Local token is already discarded. */ }
    try {
      const session = await bridgeApi.createSession(moduleId, language);
      sessionRef.current = session;
      localStorage.setItem(sessionKey(moduleId), JSON.stringify(session));
      setAssessmentLocked(session.lock_status); setAvatar(normalizeAvatarState(session.avatar_state));
      setLines([{ id: nextId(), kind: 'assistant', content: session.welcome, welcomeLanguage: session.language,
        groundingStatus: session.grounding_status || 'INSUFFICIENT EVIDENCE', sources: session.sources || [] }]); setSessionReady(true);
    } catch { setModuleError(text('无法开始新会话。请稍后重试。', 'Unable to start a new session. Please retry shortly.')); }
    finally { setBusy(false); }
  };
  const toggleMotion = () => {
    const next = !reducedMotion;
    setReducedMotion(next);
    localStorage.setItem('bridge-reduced-motion', String(next));
  };
  const submit = (event: FormEvent) => { event.preventDefault(); void send(draft); };

  return <main className={`bridge-page${reducedMotion ? ' bridge-reduced-motion' : ''}`}>
    <header className="bridge-header">
      <div><p className="bridge-eyebrow">BRIDGE</p><h1>{text('双语学习助教', 'Bilingual learning assistant')}</h1></div>
      <div className="bridge-header-actions"><LanguageToggle /><button type="button" className="bridge-button" onClick={toggleMotion} aria-pressed={reducedMotion}>
        {reducedMotion ? text('减少动态：开', 'Reduced motion: on') : text('减少动态：关', 'Reduced motion: off')}
      </button><Link className="bridge-link" to="/">{text('首页', 'Home')}</Link></div>
    </header>
    <div className="bridge-layout">
      <aside className="bridge-side" aria-label={text('学习设置', 'Learning settings')}>
        <BridgeAvatar state={busy ? 'thinking' : avatar} language={language} reducedMotion={reducedMotion} />
        <p className="bridge-intro">{text('我会先问你已经知道什么，再给出逐步提示。请尝试用自己的话解释所学内容。', 'I will ask what you know, offer gradual hints, and invite you to explain the idea in your own words.')}</p>
        <label className="bridge-label" htmlFor="bridge-module">{text('课程模块', 'Module')}</label>
        <select id="bridge-module" className="bridge-control" disabled={busy || loadingModules || modules.length === 0} value={moduleId} onChange={event => setModuleId(event.target.value)}>
          {modules.length === 0 && <option value="">{text('暂无可用模块', 'No active modules')}</option>}
          {modules.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
        </select>
        <label className="bridge-label" htmlFor="bridge-preferred-name">{text('希望我怎么称呼你？（选填）', 'What should I call you? (optional)')}</label>
        <input id="bridge-preferred-name" className="bridge-control" value={preferredName} maxLength={40} autoComplete="off"
          aria-describedby="bridge-name-help" placeholder={text('例如：小明', 'For example: Ming')}
          onChange={event => setPreferredName(event.target.value)} />
        <p id="bridge-name-help" className="bridge-small">{text('留空时，已登录学生使用账号显示姓名；访客则不显示姓名。这里填写的称呼仅保留在本页，不会通过匿名辅导接口发送。账号姓名仍由原有账户服务保存。', 'Signed-in students can leave this blank to use their account display name. Visitors remain unnamed unless they enter one. A preferred name typed here stays on this page; neither name is sent in anonymous tutor requests. Your account name remains with the existing account service.')}</p>
        {moduleError && <p role="alert" className="bridge-error">{moduleError} <button type="button" onClick={() => { void loadModules(); setSessionAttempt(value => value + 1); }}>{text('重试', 'Retry')}</button></p>}
        {assessmentLocked && <p className="bridge-lock" role="status">{text('考核时段：仅提供提示和新的练习题。', 'Assessment window: hints and new practice questions only.')}</p>}
        <button type="button" className="bridge-button bridge-new-session" disabled={!moduleId || busy || !sessionReady} onClick={() => void resetSession()}>{text('开始新学习会话', 'Start a new learning session')}</button>
        <p className="bridge-small">{text('概念学习进度由匿名会话保存；姓名和学号均非必填。登录或退出账号会清除本机已保存的 BRIDGE 会话。', 'Concept progress uses an anonymous session; a name or student ID is never required. Signing in or out clears saved BRIDGE sessions on this device.')}</p>
      </aside>
      <section className="bridge-chat" aria-label={text('学习对话', 'Learning conversation')}>
        <div className="bridge-chat-heading"><h2>{module?.title || text('选择一个课程模块', 'Choose a module')}</h2><p>{text('依据所选模块的资料学习', 'Learn from the selected module materials')}</p></div>
        <div className="bridge-dialogue" role="log" aria-live="polite" aria-relevant="additions" aria-label={text('对话消息', 'Conversation messages')}>
          {lines.length === 0 && <div className="bridge-welcome"><h3>{text('你想学习什么？', 'What would you like to learn?')}</h3><p>{text('描述你正在做的题目或不理解的概念。我会先了解你的想法。', 'Describe the topic or problem you are working on. I will start by asking about your thinking.')}</p></div>}
          {lines.map(line => <article key={line.id} className={`bridge-message bridge-message--${line.kind}`}>
            <div className="bridge-speaker">{line.kind === 'student' ? text('你', 'You') : line.kind === 'assistant' ? 'BRIDGE' : text('提示', 'Notice')}</div>
            {line.reply?.stage && <span className="bridge-stage">{stageLabel(line.reply.stage, language)}</span>}
            <p className="bridge-message-text">{personalizedLines.has(line.id) && line.welcomeLanguage
              ? <>{line.welcomeLanguage === 'zh' ? `你好，${studentName}！` : `Hello, ${studentName}!`}{line.content.slice(line.welcomeLanguage === 'zh' ? '你好！'.length : 'Hello!'.length)}</>
              : <>{personalizedLines.has(line.id) && line.reply && <>{studentName}{line.reply.language === 'zh' ? '，' : ', '}</>}{line.content}</>}</p>
            {line.reply?.practice && <div className="bridge-practice"><strong>{text('练习题', 'Practice question')}</strong><p>{line.reply.practice}</p></div>}
            {(line.reply || line.groundingStatus) && <BridgeEvidence status={line.reply?.grounding_status || line.groundingStatus || 'INSUFFICIENT EVIDENCE'} sources={line.reply?.sources || line.sources || []} language={language} />}
          </article>)}
          {busy && <div className="bridge-wait" role="status"><span className="bridge-wait-dot" aria-hidden="true" />{thinkingHint}<button type="button" onClick={() => inFlightRef.current?.abort()}>{text('取消', 'Cancel')}</button></div>}
          {queued && <div className="bridge-queued" role="status">{text('消息将在连接恢复后发送。', 'Message will be sent when the connection is restored.')} <button type="button" onClick={() => setQueued(null)}>{text('取消', 'Cancel')}</button></div>}
          {retryMessage && !busy && !queued && <button type="button" className="bridge-button" onClick={() => void send(retryMessage, false)}>{text('重试上一条消息', 'Retry the last message')}</button>}
          <div ref={chatEndRef} />
        </div>
        <form className="bridge-composer" onSubmit={submit}>
          <label className="bridge-label" htmlFor="bridge-question">{text('你的问题或解释', 'Your question or explanation')}</label>
          <textarea id="bridge-question" value={draft} onChange={event => setDraft(event.target.value)} disabled={!sessionReady || busy || !!queued} rows={3} maxLength={2000} placeholder={text('例如：我已经试过……但不明白下一步。', 'For example: I have tried… but I do not understand the next step.')} />
          <div className="bridge-composer-footer"><span>{!online ? text('当前离线', 'Offline') : !sessionReady ? text('正在准备学习会话…', 'Preparing learning session…') : text('请自己尝试，犯错也没关系。', 'Try it yourself; mistakes are part of learning.')}</span><button type="submit" className="bridge-primary" disabled={!sessionReady || !draft.trim() || busy || !!queued}>{text('发送', 'Send')}</button></div>
        </form>
      </section>
    </div>
  </main>;
}
