import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {activeCaption} from './caption';
import type {Caption} from './types';

// 하단 자막: 흰 글씨 + 검은 외곽선. 줄바꿈은 브라우저가 단어 단위로(keep-all) — 한 장 글자 수는 plan이 2줄 분량으로 자른다
export const CaptionLayer: React.FC<{captions: Caption[]; size: number; bottom: number}> = ({captions, size, bottom}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const text = activeCaption(captions, frame / fps);
  if (!text) return null;
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: bottom}}>
      <div style={{
        maxWidth: '80%', textAlign: 'center', color: 'white', fontSize: size, fontWeight: 800, lineHeight: 1.3,
        wordBreak: 'keep-all', WebkitTextStroke: `${size / 10}px black`, paintOrder: 'stroke fill',
        overflowWrap: 'anywhere',  // 띄어쓰기 없는 긴 말(ㅋㅋㅋ…)도 화면 안에서 줄바꿈
        fontFamily: '"Apple SD Gothic Neo", "Noto Sans KR", sans-serif',
      }}>{text}</div>
    </AbsoluteFill>
  );
};
