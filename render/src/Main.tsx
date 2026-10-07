import React from 'react';
import {AbsoluteFill, Html5Audio, Sequence, staticFile, useVideoConfig} from 'remotion';
import {ClipShot} from './ClipShot';
import {musicVolume} from './duck';
import {PhotoShot} from './PhotoShot';
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
        volume={(f) => musicVolume(f / fps, plan.shots, total)}
      />
      {plan.shots.map((shot, i) => {
        const from = Math.round(shot.start * fps);
        const frames = Math.max(1, Math.round(shot.end * fps) - from);
        return (
          <Sequence key={i} from={from} durationInFrames={frames}>
            {shot.type === 'photo' ? (
              <PhotoShot shot={shot} frames={frames} />
            ) : shot.type === 'video' ? (
              <VideoShot shot={shot} />
            ) : (
              <ClipShot shot={shot} frames={frames} />
            )}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
