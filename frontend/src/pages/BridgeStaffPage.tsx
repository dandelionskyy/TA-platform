import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import BridgeChunkReview from '../components/bridge/BridgeChunkReview';
import { useLanguage } from '../i18n/LanguageContext';
import { api } from '../services/api';
import { bridgeApi, type BridgeArtefacts, type BridgeChunk, type BridgeChunkType, type BridgeConcept, type BridgeDashboard, type BridgeGlossaryTerm, type BridgeMaterial, type BridgeModule, type BridgeRegressionPrompt, type BridgeSolution, type BridgeTemplate, type BridgeTestRun } from '../services/bridgeApi';
import '../styles/bridge.css';

interface Course { id: string; name: string; }

function rowsOfCsv(content: string): string[][] {
  const rows: string[][] = []; let row: string[] = []; let cell = ''; let quoted = false;
  const input = content.replace(/^\uFEFF/, '');
  for (let i = 0; i < input.length; i++) {
    const char = input[i];
    if (char === '"') {
      if (quoted && input[i + 1] === '"') { cell += '"'; i++; } else quoted = !quoted;
    } else if (char === ',' && !quoted) { row.push(cell); cell = ''; }
    else if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && input[i + 1] === '\n') i++;
      row.push(cell); if (row.some(value => value.trim())) rows.push(row);
      row = []; cell = '';
    } else cell += char;
  }
  if (quoted) throw new Error('Unclosed CSV quotation');
  row.push(cell); if (row.some(value => value.trim())) rows.push(row);
  return rows;
}

function parseGlossary(fileName: string, input: string): BridgeGlossaryTerm[] {
  let entries: Record<string, unknown>[];
  if (fileName.toLowerCase().endsWith('.json')) {
    const parsed: unknown = JSON.parse(input.replace(/^\uFEFF/, ''));
    const array = Array.isArray(parsed) ? parsed : (parsed as { terms?: unknown })?.terms;
    if (!Array.isArray(array)) throw new Error('JSON must contain a terms array');
    entries = array as Record<string, unknown>[];
  } else {
    const rows = rowsOfCsv(input); const header = rows.shift()?.map(value => value.trim().toLowerCase()) || [];
    if (!header.length) throw new Error('Missing CSV header');
    entries = rows.map(values => Object.fromEntries(header.map((key, index) => [key, values[index]?.trim() || ''])));
  }
  const terms = entries.map(item => ({
    english: String(item.english ?? item.english_term ?? '').trim(),
    chinese: String(item.chinese ?? item.chinese_term ?? '').trim(),
    notes: String(item.notes ?? item.context_notes ?? '').trim(),
  }));
  if (!terms.length || terms.some(term => !term.english || !term.chinese)) throw new Error('Every term needs English and Chinese text');
  return terms;
}

function shortDate(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
}
function fileSize(bytes: number): string { return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`; }

export default function BridgeStaffPage() {
  const { text } = useLanguage();
  const [courses, setCourses] = useState<Course[]>([]);
  const [modules, setModules] = useState<BridgeModule[]>([]);
  const [moduleId, setModuleId] = useState('');
  const [courseId, setCourseId] = useState('');
  const [title, setTitle] = useState('');
  const [materials, setMaterials] = useState<BridgeMaterial[]>([]);
  const [chunks, setChunks] = useState<BridgeChunk[]>([]);
  const [solutions, setSolutions] = useState<BridgeSolution[]>([]);
  const [glossary, setGlossary] = useState<BridgeGlossaryTerm[]>([]);
  const [pendingGlossary, setPendingGlossary] = useState<BridgeGlossaryTerm[] | null>(null);
  const [glossaryFileName, setGlossaryFileName] = useState('');
  const [artefacts, setArtefacts] = useState<BridgeArtefacts | null>(null);
  const [testRun, setTestRun] = useState<BridgeTestRun | null>(null);
  const [dashboard, setDashboard] = useState<BridgeDashboard | null>(null);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const module = modules.find(entry => entry.id === moduleId);
  const canActivate = chunks.some(chunk => chunk.reviewed && ['DEFINITION', 'EXAMPLE', 'HINT'].includes(chunk.chunk_type));

  const loadModules = useCallback(async (preferredId?: string) => {
    const available = await bridgeApi.listStaffModules();
    setModules(available);
    setModuleId(current => available.some(entry => entry.id === (preferredId || current)) ? (preferredId || current) : available[0]?.id || '');
  }, []);

  useEffect(() => {
    api.getTeacherCourses().then(result => {
      const available = (result.courses || []) as Course[];
      setCourses(available); setCourseId(current => current || available[0]?.id || '');
    }).catch(() => setError(text('无法读取教师课程。', 'Unable to load teacher courses.')));
    loadModules().catch(() => setError(text('无法读取模块。请确认你的教师权限。', 'Unable to load module packs. Check your teacher access.')));
  }, [loadModules]);

  const loadModuleData = useCallback(async (selectedId: string) => {
    const [files, sourceChunks, restricted, terms, generated, summary] = await Promise.allSettled([
      bridgeApi.listMaterials(selectedId), bridgeApi.listChunks(selectedId), bridgeApi.listSolutions(selectedId),
      bridgeApi.getGlossary(selectedId), bridgeApi.getArtefacts(selectedId), bridgeApi.getDashboard(selectedId),
    ]);
    setMaterials(files.status === 'fulfilled' ? files.value : []);
    setChunks(sourceChunks.status === 'fulfilled' ? sourceChunks.value : []);
    setSolutions(restricted.status === 'fulfilled' ? restricted.value : []);
    setGlossary(terms.status === 'fulfilled' ? terms.value : []);
    setArtefacts(generated.status === 'fulfilled' ? generated.value : null);
    setDashboard(summary.status === 'fulfilled' ? summary.value : null);
    if ([files, sourceChunks, restricted, terms, generated, summary].some(result => result.status === 'rejected')) {
      setError(text('部分模块信息无法加载，请刷新后重试。', 'Some module information could not be loaded. Please refresh and retry.'));
    }
  }, [text]);

  useEffect(() => {
    setPendingGlossary(null); setGlossaryFileName(''); setTestRun(null); setError(''); setNotice('');
    if (moduleId) void loadModuleData(moduleId);
    else { setMaterials([]); setChunks([]); setSolutions([]); setGlossary([]); setArtefacts(null); setDashboard(null); }
  }, [moduleId, loadModuleData]);
  useEffect(() => {
    if (!moduleId || !materials.some(item => ['queued', 'processing'].includes(item.processing_status))) return;
    const timer = window.setInterval(() => {
      bridgeApi.listMaterials(moduleId).then(setMaterials).catch(() => undefined);
      bridgeApi.listChunks(moduleId).then(setChunks).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [moduleId, materials]);

  const task = async (name: string, work: () => Promise<void>, success: string) => {
    setBusy(name); setError(''); setNotice('');
    try { await work(); setNotice(success); }
    catch { setError(text('操作未完成。请检查模块权限、文件或网络连接后重试。', 'The action did not complete. Check module access, file and connection, then retry.')); }
    finally { setBusy(''); }
  };

  const create = (event: FormEvent) => {
    event.preventDefault(); if (!courseId || !title.trim()) return;
    void task('create', async () => {
      const created = await bridgeApi.createModule(courseId, title.trim());
      setTitle(''); await loadModules(created.id);
    }, text('模块已创建。', 'Module pack created.'));
  };
  const changeModule = (data: { active?: boolean; assessment_locked?: boolean }) => {
    if (!module) return;
    void task('settings', async () => {
      await bridgeApi.updateModule(module.id, data);
      await loadModules(module.id);
    }, text('模块设置已保存。', 'Module settings saved.'));
  };
  const upload = (event: FormEvent<HTMLFormElement>, solution: boolean) => {
    event.preventDefault(); if (!moduleId) return;
    const input = event.currentTarget.elements.namedItem(solution ? 'solutionFile' : 'materialFile') as HTMLInputElement;
    const file = input.files?.[0]; if (!file) return;
    if (file.size > 50 * 1024 * 1024) { setError(text('单个文件不能超过 50 MB。', 'Each file must be 50 MB or less.')); return; }
    void task(solution ? 'solution' : 'upload', async () => {
      if (solution) { await bridgeApi.uploadSolution(moduleId, file); setSolutions(await bridgeApi.listSolutions(moduleId)); }
      else { await bridgeApi.uploadMaterial(moduleId, file); setMaterials(await bridgeApi.listMaterials(moduleId)); setChunks(await bridgeApi.listChunks(moduleId)); }
      input.value = '';
      await loadModules(moduleId);
    }, solution ? text('教师专用答案已上传。', 'Staff-only solution uploaded.') : text('资料已上传，索引状态将在下方更新。', 'Material uploaded. Its indexing status will update below.'));
  };
  const removeMaterial = (item: BridgeMaterial) => {
    if (!moduleId || !window.confirm(text(`删除 ${item.filename}？`, `Delete ${item.filename}?`))) return;
    void task('delete', async () => { await bridgeApi.deleteMaterial(moduleId, item.id); setMaterials(await bridgeApi.listMaterials(moduleId)); setChunks(await bridgeApi.listChunks(moduleId)); await loadModules(moduleId); }, text('资料已删除。', 'Material deleted.'));
  };
  const reindexMaterial = (item: BridgeMaterial) => {
    if (!moduleId || !window.confirm(text(`重新处理 ${item.filename}？原有资料段的审核状态将被清除。`, `Reindex ${item.filename}? Existing chunk reviews will be cleared.`))) return;
    void task('reindex', async () => { await bridgeApi.reindexMaterial(moduleId, item.id); setMaterials(await bridgeApi.listMaterials(moduleId)); setChunks(await bridgeApi.listChunks(moduleId)); await loadModules(moduleId); }, text('已安排重新处理。处理完成后请再次审核资料段。', 'Reindexing queued. Review the new chunks when processing finishes.'));
  };
  const reviewChunk = (chunk: BridgeChunk, type: BridgeChunkType, reviewed: boolean) => {
    if (!moduleId) return;
    void task('chunk', async () => { await bridgeApi.updateChunk(moduleId, chunk.id, type, reviewed); setChunks(await bridgeApi.listChunks(moduleId)); await loadModules(moduleId); }, text('资料段分类已保存。', 'Chunk classification saved.'));
  };
  const removeSolution = (item: BridgeSolution) => {
    if (!moduleId || !window.confirm(text(`删除教师专用答案 ${item.filename}？`, `Delete staff-only solution ${item.filename}?`))) return;
    void task('delete', async () => { await bridgeApi.deleteSolution(moduleId, item.id); setSolutions(await bridgeApi.listSolutions(moduleId)); }, text('教师专用答案已删除。', 'Staff-only solution deleted.'));
  };
  const prepareGlossary = async (file?: File) => {
    if (!file) return;
    try { setPendingGlossary(parseGlossary(file.name, await file.text())); setGlossaryFileName(file.name); setError(''); }
    catch { setPendingGlossary(null); setError(text('术语表格式无效。请使用包含 english_term 和 chinese_term 列的 UTF-8 CSV，或等效 JSON。', 'Invalid glossary. Use UTF-8 CSV with english_term and chinese_term columns, or equivalent JSON.')); }
  };
  const saveGlossary = () => {
    if (!moduleId || !pendingGlossary) return;
    void task('glossary', async () => { setGlossary(await bridgeApi.putGlossary(moduleId, pendingGlossary)); setPendingGlossary(null); setGlossaryFileName(''); }, text('双语术语表已替换。', 'Bilingual glossary replaced.'));
  };
  const compile = () => {
    if (!moduleId) return;
    void task('compile', async () => { setArtefacts(await bridgeApi.compile(moduleId)); }, text('已生成可审核的模块资料。请检查模板和测试题。', 'Draft module artefacts generated. Review the templates and test prompts.'));
  };
  const runTests = () => {
    if (!moduleId) return;
    void task('test', async () => { setTestRun(await bridgeApi.runTests(moduleId)); }, text('模块回归测试已完成。', 'Module regression tests completed.'));
  };
  const saveConcept = (item: BridgeConcept, form: FormData) => {
    if (!moduleId) return;
    const data = { title_en: String(form.get('title_en') || ''), title_zh: String(form.get('title_zh') || ''), description: String(form.get('description') || ''), source_chunk_id: String(form.get('source_chunk_id') || '') || null, reviewed: form.get('reviewed') === 'on' };
    void task('edit', async () => { await bridgeApi.editConcept(moduleId, item.id, data); setArtefacts(await bridgeApi.getArtefacts(moduleId)); }, text('概念已保存。', 'Concept saved.'));
  };
  const saveTemplate = (item: BridgeTemplate, form: FormData) => {
    if (!moduleId) return;
    const data = { text: String(form.get('text') || ''), source_chunk_id: String(form.get('source_chunk_id') || '') || null, reviewed: form.get('reviewed') === 'on' };
    void task('edit', async () => { await bridgeApi.editTemplate(moduleId, item.id, data); setArtefacts(await bridgeApi.getArtefacts(moduleId)); }, text('模板已保存。', 'Template saved.'));
  };
  const savePrompt = (item: BridgeRegressionPrompt, form: FormData) => {
    if (!moduleId) return;
    const data = { question: String(form.get('question') || ''), expected_status: String(form.get('expected_status') || ''), expected_chunk_id: String(form.get('expected_chunk_id') || '') || null, reviewed: form.get('reviewed') === 'on' };
    void task('edit', async () => { await bridgeApi.editRegressionPrompt(moduleId, item.id, data); setArtefacts(await bridgeApi.getArtefacts(moduleId)); }, text('测试题已保存。', 'Test prompt saved.'));
  };
  const addArtefact = (event: FormEvent<HTMLFormElement>, kind: 'concept' | 'template' | 'prompt') => {
    event.preventDefault(); if (!moduleId) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const optional = (key: string) => String(values.get(key) || '').trim() || null;
    void task('add', async () => {
      if (kind === 'concept') await bridgeApi.addConcept(moduleId, {
        key: String(values.get('key') || '').trim(), title_en: String(values.get('title_en') || '').trim(),
        title_zh: String(values.get('title_zh') || '').trim(), description: String(values.get('description') || '').trim(),
        source_chunk_id: optional('source_chunk_id'),
      });
      if (kind === 'template') await bridgeApi.addTemplate(moduleId, {
        concept_id: optional('concept_id'), template_type: String(values.get('template_type') || 'micro_question'),
        language: String(values.get('language') || 'en'), text: String(values.get('text') || '').trim(),
        source_chunk_id: optional('source_chunk_id'),
      });
      if (kind === 'prompt') await bridgeApi.addRegressionPrompt(moduleId, {
        concept_id: optional('concept_id'), question: String(values.get('question') || '').trim(),
        language: String(values.get('language') || 'en'), expected_status: String(values.get('expected_status') || 'GROUNDED'),
        expected_chunk_id: optional('expected_chunk_id'),
      });
      setArtefacts(await bridgeApi.getArtefacts(moduleId));
      form.reset();
    }, text('已新增待审核内容。', 'Draft artefact added for review.'));
  };

  return <main className="bridge-page bridge-staff-page">
    <header className="bridge-header"><div><p className="bridge-eyebrow">BRIDGE · STAFF</p><h1>{text('课程模块管理', 'Module pack management')}</h1></div><div className="bridge-header-actions"><Link className="bridge-link" to="/teacher">{text('返回教师工作台', 'Teacher workspace')}</Link></div></header>
    <div className="bridge-staff-layout">
      <aside className="bridge-staff-menu">
        <h2>{text('模块', 'Modules')}</h2>
        <label className="bridge-label" htmlFor="bridge-staff-module">{text('编辑模块', 'Edit module')}</label>
        <select className="bridge-control" id="bridge-staff-module" value={moduleId} onChange={event => setModuleId(event.target.value)}>
          {modules.length === 0 && <option value="">{text('暂无模块', 'No module packs')}</option>}
          {modules.map(item => <option value={item.id} key={item.id}>{item.title}{item.active ? ` · ${text('已启用', 'active')}` : ''}</option>)}
        </select>
        <form onSubmit={create} className="bridge-form bridge-new-module"><h3>{text('新建模块', 'Create module pack')}</h3>
          <label htmlFor="bridge-new-course">{text('所属课程', 'Teacher course')}</label><select id="bridge-new-course" value={courseId} onChange={event => setCourseId(event.target.value)} required><option value="">{text('选择课程', 'Select course')}</option>{courses.map(course => <option value={course.id} key={course.id}>{course.name}</option>)}</select>
          <label htmlFor="bridge-new-title">{text('模块名称', 'Module title')}</label><input id="bridge-new-title" value={title} onChange={event => setTitle(event.target.value)} maxLength={140} required />
          <button className="bridge-primary" disabled={!!busy || !courseId || !title.trim()}>{text('创建', 'Create')}</button>
        </form>
        <nav aria-label={text('管理分区', 'Management sections')} className="bridge-staff-nav">
          <a href="#bridge-settings">{text('状态与考核', 'Status and assessment')}</a><a href="#bridge-materials">{text('课程资料', 'Materials')}</a><a href="#bridge-chunks">{text('资料段审核', 'Chunk review')}</a>
          <a href="#bridge-glossary">{text('双语术语', 'Glossary')}</a><a href="#bridge-compiler">{text('资料编译与测试', 'Compiler and tests')}</a>
          <a href="#bridge-summary">{text('教学汇总', 'Instructor summary')}</a>
        </nav>
      </aside>
      <div className="bridge-staff-main">
        {error && <div className="bridge-alert bridge-alert--error" role="alert">{error} <button type="button" onClick={() => { setError(''); void loadModules(moduleId); if (moduleId) void loadModuleData(moduleId); }}>{text('刷新', 'Refresh')}</button></div>}
        {notice && <div className="bridge-alert" role="status">{notice}</div>}
        {!module ? <section className="bridge-panel"><h2>{text('创建第一个模块', 'Create your first module pack')}</h2><p>{text('选择教师课程并创建模块，然后上传教学资料。', 'Select a teacher course, create a module, then upload its teaching materials.')}</p></section> : <>
          <section className="bridge-panel" id="bridge-settings"><h2>{text('模块与考核设置', 'Module and assessment settings')}</h2><p>{module.title} · {module.course_id}</p>
            <div className="bridge-setting-row"><div><strong>{text('向学生开放模块', 'Publish this module')}</strong><p>{text('至少一段资料应审核并标为定义、例子或提示，才能启用模块。', 'Review and tag at least one definition, example or hint before publishing.')}</p></div><button type="button" className="bridge-button" disabled={!!busy || (!module.active && !canActivate)} aria-pressed={!!module.active} onClick={() => changeModule({ active: !module.active })}>{module.active ? text('已启用 · 点击停用', 'Active · deactivate') : text('未启用 · 点击启用', 'Inactive · activate')}</button></div>
            <div className="bridge-setting-row"><div><strong>{text('考核时段锁定', 'Assessment window lock')}</strong><p>{text('锁定期间只给提示，并引导到新的练习题。', 'Scaffold-only help and a new practice variant are enforced while locked.')}</p></div><button type="button" className="bridge-button" disabled={!!busy} aria-pressed={!!module.assessment_locked} onClick={() => changeModule({ assessment_locked: !module.assessment_locked })}>{module.assessment_locked ? text('已锁定 · 点击解除', 'Locked · unlock') : text('未锁定 · 点击锁定', 'Unlocked · lock')}</button></div>
          </section>

          <section className="bridge-panel" id="bridge-materials"><h2>{text('课程资料', 'Module materials')}</h2><p>{text('PDF、DOCX、TXT 或 MD。单个文件最多 50 MB。仅 ready 状态的资料可用于检索。', 'PDF, DOCX, TXT or MD, up to 50 MB each. Only ready materials can be retrieved.')}</p>
            <form className="bridge-form bridge-inline-form" onSubmit={event => upload(event, false)}><label htmlFor="bridge-material-file">{text('上传资料', 'Upload material')}</label><input id="bridge-material-file" name="materialFile" type="file" accept=".pdf,.docx,.txt,.md" required /><button className="bridge-primary" disabled={!!busy}>{busy === 'upload' ? text('上传中…', 'Uploading…') : text('上传', 'Upload')}</button></form>
            <div className="bridge-list" aria-live="polite">{materials.map(item => <div className="bridge-list-item" key={item.id}><div><strong>{item.filename}</strong><p>{fileSize(item.size_bytes)} · {shortDate(item.created_at)} · {text('索引状态', 'Index status')}: <span className={`bridge-file-status bridge-file-status--${item.processing_status}`}>{item.processing_status}</span>{item.chunk_count != null ? ` · ${item.chunk_count} ${text('段', 'chunks')}` : ''}</p>{item.processing_error && <p className="bridge-error">{item.processing_error}</p>}</div><div className="bridge-list-actions">{['failed', 'ready'].includes(item.processing_status) && <button type="button" className="bridge-button" disabled={!!busy} onClick={() => reindexMaterial(item)}>{text('重新处理', 'Reindex')}</button>}<button type="button" className="bridge-button" disabled={!!busy} onClick={() => removeMaterial(item)}>{text('删除', 'Delete')}</button></div></div>)}{materials.length === 0 && <p>{text('尚未上传资料。', 'No materials uploaded yet.')}</p>}</div>
            <details className="bridge-restricted"><summary>{text('教师专用答案（不进入学生检索）', 'Staff-only solutions (excluded from student retrieval)')}</summary><form className="bridge-form bridge-inline-form" onSubmit={event => upload(event, true)}><label htmlFor="bridge-solution-file">{text('上传教师专用答案', 'Upload restricted solution')}</label><input id="bridge-solution-file" name="solutionFile" type="file" accept=".pdf,.docx,.txt,.md" required /><button className="bridge-primary" disabled={!!busy}>{text('上传', 'Upload')}</button></form><div className="bridge-list">{solutions.map(item => <div className="bridge-list-item" key={item.id}><span>{item.filename} · {fileSize(item.size_bytes)}</span><button className="bridge-button" type="button" disabled={!!busy} onClick={() => removeSolution(item)}>{text('删除', 'Delete')}</button></div>)}{solutions.length === 0 && <p>{text('暂无教师专用答案。', 'No staff-only solutions.')}</p>}</div></details>
          </section>

          <section className="bridge-panel" id="bridge-chunks"><h2>{text('课程资料段审核', 'Source chunk review')}</h2>
            <BridgeChunkReview chunks={chunks} busy={!!busy} onSave={reviewChunk} />
          </section>

          <section className="bridge-panel" id="bridge-glossary"><h2>{text('双语术语表', 'Bilingual glossary')}</h2><p>{text('上传 UTF-8 CSV 或 JSON。列名可用 english_term、chinese_term、context_notes。替换前可预览。', 'Upload UTF-8 CSV or JSON. Accepted keys include english_term, chinese_term, context_notes. Preview before replacing.')}</p>
            <label className="bridge-label" htmlFor="bridge-glossary-file">{text('选择术语表', 'Choose glossary file')}</label><input id="bridge-glossary-file" type="file" accept=".csv,.json,text/csv,application/json" onChange={event => void prepareGlossary(event.target.files?.[0])} />
            {pendingGlossary && <div className="bridge-preview"><strong>{glossaryFileName}: {pendingGlossary.length} {text('个术语', 'terms')}</strong><ul>{pendingGlossary.slice(0, 5).map((term, index) => <li key={`${term.english}-${index}`}>{term.english} — {term.chinese}</li>)}</ul><button type="button" className="bridge-primary" disabled={!!busy} onClick={saveGlossary}>{text('替换当前术语表', 'Replace current glossary')}</button></div>}
            <p className="bridge-small">{text('当前术语数：', 'Current terms: ')}{glossary.length}</p>
          </section>

          <section className="bridge-panel" id="bridge-compiler"><h2>{text('模块资料编译与回归测试', 'Module pack compiler and regression tests')}</h2><p>{text('编译生成概念、误区模板、微问题和测试题。请审核后运行测试。', 'Compile draft concepts, misconception and micro-question templates, and test prompts. Review them before running tests.')}</p>
            <div className="bridge-actions"><button type="button" className="bridge-primary" disabled={!!busy || !materials.some(item => item.processing_status === 'ready')} onClick={compile}>{busy === 'compile' ? text('编译中…', 'Compiling…') : text('编译模块资料', 'Compile module pack')}</button><button type="button" className="bridge-button" disabled={!!busy} onClick={runTests}>{busy === 'test' ? text('测试中…', 'Testing…') : text('测试模块资料', 'Test module pack')}</button></div>
            {artefacts && <><div className="bridge-counts"><span>{artefacts.concepts.length} {text('个概念', 'concepts')}</span><span>{artefacts.templates.filter(item => item.template_type === 'micro_question').length} {text('个微问题', 'micro-questions')}</span><span>{artefacts.templates.filter(item => item.template_type === 'misconception').length} {text('个误区模板', 'misconceptions')}</span><span>{artefacts.regression_prompts.length} {text('个测试题', 'test prompts')}</span></div>
              {artefacts.gaps.length > 0 && <div className="bridge-gap" role="status"><strong>{text('需要补充资料', 'Content gaps')}</strong><ul>{artefacts.gaps.map((gap, index) => <li key={index}>{gap}</li>)}</ul></div>}
              <details className="bridge-artefact-group"><summary>{text('概念分类与编辑', 'Concept taxonomy and edits')} ({artefacts.concepts.length})</summary>{artefacts.concepts.map(item => <details className="bridge-edit-row" key={item.id}><summary>{item.title_en || item.key} · {item.reviewed ? text('已审核', 'Reviewed') : text('待审核', 'Draft')}</summary><form className="bridge-form" onSubmit={event => { event.preventDefault(); saveConcept(item, new FormData(event.currentTarget)); }}><label>{text('英文标题', 'English title')}<input name="title_en" defaultValue={item.title_en} required /></label><label>{text('中文标题', 'Chinese title')}<input name="title_zh" defaultValue={item.title_zh} /></label><label>{text('说明', 'Description')}<textarea name="description" defaultValue={item.description} /></label><label>{text('依据资料段', 'Source chunk')}<select name="source_chunk_id" defaultValue={item.source_chunk_id || ''}><option value="">{text('尚未指定', 'Not linked')}</option>{chunks.map(chunk => <option key={chunk.id} value={chunk.id}>{chunk.filename} #{chunk.chunk_index + 1} · {chunk.chunk_type} · {chunk.reviewed ? text('已审核', 'reviewed') : text('待审核', 'draft')}</option>)}</select></label><label className="bridge-check"><input type="checkbox" name="reviewed" defaultChecked={item.reviewed} />{text('人工审核通过', 'Mark reviewed')}</label><button className="bridge-primary" disabled={!!busy}>{text('保存', 'Save')}</button></form></details>)}</details>
              <details className="bridge-artefact-group"><summary>{text('误区与微问题模板', 'Misconception and micro-question templates')} ({artefacts.templates.length})</summary>{artefacts.templates.map(item => <details className="bridge-edit-row" key={item.id}><summary>{item.template_type} · {item.language} · {item.reviewed ? text('已审核', 'Reviewed') : text('待审核', 'Draft')}</summary><form className="bridge-form" onSubmit={event => { event.preventDefault(); saveTemplate(item, new FormData(event.currentTarget)); }}><label>{text('模板文字', 'Template text')}<textarea name="text" defaultValue={item.text} required /></label><label>{text('依据资料段', 'Source chunk')}<select name="source_chunk_id" defaultValue={item.source_chunk_id || ''}><option value="">{text('尚未指定', 'Not linked')}</option>{chunks.map(chunk => <option key={chunk.id} value={chunk.id}>{chunk.filename} #{chunk.chunk_index + 1} · {chunk.chunk_type} · {chunk.reviewed ? text('已审核', 'reviewed') : text('待审核', 'draft')}</option>)}</select></label><label className="bridge-check"><input type="checkbox" name="reviewed" defaultChecked={item.reviewed} />{text('人工审核通过', 'Mark reviewed')}</label><button className="bridge-primary" disabled={!!busy}>{text('保存', 'Save')}</button></form></details>)}</details>
              <details className="bridge-artefact-group"><summary>{text('回归测试题', 'Regression prompts')} ({artefacts.regression_prompts.length})</summary>{artefacts.regression_prompts.map(item => <details className="bridge-edit-row" key={item.id}><summary>{item.question.slice(0, 90)} · {item.reviewed ? text('已审核', 'Reviewed') : text('待审核', 'Draft')}</summary><form className="bridge-form" onSubmit={event => { event.preventDefault(); savePrompt(item, new FormData(event.currentTarget)); }}><label>{text('问题', 'Question')}<textarea name="question" defaultValue={item.question} required /></label><label>{text('预期证据状态', 'Expected evidence status')}<select name="expected_status" defaultValue={item.expected_status}><option value="GROUNDED">GROUNDED</option><option value="INSUFFICIENT EVIDENCE">INSUFFICIENT EVIDENCE</option></select></label><label>{text('预期资料段', 'Expected source chunk')}<select name="expected_chunk_id" defaultValue={item.expected_chunk_id || ''}><option value="">{text('无资料段', 'No source')}</option>{chunks.map(chunk => <option key={chunk.id} value={chunk.id}>{chunk.filename} #{chunk.chunk_index + 1} · {chunk.chunk_type} · {chunk.reviewed ? text('已审核', 'reviewed') : text('待审核', 'draft')}</option>)}</select></label><label className="bridge-check"><input type="checkbox" name="reviewed" defaultChecked={item.reviewed} />{text('人工审核通过', 'Mark reviewed')}</label><button className="bridge-primary" disabled={!!busy}>{text('保存', 'Save')}</button></form></details>)}</details>
            </>}
            {artefacts && <details className="bridge-artefact-group"><summary>{text('手动补充概念、模板或测试题', 'Add a concept, template or test prompt')}</summary>
              <p className="bridge-small">{text('新增内容先作为草稿保存。请给出已审核的资料块，并在上方审核后再用于测试。', 'New items start as drafts. Link to a reviewed source chunk, then review above before testing.')}</p>
              <div className="bridge-add-grid">
                <form className="bridge-form" onSubmit={event => addArtefact(event, 'concept')}><h3>{text('新概念', 'New concept')}</h3><label>{text('概念键（字母、数字、-、_）', 'Key (letters, digits, - or _)')}<input name="key" pattern="[a-zA-Z0-9_-]{3,100}" required /></label><label>{text('英文标题', 'English title')}<input name="title_en" required /></label><label>{text('中文标题', 'Chinese title')}<input name="title_zh" /></label><label>{text('说明', 'Description')}<textarea name="description" /></label><label>{text('依据资料段', 'Source chunk')}<select name="source_chunk_id"><option value="">{text('稍后指定', 'Choose later')}</option>{chunks.map(chunk => <option key={chunk.id} value={chunk.id}>{chunk.filename} #{chunk.chunk_index + 1} · {chunk.chunk_type} · {chunk.reviewed ? text('已审核', 'reviewed') : text('待审核', 'draft')}</option>)}</select></label><button className="bridge-primary" disabled={!!busy}>{text('添加概念', 'Add concept')}</button></form>
                <form className="bridge-form" onSubmit={event => addArtefact(event, 'template')}><h3>{text('新教学模板', 'New teaching template')}</h3><label>{text('所属概念', 'Concept')}<select name="concept_id"><option value="">{text('暂不关联', 'Unlinked')}</option>{artefacts.concepts.map(item => <option key={item.id} value={item.id}>{item.title_en || item.key}</option>)}</select></label><label>{text('类型', 'Type')}<select name="template_type"><option value="micro_question">{text('微问题', 'Micro-question')}</option><option value="misconception">{text('常见误区', 'Misconception')}</option></select></label><label>{text('语言', 'Language')}<select name="language"><option value="en">English</option><option value="zh">中文</option></select></label><label>{text('文字', 'Text')}<textarea name="text" required /></label><label>{text('依据资料段', 'Source chunk')}<select name="source_chunk_id"><option value="">{text('稍后指定', 'Choose later')}</option>{chunks.map(chunk => <option key={chunk.id} value={chunk.id}>{chunk.filename} #{chunk.chunk_index + 1} · {chunk.chunk_type} · {chunk.reviewed ? text('已审核', 'reviewed') : text('待审核', 'draft')}</option>)}</select></label><button className="bridge-primary" disabled={!!busy}>{text('添加模板', 'Add template')}</button></form>
                <form className="bridge-form" onSubmit={event => addArtefact(event, 'prompt')}><h3>{text('新回归测试题', 'New regression prompt')}</h3><label>{text('所属概念', 'Concept')}<select name="concept_id"><option value="">{text('暂不关联', 'Unlinked')}</option>{artefacts.concepts.map(item => <option key={item.id} value={item.id}>{item.title_en || item.key}</option>)}</select></label><label>{text('语言', 'Language')}<select name="language"><option value="en">English</option><option value="zh">中文</option></select></label><label>{text('问题', 'Question')}<textarea name="question" required /></label><label>{text('预期证据状态', 'Expected evidence status')}<select name="expected_status"><option value="GROUNDED">GROUNDED</option><option value="INSUFFICIENT EVIDENCE">INSUFFICIENT EVIDENCE</option></select></label><label>{text('预期资料段', 'Expected source chunk')}<select name="expected_chunk_id"><option value="">{text('不适用或稍后指定', 'None or choose later')}</option>{chunks.map(chunk => <option key={chunk.id} value={chunk.id}>{chunk.filename} #{chunk.chunk_index + 1} · {chunk.chunk_type} · {chunk.reviewed ? text('已审核', 'reviewed') : text('待审核', 'draft')}</option>)}</select></label><button className="bridge-primary" disabled={!!busy}>{text('添加测试题', 'Add test prompt')}</button></form>
              </div>
            </details>}
            {testRun && <div className="bridge-test-result" role="status"><strong>{text('测试结果', 'Test results')}: {testRun.passed}/{testRun.total} {text('通过', 'passed')} · {testRun.failed} {text('失败', 'failed')} · {testRun.skipped} {text('跳过', 'skipped')}</strong><ul>{testRun.results.map(result => <li key={result.id}><strong>{result.passed === true ? text('通过', 'Pass') : result.passed === false ? text('失败', 'Fail') : text('跳过', 'Skipped')}</strong> — {result.question} · {result.reason}{result.actual_sources?.length ? ` · ${result.actual_sources.join(', ')}` : ''}</li>)}</ul></div>}
          </section>

          <section className="bridge-panel" id="bridge-summary"><h2>{text('匿名教学汇总', 'Anonymous instructor summary')}</h2><p>{text('只显示至少 10 次互动的汇总，不显示学生身份或聊天记录。', 'Only aggregate groups with at least 10 interactions are shown. No student identities or chat transcripts.')}</p><button type="button" className="bridge-button" disabled={!!busy} onClick={() => void task('dashboard', async () => { setDashboard(await bridgeApi.getDashboard(moduleId)); }, text('汇总已更新。', 'Summary refreshed.'))}>{text('更新汇总', 'Refresh summary')}</button>
            {dashboard?.interaction_count_band === 'suppressed' ? <p className="bridge-gap">{text('互动数量不足 10，数据已隐藏。', 'Fewer than 10 interactions. Metrics are suppressed.')}</p> : dashboard && <div className="bridge-summary-grid"><div><h3>{text('常见误区', 'Common misconceptions')}</h3><ul>{dashboard.misconceptions.map((item, i) => <li key={i}>{item.concept_key}: {item.count}</li>)}</ul></div><div><h3>{text('对话阶段', 'Dialogue stages')}</h3><ul>{dashboard.stages.map((item, i) => <li key={i}>{item.stage}: {item.count}</li>)}</ul></div><div><h3>{text('停滞点', 'Stall points')}</h3><ul>{dashboard.stall_points?.map((item, i) => <li key={i}>{item.concept_key || item.stage}: {item.count}</li>)}</ul></div><div><h3>{text('常用资料', 'Most retrieved materials')}</h3><ul>{dashboard.most_retrieved_materials?.map((item, i) => <li key={i}>{item.source_file || item.filename}: {item.count}</li>)}</ul></div><div><h3>{text('教学建议', 'Suggested interventions')}</h3><ul>{dashboard.suggested_interventions?.map((item, i) => <li key={i}>{item.suggestion || item.prompt || item.text}</li>)}</ul></div></div>}
          </section>
        </>}
      </div>
    </div>
  </main>;
}
