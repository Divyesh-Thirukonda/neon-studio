export type TrackKind = "audio" | "instrument" | "automation" | "send";

export type Clip = {
  id: string;
  name: string;
  startBar: number;
  bars: number;
  lane: string;
  color: string;
  type: "audio" | "pattern" | "automation";
};

export type EffectSlot = {
  id: string;
  name: string;
  active: boolean;
  amount: number;
};

export type Track = {
  id: string;
  name: string;
  kind: TrackKind;
  file?: string;
  color: string;
  gain: number;
  pan: number;
  steps: number[];
  clips: Clip[];
  instrument: string;
  effects: EffectSlot[];
};

export type MixerControl = {
  gain: number;
  pan: number;
  mute: boolean;
  solo: boolean;
  arm: boolean;
  sendA: number;
  sendB: number;
};

export type PianoNote = {
  id: string;
  beat: number;
  duration: number;
  note: number;
  velocity: number;
  color: string;
};

export type RecipeSection = "Foundation" | "Intro" | "Verse" | "Build" | "Drop" | "Mix" | "Advanced";

export type RecipeItem = {
  id: string;
  section: RecipeSection;
  label: string;
  detail: string;
  status: "implemented" | "mapped";
  trackIds: string[];
};

export type WorkView = "playlist" | "piano" | "mixer" | "plugins" | "sample" | "recipe";

export type ProjectSnapshot = {
  version: 3;
  bpm: number;
  swing: number;
  snap: string;
  loopEnabled: boolean;
  loopStartBar: number;
  loopEndBar: number;
  tracks: Track[];
  controls: Record<string, MixerControl>;
  notes: PianoNote[];
  selectedTrackId: string;
  selectedClipId: string;
  activeView: WorkView;
  patternIndex: number;
  arrangementMode: "song" | "pattern";
  recipe: RecipeItem[];
};

export type ProjectAsset = {
  trackId: string;
  file: string;
  data?: string;
};

export type LocalProject = {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  projectFile?: string;
  assets?: ProjectAsset[];
  description?: string;
  keyCenter?: string;
  snapshot: ProjectSnapshot;
};

export type ProjectFile = LocalProject & {
  format?: string;
  formatVersion?: number;
  portable?: boolean;
  assetMode?: "external" | "embedded";
  description?: string;
  keyCenter?: string;
  projectFile?: string;
  assets?: ProjectAsset[];
};
