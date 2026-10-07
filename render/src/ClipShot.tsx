import React from 'react';
import {Freeze, OffthreadVideo, Sequence, staticFile, useVideoConfig} from 'remotion';
import type {ClipShotT} from './types';

// 인트로/아웃트로 카드 mp4의 길이(초). 샷이 더 길면 마지막 프레임을 유지한다.
export const CARD_SECONDS = 3;

export const ClipShot: React.FC<{shot: ClipShotT; frames: number}> = ({shot, frames}) => {
  const {fps} = useVideoConfig();
  const cardFrames = CARD_SECONDS * fps;
  const video = <OffthreadVideo src={staticFile(shot.src)} muted />;
  if (frames <= cardFrames) return video;
  return (
    <>
      <Sequence durationInFrames={cardFrames}>{video}</Sequence>
      <Sequence from={cardFrames}>
        <Freeze frame={cardFrames - 1}>{video}</Freeze>
      </Sequence>
    </>
  );
};
