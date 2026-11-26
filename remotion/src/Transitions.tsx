import React from 'react';
import {AbsoluteFill, Freeze, OffthreadVideo, Sequence, staticFile, useCurrentFrame} from 'remotion';
import type {BlurSpan, Direction, ShotClip, Transition} from './types';

// Shot-to-shot transitions, drawn over the boundary between two shots without moving it. Every value is a pure function of the film
// frame number, so a render is repeatable. The outgoing shot is held on its last frame and the incoming one on its first for the
// part of the window that falls outside the frames each shot really has (tools/assemble.py encodes the held tail into the shot file).
// Captions, the finish and the audio live above or beside this file and are never touched by it.

const DIRS: Record<Direction, [number, number]> = {left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1]};
const CSS_TO: Record<Direction, string> = {left: 'to left', right: 'to right', up: 'to top', down: 'to bottom'};

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const easeQuart = (p: number) => (p < 0.5 ? 8 * p * p * p * p : 1 - Math.pow(-2 * p + 2, 4) / 2); // sharp in, sharp out: the whip
const easeSine = (p: number) => -(Math.cos(Math.PI * p) - 1) / 2; // gentle: the dissolve
const easeCubic = (p: number) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);

/** Where the film frame f sits in the transition window (0..1, never exactly 0 or 1), or null outside it. */
export const windowProgress = (t: Transition, f: number): number | null => {
  const d = t.before + t.after;
  if (d <= 0) return null;
  const s = t.boundary - t.before;
  if (f < s || f >= s + d) return null;
  return (f - s + 1) / (d + 1);
};

export type LayerEffect = {transform: string; opacity: number; blurX: number; blurY: number; brightness: number; mask?: string};

const NEUTRAL: LayerEffect = {transform: '', opacity: 1, blurX: 0, blurY: 0, brightness: 1};

/** How one shot layer looks at film frame f because of one transition. `role` says whether this shot is leaving or arriving. */
export const effectFor = (t: Transition, f: number, role: 'in' | 'out', W: number, H: number): LayerEffect => {
  if (t.type === 'match') {
    const k = f - t.boundary;
    if (role === 'in' && k >= 0 && k < 2) return {...NEUTRAL, transform: `scale(${1 + 0.04 * (1 - k / 2)})`};
    return NEUTRAL;
  }
  const p = windowProgress(t, f);
  if (p === null) return NEUTRAL;
  const [dx, dy] = DIRS[t.dir];
  switch (t.type) {
    case 'whip': {
      const q = easeQuart(p);
      const env = Math.pow(Math.sin(Math.PI * p), 0.8);
      const S = dx !== 0 ? W : H;
      const off = role === 'out' ? q * S : (q - 1) * S;
      const stretch = 1 + 0.14 * env;
      const sx = dx !== 0 ? stretch : 1;
      const sy = dy !== 0 ? stretch : 1;
      const blur = 78 * env;
      return {
        transform: `translate(${dx * off}px, ${dy * off}px) scale(${sx}, ${sy})`,
        opacity: 1,
        blurX: dx !== 0 ? blur : blur * 0.05,
        blurY: dy !== 0 ? blur : blur * 0.05,
        brightness: 1,
      };
    }
    case 'dissolve': {
      const e = easeSine(p);
      return role === 'in' ? {...NEUTRAL, opacity: e} : NEUTRAL; // the arriving shot fades in over the leaving one: a true cross-fade
    }
    case 'dip': {
      return role === 'out' ? {...NEUTRAL, opacity: 1 - easeCubic(clamp01(2 * p))} : {...NEUTRAL, opacity: easeCubic(clamp01(2 * p - 1))};
    }
    case 'flash': {
      const w = Math.pow(1 - Math.abs(2 * p - 1), 0.6); // 1 at the swap, falling off either side
      const swapped = p >= 0.5;
      const bloom = 14 * w;
      return {
        ...NEUTRAL,
        opacity: role === 'in' ? (swapped ? 1 : 0) : 1,
        blurX: bloom,
        blurY: bloom,
        brightness: 1 + 0.5 * w,
      };
    }
    case 'wipe': {
      if (role === 'out') return NEUTRAL;
      const soft = 24;
      const t0 = easeSine(p) * (100 + soft) - soft;
      return {...NEUTRAL, mask: `linear-gradient(${CSS_TO[t.dir]}, #000 ${t0}%, transparent ${t0 + soft}%)`};
    }
    default:
      return NEUTRAL;
  }
};

const combine = (a: LayerEffect, b: LayerEffect): LayerEffect => ({
  transform: `${a.transform} ${b.transform}`.trim(),
  opacity: a.opacity * b.opacity,
  blurX: a.blurX + b.blurX,
  blurY: a.blurY + b.blurY,
  brightness: a.brightness * b.brightness,
  mask: a.mask ?? b.mask,
});

/** A directional Gaussian blur as an SVG filter: different sigma per axis is what makes it directional (a streak, not a haze). */
const BlurFilter: React.FC<{id: string; blurX: number; blurY: number}> = ({id, blurX, blurY}) => (
  <svg width={0} height={0} style={{position: 'absolute'}} aria-hidden>
    <filter id={id} x="-15%" y="-15%" width="130%" height="130%" colorInterpolationFilters="sRGB">
      <feGaussianBlur stdDeviation={`${blurX.toFixed(2)} ${blurY.toFixed(2)}`} />
    </filter>
  </svg>
);

const filterStyle = (id: string, e: {blurX: number; blurY: number; brightness: number}): string | undefined => {
  const parts: string[] = [];
  if (e.blurX > 0.4 || e.blurY > 0.4) parts.push(`url(#${id})`);
  if (Math.abs(e.brightness - 1) > 0.001) parts.push(`brightness(${e.brightness.toFixed(3)})`);
  return parts.length ? parts.join(' ') : undefined;
};

const videoStyle: React.CSSProperties = {position: 'absolute', left: 0, top: 0, width: '100%', height: '100%', objectFit: 'cover'};

/** One shot on the timeline, with the held head and tail the transitions need and the effects they apply to it. */
export const ShotLayer: React.FC<{shot: ShotClip; width: number; height: number}> = ({shot, width, height}) => {
  const local = useCurrentFrame();
  const pre = shot.transitionIn ? shot.transitionIn.before : 0;
  const post = shot.transitionOut ? shot.transitionOut.after : 0;
  const f = local + shot.from - pre; // film frame
  let e = NEUTRAL;
  if (shot.transitionIn) e = combine(e, effectFor(shot.transitionIn, f, 'in', width, height));
  if (shot.transitionOut) e = combine(e, effectFor(shot.transitionOut, f, 'out', width, height));
  const id = `blur_${shot.id}`;
  const filter = filterStyle(id, e);
  const style: React.CSSProperties = {
    transform: e.transform || undefined,
    opacity: e.opacity,
    filter,
    ...(e.mask ? {maskImage: e.mask, WebkitMaskImage: e.mask} : {}),
  };
  const src = staticFile(shot.src);
  return (
    <AbsoluteFill style={style}>
      {filter && filter.includes('url(') ? <BlurFilter id={id} blurX={e.blurX} blurY={e.blurY} /> : null}
      {pre > 0 ? (
        <Sequence from={0} durationInFrames={pre} layout="none">
          <Freeze frame={0}>
            <OffthreadVideo src={src} muted style={videoStyle} />
          </Freeze>
        </Sequence>
      ) : null}
      <Sequence from={pre} durationInFrames={shot.frames + post} layout="none">
        <OffthreadVideo src={src} muted style={videoStyle} />
      </Sequence>
    </AbsoluteFill>
  );
};

/** Behind the shots: the colour a dip passes through. */
export const TransitionBackdrop: React.FC<{transitions: Transition[]}> = ({transitions}) => {
  const f = useCurrentFrame();
  const t = transitions.find((x) => x.type === 'dip' && windowProgress(x, f) !== null);
  return t ? <AbsoluteFill style={{backgroundColor: t.color}} /> : null;
};

/** Above the shots, below the finish and captions: the white of a flash and the bright edge of a wipe. */
export const TransitionOverlays: React.FC<{transitions: Transition[]}> = ({transitions}) => {
  const f = useCurrentFrame();
  const out: React.ReactNode[] = [];
  transitions.forEach((t, i) => {
    const p = windowProgress(t, f);
    if (p === null) return;
    if (t.type === 'flash') {
      const w = Math.pow(1 - Math.abs(2 * p - 1), 0.6);
      out.push(<AbsoluteFill key={i} style={{backgroundColor: t.color, opacity: w}} />);
    } else if (t.type === 'wipe') {
      const soft = 24;
      const t0 = easeSine(p) * (100 + soft) - soft;
      const g = `linear-gradient(${CSS_TO[t.dir]}, transparent ${t0}%, rgba(255,244,214,0.85) ${t0 + soft * 0.42}%, transparent ${t0 + soft}%)`;
      out.push(<AbsoluteFill key={i} style={{backgroundImage: g, mixBlendMode: 'screen', opacity: Math.sin(Math.PI * p) * 0.9 + 0.1}} />);
    }
  });
  return <>{out}</>;
};

/** Motion blur for a fast camera move inside a shot: one directional blur over the whole picture while a span is active. */
export const blurAt = (spans: BlurSpan[], f: number): {dir: Direction; sigma: number} | null => {
  let best: {dir: Direction; sigma: number} | null = null;
  for (const s of spans) {
    if (f < s.from || f > s.to) continue;
    const sigma = s.strength * Math.sin((Math.PI * (f - s.from + 0.5)) / (s.to - s.from + 1));
    if (!best || sigma > best.sigma) best = {dir: s.dir, sigma};
  }
  return best;
};

export const MotionBlur: React.FC<{spans: BlurSpan[]; children: React.ReactNode}> = ({spans, children}) => {
  const f = useCurrentFrame();
  const b = blurAt(spans, f);
  const on = !!b && b.sigma >= 0.4;
  const horizontal = !!b && (b.dir === 'left' || b.dir === 'right');
  const sigma = b ? b.sigma : 0;
  // the same two slots every frame, so the shot videos below are never remounted when a blur starts or stops
  return (
    <AbsoluteFill style={on ? {filter: 'url(#span_blur)'} : undefined}>
      {on ? <BlurFilter id="span_blur" blurX={horizontal ? sigma : sigma * 0.05} blurY={horizontal ? sigma * 0.05 : sigma} /> : <svg width={0} height={0} />}
      {children}
    </AbsoluteFill>
  );
};
