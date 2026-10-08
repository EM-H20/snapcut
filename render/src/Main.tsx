import React from 'react';
import {AbsoluteFill, Html5Audio, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {ClipShot} from './ClipShot';
import {CollageShot} from './CollageShot';
import {CreditsShot} from './CreditsShot';
import {musicVolume} from './duck';
import {PhotoShot} from './PhotoShot';
import {ShotTag} from './ShotTag';
import {shotLabel} from './shotLabel';
import {blurAmount, span} from './span';
import {VideoShot} from './VideoShot';
import type {Storyboard} from './types';

export const Main: React.FC<Storyboard> = (props) => {
  const {fps, durationInFrames} = useVideoConfig();
  const plan = props.active ? props.formats[props.active] : undefined;
  if (!plan) return null;
  const total = durationInFrames / fps;
  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      <Html5Audio
        src={staticFile(props.music)}
        trimBefore={Math.round(plan.musicStart * fps)}
        volume={(f) => musicVolume(f / fps, plan.shots, plan.musicFadeEnd ?? total)}
      />
      {plan.shots.map((shot, i) => {
        const {from, frames, duration, fadeIn, blurIn, blurOut} = span(plan.shots, i, fps);
        return (
          // premountFor: 1초 전에 숨겨서 미리 붙인다 — 영상 탐색·사진 로딩이 전환 순간이 아니라 그 전에 끝나 매끄럽게 넘어간다
          <Sequence key={i} name={shotLabel(shot, 0)} from={from} durationInFrames={duration} premountFor={fps}>
            <FadeIn frames={fadeIn} blurIn={blurIn} blurOut={blurOut} length={frames}>
              {shot.type === 'photo' ? (
                <PhotoShot shot={shot} frames={frames} />
              ) : shot.type === 'collage' ? (
                <CollageShot shot={shot} frames={frames} />
              ) : shot.type === 'video' ? (
                <VideoShot shot={shot} />
              ) : shot.type === 'credits' ? (
                <CreditsShot shot={shot} font={props.font} />
              ) : (
                <ClipShot shot={shot} frames={frames} />
              )}
            </FadeIn>
          </Sequence>
        );
      })}
      <ShotTag shots={plan.shots} />
    </AbsoluteFill>
  );
};

// dissolve: 앞 장면(아래에 남아 있음) 위로 서서히 떠오른다. blur: 경계 앞뒤로 가우시안 블러가 걸렸다 풀린다
const FadeIn: React.FC<{frames: number; blurIn: number; blurOut: number; length: number; children: React.ReactNode}> = ({frames, blurIn, blurOut, length, children}) => {
  const frame = useCurrentFrame();
  const {height} = useVideoConfig();
  if (!frames && !blurIn && !blurOut) return <>{children}</>;
  const px = blurAmount(frame, length, blurIn, blurOut, height / 36);
  return (
    <AbsoluteFill style={{
      opacity: frames ? interpolate(frame, [0, frames], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}) : 1,
      filter: px ? `blur(${px}px)` : undefined,
      transform: px ? `scale(${1 + (0.06 * px) / (height / 36)})` : undefined,  // 가장자리로 검은 배경이 번져 보이지 않게 살짝 확대
    }}>{children}</AbsoluteFill>
  );
};
