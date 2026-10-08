import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile, useVideoConfig} from 'remotion';
import type {VideoShotT} from './types';

export const VideoShot: React.FC<{shot: VideoShotT}> = ({shot}) => {
  const {fps, width, height} = useVideoConfig();
  const rot = shot.rotate ?? 0;
  const turned = Math.abs(rot) === 90;  // 옆으로 찍힌 영상: 돌린 뒤 화면에 맞도록 가로·세로 크기를 바꿔 잡는다
  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
      <OffthreadVideo
        src={staticFile(shot.src)}
        trimBefore={Math.round(shot.in * fps)}
        muted={!shot.liveAudio}
        style={{width: turned ? height : width, height: turned ? width : height, flexShrink: 0, objectFit: 'contain', transform: rot ? `rotate(${rot}deg)` : undefined}}
      />
    </AbsoluteFill>
  );
};
