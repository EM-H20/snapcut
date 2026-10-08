import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {collageGrid} from './collage';
import {kenBurns} from './kenburns';
import type {CollageShotT} from './types';

const GAP = 8;

export const CollageShot: React.FC<{shot: CollageShotT; frames: number}> = ({shot, frames}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const {cols, rows} = collageGrid(shot.srcs.length, width > height);
  const {scale} = kenBurns(shot.kenBurns, frame / frames);
  return (
    <AbsoluteFill style={{display: 'grid', gap: GAP, padding: GAP, gridTemplateColumns: `repeat(${cols}, 1fr)`, gridTemplateRows: `repeat(${rows}, 1fr)`}}>
      {shot.srcs.map((src, i) => (
        <div key={i} style={{position: 'relative', overflow: 'hidden'}}>
          {/* 사진이 잘리지 않게 전체를 보이고, 남는 자리는 흐린 같은 사진으로 채운다 */}
          <Img src={staticFile(src)} style={{position: 'absolute', width: '100%', height: '100%', objectFit: 'cover', filter: 'blur(30px) brightness(0.6)', transform: 'scale(1.2)'}} />
          <Img src={staticFile(src)} style={{position: 'absolute', width: '100%', height: '100%', objectFit: 'contain', transform: `scale(${scale})`}} />
        </div>
      ))}
    </AbsoluteFill>
  );
};
