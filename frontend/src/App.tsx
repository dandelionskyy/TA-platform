import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './stores/authStore';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import StudentPage from './pages/StudentPage';
import TeacherPage from './pages/TeacherPage';
import TAPage from './pages/TAPage';

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
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/student" element={<ProtectedRoute roles={['student']}><StudentPage /></ProtectedRoute>} />
      <Route path="/teacher" element={<ProtectedRoute roles={['teacher']}><TeacherPage /></ProtectedRoute>} />
      <Route path="/ta" element={<ProtectedRoute roles={['ta']}><TAPage /></ProtectedRoute>} />
      <Route path="/" element={<HomeRedirect />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
