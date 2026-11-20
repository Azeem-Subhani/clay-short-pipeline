import React from 'react';
import {Composition} from 'remotion';
import {Short} from './Short';
import type {ShortProps} from './types';

const defaults: ShortProps = {
  fps: 24,
  width: 1080,
  height: 1920,
  durationInFrames: 48,
  shots: [],
  narration: null,
  cues: [],
  musicGain: [],
  captions: [],
  captionStyle: {
    enabled: true,
    fontFamily: 'Montserrat',
    fontWeight: 800,
    fontSizePx: 72,
    centerYFraction: 0.69,
    color: '#FFFFFF',
    activeColor: '#FFD84A',
    strokeColor: '#0B0B10',
    strokePx: 10,
    uppercase: false,
  },
  safeArea: {top: 0.08, bottom: 0.24, left: 0.05, right: 0.14},
  finish: {vignette: 0.22, grain: 0.035, fadeInFrames: 6, fadeOutFrames: 10},
  showSafeArea: false,
};

export const Root: React.FC = () => {
  return (
    <Composition
      id="Short"
      component={Short}
      defaultProps={defaults}
      durationInFrames={defaults.durationInFrames}
      fps={defaults.fps}
      width={defaults.width}
      height={defaults.height}
      calculateMetadata={({props}) => ({
        durationInFrames: props.durationInFrames,
        fps: props.fps,
        width: props.width,
        height: props.height,
      })}
    />
  );
};
