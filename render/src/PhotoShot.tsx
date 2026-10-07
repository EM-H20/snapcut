import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import {kenBurns} from './kenburns';
import type {PhotoShotT} from './types';

export const PhotoShot: React.FC<{shot: PhotoShotT; frames: number}> = ({shot, frames}) => {
  const frame = useCurrentFrame();
  const {scale, x} = kenBurns(shot.kenBurns, frame / frames);
  const src = staticFile(shot.src);
  return (
    <AbsoluteFill>
      <Img src={src} style={{width: '100%', height: '100%', objectFit: 'cover', filter: 'blur(40px) brightness(0.6)', transform: 'scale(1.15)'}} />
      <AbsoluteFill style={{transform: `scale(${scale}) translateX(${x}%)`}}>
        <Img src={src} style={{width: '100%', height: '100%', objectFit: 'contain'}} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
