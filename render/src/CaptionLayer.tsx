import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {activeByPlace} from './caption';
import type {Caption, CaptionStyle} from './types';

// 스타일이 없는 예전 storyboard용 — 공용/자막/흰바.json과 같은 값
const FALLBACK: CaptionStyle = {
  font: '"Apple SD Gothic Neo", "Noto Sans KR", sans-serif',
  bar: {background: '#ffffff', color: '#111111', border: '3px solid #111111', radius: 14},
  name: {background: 'transparent', color: '#e5484d', radius: 0, separator: true},
  bubble: {background: '#ffffff', color: '#111111', border: '3px solid #111111', radius: 28},
  icon: null,
};

// 줄바꿈은 단어 단위(keep-all), 띄어쓰기 없는 긴 말(ㅋㅋㅋ…)은 아무 데서나 — 한 장 글자 수는 plan이 2줄 분량으로 자른다
const TEXT: React.CSSProperties = {wordBreak: 'keep-all', overflowWrap: 'anywhere', lineHeight: 1.3, fontWeight: 800};
const SHADOW = '0 6px 18px rgba(0,0,0,0.35)';

// 치수는 longform.py FORMATS의 chars와 짝: 자막바 글자 h/18(가로)·w/14(세로), 폭 86% / 말풍선 h/24·w/18, 폭 38%·70%
export const CaptionLayer: React.FC<{captions: Caption[]; style?: CaptionStyle; vertical: boolean}> = ({captions, style = FALLBACK, vertical}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const now = activeByPlace(captions, frame / fps);
  const barSize = vertical ? width / 14 : height / 18;
  const bubbleSize = vertical ? width / 18 : height / 24;
  return (
    <AbsoluteFill style={{fontFamily: style.font}}>
      <div style={{position: 'absolute', left: 0, right: 0, bottom: vertical ? height * 0.16 : height * 0.06,
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: barSize * 0.3}}>
        {now.bar.map((c, i) => <Bar key={i} c={c} s={style} size={barSize} inline={!vertical} />)}
      </div>
      {vertical ? (
        // 세로(쇼츠): 게임 화면 위 흐린 영역에 메신저처럼 한 줄로 쌓고 왼쪽·오른쪽으로 붙인다 (폭이 좁아 양옆 칸으로 나누면 겹친다)
        <div style={{position: 'absolute', top: height * 0.06, left: width * 0.04, right: width * 0.04,
          display: 'flex', flexDirection: 'column', gap: bubbleSize * 0.6}}>
          {[...now.left.map((c) => [c, 'left'] as const), ...now.right.map((c) => [c, 'right'] as const)]
            .sort((a, b) => a[0].start - b[0].start)
            .map(([c, side], i) => (
              <div key={i} style={{alignSelf: side === 'left' ? 'flex-start' : 'flex-end', maxWidth: '76%'}}>
                <Bubble c={c} s={style} size={bubbleSize} side={side} />
              </div>
            ))}
        </div>
      ) : (['left', 'right'] as const).map((side) => (
        // 가로: 자막바 위 양옆
        <div key={side} style={{position: 'absolute', [side]: width * 0.04, maxWidth: '38%', bottom: height * 0.28,
          display: 'flex', flexDirection: 'column', alignItems: side === 'left' ? 'flex-start' : 'flex-end', gap: bubbleSize * 0.6}}>
          {now[side].map((c, i) => <Bubble key={i} c={c} s={style} size={bubbleSize} side={side} />)}
        </div>
      ))}
    </AbsoluteFill>
  );
};

const NameTag: React.FC<{name: string; s: NonNullable<CaptionStyle['name']>; size: number}> = ({name, s, size}) => (
  <span style={{background: s.background, color: s.color, borderRadius: s.radius, whiteSpace: 'nowrap', flexShrink: 0, fontWeight: 900,
    padding: s.background === 'transparent' ? 0 : `${size * 0.08}px ${size * 0.45}px`}}>{name}</span>
);

const PlayIcon: React.FC<{size: number}> = ({size}) => (
  <span style={{display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
    width: size * 1.3, height: size * 0.95, background: '#ffffff', borderRadius: size * 0.25}}>
    <span style={{width: 0, height: 0, marginLeft: size * 0.08, borderTop: `${size * 0.22}px solid transparent`,
      borderBottom: `${size * 0.22}px solid transparent`, borderLeft: `${size * 0.36}px solid #ff0033`}} />
  </span>
);

// 자막바: 가로는 [아이콘][이름 │ ]자막 한 줄 배치, 세로(쇼츠)는 폭이 좁아 이름표를 위쪽 테두리에 걸친다
const Bar: React.FC<{c: Caption; s: CaptionStyle; size: number; inline: boolean}> = ({c, s, size, inline}) => {
  const name = c.name && s.name ? s.name : null;
  return (
    <div style={{position: 'relative', display: 'flex', alignItems: 'center', gap: size * 0.35, maxWidth: '86%', fontSize: size,
      background: s.bar.background, color: s.bar.color, border: s.bar.border, borderRadius: s.bar.radius,
      padding: `${size * 0.25}px ${size * 0.5}px`, marginTop: name && !inline ? size * 0.5 : 0, boxShadow: SHADOW}}>
      {s.icon === 'play' && <PlayIcon size={size} />}
      {name && inline && <NameTag name={c.name!} s={name} size={size} />}
      {name && inline && name.separator && <span style={{opacity: 0.45, flexShrink: 0}}>│</span>}
      {name && !inline && (
        <span style={{position: 'absolute', top: -size * 0.55, left: size * 0.4, fontSize: size * 0.72}}>
          <NameTag name={c.name!} s={name.background === 'transparent' ? {...name, background: s.bar.background} : name} size={size * 0.72} />
        </span>
      )}
      <span style={TEXT}>{c.text}</span>
    </div>
  );
};

// 말풍선: 이름은 윗줄 작게, 꼬리는 바깥 가장자리 쪽 아래
const Bubble: React.FC<{c: Caption; s: CaptionStyle; size: number; side: 'left' | 'right'}> = ({c, s, size, side}) => (
  <div style={{position: 'relative', fontSize: size, background: s.bubble.background, color: s.bubble.color,
    border: s.bubble.border, borderRadius: s.bubble.radius, padding: `${size * 0.35}px ${size * 0.6}px`, boxShadow: SHADOW}}>
    {c.name && s.name && (
      <div style={{fontSize: size * 0.72, fontWeight: 900, marginBottom: size * 0.1,
        color: s.name.background === 'transparent' ? s.name.color : s.name.background}}>{c.name}</div>
    )}
    <span style={TEXT}>{c.text}</span>
    <span style={{position: 'absolute', bottom: -size * 0.3, [side]: size * 0.8, width: size * 0.55, height: size * 0.55,
      background: s.bubble.background, borderRight: s.bubble.border, borderBottom: s.bubble.border, transform: 'rotate(45deg)'}} />
  </div>
);
