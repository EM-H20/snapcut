import React, {useEffect, useState} from 'react';
import {AbsoluteFill, OffthreadVideo, continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {creditsRoll} from './creditsRoll';
import type {CreditsShotT} from './types';

const FAMILY = 'SnapcutHand';

// 노래가 끝난 뒤 크레딧: 영상(자기 소리) 위로 멤버별 역할이 영화 크레딧처럼 아래에서 위로 올라가고, 끝은 검게 어두워진다
export const CreditsShot: React.FC<{shot: CreditsShotT; font?: string}> = ({shot, font}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  const [handle] = useState(() => (font ? delayRender('크레딧 폰트') : null));
  useEffect(() => {
    if (!font || handle === null) return;
    const face = new FontFace(FAMILY, `url(${staticFile(font)})`);
    face.load().then((f) => {
      (document.fonts as unknown as {add: (f: FontFace) => void}).add(f);  // tsconfig lib에 FontFaceSet.add 타입이 없음
      continueRender(handle);
    }, () => continueRender(handle));  // 폰트를 못 읽어도 기본 글꼴로 렌더는 계속
  }, [font, handle]);
  const size = Math.round(height / 13);
  const gap = size * 0.35;
  const block = shot.lines.length * size * 1.2 + (shot.lines.length - 1) * gap;
  const frames = Math.round((shot.end - shot.start) * fps);
  const {y, dark} = creditsRoll(frame, frames, height, block, fps);
  return (
    <AbsoluteFill>
      <OffthreadVideo src={staticFile(shot.src)} trimBefore={Math.round(shot.in * fps)} muted={!shot.liveAudio}
        volume={(f) => 1 - creditsRoll(f, frames, height, block, fps).dark}
        style={{width: '100%', height: '100%', objectFit: 'contain'}} />
      <AbsoluteFill style={{background: 'rgba(0,0,0,.35)', alignItems: 'center'}}>
        <div style={{transform: `translateY(${y}px)`, display: 'flex', flexDirection: 'column', alignItems: 'center', gap}}>
          {shot.lines.map((line, i) => (
            <div key={i} style={{fontFamily: `${FAMILY}, sans-serif`, fontSize: size, lineHeight: 1.2, color: '#fff',
              textShadow: '0 2px 12px rgba(0,0,0,.5)', whiteSpace: 'nowrap'}}>
              {line}
            </div>
          ))}
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{background: '#000', opacity: dark}} />
    </AbsoluteFill>
  );
};
