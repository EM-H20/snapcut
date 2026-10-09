export type FormatId = 'reels' | 'youtube';
export type KenBurns = 'zoom-in' | 'pan-left' | 'zoom-out' | 'pan-right' | 'still';
export type PhotoShotT = {type: 'photo'; src: string; start: number; end: number; kenBurns: KenBurns; dissolve?: number; blur?: number};
export type VideoShotT = {type: 'video'; src: string; start: number; end: number; in: number; out: number; liveAudio: boolean; rotate?: 90 | -90 | 180; dissolve?: number; duck?: false; blur?: number};
export type CollageShotT = {type: 'collage'; srcs: string[]; start: number; end: number; kenBurns: KenBurns};
export type ClipShotT = {type: 'clip'; src: string; start: number; end: number; fadeOut?: number};
export type CreditsShotT = {type: 'credits'; src: string; in: number; out: number; lines: string[]; start: number; end: number; liveAudio: boolean};
export type Shot = PhotoShotT | CollageShotT | VideoShotT | ClipShotT | CreditsShotT;
export type FormatPlan = {width: number; height: number; musicStart: number; musicEnd: number; musicFadeEnd?: number; shots: Shot[]; dropped: number};
export type Storyboard = {
  fps: number;
  title: string;
  ending: string;
  music: string;
  font?: string;  // 크레딧 손글씨 폰트 (public dir 기준)
  formats: Partial<Record<FormatId, FormatPlan>>;
  active?: FormatId;
};

export type Place = 'bar' | 'left' | 'right';
export type Caption = {start: number; end: number; text: string; name?: string; place?: Place};
type Box = {background: string; color: string; border: string; radius: number};
export type CaptionStyle = {
  font: string;
  bar: Box;
  name: {background: string; color: string; radius: number; separator: boolean} | null;
  bubble: Box;
  icon: 'play' | null;
};
export type LongClip = {in: number; out: number; start: number; end: number; title: string};
export type LongPlan = {width: number; height: number; duration: number; clips: LongClip[]; captions: Caption[]};
export type ShortPlan = LongPlan & {title: string};
export type LongStoryboard = {mode: 'longform'; fps: number; src: string; formats: {longform?: LongPlan; shorts?: ShortPlan[]}; clip?: number; captionStyle?: CaptionStyle};
