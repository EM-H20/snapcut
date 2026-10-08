import type {Shot} from './types';

const fadeOf = (s: Shot | undefined, fps: number) => (s && 'dissolve' in s && s.dissolve ? Math.round(s.dissolve * fps) : 0);
const halfBlur = (s: Shot | undefined, fps: number) => (s && 'blur' in s && s.blur ? Math.round((s.blur * fps) / 2) : 0);

// 블러 전환: 경계에서 maxPx, 들어오는 장면은 앞 blurIn 프레임 동안 선명해지고 나가는 장면은 끝 blurOut 프레임 동안 흐려진다
export function blurAmount(frame: number, frames: number, blurIn: number, blurOut: number, maxPx: number): number {
  const a = blurIn ? Math.max(0, 1 - frame / blurIn) : 0;
  const b = blurOut ? Math.max(0, 1 - (frames - 1 - frame) / blurOut) : 0;
  return Math.round(maxPx * Math.max(a, b) * 100) / 100;
}

// 장면 i의 프레임 구간. 다음 장면이 dissolve면 이 장면을 그만큼 더 남겨 두고(아래에 깔림),
// dissolve 장면은 그동안 투명→불투명으로 떠오른다 (뒤 Sequence가 위에 그려짐).
// 끝 페이드아웃: 마지막 fadeFrames 동안 1→0 (아웃트로 카드가 검은 화면으로 끝남)
export function tailOpacity(frame: number, frames: number, fadeFrames: number): number {
  if (!fadeFrames) return 1;
  const start = frames - fadeFrames;
  return Math.min(1, Math.max(0, 1 - (frame - start) / Math.max(1, fadeFrames - 1)));
}

export function span(shots: Shot[], i: number, fps: number): {from: number; frames: number; duration: number; fadeIn: number; blurIn: number; blurOut: number} {
  const s = shots[i];
  const from = Math.round(s.start * fps);
  const frames = Math.max(1, Math.round(s.end * fps) - from);
  return {from, frames, duration: frames + fadeOf(shots[i + 1], fps), fadeIn: fadeOf(s, fps),
    blurIn: halfBlur(s, fps), blurOut: halfBlur(shots[i + 1], fps)};
}
