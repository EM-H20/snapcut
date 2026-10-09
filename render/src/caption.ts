import type {Caption, Place} from './types.ts';

// 지금 보이는 자막을 자리별로. 같은 자리에 여럿이면 순서대로 쌓는다. place가 없으면(예전 storyboard) 자막바
export const activeByPlace = (caps: Caption[], t: number): Record<Place, Caption[]> => {
  const out: Record<Place, Caption[]> = {bar: [], left: [], right: []};
  for (const c of caps) if (c.start <= t && t < c.end) out[c.place ?? 'bar'].push(c);
  return out;
};
