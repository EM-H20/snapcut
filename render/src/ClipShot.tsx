import React from 'react';
import {AbsoluteFill, Freeze, OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {tailOpacity} from './span';
import type {ClipShotT} from './types';

// 인트로/아웃트로 카드 mp4의 길이(초). 샷이 더 길면 마지막 프레임을 유지한다.
export const CARD_SECONDS = 3;

export const ClipShot: React.FC<{shot: ClipShotT; frames: number}> = ({shot, frames}) => {
  const {fps} = useVideoConfig();
  const frame = useCurrentFrame();
  const cardFrames = CARD_SECONDS * fps;
  const video = <OffthreadVideo src={staticFile(shot.src)} muted />;
  const body = frames <= cardFrames ? video : (
    <>
      <Sequence durationInFrames={cardFrames}>{video}</Sequence>
      <Sequence from={cardFrames}>
        <Freeze frame={cardFrames - 1}>{video}</Freeze>
      </Sequence>
    </>
  );
  // fadeOut: 아웃트로가 끝에서 검은 화면으로 사라진다 (뒤는 Main의 검은 배경)
  return <AbsoluteFill style={{opacity: tailOpacity(frame, frames, Math.round((shot.fadeOut ?? 0) * fps))}}>{body}</AbsoluteFill>;
};
