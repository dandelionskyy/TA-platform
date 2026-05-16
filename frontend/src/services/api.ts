const BASE_URL = '/api';

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
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

    const response = await fetch(`${BASE_URL}${path}`, fetchOptions);

    if (response.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
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

  // TA
  getTAStudentUsage(studentId: string) {
    return this.request<any>(`/ta/students/${studentId}/usage-stats`);
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
}

export const api = new ApiClient();
