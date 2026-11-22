import '@fontsource/montserrat/800.css';
import '@fontsource/montserrat/900.css';
import React, {useEffect, useState} from 'react';
import {AbsoluteFill, continueRender, delayRender, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Caption, CaptionStyle} from './types';

// One short caption at a time, on one fixed line, centred on the FRAME (not on the safe area: the Shorts UI is not
// symmetric, and text centred between unequal margins looks pushed to the left). Long captions are scaled, never wrapped.
export const Captions: React.FC<{captions: Caption[]; style: CaptionStyle}> = ({captions, style}) => {
  const frame = useCurrentFrame();
  const {width} = useVideoConfig();
  const [handle] = useState(() => delayRender('fonts'));
  useEffect(() => {
    let done = false;
    const finish = () => {
      if (!done) {
        done = true;
        continueRender(handle);
      }
    };
    Promise.all([document.fonts.load(`${style.fontWeight} ${style.fontSizePx}px "${style.fontFamily}"`), document.fonts.ready]).then(finish, finish);
    const t = setTimeout(finish, 8000);
    return () => clearTimeout(t);
  }, [handle, style.fontFamily, style.fontSizePx, style.fontWeight]);

  const cap = captions.find((c) => frame >= c.from && frame < c.to);
  if (!cap) {
    return null;
  }
  const pop = style.pop ? interpolate(frame - cap.from, [0, 2], [0.9, 1], {extrapolateRight: 'clamp'}) : 1;
  const half = (style.maxWidthFraction * width) / 2;
  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          left: `${style.centerXFraction * 100}%`,
          top: `${style.centerYFraction * 100}%`,
          width: half * 2,
          marginLeft: -half,
          transform: `translateY(-50%) scale(${pop * cap.scale})`,
          transformOrigin: '50% 50%',
          textAlign: 'center',
          whiteSpace: 'nowrap',
          fontFamily: `"${style.fontFamily}", "Arial Black", Arial, sans-serif`,
          fontWeight: style.fontWeight,
          fontSize: style.fontSizePx,
          lineHeight: 1.1,
          letterSpacing: '-0.005em',
          textTransform: style.uppercase ? 'uppercase' : 'none',
          color: style.color,
          WebkitTextStroke: `${style.strokePx}px ${style.strokeColor}`,
          paintOrder: 'stroke fill',
          textShadow: style.shadow,
        }}
      >
        {style.highlight
          ? cap.words.map((w, i) => (
              <span key={i} style={{color: frame >= w.from && frame < w.to ? style.activeColor : style.color}}>
                {(i ? ' ' : '') + w.text}
              </span>
            ))
          : cap.text}
      </div>
    </AbsoluteFill>
  );
};
