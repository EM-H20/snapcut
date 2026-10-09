import React from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, staticFile, useVideoConfig} from 'remotion';
import {CaptionLayer} from './CaptionLayer';
import type {LongClip, LongStoryboard} from './types';

// 원본 한 파일에서 고른 구간을 이어 붙인다. 소리는 원본 그대로(첫 오디오 트랙 = OBS 전체 믹스)
export const ClipsTrack: React.FC<{src: string; clips: LongClip[]}> = ({src, clips}) => {
  const {fps} = useVideoConfig();
  return (
    <>
      {clips.map((c, i) => {
        const from = Math.round(c.start * fps);
        return (
          // premountFor: 1초 전에 미리 붙여 탐색이 컷 순간이 아니라 그 전에 끝나게
          <Sequence key={i} name={c.title || `구간 ${i + 1}`} from={from} durationInFrames={Math.round(c.end * fps) - from} premountFor={fps}>
            <OffthreadVideo src={staticFile(src)} trimBefore={Math.round(c.in * fps)} style={{width: '100%', height: '100%', objectFit: 'contain'}} />
          </Sequence>
        );
      })}
    </>
  );
};

export const Longform: React.FC<LongStoryboard> = (sb) => {
  const plan = sb.formats.longform;
  if (!plan) return null;
  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      <ClipsTrack src={sb.src} clips={plan.clips} />
      <CaptionLayer captions={plan.captions} size={plan.height / 18} bottom={plan.height * 0.07} />
    </AbsoluteFill>
  );
};
