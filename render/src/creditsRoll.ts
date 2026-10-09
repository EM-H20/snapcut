const FADE_SECONDS = 2;

// 영화 엔딩 크레딧: 글자 묶음(blockHeight)이 화면 아래에서 들어와 위로 다 빠져나가고, 끝 2초는 검게 어두워진다
export function creditsRoll(frame: number, frames: number, height: number, blockHeight: number, fps = 30): {y: number; dark: number} {
  const p = Math.min(1, Math.max(0, frame / frames));
  const fadeStart = frames - FADE_SECONDS * fps;
  const dark = Math.min(1, Math.max(0, (frame - fadeStart) / (FADE_SECONDS * fps)));
  return {y: height - p * (height + blockHeight), dark};
}
