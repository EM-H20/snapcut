import type {KenBurns} from './types';

export function kenBurns(kind: KenBurns, p: number): {scale: number; x: number} {
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
  }
}
