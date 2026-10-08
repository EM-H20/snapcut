// 분할 화면 칸 배치: 2·3장은 화면 긴 쪽으로 나란히, 4장은 2x2
export function collageGrid(n: number, landscape: boolean): {cols: number; rows: number} {
  if (n >= 4) return {cols: 2, rows: 2};
  return landscape ? {cols: n, rows: 1} : {cols: 1, rows: n};
}
