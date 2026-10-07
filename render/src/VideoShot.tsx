import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile, useVideoConfig} from 'remotion';
import type {VideoShotT} from './types';

export const VideoShot: React.FC<{shot: VideoShotT}> = ({shot}) => {
  const {fps} = useVideoConfig();
  return (
    <AbsoluteFill>
      <OffthreadVideo
        src={staticFile(shot.src)}
        trimBefore={Math.round(shot.in * fps)}
        muted={!shot.liveAudio}
        style={{width: '100%', height: '100%', objectFit: 'contain'}}
      />
    </AbsoluteFill>
  );
};
