import type {Caption} from './types.ts';

export const activeCaption = (caps: Caption[], t: number): string | null =>
  caps.find((c) => c.start <= t && t < c.end)?.text ?? null;
