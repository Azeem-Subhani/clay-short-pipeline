import React from 'react';
import {AbsoluteFill, Audio, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Captions} from './Captions';
import type {Cue, ShortProps} from './types';

const CueAudio: React.FC<{cue: Cue; musicGain: number[]}> = ({cue, musicGain}) => {
  const volume = (f: number) => {
    const fadeIn = cue.fadeInFrames > 0 ? interpolate(f, [0, cue.fadeInFrames], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}) : 1;
    const fadeOut =
      cue.fadeOutFrames > 0
        ? interpolate(f, [cue.frames - cue.fadeOutFrames, cue.frames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})
        : 1;
    const duck = cue.kind === 'music' ? (musicGain[Math.min(musicGain.length - 1, Math.max(0, cue.from + f))] ?? 1) : 1;
    return cue.volume * fadeIn * fadeOut * duck;
  };
  return (
    <Sequence from={cue.from} durationInFrames={Math.max(1, cue.frames)} layout="none">
      <Audio src={staticFile(cue.src)} volume={volume} loop={cue.loop} />
    </Sequence>
  );
};

const Finish: React.FC<{finish: ShortProps['finish']}> = ({finish}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const fadeIn = finish.fadeInFrames > 0 ? interpolate(frame, [0, finish.fadeInFrames], [1, 0], {extrapolateRight: 'clamp'}) : 0;
  const fadeOut =
    finish.fadeOutFrames > 0
      ? interpolate(frame, [durationInFrames - finish.fadeOutFrames, durationInFrames - 1], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})
      : 0;
  return (
    <>
      {finish.vignette > 0 ? (
        <AbsoluteFill
          style={{background: `radial-gradient(ellipse at 50% 46%, rgba(0,0,0,0) 52%, rgba(0,0,0,${finish.vignette}) 100%)`}}
        />
      ) : null}
      {finish.grain > 0 ? (
        <AbsoluteFill style={{opacity: finish.grain, mixBlendMode: 'overlay'}}>
          <svg width="100%" height="100%">
            <filter id="grain">
              <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed={frame % 97} />
              <feColorMatrix type="saturate" values="0" />
            </filter>
            <rect width="100%" height="100%" filter="url(#grain)" />
          </svg>
        </AbsoluteFill>
      ) : null}
      <AbsoluteFill style={{backgroundColor: 'black', opacity: Math.max(fadeIn, fadeOut)}} />
    </>
  );
};

export const Short: React.FC<ShortProps> = (props) => {
  const {shots, narration, cues, musicGain, captions, captionStyle, safeArea, finish, showSafeArea} = props;
  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      {shots.map((s) => (
        <Sequence key={s.id} from={s.from} durationInFrames={s.frames} name={s.id}>
          <OffthreadVideo src={staticFile(s.src)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
        </Sequence>
      ))}
      <Finish finish={finish} />
      {captionStyle.enabled ? <Captions pages={captions} style={captionStyle} safeArea={safeArea} /> : null}
      {showSafeArea ? (
        <AbsoluteFill>
          <div
            style={{
              position: 'absolute',
              top: `${safeArea.top * 100}%`,
              bottom: `${safeArea.bottom * 100}%`,
              left: `${safeArea.left * 100}%`,
              right: `${safeArea.right * 100}%`,
              border: '3px dashed rgba(255,216,74,0.9)',
            }}
          />
        </AbsoluteFill>
      ) : null}
      {narration ? <Audio src={staticFile(narration.src)} volume={narration.volume} /> : null}
      {cues.map((c) => (
        <CueAudio key={c.id} cue={c} musicGain={musicGain} />
      ))}
    </AbsoluteFill>
  );
};
