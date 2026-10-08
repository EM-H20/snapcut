import React, {useEffect, useState} from 'react';
import {AbsoluteFill, OffthreadVideo, continueRender, delayRender, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import type {CreditsShotT} from './types';

const FAMILY = 'SnapcutHand';

// 노래가 끝난 뒤 크레딧: 영상(자기 소리) 위에 멤버별 역할을 한 줄씩 띄운다
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
  return (
    <AbsoluteFill>
      <OffthreadVideo src={staticFile(shot.src)} trimBefore={Math.round(shot.in * fps)} muted={!shot.liveAudio}
        style={{width: '100%', height: '100%', objectFit: 'contain'}} />
      <AbsoluteFill style={{background: 'rgba(0,0,0,.35)', justifyContent: 'center', alignItems: 'center', flexDirection: 'column', gap: size * 0.35}}>
        {shot.lines.map((line, i) => (
          <div key={i} style={{fontFamily: `${FAMILY}, sans-serif`, fontSize: size, color: '#fff', textShadow: '0 2px 12px rgba(0,0,0,.5)',
            opacity: interpolate(frame, [fps * (0.3 + 0.35 * i), fps * (0.8 + 0.35 * i)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}}>
            {line}
          </div>
        ))}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
