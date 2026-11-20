import '@fontsource/montserrat/700.css';
import '@fontsource/montserrat/800.css';
import React, {useEffect, useState} from 'react';
import {AbsoluteFill, continueRender, delayRender, interpolate, useCurrentFrame} from 'remotion';
import type {CaptionPage, CaptionStyle} from './types';

// One short page at a time, the spoken word lit. Sits inside the Shorts safe area (above the title and buttons).
export const Captions: React.FC<{
  pages: CaptionPage[];
  style: CaptionStyle;
  safeArea: {top: number; bottom: number; left: number; right: number};
}> = ({pages, style, safeArea}) => {
  const frame = useCurrentFrame();
  const [handle] = useState(() => delayRender('fonts'));
  useEffect(() => {
    let done = false;
    const finish = () => {
      if (!done) {
        done = true;
        continueRender(handle);
      }
    };
    Promise.all([
      document.fonts.load(`${style.fontWeight} ${style.fontSizePx}px "${style.fontFamily}"`),
      document.fonts.ready,
    ]).then(finish, finish);
    const t = setTimeout(finish, 8000);
    return () => clearTimeout(t);
  }, [handle, style.fontFamily, style.fontSizePx, style.fontWeight]);

  const page = pages.find((p) => frame >= p.from && frame < p.to);
  if (!page) {
    return null;
  }
  const pop = interpolate(frame - page.from, [0, 3], [0.94, 1], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          left: `${safeArea.left * 100}%`,
          right: `${safeArea.right * 100}%`,
          top: `${style.centerYFraction * 100}%`,
          transform: `translateY(-50%) scale(${pop})`,
          textAlign: 'center',
          fontFamily: `"${style.fontFamily}", "Arial Black", Arial, sans-serif`,
          fontWeight: style.fontWeight,
          fontSize: style.fontSizePx,
          lineHeight: 1.16,
          letterSpacing: '-0.01em',
          textTransform: style.uppercase ? 'uppercase' : 'none',
          color: style.color,
          WebkitTextStroke: `${style.strokePx}px ${style.strokeColor}`,
          paintOrder: 'stroke fill',
          textShadow: '0 6px 18px rgba(0,0,0,0.55)',
        }}
      >
        {page.words.map((w, i) => {
          const active = frame >= w.from && frame < w.to;
          const spoken = frame >= w.to;
          return (
            <span
              key={i}
              style={{
                display: 'inline-block',
                margin: '0 0.14em',
                color: active ? style.activeColor : style.color,
                opacity: active || spoken ? 1 : 0.92,
                transform: active ? 'scale(1.07)' : 'scale(1)',
              }}
            >
              {w.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
