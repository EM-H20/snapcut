import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import {kenBurns} from './kenburns';
import type {PhotoShotT} from './types';

export const PhotoShot: React.FC<{shot: PhotoShotT; frames: number}> = ({shot, frames}) => {
  const frame = useCurrentFrame();
  const {scale, x, y = 0} = kenBurns(shot.kenBurns, frame / frames);
  const src = staticFile(shot.src);
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{transform: `scale(${scale}) translate(${x}%, ${y}%)`}}>
        <Img src={src} style={{width: '100%', height: '100%', objectFit: 'contain'}} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
