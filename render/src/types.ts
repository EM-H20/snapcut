export type FormatId = 'reels' | 'youtube';
export type KenBurns = 'zoom-in' | 'pan-left' | 'zoom-out' | 'pan-right';
export type PhotoShotT = {type: 'photo'; src: string; start: number; end: number; kenBurns: KenBurns};
export type VideoShotT = {type: 'video'; src: string; start: number; end: number; in: number; out: number; liveAudio: boolean};
export type CollageShotT = {type: 'collage'; srcs: string[]; start: number; end: number; kenBurns: KenBurns};
export type ClipShotT = {type: 'clip'; src: string; start: number; end: number};
export type Shot = PhotoShotT | CollageShotT | VideoShotT | ClipShotT;
export type FormatPlan = {width: number; height: number; musicStart: number; musicEnd: number; shots: Shot[]; dropped: number};
export type Storyboard = {
  fps: number;
  title: string;
  ending: string;
  music: string;
  formats: Partial<Record<FormatId, FormatPlan>>;
  active?: FormatId;
};
