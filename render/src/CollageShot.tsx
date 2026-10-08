import React from 'react';
import {AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {collageGrid} from './collage';
import {kenBurns} from './kenburns';
import type {CollageShotT} from './types';

const GAP = 8;

export const CollageShot: React.FC<{shot: CollageShotT; frames: number}> = ({shot, frames}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const {cols, rows} = collageGrid(shot.srcs.length, width > height);
  const {scale} = kenBurns(shot.kenBurns, frame / frames);
  const step = Math.min(4, Math.floor(frames / (2 * shot.srcs.length)));  // 칸이 차례로 뜬다
  return (
    <AbsoluteFill style={{display: 'grid', gap: GAP, padding: GAP, gridTemplateColumns: `repeat(${cols}, 1fr)`, gridTemplateRows: `repeat(${rows}, 1fr)`}}>
      {shot.srcs.map((src, i) => (
        <div key={i} style={{overflow: 'hidden', opacity: interpolate(frame, [i * step, i * step + 3], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}}>
          <Img src={staticFile(src)} style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${scale})`}} />
        </div>
      ))}
    </AbsoluteFill>
  );
};
