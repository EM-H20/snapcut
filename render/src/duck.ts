import type {Shot} from './types';

export const DUCK = 0.3;      // 현장 소리 구간의 음악 볼륨
export const FADE = 0.3;      // 덕킹 진입/복귀 초
export const END_FADE = 2;    // 끝 페이드아웃 초

export function musicVolume(t: number, shots: Shot[], total: number): number {
  let v = 1;
  for (const s of shots) {
    if (s.type !== 'video' || !s.liveAudio || s.duck === false) continue;  // duck: false면 음악도 그대로
    const fade = s.duckFade ?? FADE;  // duckFade: 현장 소리 앞뒤로 음악이 서서히 줄었다 커지는 초
    const w = Math.min(Math.max(0, (t - (s.start - fade)) / fade), Math.max(0, (s.end + fade - t) / fade), 1);
    const level = typeof s.duck === 'number' ? s.duck : DUCK;  // duck: 0.6이면 이 장면은 음악을 60%까지만 줄임
    v = Math.min(v, level + (1 - level) * (1 - w)); // 1-(1-level)*w 는 부동소수 오차로 w=1에서 level과 어긋남
  }
  return v * Math.min(1, Math.max(0, (total - t) / END_FADE));
}
