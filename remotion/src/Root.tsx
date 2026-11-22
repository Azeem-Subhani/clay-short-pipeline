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
    fontWeight: 900,
    fontSizePx: 84,
    centerXFraction: 0.5,
    centerYFraction: 0.705,
    maxWidthFraction: 0.72,
    color: '#FFFFFF',
    activeColor: '#FFD84A',
    strokeColor: '#111016',
    strokePx: 14,
    shadow: '0 6px 14px rgba(0,0,0,0.55)',
    pop: true,
    highlight: false,
    uppercase: false,
  },
  safeArea: {top: 0.08, bottom: 0.24, left: 0.05, right: 0.14},
  finish: {vignette: 0.16, grain: 0.02, fadeInFrames: 0, fadeOutFrames: 8},
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
