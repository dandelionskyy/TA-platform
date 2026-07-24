const BASE_URL = '/api';

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
}

function localizeError(detail: unknown): string {
  const raw = Array.isArray(detail) ? detail.map(item => item?.msg || String(item)).join('; ') : String(detail || 'Request failed');
  if (localStorage.getItem('language') === 'en') return raw;
  const messages: Record<string, string> = {
    'Request failed': '请求失败',
    'Invalid credentials': '账号或密码错误',
    'Account is deactivated': '账号已停用',
    'Invalid or expired SMS code': '验证码错误或已过期',
    'Failed to send SMS': '验证码发送失败',
    'Student ID or phone already registered': '学号或手机号已注册',
    'Invalid or expired token': '登录已过期，请重新登录',
    'Insufficient permissions': '权限不足',
    'Course access denied': '无权访问该课程',
    'Course not found': '课程不存在',
    'Assignment not found': '作业不存在',
    'This assignment is past its deadline': '作业已超过截止时间',
    'Resubmission is disabled for this assignment': '该作业不允许重新提交',
    'Unsupported submission file type': '不支持该作业附件格式',
    'Submission file is too large': '作业附件过大',
    'Submission not found': '提交记录不存在',
    'Submission access denied': '无权访问该提交记录',
    'Score exceeds assignment maximum': '分数不能超过作业满分',
    'Attendance end time must be after start time': '签到结束时间必须晚于开始时间',
    'Attendance session not found': '签到场次不存在',
    'Invalid attendance code': '签到码错误',
    'Attendance session is not open': '当前不在签到时间内',
    'Student is not enrolled in this course': '学生未加入该课程',
    'Attendance record not found': '考勤记录不存在',
    'File is too large': '文件过大',
    'Unsupported file type': '不支持该文件格式',
    'Conversation not found': '会话不存在',
    'Submission attachment not found': '附件不存在',
    'Message permission denied': '老师暂未接受该学生的消息',
    'Thread not found': '对话不存在',
    'Thread access denied': '无权访问该对话',
    'Recipient is not in this course': '对方不是该课程成员',
    'Message cannot be empty': '消息不能为空',
    'Course chapter not found': '课程章节不存在',
    'Course material not found': '课程资料不存在',
    'Course material file not found': '课程资料文件不存在',
    'Unsupported course material type': '不支持该课程资料格式',
    'Course material is too large': '课程资料文件过大',
  };
  return messages[raw] || raw;
}

class ApiClient {
  private getToken(): string | null {
    return localStorage.getItem('access_token');
  }

  private async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { method = 'GET', body, headers = {} } = options;
    const token = this.getToken();

    const fetchHeaders: Record<string, string> = { ...headers };
    if (token) {
      fetchHeaders['Authorization'] = `Bearer ${token}`;
    }

    const fetchOptions: RequestInit = {
      method,
      headers: fetchHeaders,
    };

    if (body) {
      if (body instanceof FormData) {
        fetchOptions.body = body;
      } else {
        fetchHeaders['Content-Type'] = 'application/json';
        fetchOptions.body = JSON.stringify(body);
      }
    }

    let response = await fetch(`${BASE_URL}${path}`, fetchOptions);

    if (response.status === 401) {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken && !path.startsWith('/auth/')) {
        const refresh = await fetch(`${BASE_URL}/auth/refresh`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (refresh.ok) {
          const tokens = await refresh.json();
          localStorage.setItem('access_token', tokens.access_token);
          localStorage.setItem('refresh_token', tokens.refresh_token);
          fetchHeaders['Authorization'] = `Bearer ${tokens.access_token}`;
          response = await fetch(`${BASE_URL}${path}`, { ...fetchOptions, headers: fetchHeaders });
        }
      }
      if (response.status === 401) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login';
        throw new Error('Unauthorized');
      }
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(localizeError(error.detail));
    }

    return response.json();
  }

  private async requestFile(path: string): Promise<Blob> {
    const token = this.getToken();
    let response = await fetch(`${BASE_URL}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (response.status === 401) {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        const refresh = await fetch(`${BASE_URL}/auth/refresh`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (refresh.ok) {
          const tokens = await refresh.json();
          localStorage.setItem('access_token', tokens.access_token);
          localStorage.setItem('refresh_token', tokens.refresh_token);
          response = await fetch(`${BASE_URL}${path}`, { headers: { Authorization: `Bearer ${tokens.access_token}` } });
        }
      }
      if (response.status === 401) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login';
        throw new Error('Unauthorized');
      }
    }
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(localizeError(error.detail));
    }
    return response.blob();
  }

  // Auth
  login(login: string, password: string) {
    return this.request<{ user: any; tokens: { access_token: string; refresh_token: string } }>('/auth/login', {
      method: 'POST', body: { login, password },
    });
  }

  register(data: { student_id: string; phone: string; password: string; sms_code: string; display_name?: string }) {
    return this.request<{ user: any; tokens: { access_token: string; refresh_token: string } }>('/auth/register', {
      method: 'POST', body: data,
    });
  }

  sendSms(phone: string) {
    return this.request<{ message: string }>('/auth/send-sms', { method: 'POST', body: { phone } });
  }

  logout(refreshToken: string) {
    return this.request<{ message: string }>('/auth/logout', { method: 'POST', body: { refresh_token: refreshToken } });
  }

  getMe() {
    return this.request<any>('/auth/me');
  }

  // Chat
  sendMessage(formData: FormData) {
    return this.request<{ message_id: string; conversation_id: string; response: string }>('/chat/send', {
      method: 'POST', body: formData,
    });
  }

  getConversations(page = 1) {
    return this.request<any>(`/chat/conversations?page=${page}`);
  }

  getMessages(conversationId: string, page = 1) {
    return this.request<any>(`/chat/conversations/${conversationId}/messages?page=${page}`);
  }

  // Teacher
  getStudents(search = '', page = 1) {
    return this.request<any>(`/teacher/students?search=${encodeURIComponent(search)}&page=${page}`);
  }

  getStudentConversations(studentId: string, page = 1) {
    return this.request<any>(`/teacher/students/${studentId}/conversations?page=${page}`);
  }

  getStudentMessages(studentId: string, convId: string, page = 1) {
    return this.request<any>(`/teacher/students/${studentId}/conversations/${convId}/messages?page=${page}`);
  }

  getStudentUsage(studentId: string) {
    return this.request<any>(`/teacher/students/${studentId}/usage-stats`);
  }

  getTeacherDashboard() {
    return this.request<any>('/teacher/dashboard');
  }

  getCourses() {
    return this.request<any>('/courses');
  }

  getTeacherCourses() {
    return this.request<any>('/teacher/courses');
  }

  createCourse(data: { name: string; description?: string; knowledge_base_path?: string; chapters?: string[] }) {
    return this.request<any>('/teacher/courses', { method: 'POST', body: data });
  }

  createCourseChapter(courseId: string, data: { title: string; description?: string }) {
    return this.request<any>(`/courses/${courseId}/chapters`, { method: 'POST', body: data });
  }

  updateCourseChapter(chapterId: string, data: { title?: string; description?: string; sort_order?: number }) {
    return this.request<any>(`/courses/chapters/${chapterId}`, { method: 'PATCH', body: data });
  }

  deleteCourseChapter(chapterId: string) {
    return this.request<any>(`/courses/chapters/${chapterId}`, { method: 'DELETE' });
  }

  uploadCourseMaterial(chapterId: string, file: File) {
    const form = new FormData();
    form.append('file', file);
    return this.request<any>(`/courses/chapters/${chapterId}/materials`, { method: 'POST', body: form });
  }

  getCourseMaterialFile(materialId: string) {
    return this.requestFile(`/courses/materials/${materialId}/file`);
  }

  deleteCourseMaterial(materialId: string) {
    return this.request<any>(`/courses/materials/${materialId}`, { method: 'DELETE' });
  }

  enrollStudent(courseId: string, studentId: string) {
    return this.request<any>(`/teacher/courses/${courseId}/students/${studentId}`, { method: 'POST' });
  }

  getCourseStudents(courseId: string) {
    return this.request<any>(`/teacher/courses/${courseId}/students`);
  }

  getAvailableCourseStudents(courseId: string, search = '', page = 1) {
    return this.request<any>(`/teacher/courses/${courseId}/available-students?search=${encodeURIComponent(search)}&page=${page}`);
  }

  enrollStudentsBulk(courseId: string, studentIds: string[]) {
    return this.request<any>(`/teacher/courses/${courseId}/students/bulk`, {
      method: 'POST',
      body: { student_ids: studentIds },
    });
  }

  assignTA(courseId: string, userId: string) {
    return this.request<any>(`/teacher/courses/${courseId}/tas`, { method: 'POST', body: { user_id: userId } });
  }

  provisionUser(data: { student_id: string; phone: string; password: string; display_name?: string; role?: 'ta' | 'student' }) {
    return this.request<any>('/auth/provision', { method: 'POST', body: data });
  }

  // TA
  getTAStudentUsage(studentId: string) {
    return this.request<any>(`/ta/students/${studentId}/usage-stats`);
  }

  getTAStudents() {
    return this.request<any>('/ta/students');
  }

  getTADashboard() {
    return this.request<any>('/ta/dashboard');
  }

  // Robot
  getRobotStatus() {
    return this.request<any>('/robot/status');
  }

  getRobotQuestions(page = 1) {
    return this.request<any>(`/robot/questions?page=${page}`);
  }

  // Academic workflows
  getAssignments(courseId: string) {
    return this.request<any>(`/courses/${courseId}/assignments`);
  }

  createAssignment(courseId: string, data: { title: string; instructions?: string; due_at?: string; max_score?: number; allow_late?: boolean; allow_resubmit?: boolean }) {
    return this.request<any>(`/courses/${courseId}/assignments`, { method: 'POST', body: data });
  }

  updateAssignment(assignmentId: string, data: Record<string, unknown>) {
    return this.request<any>(`/assignments/${assignmentId}`, { method: 'PATCH', body: data });
  }

  publishAssignment(assignmentId: string) {
    return this.request<any>(`/assignments/${assignmentId}/publish`, { method: 'POST' });
  }

  submitAssignment(assignmentId: string, answerText: string, file?: File | null) {
    const form = new FormData();
    form.append('answer_text', answerText);
    if (file) form.append('file', file);
    return this.request<any>(`/assignments/${assignmentId}/submit`, { method: 'POST', body: form });
  }

  getAssignmentSubmissions(assignmentId: string) {
    return this.request<any>(`/assignments/${assignmentId}/submissions`);
  }

  gradeSubmission(submissionId: string, data: { score: number; feedback?: string }) {
    return this.request<any>(`/submissions/${submissionId}/grade`, { method: 'POST', body: data });
  }

  returnSubmission(submissionId: string) {
    return this.request<any>(`/submissions/${submissionId}/return`, { method: 'POST' });
  }

  getSubmissionFile(submissionId: string) {
    return this.requestFile(`/submissions/${submissionId}/file`);
  }

  getAttendanceSessions(courseId: string) {
    return this.request<any>(`/courses/${courseId}/attendance/sessions`);
  }

  createAttendanceSession(courseId: string, data: { title: string; starts_at: string; ends_at: string; code?: string }) {
    return this.request<any>(`/courses/${courseId}/attendance/sessions`, { method: 'POST', body: data });
  }

  checkIn(sessionId: string, code: string) {
    return this.request<any>(`/attendance/sessions/${sessionId}/check-in`, { method: 'POST', body: { code } });
  }

  getAttendanceRecords(sessionId: string) {
    return this.request<any>(`/attendance/sessions/${sessionId}/records`);
  }

  updateAttendanceRecord(recordId: string, data: { status: string; note?: string }) {
    return this.request<any>(`/attendance/records/${recordId}`, { method: 'PATCH', body: data });
  }

  upsertAttendanceRecord(sessionId: string, studentId: string, data: { status: string; note?: string }) {
    return this.request<any>(`/attendance/sessions/${sessionId}/records/${studentId}`, { method: 'POST', body: data });
  }

  getAnnouncements(courseId: string) {
    return this.request<any>(`/courses/${courseId}/announcements`);
  }

  createAnnouncement(courseId: string, data: { title: string; content: string; expires_at?: string }) {
    return this.request<any>(`/courses/${courseId}/announcements`, { method: 'POST', body: data });
  }

  // Direct messaging
  getMessageContacts() {
    return this.request<any>('/messaging/contacts');
  }

  getMessageThreads() {
    return this.request<any>('/messaging/threads');
  }

  createMessageThread(courseId: string, recipientId: string) {
    return this.request<any>('/messaging/threads', { method: 'POST', body: { course_id: courseId, recipient_id: recipientId } });
  }

  getMessageThread(threadId: string) {
    return this.request<any>(`/messaging/threads/${threadId}`);
  }

  sendDirectMessage(threadId: string, content: string) {
    return this.request<any>(`/messaging/threads/${threadId}/messages`, { method: 'POST', body: { content } });
  }

  getMessagePermissions(courseId: string) {
    return this.request<any>(`/messaging/permissions?course_id=${encodeURIComponent(courseId)}`);
  }

  updateMessagePermission(courseId: string, studentId: string, accepted: boolean) {
    return this.request<any>(`/messaging/permissions/${courseId}/${studentId}`, { method: 'PATCH', body: { accepted } });
  }
}

export const api = new ApiClient();
