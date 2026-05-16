import { useState, useEffect } from 'react';
import { api } from '../../services/api';

interface Props {
  role: 'teacher' | 'ta' | 'student';
}

interface RobotStatus {
  robot_name: string;
  status: string;
  battery_pct: number;
  position_x: number | null;
  position_y: number | null;
  position_label: string;
  last_seen_at: string | null;
  total_questions_today: number;
}

interface RobotQuestion {
  id: string;
  student_name?: string;
  question_text: string;
  response_text?: string;
  created_at: string;
}

const STATUS_LABELS: Record<string, string> = {
  active: 'Active',
  standby: 'Standby',
  offline: 'Offline',
  charging: 'Charging',
};

const STATUS_COLORS: Record<string, string> = {
  active: '#22c55e',
  standby: '#f59e0b',
  offline: '#6b7280',
  charging: '#3b82f6',
};

export default function RobotMonitor({ role }: Props) {
  const [status, setStatus] = useState<RobotStatus | null>(null);
  const [questions, setQuestions] = useState<RobotQuestion[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStatus();
    if (role === 'teacher') loadQuestions();
    const interval = setInterval(loadStatus, 10000); // Poll every 10s
    return () => clearInterval(interval);
  }, []);

  const loadStatus = async () => {
    try {
      const data = await api.getRobotStatus();
      setStatus(data);
    } catch {} finally {
      setLoading(false);
    }
  };

  const loadQuestions = async () => {
    try {
      const data = await api.getRobotQuestions(1);
      setQuestions(data.questions || []);
    } catch {}
  };

  if (loading) {
    return <div className="flex items-center gap-3 text-sm text-[var(--text-secondary)]">
      <div className="skeleton rounded-full" style={{width:12,height:12}} /> Loading robot status...
    </div>;
  }

  if (!status) {
    return <p className="text-sm text-[var(--text-secondary)]">No robot connected</p>;
  }

  const color = STATUS_COLORS[status.status] || STATUS_COLORS.offline;

  return (
    <div className="space-y-4">
      {/* Status row */}
      <div className="flex flex-wrap items-center gap-4 md:gap-6">
        {/* Status indicator */}
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
          <span className="text-sm font-medium">{STATUS_LABELS[status.status] || status.status}</span>
        </div>

        {/* Battery */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-[var(--text-secondary)]">Battery</span>
          <div className="w-24 h-5 bg-[var(--bg-secondary)] rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${status.battery_pct}%`,
                background: status.battery_pct > 30 ? '#22c55e' : status.battery_pct > 15 ? '#f59e0b' : '#ef4444',
              }}
            />
          </div>
          <span className="text-sm font-medium">{status.battery_pct}%</span>
        </div>

        {/* Position */}
        {status.position_label && (
          <div className="flex items-center gap-1 text-sm text-[var(--text-secondary)]">
            <span>📍</span>
            <span>{status.position_label}</span>
          </div>
        )}

        {/* Questions today */}
        <div className="flex items-center gap-1 text-sm text-[var(--text-secondary)]">
          <span>Questions today:</span>
          <span className="font-semibold text-[var(--text-primary)]">{status.total_questions_today}</span>
        </div>

        {/* Last seen */}
        {status.last_seen_at && (
          <div className="text-xs text-[var(--text-secondary)]">
            Last seen: {new Date(status.last_seen_at).toLocaleTimeString()}
          </div>
        )}
      </div>

      {/* 2D Position Map (simple SVG) */}
      {(status.position_x != null && status.position_y != null) && (
        <div className="w-full h-40 bg-[var(--bg-secondary)] rounded-lg relative overflow-hidden border border-[var(--border-color)]">
          <svg viewBox="0 0 100 100" className="w-full h-full">
            <circle cx={status.position_x * 10 + 50} cy={50 - status.position_y * 10} r="3"
              fill={color} stroke="white" strokeWidth="0.5">
              <animate attributeName="r" values="3;4;3" dur="2s" repeatCount="indefinite" />
            </circle>
            <text x="5" y="95" className="text-[10px] fill-[var(--text-secondary)]" fontSize="3">Origin</text>
          </svg>
        </div>
      )}

      {/* Teacher-only: question history */}
      {role === 'teacher' && questions.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold mb-2">Recent Questions</h4>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {questions.map(q => (
              <div key={q.id} className="bg-[var(--bg-secondary)] rounded-lg p-3 text-sm">
                <div className="flex justify-between text-xs text-[var(--text-secondary)] mb-1">
                  <span>{q.student_name || 'Anonymous'}</span>
                  <span>{new Date(q.created_at).toLocaleString()}</span>
                </div>
                <p className="font-medium">Q: {q.question_text}</p>
                {q.response_text && <p className="text-[var(--text-secondary)] mt-1">A: {q.response_text.slice(0, 200)}{q.response_text.length > 200 ? '...' : ''}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
