import type {KenBurns} from './types';

export function kenBurns(kind: KenBurns, p: number): {scale: number; x: number; y?: number} {
  const t = Math.min(1, Math.max(0, p));
  switch (kind) {
    case 'zoom-in':
      return {scale: 1 + 0.1 * t, x: 0};
    case 'zoom-out':
      return {scale: 1.1 - 0.1 * t, x: 0};
    case 'pan-left':
      return {scale: 1.08, x: 2 - 4 * t};
    case 'pan-right':
      return {scale: 1.08, x: -2 + 4 * t};
    case 'scroll-down': // 세로로 긴 사진(4컷 등): 확대해서 윗변 → 아랫변까지 훑는다 (y는 이미지 높이 %)
      return {scale: 2.5, x: 0, y: 30 - 60 * t};
    case 'still':
      return {scale: 1, x: 0};
  }
}
