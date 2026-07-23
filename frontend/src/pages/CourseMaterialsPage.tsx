import { FormEvent, useEffect, useMemo, useState } from 'react';
import AcademicShell from '../components/shared/AcademicShell';
import { useLanguage } from '../i18n/LanguageContext';
import { api } from '../services/api';

type Role = 'teacher' | 'ta';
interface Material { id: string; filename: string; size_bytes: number; processing_status: string; preview_kind: string; }
interface Chapter { id: string; title: string; description: string; sort_order: number; materials: Material[]; legacy?: boolean; }
interface Course { id: string; name: string; description?: string; chapters: Chapter[]; }

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function CourseMaterialsPage({ role }: { role: Role }) {
  const { text } = useLanguage();
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState('');
  const [chapterId, setChapterId] = useState('');
  const [chapterForm, setChapterForm] = useState({ title: '', description: '' });
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const selectedCourse = useMemo(() => courses.find(course => course.id === courseId), [courses, courseId]);
  const selectedChapter = useMemo(() => selectedCourse?.chapters.find(chapter => chapter.id === chapterId), [selectedCourse, chapterId]);

  const load = async (preferredCourse = courseId, preferredChapter = chapterId) => {
    const data = await api.getCourses();
    const next: Course[] = data.courses || [];
    setCourses(next);
    const nextCourseId = next.some(course => course.id === preferredCourse) ? preferredCourse : next[0]?.id || '';
    setCourseId(nextCourseId);
    const nextCourse = next.find(course => course.id === nextCourseId);
    setChapterId(nextCourse?.chapters.some(chapter => chapter.id === preferredChapter) ? preferredChapter : nextCourse?.chapters[0]?.id || '');
  };
  useEffect(() => { load().catch((caught: any) => setMessage(caught?.message || text('课程加载失败。', 'Unable to load courses.'))); }, []);

  const createChapter = async (event: FormEvent) => {
    event.preventDefault();
    if (!courseId || !chapterForm.title.trim() || busy) return;
    setBusy(true); setMessage('');
    try {
      const chapter = await api.createCourseChapter(courseId, chapterForm);
      setChapterForm({ title: '', description: '' });
      await load(courseId, chapter.id);
      setMessage(text('章节已创建。', 'Chapter created.'));
    } catch (caught: any) { setMessage(caught?.message || text('章节创建失败。', 'Unable to create chapter.')); }
    finally { setBusy(false); }
  };

  const upload = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedChapter || selectedChapter.legacy || !file || busy) return;
    setBusy(true); setMessage(text('正在上传并提取课件内容...', 'Uploading and extracting course content...'));
    try {
      await api.uploadCourseMaterial(selectedChapter.id, file);
      setFile(null);
      await load(courseId, selectedChapter.id);
      setMessage(text('资料已上传，学生端现在可以查看并用于章节提问。', 'Material uploaded. Students can now view it and use it for chapter questions.'));
    } catch (caught: any) { setMessage(caught?.message || text('资料上传失败。', 'Unable to upload material.')); }
    finally { setBusy(false); }
  };

  const removeMaterial = async (material: Material) => {
    if (!window.confirm(text(`确定删除“${material.filename}”吗？`, `Delete "${material.filename}"?`))) return;
    try { await api.deleteCourseMaterial(material.id); await load(courseId, chapterId); }
    catch (caught: any) { setMessage(caught?.message || text('资料删除失败。', 'Unable to delete material.')); }
  };
  const removeChapter = async (chapter: Chapter) => {
    if (chapter.legacy || !window.confirm(text(`确定删除章节“${chapter.title}”及其中全部资料吗？`, `Delete "${chapter.title}" and all its materials?`))) return;
    try { await api.deleteCourseChapter(chapter.id); await load(courseId, ''); }
    catch (caught: any) { setMessage(caught?.message || text('章节删除失败。', 'Unable to delete chapter.')); }
  };
  const download = async (material: Material) => {
    try {
      const blob = await api.getCourseMaterialFile(material.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = material.filename; document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (caught: any) { setMessage(caught?.message || text('资料下载失败。', 'Unable to download material.')); }
  };

  const totalMaterials = selectedCourse?.chapters.reduce((sum, chapter) => sum + chapter.materials.length, 0) || 0;
  return <AcademicShell role={role} eyebrow={role === 'teacher' ? text('教师工作台', 'Teacher workspace') : text('助教工作台', 'Teaching assistant workspace')} title={text('课程资料库', 'Course materials')} description={text('按章节整理课件和学习资料；可提取的文字会自动成为学生章节 AI 的参考内容。', 'Organize course files by chapter. Extracted text automatically becomes reference context for the chapter AI.')}>
    {message && <div className="rounded-md border border-[var(--border-color)] bg-[var(--bg-secondary)] px-4 py-3 text-sm">{message}</div>}
    <div className="flex flex-wrap items-center justify-between gap-3"><select className="field max-w-sm" value={courseId} onChange={event => { setCourseId(event.target.value); const course = courses.find(item => item.id === event.target.value); setChapterId(course?.chapters[0]?.id || ''); }}><option value="">{text('选择课程', 'Select course')}</option>{courses.map(course => <option key={course.id} value={course.id}>{course.name}</option>)}</select><div className="flex gap-2 text-xs muted"><span>{selectedCourse?.chapters.length || 0} {text('个章节', 'chapters')}</span><span>·</span><span>{totalMaterials} {text('份资料', 'files')}</span></div></div>
    <div className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
      <aside className="panel overflow-hidden"><div className="border-b border-[var(--border-color)] px-4 py-3"><h2 className="font-semibold">{text('章节目录', 'Chapter directory')}</h2><p className="mt-1 text-xs muted">{text('按教学顺序组织资料', 'Organized in teaching order')}</p></div><div className="divide-y divide-[var(--border-color)]">{selectedCourse?.chapters.map((chapter, index) => <div key={chapter.id} className={chapterId === chapter.id ? 'bg-[var(--accent-muted)]' : ''}><button className="w-full px-4 py-3 text-left" onClick={() => setChapterId(chapter.id)}><div className="flex items-center justify-between gap-2"><span className="text-sm font-medium">{index + 1}. {chapter.title}</span><span className="text-xs muted">{chapter.materials.length}</span></div>{chapter.description && <p className="mt-1 line-clamp-2 text-xs muted">{chapter.description}</p>}</button></div>)}{selectedCourse && selectedCourse.chapters.length === 0 && <p className="px-4 py-8 text-center text-sm muted">{text('还没有章节，请先创建。', 'No chapters yet. Create the first one.')}</p>}</div><form onSubmit={createChapter} className="space-y-2 border-t border-[var(--border-color)] p-4"><h3 className="text-sm font-semibold">{text('新建章节', 'New chapter')}</h3><input className="field w-full" value={chapterForm.title} onChange={event => setChapterForm({ ...chapterForm, title: event.target.value })} placeholder={text('例如：第一章 电路基础', 'Example: Chapter 1 Circuit Basics')} /><textarea className="field min-h-20 w-full" value={chapterForm.description} onChange={event => setChapterForm({ ...chapterForm, description: event.target.value })} placeholder={text('章节简介（可选）', 'Chapter description (optional)')} /><button className="btn-primary w-full rounded-md px-3 py-2 text-sm" disabled={!courseId || busy}>{text('添加章节', 'Add chapter')}</button></form></aside>
      <section className="panel min-h-[520px] overflow-hidden">{selectedChapter ? <><div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--border-color)] px-5 py-4"><div><h2 className="text-lg font-semibold">{selectedChapter.title}</h2><p className="mt-1 text-sm muted">{selectedChapter.description || text('暂无章节简介', 'No chapter description')}</p></div>{!selectedChapter.legacy && <button className="btn-danger px-3 py-2 text-xs" onClick={() => removeChapter(selectedChapter)}>{text('删除章节', 'Delete chapter')}</button>}</div><form onSubmit={upload} className="flex flex-wrap items-center gap-3 border-b border-[var(--border-color)] bg-[var(--bg-secondary)] px-5 py-4"><input type="file" accept=".pdf,.pptx,.docx,.txt,.md,.png,.jpg,.jpeg,.webp" onChange={event => setFile(event.target.files?.[0] || null)} className="min-w-0 flex-1 text-sm muted" disabled={selectedChapter.legacy} /><button className="btn-primary rounded-md px-4 py-2 text-sm" disabled={!file || busy || selectedChapter.legacy}>{busy ? text('处理中', 'Processing') : text('上传资料', 'Upload')}</button>{selectedChapter.legacy && <span className="text-xs text-amber-700">{text('这是旧版章节，请新建同名章节后上传资料。', 'This is a legacy chapter. Create a managed chapter before uploading.')}</span>}</form><div className="divide-y divide-[var(--border-color)]">{selectedChapter.materials.map(material => <div key={material.id} className="flex flex-wrap items-center gap-3 px-5 py-4"><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{material.filename}</p><p className="mt-1 text-xs muted">{formatSize(material.size_bytes)} · {material.processing_status === 'processed' ? text('已加入 AI 资料库', 'Added to AI context') : material.processing_status === 'image' ? text('图片资料', 'Image material') : material.processing_status === 'no_text' ? text('未提取到文字', 'No text extracted') : text('解析失败，可正常下载', 'Extraction failed; download is available')}</p></div><button className="btn px-3 py-2 text-xs" onClick={() => download(material)}>{text('下载', 'Download')}</button><button className="btn-danger px-3 py-2 text-xs" onClick={() => removeMaterial(material)}>{text('删除', 'Delete')}</button></div>)}{selectedChapter.materials.length === 0 && <div className="px-5 py-16 text-center"><p className="text-sm font-medium">{text('本章节还没有资料', 'No materials in this chapter')}</p><p className="mt-1 text-xs muted">{text('支持 PDF、PPTX、DOCX、TXT 和常见图片，单个文件不超过 10 MB。', 'Supports PDF, PPTX, DOCX, TXT and common images up to 10 MB each.')}</p></div>}</div></> : <div className="flex min-h-[520px] items-center justify-center text-sm muted">{courseId ? text('选择或创建一个章节。', 'Select or create a chapter.') : text('先选择一门课程。', 'Select a course first.')}</div>}</section>
    </div>
  </AcademicShell>;
}
