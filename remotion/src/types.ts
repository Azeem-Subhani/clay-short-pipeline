export type TransitionType = 'cut' | 'whip' | 'dissolve' | 'dip' | 'flash' | 'wipe' | 'match';
export type Direction = 'left' | 'right' | 'up' | 'down';

// How a shot is entered from the previous one. The window is [boundary - before, boundary + after) in film frames; it is drawn over
// frames that already exist (the outgoing shot held on its last frame, the incoming shot held on its first), so timing never moves.
export type Transition = {type: TransitionType; boundary: number; before: number; after: number; dir: Direction; color: string};

export type BlurSpan = {from: number; to: number; dir: Direction; strength: number}; // global frames, strength = peak blur in px

export type ShotClip = {
  id: string;
  src: string;
  from: number;
  frames: number;
  placeholder?: boolean;
  transitionIn?: Transition | null; // entry from the previous shot
  transitionOut?: Transition | null; // the next shot's entry, drawn over this shot's tail
};

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
export type Caption = {from: number; to: number; text: string; scale: number; words: CaptionWord[]};

export type CaptionStyle = {
  enabled: boolean;
  fontFamily: string;
  fontWeight: number;
  fontSizePx: number;
  centerXFraction: number;
  centerYFraction: number;
  maxWidthFraction: number;
  color: string;
  activeColor: string;
  strokeColor: string;
  strokePx: number;
  shadow: string;
  pop: boolean;
  highlight: boolean;
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
  captions: Caption[];
  captionStyle: CaptionStyle;
  safeArea: {top: number; bottom: number; left: number; right: number};
  finish: {vignette: number; grain: number; fadeInFrames: number; fadeOutFrames: number};
  showSafeArea: boolean;
  blur_spans?: BlurSpan[];
};
