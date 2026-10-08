import type {Shot} from './types';

const name = (src: string) => src.replace(/^media\//, '').replace(/\.[^.]+$/, '');

// Studio에서 클릭해 복사하는 문구: 파일 이름(+ 영상이면 원본 몇 초인지)
export function shotLabel(shot: Shot, sec: number): string {
  switch (shot.type) {
    case 'video':
      return `${name(shot.src)} ${(shot.in + sec).toFixed(1)}초`;
    case 'photo':
      return name(shot.src);
    case 'collage':
      return shot.srcs.map(name).join(', ');
    case 'credits':
      return '크레딧';
    default:
      return '인트로/아웃트로 카드';
  }
}
