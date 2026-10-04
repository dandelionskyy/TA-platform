import { FormEvent, useEffect, useState } from 'react';
import { api } from '../../services/api';
import { useLanguage } from '../../i18n/LanguageContext';

interface Course {
  id: string;
  name: string;
}

interface Student {
  id: string;
  student_id: string;
  display_name: string;
  phone: string;
  is_active: boolean;
}

interface CourseMemberManagerProps {
  courses: Course[];
}

export default function CourseMemberManager({ courses }: CourseMemberManagerProps) {
  const { text } = useLanguage();
  const [courseId, setCourseId] = useState('');
  const [search, setSearch] = useState('');
  const [available, setAvailable] = useState<Student[]>([]);
  const [enrolled, setEnrolled] = useState<Student[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!courseId && courses[0]) setCourseId(courses[0].id);
    if (courseId && !courses.some(course => course.id === courseId)) setCourseId(courses[0]?.id || '');
  }, [courses, courseId]);

  const loadMembers = async (nextSearch = search) => {
    if (!courseId) {
      setAvailable([]);
      setEnrolled([]);
      return;
    }
    setLoading(true);
    try {
      const [availableData, enrolledData] = await Promise.all([
        api.getAvailableCourseStudents(courseId, nextSearch),
        api.getCourseStudents(courseId),
      ]);
      setAvailable(availableData.students || []);
      setEnrolled(enrolledData.students || []);
      setSelected(current => current.filter(id => (availableData.students || []).some((student: Student) => student.id === id)));
    } catch (error: any) {
      setMessage(error.message || text('课程成员加载失败。', 'Unable to load course members.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (courseId) loadMembers('');
  }, [courseId]);

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    loadMembers(search);
  };

  const toggleStudent = (studentId: string) => {
    setSelected(current => current.includes(studentId)
      ? current.filter(id => id !== studentId)
      : [...current, studentId]);
  };

  const toggleAll = () => {
    const visibleIds = available.map(student => student.id);
    setSelected(current => visibleIds.every(id => current.includes(id))
      ? current.filter(id => !visibleIds.includes(id))
      : Array.from(new Set([...current, ...visibleIds])));
  };

  const enrollSelected = async () => {
    if (!courseId || selected.length === 0) return;
    setLoading(true);
    try {
      const result = await api.enrollStudentsBulk(courseId, selected);
      setMessage(text(`已将 ${result.added_count} 名学生加入课程。`, `${result.added_count} student(s) added to the course.`));
      setSelected([]);
      await loadMembers(search);
    } catch (error: any) {
      setMessage(error.message || text('学生加入课程失败。', 'Unable to add students to the course.'));
    } finally {
      setLoading(false);
    }
  };

  const removeStudent = async (student: Student) => {
    if (!courseId) return;
    const name = student.display_name || student.student_id;
    if (!window.confirm(text(`确定将“${name}”移出本课程吗？学生账号和其他课程不会受到影响。`, `Remove “${name}” from this course? Their account and other courses will not be affected.`))) return;

    setLoading(true);
    try {
      await api.removeStudentFromCourse(courseId, student.id);
      setMessage(text(`已将 ${name} 移出本课程。`, `${name} was removed from this course.`));
      await loadMembers(search);
    } catch (error: any) {
      setMessage(error.message || text('移除学生失败。', 'Unable to remove the student.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">{text('课程成员管理', 'Course members')}</h2>
          <p className="mt-1 max-w-2xl text-sm muted">
            {text('学生在注册页面创建账号后，可以在这里搜索并批量加入课程，不需要教师重复创建账号。', 'After students register, search and add them to a course here without creating duplicate accounts.')}
          </p>
        </div>
        {message && <span className="text-sm muted">{message}</span>}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <select className="field min-w-52" value={courseId} onChange={event => setCourseId(event.target.value)}>
          <option value="">{text('选择课程', 'Select course')}</option>
          {courses.map(course => <option key={course.id} value={course.id}>{course.name}</option>)}
        </select>
        <span className="text-sm muted">
          {courseId ? `${enrolled.length} ${text('名已加入学生', 'enrolled student(s)')}` : text('请先选择课程', 'Select a course first')}
        </span>
      </div>

      {courseId && <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(260px,360px)]">
        <div className="min-w-0 rounded-md border border-[var(--border-color)]">
          <div className="border-b border-[var(--border-color)] p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="font-medium">{text('已注册学生', 'Registered students')}</h3>
                <p className="mt-1 text-xs muted">{text('搜索学号、姓名或手机号后勾选学生。', 'Search by student ID, name, or phone, then select students.')}</p>
              </div>
              <button type="button" className="btn px-3 py-1.5 text-xs" onClick={toggleAll} disabled={available.length === 0}>
                {available.length > 0 && available.every(student => selected.includes(student.id))
                  ? text('取消全选', 'Clear all')
                  : text('选择当前列表', 'Select visible')}
              </button>
            </div>
            <form className="mt-3 flex flex-wrap gap-2" onSubmit={submitSearch}>
              <input className="field min-w-0 flex-1" value={search} onChange={event => setSearch(event.target.value)} placeholder={text('搜索已注册学生...', 'Search registered students...')} />
              <button type="submit" className="btn px-4 py-2" disabled={loading}>{text('搜索', 'Search')}</button>
            </form>
          </div>
          <div className="max-h-80 divide-y divide-[var(--border-color)] overflow-y-auto">
            {available.map(student => <label key={student.id} className="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-[var(--bg-secondary)]">
              <input type="checkbox" checked={selected.includes(student.id)} onChange={() => toggleStudent(student.id)} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{student.display_name || student.student_id}</span>
                <span className="block truncate text-xs muted">{student.student_id} · {student.phone}</span>
              </span>
            </label>)}
            {available.length === 0 && <p className="px-4 py-10 text-center text-sm muted">
              {loading ? text('正在加载...', 'Loading...') : text('没有找到未加入本课程的学生。', 'No registered students are waiting to be added.')}
            </p>}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border-color)] p-4">
            <span className="text-sm muted">{text('已选择', 'Selected')} {selected.length}</span>
            <button type="button" className="btn-primary rounded-md px-4 py-2 text-sm" onClick={enrollSelected} disabled={loading || selected.length === 0}>
              {text('批量加入课程', 'Add selected to course')}
            </button>
          </div>
        </div>

        <div className="min-w-0 rounded-md border border-[var(--border-color)]">
          <div className="border-b border-[var(--border-color)] px-4 py-3">
            <h3 className="font-medium">{text('当前课程学生', 'Current course students')}</h3>
          </div>
          <div className="max-h-80 divide-y divide-[var(--border-color)] overflow-y-auto">
            {enrolled.map(student => <div key={student.id} className="flex items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{student.display_name || student.student_id}</div>
                <div className="mt-1 truncate text-xs muted">{student.student_id} · {student.phone}</div>
              </div>
              <button type="button" className="btn px-2.5 py-1.5 text-xs" onClick={() => removeStudent(student)} disabled={loading}>
                {text('移除', 'Remove')}
              </button>
            </div>)}
            {enrolled.length === 0 && <p className="px-4 py-10 text-center text-sm muted">{text('暂时没有学生。', 'No students enrolled yet.')}</p>}
          </div>
        </div>
      </div>}
    </section>
  );
}
