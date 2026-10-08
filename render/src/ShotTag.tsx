import React, {useEffect, useRef, useState} from 'react';
import {AbsoluteFill, getRemotionEnvironment, useCurrentFrame, useVideoConfig} from 'remotion';
import {shotLabel} from './shotLabel';
import type {Shot} from './types';

// Studio 미리보기 전용: 지금 장면의 파일 이름을 띄우고 Q 키로 복사한다 (렌더에는 안 나옴).
// 클릭은 Studio의 선택 레이어가 가로채서 쓰지 않는다. Q는 Studio 단축키가 아니다.
const COPY_KEY = 'q';

// 지금 시각의 장면 하나에만 띄운다 (장면마다 두면 premount로 미리 붙은 다음 장면 이름이 복사될 수 있음)
export const ShotTag: React.FC<{shots: Shot[]}> = ({shots}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const shot = shots.find((s) => frame < Math.round(s.end * fps)) ?? shots[shots.length - 1];
  const [copied, setCopied] = useState(false);
  const studio = getRemotionEnvironment().isStudio;
  const label = shotLabel(shot, frame / fps - shot.start);
  const latest = useRef(label);
  latest.current = label;
  useEffect(() => {
    if (!studio) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== COPY_KEY || e.metaKey || e.ctrlKey || e.altKey) return;
      navigator.clipboard.writeText(latest.current).then(
        () => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        },
        () => window.prompt('복사하세요', latest.current),
      );
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [studio]);
  if (!studio) return null;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 16, top: 16, padding: '6px 12px', background: 'rgba(0,0,0,.6)', color: '#fff', fontSize: 28, fontFamily: 'monospace', borderRadius: 6}}>
        {copied ? '복사됨 ✓ ' : 'Q 복사 · '}
        {label}
      </div>
    </AbsoluteFill>
  );
};
