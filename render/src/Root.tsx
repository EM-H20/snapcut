import React from 'react';
import {Composition, staticFile, type CalculateMetadataFunction} from 'remotion';
import {Longform} from './Longform';
import {Main} from './Main';
import type {FormatId, LongStoryboard, Storyboard} from './types';

const FPS = 30;
const EMPTY: Storyboard = {fps: FPS, title: '', ending: '', music: '', formats: {}};
const EMPTY_LONG: LongStoryboard = {mode: 'longform', fps: FPS, src: '', formats: {}};

const loadStoryboard = async (): Promise<unknown> => {
  const res = await fetch(`${staticFile('storyboard.json')}?t=${Date.now()}`);
  if (!res.ok) throw new Error('storyboard.json이 없습니다. 먼저 `python -m pipeline plan <영상명>`을 실행하세요.');
  return res.json().catch(() => {
    throw new Error('storyboard.json을 읽을 수 없습니다 (JSON 형식 오류). plan을 다시 실행하세요.');
  });
};

const metadataFor = (id: FormatId): CalculateMetadataFunction<Storyboard> => async () => {
  const sb = (await loadStoryboard()) as Storyboard;
  const plan = sb.formats[id];
  if (!plan) throw new Error(`storyboard.json에 '${id}' 형식이 없습니다. selection.json의 formats를 확인하세요.`);
  return {
    durationInFrames: Math.max(1, Math.round((plan.musicEnd - plan.musicStart) * FPS)),
    width: plan.width,
    height: plan.height,
    fps: FPS,
    props: {...sb, active: id},
  };
};

const longformMetadata: CalculateMetadataFunction<LongStoryboard> = async () => {
  const sb = (await loadStoryboard()) as LongStoryboard;
  const plan = sb.mode === 'longform' ? sb.formats.longform : undefined;
  if (!plan) throw new Error("롱폼 storyboard가 아닙니다 — longform.json을 만든 뒤 plan을 다시 실행하세요.");
  return {durationInFrames: Math.max(1, Math.round(plan.duration * FPS)), width: plan.width, height: plan.height, fps: FPS, props: sb};
};

export const Root: React.FC = () => (
  <>
    <Composition id="reels" component={Main} width={1080} height={1920} fps={FPS} durationInFrames={1} defaultProps={EMPTY} calculateMetadata={metadataFor('reels')} />
    <Composition id="youtube" component={Main} width={1920} height={1080} fps={FPS} durationInFrames={1} defaultProps={EMPTY} calculateMetadata={metadataFor('youtube')} />
    <Composition id="longform" component={Longform} width={1920} height={1080} fps={FPS} durationInFrames={1} defaultProps={EMPTY_LONG} calculateMetadata={longformMetadata} />
  </>
);
