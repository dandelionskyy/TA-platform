import type { BridgeLanguage } from '../../services/bridgeApi';

const STATES = ['thinking', 'questioning', 'encouraging', 'explaining', 'cautioning', 'celebrating', 'uncertain'] as const;
export type AvatarState = typeof STATES[number];

export function normalizeAvatarState(value: string | undefined): AvatarState {
  const state = value?.toLowerCase();
  return STATES.find(option => option === state) || 'thinking';
}

const labels: Record<AvatarState, [string, string]> = {
  thinking: ['正在思考', 'Thinking'],
  questioning: ['在问一个问题', 'Asking a question'],
  encouraging: ['在鼓励你', 'Encouraging you'],
  explaining: ['在解释', 'Explaining'],
  cautioning: ['温和地提醒你', 'Gently correcting'],
  celebrating: ['在庆祝你的进步', 'Celebrating your progress'],
  uncertain: ['正在检查证据', 'Checking the evidence'],
};

export default function BridgeAvatar({ state, language, reducedMotion }: {
  state: AvatarState;
  language: BridgeLanguage;
  reducedMotion: boolean;
}) {
  const label = labels[state][language === 'zh' ? 0 : 1];
  return (
    <div className={`bridge-avatar bridge-avatar--${state}${reducedMotion ? ' bridge-avatar--still' : ''}`}>
      <div className="bridge-avatar-figure" role="img" aria-label={language === 'zh' ? `BRIDGE 助教：${label}` : `BRIDGE assistant: ${label}`}>
        <div className="bridge-avatar-head" aria-hidden="true">
          <span className="bridge-avatar-brow bridge-avatar-brow-left" />
          <span className="bridge-avatar-brow bridge-avatar-brow-right" />
          <span className="bridge-avatar-eye bridge-avatar-eye-left" />
          <span className="bridge-avatar-eye bridge-avatar-eye-right" />
          <span className="bridge-avatar-mouth" />
        </div>
        <div className="bridge-avatar-body" aria-hidden="true"><span className="bridge-avatar-arm bridge-avatar-arm-left" /><span className="bridge-avatar-arm bridge-avatar-arm-right" /></div>
      </div>
      <p className="bridge-avatar-caption">{label}</p>
    </div>
  );
}
