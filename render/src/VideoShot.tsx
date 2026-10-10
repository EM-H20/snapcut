import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {tailOpacity} from './span';
import type {VideoShotT} from './types';

export const VideoShot: React.FC<{shot: VideoShotT; frames: number}> = ({shot, frames}) => {
  const {fps, width, height} = useVideoConfig();
  const frame = useCurrentFrame();
  const rot = shot.rotate ?? 0;
  const turned = Math.abs(rot) === 90;  // 옆으로 찍힌 영상: 돌린 뒤 화면에 맞도록 가로·세로 크기를 바꿔 잡는다
  return (
    // fadeOut: 끝에서 검은 화면으로 서서히 어두워진다 (뒤는 Main의 검은 배경)
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', opacity: tailOpacity(frame, frames, Math.round((shot.fadeOut ?? 0) * fps))}}>
      <OffthreadVideo
        src={staticFile(shot.src)}
        trimBefore={Math.round(shot.in * fps)}
        muted={!shot.liveAudio}
        style={{width: turned ? height : width, height: turned ? width : height, flexShrink: 0, objectFit: 'contain', transform: rot ? `rotate(${rot}deg)` : undefined}}
      />
    </AbsoluteFill>
  );
};
