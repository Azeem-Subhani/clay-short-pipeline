export type ShotClip = {id: string; src: string; from: number; frames: number; placeholder?: boolean};

export type Cue = {
  id: string;
  kind: 'sfx' | 'ambience' | 'music';
  src: string;
  from: number; // start frame on the film timeline
  frames: number; // how long it plays
  volume: number; // linear gain
  loop: boolean;
  fadeInFrames: number;
  fadeOutFrames: number;
};

export type CaptionWord = {text: string; from: number; to: number};
export type CaptionPage = {from: number; to: number; words: CaptionWord[]};

export type CaptionStyle = {
  enabled: boolean;
  fontFamily: string;
  fontWeight: number;
  fontSizePx: number;
  centerYFraction: number;
  color: string;
  activeColor: string;
  strokeColor: string;
  strokePx: number;
  uppercase: boolean;
};

export type ShortProps = {
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  shots: ShotClip[];
  narration: {src: string; volume: number} | null;
  cues: Cue[];
  musicGain: number[]; // per-frame multiplier on the music (ducking under the voice)
  captions: CaptionPage[];
  captionStyle: CaptionStyle;
  safeArea: {top: number; bottom: number; left: number; right: number};
  finish: {vignette: number; grain: number; fadeInFrames: number; fadeOutFrames: number};
  showSafeArea: boolean;
};
