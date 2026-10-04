import { Routes, Route, Navigate } from 'react-router-dom';
import { useEffect } from 'react';
import { useAuthStore } from './stores/authStore';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import StudentPage from './pages/StudentPage';
import TeacherPage from './pages/TeacherPage';
import TAPage from './pages/TAPage';
import { StudentAssignmentsPage, StaffAssignmentsPage } from './pages/AssignmentsPage';
import { StudentAttendancePage, StaffAttendancePage } from './pages/AttendancePage';
import AnnouncementsPage from './pages/AnnouncementsPage';
import MessagingPage from './pages/MessagingPage';
import CourseMaterialsPage from './pages/CourseMaterialsPage';
import BridgeStudentPage from './pages/BridgeStudentPage';
import BridgeStaffPage from './pages/BridgeStaffPage';

function ProtectedRoute({ children, roles }: { children: React.ReactNode; roles?: string[] }) {
  const { user, isAuthenticated } = useAuthStore();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (roles && user && !roles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

function HomeRedirect() {
  const { user, isAuthenticated } = useAuthStore();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  switch (user?.role) {
    case 'teacher': return <Navigate to="/teacher" replace />;
    case 'ta': return <Navigate to="/ta" replace />;
    case 'student': return <Navigate to="/student" replace />;
    default: return <Navigate to="/login" replace />;
  }
}

export default function App() {
  const checkAuth = useAuthStore(state => state.checkAuth);
  useEffect(() => { if (localStorage.getItem('access_token')) checkAuth(); }, [checkAuth]);
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/bridge" element={<BridgeStudentPage />} />
      <Route path="/student" element={<ProtectedRoute roles={['student']}><StudentPage /></ProtectedRoute>} />
      <Route path="/student/chat" element={<ProtectedRoute roles={['student']}><StudentPage /></ProtectedRoute>} />
      <Route path="/student/assignments" element={<ProtectedRoute roles={['student']}><StudentAssignmentsPage /></ProtectedRoute>} />
      <Route path="/student/attendance" element={<ProtectedRoute roles={['student']}><StudentAttendancePage /></ProtectedRoute>} />
      <Route path="/student/announcements" element={<ProtectedRoute roles={['student']}><AnnouncementsPage role="student" /></ProtectedRoute>} />
      <Route path="/student/messages" element={<ProtectedRoute roles={['student']}><MessagingPage role="student" /></ProtectedRoute>} />
      <Route path="/teacher" element={<ProtectedRoute roles={['teacher']}><TeacherPage /></ProtectedRoute>} />
      <Route path="/teacher/assignments" element={<ProtectedRoute roles={['teacher']}><StaffAssignmentsPage role="teacher" /></ProtectedRoute>} />
      <Route path="/teacher/attendance" element={<ProtectedRoute roles={['teacher']}><StaffAttendancePage role="teacher" /></ProtectedRoute>} />
      <Route path="/teacher/announcements" element={<ProtectedRoute roles={['teacher']}><AnnouncementsPage role="teacher" /></ProtectedRoute>} />
      <Route path="/teacher/messages" element={<ProtectedRoute roles={['teacher']}><MessagingPage role="teacher" /></ProtectedRoute>} />
      <Route path="/teacher/materials" element={<ProtectedRoute roles={['teacher']}><CourseMaterialsPage role="teacher" /></ProtectedRoute>} />
      <Route path="/teacher/bridge" element={<ProtectedRoute roles={['teacher']}><BridgeStaffPage /></ProtectedRoute>} />
      <Route path="/ta" element={<ProtectedRoute roles={['ta']}><TAPage /></ProtectedRoute>} />
      <Route path="/ta/assignments" element={<ProtectedRoute roles={['ta']}><StaffAssignmentsPage role="ta" /></ProtectedRoute>} />
      <Route path="/ta/attendance" element={<ProtectedRoute roles={['ta']}><StaffAttendancePage role="ta" /></ProtectedRoute>} />
      <Route path="/ta/announcements" element={<ProtectedRoute roles={['ta']}><AnnouncementsPage role="ta" /></ProtectedRoute>} />
      <Route path="/ta/messages" element={<ProtectedRoute roles={['ta']}><MessagingPage role="ta" /></ProtectedRoute>} />
      <Route path="/ta/materials" element={<ProtectedRoute roles={['ta']}><CourseMaterialsPage role="ta" /></ProtectedRoute>} />
      <Route path="/" element={<HomeRedirect />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
