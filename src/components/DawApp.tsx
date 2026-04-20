"use client";

import {
  Boxes,
  Circle,
  Download,
  Eraser,
  FileAudio,
  FolderOpen,
  Home,
  Keyboard,
  ListChecks,
  ListMusic,
  Magnet,
  Mic,
  MousePointer2,
  Paintbrush,
  Pause,
  Pencil,
  Piano,
  Play,
  PlugZap,
  Plus,
  RotateCcw,
  RotateCw,
  Save,
  Scissors,
  Search,
  Settings2,
  SlidersVertical,
  Square,
  Trash2,
  Upload,
  AudioWaveform,
  HelpCircle,
  WandSparkles,
  ZoomIn,
  ZoomOut
} from "lucide-react";
import {
  ChangeEvent,
  CSSProperties,
  DragEvent,
  MouseEvent,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import {
  LocalProject,
  MixerControl,
  PianoNote,
  ProjectFile,
  ProjectSnapshot,
  RecipeItem,
  Track,
  WorkView
} from "@/lib/projectTypes";

const BEATS_PER_BAR = 4;
const TOTAL_BARS = 72;
const DEFAULT_BPM = 142;
const LANE_HEIGHT = 78;
const RULER_HEIGHT = 32;

type ChannelNode = {
  gain: GainNode;
  pan?: StereoPannerNode;
  analyser: AnalyserNode;
};

type ToolId = "select" | "draw" | "paint" | "slice" | "mute" | "erase";

const PROJECTS_API = "/api/projects";
const VOCALS_API = "/api/vocals";

type VocalProcessResponse = {
  track: Track;
  analysis: {
    segments?: number;
    averageCorrectionSemitones?: number;
    durationSeconds?: number;
    placements?: Array<{ segment: number; bar: number; beat: number; durationBeats: number }>;
  };
  warnings?: string[];
  error?: string;
};

const browserSections = [
  { name: "Current Project", items: ["Patterns", "Playlist clips", "Mixer states", "Automation clips", "Recipe checklist", "Project file"] },
  { name: "Packs", items: ["Drums", "Impacts", "Risers", "Vocal chops", "Noise sweeps", "Breaths", "Sirens", "Crowd", "Ear candy"] },
  { name: "Generators", items: ["Sampler", "Sub Synth", "Supersaw", "Square Lead", "Granular Bass", "Rave Generator", "Analog Bass"] },
  { name: "Effects", items: ["Low Cut EQ", "Compressor", "Delay", "Reverb", "Stereo Spread", "Sidechain", "Wave Shaper", "Transit Macro"] }
];

function makeStarterTrack(): Track {
  return {
    id: "audio-1",
    name: "Audio 1",
    kind: "audio",
    color: "#60c8f8",
    gain: 0.82,
    pan: 0,
    steps: [],
    instrument: "Sampler",
    clips: [],
    effects: [
      { id: "eq", name: "EQ Eight", active: false, amount: 0.35 },
      { id: "comp", name: "Compressor", active: false, amount: 0.35 }
    ]
  };
}

function makeBlankProjectSnapshot(): ProjectSnapshot {
  const tracks = [makeStarterTrack()];
  return {
    version: 3,
    bpm: DEFAULT_BPM,
    swing: 0,
    snap: "1/4",
    loopEnabled: false,
    loopStartBar: 0,
    loopEndBar: 16,
    tracks,
    controls: makeDefaultControls(tracks),
    notes: [],
    selectedTrackId: tracks[0].id,
    selectedClipId: "",
    activeView: "playlist",
    patternIndex: 1,
    arrangementMode: "song",
    recipe: []
  };
}

function normalizeSnapshot(raw?: Partial<ProjectSnapshot>): ProjectSnapshot {
  const base = makeBlankProjectSnapshot();
  const tracks = cloneTracks(raw?.tracks ?? base.tracks);
  const controls = cloneControls(raw?.controls ?? makeDefaultControls(tracks));
  return {
    ...base,
    ...raw,
    version: 3,
    tracks,
    controls,
    notes: cloneNotes(raw?.notes ?? base.notes),
    recipe: cloneRecipe(raw?.recipe ?? base.recipe),
    selectedTrackId: raw?.selectedTrackId ?? tracks[0]?.id ?? "",
    selectedClipId: raw?.selectedClipId ?? tracks.flatMap((track) => track.clips)[0]?.id ?? "",
    activeView: raw?.activeView ?? "playlist",
    patternIndex: raw?.patternIndex ?? 1,
    arrangementMode: raw?.arrangementMode ?? "song"
  };
}

function normalizeProjectFile(raw: Partial<ProjectFile> & Partial<ProjectSnapshot>, fallbackName: string, projectFile?: string): LocalProject {
  const now = new Date().toISOString();
  const rawSnapshot = raw.snapshot ?? raw;
  return {
    id: raw.id || makeId("project"),
    name: raw.name || fallbackName,
    createdAt: raw.createdAt || now,
    updatedAt: raw.updatedAt || now,
    projectFile,
    assets: raw.assets,
    snapshot: normalizeSnapshot(rawSnapshot)
  };
}

const tools: { id: ToolId; icon: ReactNode; label: string }[] = [
  { id: "select", icon: <MousePointer2 size={15} />, label: "Select" },
  { id: "draw", icon: <Pencil size={15} />, label: "Draw" },
  { id: "paint", icon: <Paintbrush size={15} />, label: "Paint" },
  { id: "slice", icon: <Scissors size={15} />, label: "Slice" },
  { id: "mute", icon: <Square size={15} />, label: "Mute" },
  { id: "erase", icon: <Eraser size={15} />, label: "Erase" }
];

const workViews: { id: WorkView; icon: ReactNode; label: string }[] = [
  { id: "playlist", icon: <ListMusic size={15} />, label: "Playlist" },
  { id: "piano", icon: <Piano size={15} />, label: "Piano" },
  { id: "mixer", icon: <SlidersVertical size={15} />, label: "Mixer" },
  { id: "plugins", icon: <PlugZap size={15} />, label: "Plugins" },
  { id: "sample", icon: <AudioWaveform size={15} />, label: "Sample" },
  { id: "recipe", icon: <ListChecks size={15} />, label: "Recipe" }
];

function cloneTracks(tracks: Track[]) {
  return tracks.map((track) => ({
    ...track,
    steps: [...track.steps],
    clips: track.clips.map((clip) => ({ ...clip })),
    effects: track.effects.map((effect) => ({ ...effect }))
  }));
}

function cloneControls(controls: Record<string, MixerControl>) {
  return Object.fromEntries(Object.entries(controls).map(([key, value]) => [key, { ...value }]));
}

function cloneNotes(notes: PianoNote[]) {
  return notes.map((note) => ({ ...note }));
}

function cloneRecipe(recipe: RecipeItem[]) {
  return recipe.map((item) => ({ ...item, trackIds: [...item.trackIds] }));
}

function makeDefaultControls(tracks: Track[]): Record<string, MixerControl> {
  return Object.fromEntries(
    tracks.map((track) => [
      track.id,
      { gain: track.gain, pan: track.pan, mute: false, solo: false, arm: false, sendA: 0.15, sendB: 0.08 }
    ])
  );
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function secondsToTime(seconds: number) {
  const whole = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(whole / 60);
  const secs = whole % 60;
  const tenths = Math.floor((seconds - whole) * 10);
  return `${minutes}:${String(secs).padStart(2, "0")}.${tenths}`;
}

function makeId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID().slice(0, 8)}`;
  }
  return `${prefix}-${Math.random().toString(16).slice(2, 10)}`;
}

function setupCanvas(canvas: HTMLCanvasElement, cssWidth: number, cssHeight: number) {
  const dpr = window.devicePixelRatio || 1;
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
  canvas.width = Math.max(1, Math.floor(cssWidth * dpr));
  canvas.height = Math.max(1, Math.floor(cssHeight * dpr));
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return ctx;
}

function writeString(view: DataView, offset: number, value: string) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}

function audioBufferToWav(buffer: AudioBuffer) {
  const channels = buffer.numberOfChannels;
  const length = buffer.length * channels * 2 + 44;
  const arrayBuffer = new ArrayBuffer(length);
  const view = new DataView(arrayBuffer);
  const samples = Array.from({ length: channels }, (_, index) => buffer.getChannelData(index));

  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + buffer.length * channels * 2, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, buffer.sampleRate, true);
  view.setUint32(28, buffer.sampleRate * channels * 2, true);
  view.setUint16(32, channels * 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, "data");
  view.setUint32(40, buffer.length * channels * 2, true);

  let offset = 44;
  for (let frame = 0; frame < buffer.length; frame += 1) {
    for (let channel = 0; channel < channels; channel += 1) {
      const value = clamp(samples[channel][frame], -1, 1);
      view.setInt16(offset, value < 0 ? value * 0x8000 : value * 0x7fff, true);
      offset += 2;
    }
  }
  return new Blob([arrayBuffer], { type: "audio/wav" });
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

export function DawApp() {
  const [tracks, setTracks] = useState<Track[]>(() => makeBlankProjectSnapshot().tracks);
  const [controls, setControls] = useState<Record<string, MixerControl>>(() => makeBlankProjectSnapshot().controls);
  const [notes, setNotes] = useState<PianoNote[]>([]);
  const [recipe, setRecipe] = useState<RecipeItem[]>([]);
  const [selectedTrackId, setSelectedTrackId] = useState("audio-1");
  const [selectedClipId, setSelectedClipId] = useState("");
  const [activeTool, setActiveTool] = useState<ToolId>("select");
  const [activeView, setActiveView] = useState<WorkView>("playlist");
  const [browserQuery, setBrowserQuery] = useState("");
  const [bpm, setBpm] = useState(DEFAULT_BPM);
  const [snap, setSnap] = useState("1/4");
  const [swing, setSwing] = useState(18);
  const [zoom, setZoom] = useState(54);
  const [loopEnabled, setLoopEnabled] = useState(true);
  const [loopStartBar, setLoopStartBar] = useState(16);
  const [loopEndBar, setLoopEndBar] = useState(32);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [status, setStatus] = useState("Ready");
  const [offset, setOffsetState] = useState(0);
  const [duration, setDuration] = useState(0);
  const [meterLevels, setMeterLevels] = useState<Record<string, number>>({});
  const [arrangementMode, setArrangementMode] = useState<"song" | "pattern">("song");
  const [patternIndex, setPatternIndex] = useState(1);
  const [screen, setScreen] = useState<"home" | "studio">("home");
  const [projects, setProjects] = useState<LocalProject[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("Untitled Project");
  const [isProjectHydrated, setIsProjectHydrated] = useState(false);
  const [leftPanelWidth, setLeftPanelWidth] = useState(300);
  const [rightPanelWidth, setRightPanelWidth] = useState(342);
  const [lowerPanelHeight, setLowerPanelHeight] = useState(260);
  const [leftTopPercent, setLeftTopPercent] = useState(42);
  const [showHelp, setShowHelp] = useState(false);
  const [showVocalLab, setShowVocalLab] = useState(false);
  const [vocalStartBar, setVocalStartBar] = useState(17);
  const [vocalKey, setVocalKey] = useState("e_minor");
  const [isVocalProcessing, setIsVocalProcessing] = useState(false);
  const [vocalDragActive, setVocalDragActive] = useState(false);
  const [lastVocalAnalysis, setLastVocalAnalysis] = useState<VocalProcessResponse["analysis"] | null>(null);

  const audioCtxRef = useRef<AudioContext | null>(null);
  const masterGainRef = useRef<GainNode | null>(null);
  const masterAnalyserRef = useRef<AnalyserNode | null>(null);
  const buffersRef = useRef<Map<string, AudioBuffer>>(new Map());
  const sourcesRef = useRef<Map<string, AudioBufferSourceNode>>(new Map());
  const channelNodesRef = useRef<Map<string, ChannelNode>>(new Map());
  const startTimeRef = useRef(0);
  const offsetRef = useRef(0);
  const playingRef = useRef(false);
  const rafRef = useRef<number | null>(null);
  const rulerRef = useRef<HTMLCanvasElement | null>(null);
  const timelineRef = useRef<HTMLDivElement | null>(null);
  const waveformRefs = useRef<Record<string, HTMLCanvasElement | null>>({});
  const pianoRef = useRef<HTMLCanvasElement | null>(null);
  const scopeRef = useRef<HTMLCanvasElement | null>(null);
  const sampleRef = useRef<HTMLCanvasElement | null>(null);
  const importAudioRef = useRef<HTMLInputElement | null>(null);
  const importProjectRef = useRef<HTMLInputElement | null>(null);
  const vocalUploadRef = useRef<HTMLInputElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const autoSaveStatusRef = useRef("");
  const undoStackRef = useRef<ProjectSnapshot[]>([]);
  const redoStackRef = useRef<ProjectSnapshot[]>([]);
  const lastHistorySnapshotRef = useRef("");
  const restoringSnapshotRef = useRef(false);

  const secondsPerBeat = 60 / bpm;
  const timelineWidth = TOTAL_BARS * zoom;
  const selectedTrack = tracks.find((track) => track.id === selectedTrackId) ?? tracks[0];
  const selectedClip = tracks.flatMap((track) => track.clips).find((clip) => clip.id === selectedClipId);
  const readoutSeconds = offset;
  const readoutBeat = readoutSeconds / secondsPerBeat;
  const readoutBar = Math.floor(readoutBeat / BEATS_PER_BAR) + 1;
  const readoutBeatInBar = Math.floor(readoutBeat % BEATS_PER_BAR) + 1;
  const cpuEstimate = isPlaying ? Math.min(42, 8 + tracks.length * 3 + Math.round(Object.values(meterLevels).reduce((a, b) => a + b, 0) / 80)) : 8;

  const visibleBrowserSections = useMemo(() => {
    const query = browserQuery.toLowerCase().trim();
    if (!query) return browserSections;
    return browserSections
      .map((section) => ({
        ...section,
        items: section.items.filter((item) => item.toLowerCase().includes(query) || section.name.toLowerCase().includes(query))
      }))
      .filter((section) => section.items.length > 0);
  }, [browserQuery]);

  const currentPosition = useCallback(() => {
    if (!playingRef.current || !audioCtxRef.current) return offsetRef.current;
    return Math.min(duration || Number.MAX_SAFE_INTEGER, offsetRef.current + audioCtxRef.current.currentTime - startTimeRef.current);
  }, [duration]);

  const ensureAudioContext = useCallback(() => {
    if (audioCtxRef.current) return audioCtxRef.current;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    const context = new AudioContextClass();
    const masterGain = context.createGain();
    const masterAnalyser = context.createAnalyser();
    masterGain.gain.value = 0.86;
    masterAnalyser.fftSize = 2048;
    masterAnalyser.smoothingTimeConstant = 0.78;
    masterGain.connect(masterAnalyser);
    masterAnalyser.connect(context.destination);
    audioCtxRef.current = context;
    masterGainRef.current = masterGain;
    masterAnalyserRef.current = masterAnalyser;
    return context;
  }, []);

  const effectiveGain = useCallback(
    (trackId: string) => {
      const control = controls[trackId];
      if (!control) return 0;
      const soloActive = Object.values(controls).some((item) => item.solo);
      if (control.mute) return 0;
      if (soloActive && !control.solo) return 0;
      return control.gain;
    },
    [controls]
  );

  const updateAudioControls = useCallback(() => {
    const context = audioCtxRef.current;
    if (!context) return;
    tracks.forEach((track) => {
      const nodes = channelNodesRef.current.get(track.id);
      const control = controls[track.id];
      if (!nodes || !control) return;
      nodes.gain.gain.setTargetAtTime(effectiveGain(track.id), context.currentTime, 0.018);
      nodes.pan?.pan.setTargetAtTime(control.pan, context.currentTime, 0.022);
    });
  }, [controls, effectiveGain, tracks]);

  const stopSourcesOnly = useCallback(() => {
    sourcesRef.current.forEach((source) => {
      try {
        source.onended = null;
        source.stop();
      } catch {
        return;
      }
    });
    sourcesRef.current.clear();
    channelNodesRef.current.clear();
  }, []);

  const setOffset = useCallback(
    (seconds: number) => {
      const next = clamp(seconds, 0, duration || Number.MAX_SAFE_INTEGER);
      offsetRef.current = next;
      setOffsetState(next);
    },
    [duration]
  );

  const stop = useCallback(() => {
    stopSourcesOnly();
    playingRef.current = false;
    setIsPlaying(false);
    setOffset(0);
  }, [setOffset, stopSourcesOnly]);

  const captureSnapshot = useCallback((): ProjectSnapshot => ({
    version: 3,
    bpm,
    swing,
    snap,
    loopEnabled,
    loopStartBar,
    loopEndBar,
    tracks: cloneTracks(tracks),
    controls: cloneControls(controls),
    notes: cloneNotes(notes),
    selectedTrackId,
    selectedClipId,
    activeView,
    patternIndex,
    arrangementMode,
    recipe: cloneRecipe(recipe)
  }), [
    activeView,
    arrangementMode,
    bpm,
    controls,
    loopEnabled,
    loopEndBar,
    loopStartBar,
    notes,
    patternIndex,
    recipe,
    selectedClipId,
    selectedTrackId,
    snap,
    swing,
    tracks
  ]);

  const restoreSnapshot = useCallback((snapshot: ProjectSnapshot) => {
    restoringSnapshotRef.current = true;
    stopSourcesOnly();
    setBpm(snapshot.bpm);
    setSwing(snapshot.swing);
    setSnap(snapshot.snap);
    setLoopEnabled(snapshot.loopEnabled);
    setLoopStartBar(snapshot.loopStartBar);
    setLoopEndBar(snapshot.loopEndBar);
    setTracks(cloneTracks(snapshot.tracks));
    setControls(cloneControls(snapshot.controls));
    setNotes(cloneNotes(snapshot.notes));
    setRecipe(cloneRecipe(snapshot.recipe ?? []));
    setSelectedTrackId(snapshot.selectedTrackId || snapshot.tracks[0]?.id || "audio-1");
    setSelectedClipId(snapshot.selectedClipId || snapshot.tracks.flatMap((track) => track.clips)[0]?.id || "");
    setActiveView(snapshot.activeView || "playlist");
    setPatternIndex(snapshot.patternIndex || 1);
    setArrangementMode(snapshot.arrangementMode || "song");
    setIsLoaded(false);
    setIsPlaying(false);
    setOffset(0);
    window.setTimeout(() => {
      restoringSnapshotRef.current = false;
    }, 0);
  }, [setOffset, stopSourcesOnly]);

  const undo = useCallback(() => {
    const previous = undoStackRef.current.pop();
    if (!previous) {
      setStatus("Nothing to undo");
      return;
    }
    const current = captureSnapshot();
    redoStackRef.current.push(current);
    restoreSnapshot(previous);
    lastHistorySnapshotRef.current = JSON.stringify(previous);
    setStatus("Undo");
  }, [captureSnapshot, restoreSnapshot]);

  const redo = useCallback(() => {
    const next = redoStackRef.current.pop();
    if (!next) {
      setStatus("Nothing to redo");
      return;
    }
    const current = captureSnapshot();
    undoStackRef.current.push(current);
    restoreSnapshot(next);
    lastHistorySnapshotRef.current = JSON.stringify(next);
    setStatus("Redo");
  }, [captureSnapshot, restoreSnapshot]);

  const persistProjects = useCallback((nextProjects: LocalProject[]) => {
    setProjects(nextProjects);
  }, []);

  const persistProjectToServer = useCallback(async (project: LocalProject) => {
    const response = await fetch(PROJECTS_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(project)
    });
    if (!response.ok) throw new Error("Could not save project");
    const body = await response.json() as { project: LocalProject };
    return body.project;
  }, []);

  const applyProject = useCallback((project: LocalProject) => {
    stopSourcesOnly();
    buffersRef.current.clear();
    sourcesRef.current.clear();
    channelNodesRef.current.clear();
    playingRef.current = false;
    offsetRef.current = 0;

    const snapshot = project.snapshot;
    setBpm(snapshot.bpm);
    setSwing(snapshot.swing);
    setSnap(snapshot.snap);
    setLoopEnabled(snapshot.loopEnabled);
    setLoopStartBar(snapshot.loopStartBar);
    setLoopEndBar(snapshot.loopEndBar);
    setTracks(cloneTracks(snapshot.tracks));
    setControls(cloneControls(snapshot.controls));
    setNotes(cloneNotes(snapshot.notes));
    setRecipe(cloneRecipe(snapshot.recipe ?? []));
    setSelectedTrackId(snapshot.selectedTrackId || snapshot.tracks[0]?.id || "drums");
    setSelectedClipId(snapshot.selectedClipId || snapshot.tracks.flatMap((track) => track.clips)[0]?.id || "");
    setActiveView(snapshot.activeView || "playlist");
    setPatternIndex(snapshot.patternIndex || 1);
    setArrangementMode(snapshot.arrangementMode || "song");
    setCurrentProjectId(project.id);
    setProjectName(project.name);
    setOffsetState(0);
    setDuration(0);
    setIsLoaded(false);
    setIsPlaying(false);
    undoStackRef.current = [];
    redoStackRef.current = [];
    lastHistorySnapshotRef.current = JSON.stringify(snapshot);
    setStatus(`Opened ${project.name}`);
    setScreen("studio");
  }, [stopSourcesOnly]);

  const saveCurrentProject = useCallback(() => {
    const now = new Date().toISOString();
    const name = projectName.trim() || "Untitled Project";
    const snapshot = captureSnapshot();
    const existing = projects.find((item) => item.id === currentProjectId);
    const projectId = currentProjectId ?? makeId("project");
    const project: LocalProject = {
      ...existing,
      id: projectId,
      name,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
      snapshot
    };
    const nextProjects = [
      project,
      ...projects.filter((item) => item.id !== project.id)
    ];
    persistProjects(nextProjects);
    setCurrentProjectId(project.id);
    setProjectName(name);
    setStatus(`Saved ${name}`);
    void persistProjectToServer(project).catch(() => setStatus("Save failed"));
  }, [captureSnapshot, currentProjectId, persistProjectToServer, persistProjects, projectName, projects]);

  const createNewProject = useCallback(() => {
    const now = new Date().toISOString();
    const project: LocalProject = {
      id: makeId("project"),
      name: `Untitled ${projects.length + 1}`,
      createdAt: now,
      updatedAt: now,
      snapshot: makeBlankProjectSnapshot()
    };
    persistProjects([project, ...projects]);
    void persistProjectToServer(project).catch(() => setStatus("Create failed"));
    applyProject(project);
  }, [applyProject, persistProjectToServer, persistProjects, projects]);

  const deleteProject = useCallback((projectId: string) => {
    const nextProjects = projects.filter((project) => project.id !== projectId);
    persistProjects(nextProjects);
    void fetch(PROJECTS_API, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: projectId })
    }).catch(() => setStatus("Delete failed"));
    if (currentProjectId === projectId) {
      stopSourcesOnly();
      setCurrentProjectId(null);
      setScreen("home");
      setStatus("Project deleted");
    }
  }, [currentProjectId, persistProjects, projects, stopSourcesOnly]);

  const goHome = useCallback(() => {
    stopSourcesOnly();
    playingRef.current = false;
    setIsPlaying(false);
    setScreen("home");
  }, [stopSourcesOnly]);

  useEffect(() => {
    if (typeof window === "undefined" || isProjectHydrated) return;
    const loadProjects = async () => {
      try {
        const response = await fetch(PROJECTS_API, { cache: "no-store" });
        if (!response.ok) throw new Error("Could not load projects");
        const body = await response.json() as { projects: LocalProject[] };
        setProjects(body.projects.map((project) => normalizeProjectFile(project, project.name)));
        setStatus("Projects loaded");
      } catch {
        setProjects([]);
        setStatus("Could not load projects");
      } finally {
        setIsProjectHydrated(true);
      }
    };
    void loadProjects();
  }, [isProjectHydrated]);

  useEffect(() => {
    if (typeof window === "undefined" || !isProjectHydrated || screen !== "studio" || !currentProjectId) return;
    const handle = window.setTimeout(() => {
      const now = new Date().toISOString();
      const name = projectName.trim() || "Untitled Project";
      const snapshot = captureSnapshot();
      setProjects((current) => {
        const existing = current.find((project) => project.id === currentProjectId);
        const nextProject: LocalProject = {
          ...existing,
          id: currentProjectId,
          name,
          createdAt: existing?.createdAt ?? now,
          updatedAt: now,
          snapshot
        };
        void persistProjectToServer(nextProject).catch(() => setStatus("Autosave failed"));
        const nextProjects = [
          nextProject,
          ...current.filter((project) => project.id !== currentProjectId)
        ];
        return nextProjects;
      });
      const nextStatus = `Autosaved ${name}`;
      if (autoSaveStatusRef.current !== nextStatus) {
        autoSaveStatusRef.current = nextStatus;
        setStatus(nextStatus);
      }
    }, 700);
    return () => window.clearTimeout(handle);
  }, [captureSnapshot, currentProjectId, isProjectHydrated, persistProjectToServer, projectName, screen]);

  useEffect(() => {
    if (typeof window === "undefined" || screen !== "studio" || restoringSnapshotRef.current) return;
    const handle = window.setTimeout(() => {
      const snapshot = captureSnapshot();
      const serialized = JSON.stringify(snapshot);
      if (!lastHistorySnapshotRef.current) {
        lastHistorySnapshotRef.current = serialized;
        return;
      }
      if (serialized === lastHistorySnapshotRef.current) return;
      undoStackRef.current = [
        ...undoStackRef.current.slice(-39),
        JSON.parse(lastHistorySnapshotRef.current) as ProjectSnapshot
      ];
      redoStackRef.current = [];
      lastHistorySnapshotRef.current = serialized;
    }, 350);
    return () => window.clearTimeout(handle);
  }, [captureSnapshot, screen]);

  const loadStems = useCallback(async () => {
    const context = ensureAudioContext();
    stopSourcesOnly();
    playingRef.current = false;
    setIsPlaying(false);
    setIsLoaded(false);
    setStatus("Loading stems");

    let maxDuration = 0;
    for (let index = 0; index < tracks.length; index += 1) {
      const track = tracks[index];
      if (buffersRef.current.has(track.id)) {
        maxDuration = Math.max(maxDuration, buffersRef.current.get(track.id)?.duration ?? 0);
        continue;
      }
      if (!track.file) continue;
      setStatus(`Loading ${index + 1}/${tracks.length}`);
      const response = await fetch(track.file, { cache: "no-store" });
      if (!response.ok) throw new Error(`Could not load ${track.name}`);
      const data = await response.arrayBuffer();
      const buffer = await context.decodeAudioData(data);
      buffersRef.current.set(track.id, buffer);
      maxDuration = Math.max(maxDuration, buffer.duration);
    }

    setDuration(maxDuration);
    setIsLoaded(true);
    setStatus("Ready");
  }, [ensureAudioContext, stopSourcesOnly, tracks]);

  const play = useCallback(async () => {
    const context = ensureAudioContext();
    if (!isLoaded) await loadStems();
    if (context.state === "suspended") await context.resume();
    if (playingRef.current) return;

    let startOffset = offsetRef.current;
    if (startOffset >= (duration || 0) - 0.02) {
      startOffset = loopEnabled ? loopStartBar * BEATS_PER_BAR * secondsPerBeat : 0;
      offsetRef.current = startOffset;
    }

    stopSourcesOnly();
    tracks.forEach((track) => {
      const buffer = buffersRef.current.get(track.id);
      const masterGain = masterGainRef.current;
      if (!buffer || !masterGain) return;

      const source = context.createBufferSource();
      const gain = context.createGain();
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.72;
      gain.gain.value = effectiveGain(track.id);
      source.buffer = buffer;

      let pan: StereoPannerNode | undefined;
      if (context.createStereoPanner) {
        pan = context.createStereoPanner();
        pan.pan.value = controls[track.id]?.pan ?? 0;
        source.connect(gain);
        gain.connect(pan);
        pan.connect(analyser);
      } else {
        source.connect(gain);
        gain.connect(analyser);
      }
      analyser.connect(masterGain);
      source.start(0, startOffset);
      source.onended = () => {
        const pos = currentPosition();
        if (!loopEnabled && pos >= (duration || 0) - 0.08) {
          stop();
        }
      };
      sourcesRef.current.set(track.id, source);
      channelNodesRef.current.set(track.id, { gain, pan, analyser });
    });

    startTimeRef.current = context.currentTime;
    playingRef.current = true;
    setIsPlaying(true);
    setStatus("Playing");
  }, [
    controls,
    currentPosition,
    duration,
    effectiveGain,
    ensureAudioContext,
    isLoaded,
    loadStems,
    loopEnabled,
    loopStartBar,
    secondsPerBeat,
    stop,
    stopSourcesOnly,
    tracks
  ]);

  const pause = useCallback(() => {
    if (!playingRef.current) return;
    setOffset(currentPosition());
    stopSourcesOnly();
    playingRef.current = false;
    setIsPlaying(false);
    setStatus("Paused");
  }, [currentPosition, setOffset, stopSourcesOnly]);

  const seek = useCallback(
    (seconds: number, resume = playingRef.current) => {
      stopSourcesOnly();
      playingRef.current = false;
      setIsPlaying(false);
      setOffset(seconds);
      if (resume) void play();
    },
    [play, setOffset, stopSourcesOnly]
  );

  useEffect(() => {
    updateAudioControls();
  }, [updateAudioControls]);

  const drawRuler = useCallback(() => {
    const canvas = rulerRef.current;
    if (!canvas) return;
    const ctx = setupCanvas(canvas, timelineWidth, RULER_HEIGHT);
    if (!ctx) return;
    ctx.clearRect(0, 0, timelineWidth, RULER_HEIGHT);
    ctx.fillStyle = "#1b1c1e";
    ctx.fillRect(0, 0, timelineWidth, RULER_HEIGHT);
    ctx.font = "11px system-ui, sans-serif";
    ctx.textBaseline = "middle";
    for (let bar = 0; bar <= TOTAL_BARS; bar += 1) {
      const x = Math.round(bar * zoom) + 0.5;
      const major = bar % 4 === 0;
      ctx.strokeStyle = major ? "#6d7076" : "#3a3d42";
      ctx.beginPath();
      ctx.moveTo(x, major ? 0 : 14);
      ctx.lineTo(x, RULER_HEIGHT);
      ctx.stroke();
      if (major && bar < TOTAL_BARS) {
        ctx.fillStyle = "#b8b0a5";
        ctx.fillText(String(bar + 1), x + 5, 14);
      }
    }
  }, [timelineWidth, zoom]);

  const drawWaveform = useCallback(
    (track: Track) => {
      const canvas = waveformRefs.current[track.id];
      if (!canvas) return;
      const ctx = setupCanvas(canvas, timelineWidth, LANE_HEIGHT);
      if (!ctx) return;
      ctx.clearRect(0, 0, timelineWidth, LANE_HEIGHT);
      ctx.fillStyle = "#191a1c";
      ctx.fillRect(0, 0, timelineWidth, LANE_HEIGHT);
      for (let bar = 0; bar <= TOTAL_BARS; bar += 1) {
        ctx.strokeStyle = bar % 4 === 0 ? "#35383d" : "#272a2f";
        ctx.beginPath();
        ctx.moveTo(bar * zoom + 0.5, 0);
        ctx.lineTo(bar * zoom + 0.5, LANE_HEIGHT);
        ctx.stroke();
      }

      const buffer = buffersRef.current.get(track.id);
      if (!buffer) return;
      const data = buffer.getChannelData(0);
      const samplesPerPixel = Math.max(1, Math.floor(data.length / timelineWidth));
      const mid = LANE_HEIGHT / 2;
      ctx.strokeStyle = track.color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = 0; x < timelineWidth; x += 1) {
        const start = x * samplesPerPixel;
        const end = Math.min(start + samplesPerPixel, data.length);
        let min = 1;
        let max = -1;
        const stride = Math.max(1, Math.floor(samplesPerPixel / 20));
        for (let index = start; index < end; index += stride) {
          const value = data[index] || 0;
          if (value < min) min = value;
          if (value > max) max = value;
        }
        ctx.moveTo(x + 0.5, mid + min * mid * 0.76);
        ctx.lineTo(x + 0.5, mid + max * mid * 0.76);
      }
      ctx.stroke();
    },
    [timelineWidth, zoom]
  );

  const drawPiano = useCallback(() => {
    const canvas = pianoRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(520, rect.width || 520);
    const height = Math.max(252, rect.height || 252);
    const ctx = setupCanvas(canvas, width, height);
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#171819";
    ctx.fillRect(0, 0, width, height);

    const left = 48;
    const top = 12;
    const rowHeight = 10;
    const highNote = 91;
    const lowNote = 54;
    const rows = highNote - lowNote + 1;
    const beatWidth = (width - left - 12) / 32;
    ctx.font = "10px system-ui, sans-serif";
    ctx.textBaseline = "middle";
    for (let row = 0; row < rows; row += 1) {
      const note = highNote - row;
      const y = top + row * rowHeight;
      const sharp = [1, 3, 6, 8, 10].includes(note % 12);
      ctx.fillStyle = sharp ? "#202225" : "#191b1e";
      ctx.fillRect(left, y, width - left, rowHeight);
      if (note % 12 === 0) {
        ctx.fillStyle = "#a9a39a";
        ctx.fillText(`C${Math.floor(note / 12) - 1}`, 8, y + rowHeight / 2);
      }
    }
    for (let beat = 0; beat <= 32; beat += 1) {
      const x = left + beat * beatWidth;
      ctx.strokeStyle = beat % 4 === 0 ? "#42454a" : "#2b2d30";
      ctx.beginPath();
      ctx.moveTo(x + 0.5, top);
      ctx.lineTo(x + 0.5, top + rows * rowHeight);
      ctx.stroke();
    }
    notes.forEach((note) => {
      const y = top + (highNote - note.note) * rowHeight;
      if (y < top || y > top + rows * rowHeight) return;
      const x = left + note.beat * beatWidth;
      const w = Math.max(8, note.duration * beatWidth - 2);
      ctx.fillStyle = note.color;
      ctx.strokeStyle = "#c6efff";
      ctx.beginPath();
      ctx.roundRect(x, y + 1, w, rowHeight - 2, 4);
      ctx.fill();
      ctx.stroke();
    });
  }, [notes]);

  const drawScope = useCallback(() => {
    const canvas = scopeRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(240, rect.width || 240);
    const height = Math.max(150, rect.height || 150);
    const ctx = setupCanvas(canvas, width, height);
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#171819";
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = "#2f3237";
    for (let y = 0; y < height; y += 24) {
      ctx.beginPath();
      ctx.moveTo(0, y + 0.5);
      ctx.lineTo(width, y + 0.5);
      ctx.stroke();
    }
    const analyser = masterAnalyserRef.current;
    if (!analyser || !playingRef.current) {
      ctx.strokeStyle = "#5a5d63";
      ctx.beginPath();
      ctx.moveTo(0, height / 2);
      ctx.lineTo(width, height / 2);
      ctx.stroke();
      return;
    }
    const data = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(data);
    ctx.strokeStyle = "#ffe083";
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let x = 0; x < width; x += 1) {
      const index = Math.floor((x / width) * data.length);
      const value = (data[index] - 128) / 128;
      const y = height / 2 + value * height * 0.42;
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }, []);

  const drawSample = useCallback(() => {
    const canvas = sampleRef.current;
    if (!canvas || !selectedTrack) return;
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(320, rect.width || 320);
    const height = Math.max(150, rect.height || 150);
    const ctx = setupCanvas(canvas, width, height);
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#171819";
    ctx.fillRect(0, 0, width, height);
    const buffer = buffersRef.current.get(selectedTrack.id);
    if (!buffer) {
      ctx.fillStyle = "#a9a39a";
      ctx.fillText("No sample loaded", 16, 28);
      return;
    }
    const data = buffer.getChannelData(0);
    const samplesPerPixel = Math.max(1, Math.floor(data.length / width));
    const mid = height / 2;
    ctx.strokeStyle = selectedTrack.color;
    ctx.beginPath();
    for (let x = 0; x < width; x += 1) {
      const start = x * samplesPerPixel;
      const end = Math.min(start + samplesPerPixel, data.length);
      let min = 1;
      let max = -1;
      for (let index = start; index < end; index += Math.max(1, Math.floor(samplesPerPixel / 18))) {
        const value = data[index] || 0;
        min = Math.min(min, value);
        max = Math.max(max, value);
      }
      ctx.moveTo(x + 0.5, mid + min * mid * 0.84);
      ctx.lineTo(x + 0.5, mid + max * mid * 0.84);
    }
    ctx.stroke();
  }, [selectedTrack]);

  useEffect(() => {
    drawRuler();
    tracks.forEach(drawWaveform);
  }, [drawRuler, drawWaveform, isLoaded, tracks, zoom]);

  useEffect(() => {
    drawPiano();
  }, [drawPiano, activeView]);

  useEffect(() => {
    drawSample();
  }, [drawSample, activeView, isLoaded]);

  useEffect(() => {
    const onResize = () => {
      drawPiano();
      drawScope();
      drawSample();
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [drawPiano, drawSample, drawScope]);

  useEffect(() => {
    const frame = () => {
      if (playingRef.current) {
        const position = currentPosition();
        const loopEndSeconds = loopEndBar * BEATS_PER_BAR * secondsPerBeat;
        if (loopEnabled && position >= loopEndSeconds) {
          seek(loopStartBar * BEATS_PER_BAR * secondsPerBeat, true);
        } else {
          setOffsetState(position);
        }
      }

      const levels: Record<string, number> = {};
      tracks.forEach((track) => {
        const node = channelNodesRef.current.get(track.id);
        if (!node) {
          levels[track.id] = 0;
          return;
        }
        const data = new Uint8Array(node.analyser.frequencyBinCount);
        node.analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (const value of data) {
          const centered = (value - 128) / 128;
          sum += centered * centered;
        }
        levels[track.id] = Math.min(100, Math.pow(Math.sqrt(sum / data.length) * 3.1, 0.72) * 100);
      });
      setMeterLevels(levels);
      drawScope();
      rafRef.current = requestAnimationFrame(frame);
    };
    rafRef.current = requestAnimationFrame(frame);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [currentPosition, drawScope, loopEnabled, loopEndBar, loopStartBar, secondsPerBeat, seek, tracks]);

  const updateTrack = (trackId: string, updater: (track: Track) => Track) => {
    setTracks((current) => current.map((track) => (track.id === trackId ? updater(track) : track)));
  };

  const updateControl = (trackId: string, patch: Partial<MixerControl>) => {
    setControls((current) => ({
      ...current,
      [trackId]: { ...current[trackId], ...patch }
    }));
  };

  const startResize = (
    event: MouseEvent<HTMLDivElement>,
    mode: "left" | "right" | "lower" | "left-split"
  ) => {
    event.preventDefault();
    const startX = event.clientX;
    const startY = event.clientY;
    const startLeft = leftPanelWidth;
    const startRight = rightPanelWidth;
    const startLower = lowerPanelHeight;
    const startTop = leftTopPercent;
    const parentHeight = event.currentTarget.parentElement?.getBoundingClientRect().height || 1;

    const onMove = (moveEvent: globalThis.MouseEvent) => {
      if (mode === "left") {
        setLeftPanelWidth(clamp(startLeft + moveEvent.clientX - startX, 220, 520));
      } else if (mode === "right") {
        setRightPanelWidth(clamp(startRight - (moveEvent.clientX - startX), 260, 560));
      } else if (mode === "lower") {
        setLowerPanelHeight(clamp(startLower - (moveEvent.clientY - startY), 160, 430));
      } else {
        setLeftTopPercent(clamp(startTop + ((moveEvent.clientY - startY) / parentHeight) * 100, 24, 72));
      }
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.body.style.cursor = mode === "lower" || mode === "left-split" ? "row-resize" : "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const handleTimelineClick = (event: MouseEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left + event.currentTarget.scrollLeft;
    const seconds = (x / timelineWidth) * (duration || TOTAL_BARS * BEATS_PER_BAR * secondsPerBeat);
    seek(seconds);
  };

  const handlePianoClick = (event: MouseEvent<HTMLCanvasElement>) => {
    if (activeTool === "erase") {
      setNotes((current) => current.slice(0, -1));
      return;
    }
    const canvas = event.currentTarget;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const left = 48;
    const top = 12;
    const beatWidth = (rect.width - left - 12) / 32;
    const rowHeight = 10;
    const highNote = 91;
    const beat = clamp(Math.round(((x - left) / beatWidth) * 4) / 4, 0, 31.75);
    const note = clamp(highNote - Math.floor((y - top) / rowHeight), 54, 91);
    setNotes((current) => [
      ...current,
      { id: makeId("note"), beat, duration: snap === "1/8" ? 0.5 : 0.75, note, velocity: 0.82, color: selectedTrack.color }
    ]);
  };

  const toggleStep = (trackId: string, step: number) => {
    updateTrack(trackId, (track) => ({
      ...track,
      steps: track.steps.includes(step) ? track.steps.filter((item) => item !== step) : [...track.steps, step].sort((a, b) => a - b)
    }));
  };

  const deleteSelection = useCallback(() => {
    if (selectedClipId) {
      setTracks((current) => current.map((track) => ({
        ...track,
        clips: track.clips.filter((clip) => clip.id !== selectedClipId)
      })));
      setSelectedClipId("");
      setStatus("Deleted clip");
      return;
    }

    if (activeView === "piano" && notes.length > 0) {
      setNotes((current) => current.slice(0, -1));
      setStatus("Deleted last note");
      return;
    }

    if (selectedTrackId && tracks.length > 1) {
      const deletingTrack = tracks.find((track) => track.id === selectedTrackId);
      setTracks((current) => current.filter((track) => track.id !== selectedTrackId));
      setControls((current) => {
        const next = { ...current };
        delete next[selectedTrackId];
        return next;
      });
      setSelectedTrackId(tracks.find((track) => track.id !== selectedTrackId)?.id ?? "");
      setSelectedClipId("");
      setStatus(`Deleted ${deletingTrack?.name ?? "track"}`);
      return;
    }

    setStatus("Nothing selected");
  }, [activeView, notes.length, selectedClipId, selectedTrackId, tracks]);

  const normalizeSelected = () => {
    const buffer = buffersRef.current.get(selectedTrack.id);
    if (!buffer) return;
    let peak = 0;
    for (let channel = 0; channel < buffer.numberOfChannels; channel += 1) {
      const data = buffer.getChannelData(channel);
      for (let index = 0; index < data.length; index += 1) peak = Math.max(peak, Math.abs(data[index]));
    }
    if (peak <= 0) return;
    const gain = 0.92 / peak;
    for (let channel = 0; channel < buffer.numberOfChannels; channel += 1) {
      const data = buffer.getChannelData(channel);
      for (let index = 0; index < data.length; index += 1) data[index] *= gain;
    }
    drawWaveform(selectedTrack);
    drawSample();
    setStatus(`Normalized ${selectedTrack.name}`);
  };

  const reverseSelected = () => {
    const buffer = buffersRef.current.get(selectedTrack.id);
    if (!buffer) return;
    for (let channel = 0; channel < buffer.numberOfChannels; channel += 1) {
      buffer.getChannelData(channel).reverse();
    }
    drawWaveform(selectedTrack);
    drawSample();
    setStatus(`Reversed ${selectedTrack.name}`);
  };

  const handleAudioImport = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const context = ensureAudioContext();
    const data = await file.arrayBuffer();
    const buffer = await context.decodeAudioData(data.slice(0));
    const id = makeId("sample");
    const color = "#9ef0c0";
    const importedTrack: Track = {
      id,
      name: file.name.replace(/\.[^.]+$/, "").slice(0, 22),
      kind: "audio",
      color,
      gain: 0.82,
      pan: 0,
      steps: [0, 8],
      instrument: "Imported Audio",
      clips: [{ id: `${id}-clip`, name: file.name, startBar: 0, bars: Math.ceil(buffer.duration / (secondsPerBeat * 4)), lane: id, color, type: "audio" }],
      effects: [
        { id: "eq", name: "EQ Eight", active: false, amount: 0.35 },
        { id: "comp", name: "Compressor", active: false, amount: 0.35 }
      ]
    };
    buffersRef.current.set(id, buffer);
    setTracks((current) => [...current, importedTrack]);
    setControls((current) => ({ ...current, [id]: { gain: 0.82, pan: 0, mute: false, solo: false, arm: false, sendA: 0, sendB: 0 } }));
    setSelectedTrackId(id);
    setDuration((current) => Math.max(current, buffer.duration));
    setIsLoaded(true);
    setStatus(`Imported ${file.name}`);
    event.target.value = "";
  };

  const addProcessedVocalTrack = useCallback((track: Track, analysis: VocalProcessResponse["analysis"]) => {
    stopSourcesOnly();
    setTracks((current) => [...current.filter((item) => item.id !== track.id), track]);
    setControls((current) => ({
      ...current,
      [track.id]: { gain: track.gain, pan: track.pan, mute: false, solo: false, arm: false, sendA: 0.26, sendB: 0.18 }
    }));
    setSelectedTrackId(track.id);
    setSelectedClipId(track.clips[0]?.id ?? "");
    setActiveView("playlist");
    setIsLoaded(false);
    setLastVocalAnalysis(analysis);
    const tuned = typeof analysis.averageCorrectionSemitones === "number" ? `, ${analysis.averageCorrectionSemitones.toFixed(2)} st avg tune` : "";
    setStatus(`Vocal tuned: ${analysis.segments ?? 1} segment${analysis.segments === 1 ? "" : "s"}${tuned}`);
  }, [stopSourcesOnly]);

  const processVocalFile = useCallback(async (file: File) => {
    setIsVocalProcessing(true);
    setStatus("Decoding vocal");
    try {
      const context = ensureAudioContext();
      const inputBuffer = await file.arrayBuffer();
      const decoded = await context.decodeAudioData(inputBuffer.slice(0));
      const wavBlob = audioBufferToWav(decoded);
      const form = new FormData();
      form.append("file", wavBlob, `${file.name.replace(/\.[^.]+$/, "") || "vocal"}.wav`);
      form.append("bpm", String(bpm));
      form.append("startBar", String(vocalStartBar));
      form.append("totalBars", String(TOTAL_BARS));
      form.append("key", vocalKey);
      setStatus("Auto-tuning vocal");
      const response = await fetch(VOCALS_API, { method: "POST", body: form });
      const body = await response.json() as VocalProcessResponse;
      if (!response.ok || !body.track) {
        throw new Error(body.error || "Vocal processing failed");
      }
      addProcessedVocalTrack(body.track, body.analysis);
      setShowVocalLab(false);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Vocal processing failed");
    } finally {
      setIsVocalProcessing(false);
      if (vocalUploadRef.current) vocalUploadRef.current.value = "";
    }
  }, [addProcessedVocalTrack, bpm, ensureAudioContext, vocalKey, vocalStartBar]);

  const handleVocalUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    await processVocalFile(file);
  };

  const handleVocalDrop = async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setVocalDragActive(false);
    const file = Array.from(event.dataTransfer.files).find((item) => item.type.startsWith("audio/"));
    if (file) await processVocalFile(file);
  };

  const downloadProjectFile = async () => {
    setStatus("Packing project file");
    const assets = await Promise.all(
      tracks
        .filter((track) => track.file)
        .map(async (track) => {
          try {
            const response = await fetch(track.file as string);
            if (!response.ok) throw new Error("asset fetch failed");
            const blob = await response.blob();
            return { trackId: track.id, file: track.file as string, data: await blobToDataUrl(blob) };
          } catch {
            return { trackId: track.id, file: track.file as string };
          }
        })
    );
    const project: ProjectFile = {
      format: "neon-studio-project",
      formatVersion: 1,
      portable: true,
      assetMode: "embedded",
      id: currentProjectId ?? makeId("project"),
      name: projectName,
      createdAt: projects.find((item) => item.id === currentProjectId)?.createdAt ?? new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      assets,
      snapshot: captureSnapshot()
    };
    const blob = new Blob([JSON.stringify(project, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${projectName.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-") || "neon-studio"}.neon.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus("Project file exported");
  };

  const loadProject = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const raw = JSON.parse(await file.text()) as Partial<ProjectFile> & Partial<ProjectSnapshot>;
    const now = new Date().toISOString();
    const importedProject = normalizeProjectFile(raw, file.name.replace(/\.[^.]+$/, "") || "Imported Project");
    importedProject.id = raw.id ? `${raw.id}-import-${now.slice(11, 19).replace(/:/g, "")}` : makeId("project");
    importedProject.createdAt = raw.createdAt ?? now;
    importedProject.updatedAt = now;

    if (raw.assets?.some((asset) => asset.data)) {
      const urlByTrack = new Map<string, string>();
      raw.assets.forEach((asset) => {
        if (!asset.data) return;
        const [meta, base64] = asset.data.split(",");
        const mime = /data:([^;]+)/.exec(meta)?.[1] ?? "audio/wav";
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
        urlByTrack.set(asset.trackId, URL.createObjectURL(new Blob([bytes], { type: mime })));
      });
      importedProject.snapshot.tracks = importedProject.snapshot.tracks.map((track) => (
        urlByTrack.has(track.id) ? { ...track, file: urlByTrack.get(track.id) } : track
      ));
    }

    const projectToStore: LocalProject = {
      ...importedProject,
      updatedAt: now,
    };
    persistProjects([projectToStore, ...projects.filter((project) => project.id !== projectToStore.id)]);
    void persistProjectToServer(projectToStore).catch(() => setStatus("Import save failed"));
    applyProject(projectToStore);
    setStatus(`Imported ${file.name}`);
    event.target.value = "";
  };

  const exportMixdown = async () => {
    await loadStems();
    const sampleRate = audioCtxRef.current?.sampleRate ?? 44100;
    const length = Math.ceil((duration || 126) * sampleRate);
    const offline = new OfflineAudioContext(2, length, sampleRate);
    const master = offline.createGain();
    master.gain.value = 0.86;
    master.connect(offline.destination);

    tracks.forEach((track) => {
      const buffer = buffersRef.current.get(track.id);
      if (!buffer) return;
      const source = offline.createBufferSource();
      const gain = offline.createGain();
      source.buffer = buffer;
      gain.gain.value = effectiveGain(track.id);
      source.connect(gain);
      if (offline.createStereoPanner) {
        const pan = offline.createStereoPanner();
        pan.pan.value = controls[track.id]?.pan ?? 0;
        gain.connect(pan);
        pan.connect(master);
      } else {
        gain.connect(master);
      }
      source.start(0);
    });

    setStatus("Rendering mixdown");
    const rendered = await offline.startRendering();
    const blob = audioBufferToWav(rendered);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${projectName.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-") || "neon-studio"}-mixdown.wav`;
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus("Mixdown exported");
  };

  const toggleRecording = async () => {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      setIsRecording(false);
      setStatus("Recording stopped");
      return;
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaStreamRef.current = stream;
    chunksRef.current = [];
    const recorder = new MediaRecorder(stream);
    mediaRecorderRef.current = recorder;
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = async () => {
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
      const context = ensureAudioContext();
      const buffer = await context.decodeAudioData(await blob.arrayBuffer());
      const id = makeId("recording");
      const color = "#f59fcb";
      buffersRef.current.set(id, buffer);
      const recordedTrack: Track = {
        id,
        name: "Recording",
        kind: "audio",
        color,
        gain: 0.9,
        pan: 0,
        steps: [0],
        instrument: "Audio Input",
        clips: [{ id: `${id}-clip`, name: "Mic take", startBar: Math.max(0, readoutBar - 1), bars: Math.ceil(buffer.duration / (secondsPerBeat * 4)), lane: id, color, type: "audio" }],
        effects: [
          { id: "eq", name: "EQ Eight", active: false, amount: 0.32 },
          { id: "gate", name: "Noise Gate", active: false, amount: 0.26 }
        ]
      };
      setTracks((current) => [...current, recordedTrack]);
      setControls((current) => ({ ...current, [id]: { gain: 0.9, pan: 0, mute: false, solo: false, arm: false, sendA: 0, sendB: 0 } }));
      setSelectedTrackId(id);
      setDuration((current) => Math.max(current, buffer.duration));
      setStatus("Recording captured");
    };
    recorder.start();
    setIsRecording(true);
    setStatus("Recording");
  };

  useEffect(() => {
    const isTypingTarget = (target: EventTarget | null) => {
      const element = target as HTMLElement | null;
      if (!element) return false;
      return ["INPUT", "TEXTAREA", "SELECT"].includes(element.tagName) || element.isContentEditable;
    };

    const onKeyDown = (event: KeyboardEvent) => {
      const command = event.metaKey || event.ctrlKey;
      const key = event.key.toLowerCase();

      if (command && key === "h") {
        event.preventDefault();
        setShowHelp((value) => !value);
        return;
      }
      if (command && key === "s") {
        event.preventDefault();
        saveCurrentProject();
        return;
      }
      if (command && key === "z") {
        event.preventDefault();
        if (event.shiftKey) redo();
        else undo();
        return;
      }
      if (command && key === "y") {
        event.preventDefault();
        redo();
        return;
      }
      if (event.key === "Escape") {
        setShowHelp(false);
        return;
      }
      if (isTypingTarget(event.target)) return;
      if (event.code === "Space") {
        event.preventDefault();
        if (isPlaying) pause();
        else void play();
        return;
      }
      if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        deleteSelection();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [deleteSelection, isPlaying, pause, play, redo, saveCurrentProject, undo]);

  const activeStep = Math.floor(((readoutSeconds / secondsPerBeat) * 4) % 16);
  const playheadX = duration ? (readoutSeconds / duration) * timelineWidth : 0;

  if (screen === "home") {
    return (
      <div className="min-h-dvh bg-shell text-paper">
        <input ref={importProjectRef} type="file" accept="application/json,.json,.neon" className="hidden" onChange={loadProject} />
        <ProjectHome
          projects={projects}
          currentProjectId={currentProjectId}
          isHydrated={isProjectHydrated}
          onOpen={applyProject}
          onCreate={createNewProject}
          onImport={() => importProjectRef.current?.click()}
          onDelete={deleteProject}
          onSaveCurrent={saveCurrentProject}
        />
        {showHelp && <KeyboardHelpModal onClose={() => setShowHelp(false)} />}
      </div>
    );
  }

  return (
    <div className="grid h-dvh grid-rows-[auto_minmax(0,1fr)] overflow-hidden bg-shell text-paper">
      <input ref={importAudioRef} type="file" accept="audio/*" className="hidden" onChange={handleAudioImport} />
      <input ref={importProjectRef} type="file" accept="application/json,.json,.neon" className="hidden" onChange={loadProject} />
      <input ref={vocalUploadRef} type="file" accept="audio/*" className="hidden" onChange={handleVocalUpload} />

      <header className="grid gap-3 border-b border-line bg-[#1b1c1e] px-3 py-3 lg:px-4 xl:grid-cols-[minmax(220px,0.8fr)_minmax(280px,1.1fr)_auto] xl:items-center 2xl:grid-cols-[minmax(220px,0.8fr)_minmax(280px,1.1fr)_auto_auto]">
        <div className="flex min-w-0 items-center justify-between gap-3 min-[1536px]:justify-start">
          <div className="flex min-w-0 items-center gap-3">
            <span className="h-9 w-9 shrink-0 rounded-lg border border-[#5a5d63] bg-[linear-gradient(135deg,#ff8d5c_0_34%,transparent_34%),linear-gradient(45deg,#45d18e_0_48%,transparent_48%),linear-gradient(315deg,#60c8f8_0_52%,#303236_52%)]" />
            <div className="min-w-0">
              <div className="truncate text-lg font-black">Neon Studio</div>
              <input
                className="mt-0.5 w-full min-w-0 bg-transparent text-xs font-semibold text-muted outline-none focus:text-paper"
                value={projectName}
                onChange={(event) => setProjectName(event.target.value)}
                aria-label="Project name"
              />
            </div>
          </div>
          <button className="grid h-10 w-10 place-items-center rounded-lg border border-line bg-panel3 text-muted hover:text-paper min-[1536px]:hidden" onClick={goHome} title="Projects" aria-label="Projects">
            <Home size={17} />
          </button>
        </div>

        <div className="studio-scrollbar flex min-w-0 items-center gap-2 overflow-x-auto pb-1 xl:pb-0">
          <button className="hidden h-8 shrink-0 items-center gap-2 rounded-md border border-line bg-panel2 px-3 text-xs font-semibold text-muted hover:border-[#777b82] hover:text-paper min-[1536px]:flex" onClick={goHome}>
            <Home size={14} />
            Projects
          </button>
          <button className="flex h-8 shrink-0 items-center gap-2 rounded-md border border-line bg-panel2 px-3 text-xs font-semibold text-muted hover:border-[#777b82] hover:text-paper" onClick={saveCurrentProject}>
            <Save size={14} />
            Save
          </button>
          {["File", "Edit", "Add", "View", "Options"].map((item) => (
            <button key={item} className="h-8 shrink-0 rounded-md border border-line bg-panel2 px-3 text-xs font-semibold text-muted hover:border-[#777b82] hover:text-paper">
              {item}
            </button>
          ))}
          <div className="flex h-8 shrink-0 items-center gap-1 rounded-md border border-line bg-[#101112] px-2 text-xs text-muted">
            <Magnet size={14} className={snap !== "none" ? "text-lead" : ""} />
            <select className="bg-transparent text-paper" value={snap} onChange={(event) => setSnap(event.target.value)}>
              <option value="none">None</option>
              <option value="1/2">1/2</option>
              <option value="1/4">1/4</option>
              <option value="1/8">1/8</option>
              <option value="1/16">1/16</option>
            </select>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 xl:justify-end">
          <div className="flex items-center gap-1 rounded-xl border border-line bg-[#101112] p-1">
          <IconButton label="Undo (Cmd+Z)" onClick={undo}><RotateCcw size={17} /></IconButton>
          <IconButton label="Redo (Shift+Cmd+Z)" onClick={redo}><RotateCw size={17} /></IconButton>
          <IconButton label={isPlaying ? "Pause" : "Play"} active={isPlaying} primary onClick={() => (isPlaying ? pause() : void play())}>
            {isPlaying ? <Pause size={18} /> : <Play size={18} fill="currentColor" />}
          </IconButton>
          <IconButton label="Stop" onClick={stop}><Square size={16} fill="currentColor" /></IconButton>
          <IconButton label="Record" active={isRecording} onClick={() => void toggleRecording()}><Circle size={17} fill={isRecording ? "currentColor" : "none"} /></IconButton>
          <IconButton label="Export mixdown" onClick={() => void exportMixdown()}><Download size={17} /></IconButton>
          <IconButton label="Help (Cmd+H)" onClick={() => setShowHelp(true)}><HelpCircle size={17} /></IconButton>
          </div>
        </div>

        <div className="grid grid-cols-5 gap-2 max-sm:grid-cols-2 xl:col-span-3 2xl:col-span-1">
          <Readout label="BPM">
            <input className="w-12 bg-transparent text-right font-bold text-paper" type="number" min={60} max={220} value={bpm} onChange={(event) => setBpm(Number(event.target.value) || DEFAULT_BPM)} />
          </Readout>
          <Readout label="BAR">{String(readoutBar).padStart(3, "0")}.{readoutBeatInBar}</Readout>
          <Readout label="TIME">{secondsToTime(readoutSeconds)}</Readout>
          <Readout label="CPU">{cpuEstimate}%</Readout>
          <Readout label="MODE">
            <button className="font-bold uppercase" onClick={() => setArrangementMode((value) => (value === "song" ? "pattern" : "song"))}>
              {arrangementMode}
            </button>
          </Readout>
        </div>
      </header>

      <main
        className="studio-shell-main grid min-h-0 overflow-hidden"
        style={{
          "--left-panel-width": `${leftPanelWidth}px`,
          "--right-panel-width": `${rightPanelWidth}px`,
          "--lower-panel-height": `${lowerPanelHeight}px`
        } as CSSProperties}
      >
        <aside
          className="studio-desktop-pane relative min-h-0 border-r border-line bg-panel"
          style={{ gridTemplateRows: `${leftTopPercent}% 8px minmax(0,1fr)` }}
        >
          <Panel title="Browser" right={<button className="rounded-md border border-line bg-panel3 p-1.5" onClick={() => importAudioRef.current?.click()} title="Import audio"><Upload size={15} /></button>}>
            <div className="flex h-full min-h-0 flex-col gap-2 p-2">
              <div className="flex h-9 items-center gap-2 rounded-md border border-line bg-[#151617] px-2">
                <Search size={15} className="text-muted" />
                <input className="min-w-0 flex-1 bg-transparent text-sm outline-none" value={browserQuery} onChange={(event) => setBrowserQuery(event.target.value)} placeholder="Search" />
              </div>
              <div className="studio-scrollbar min-h-0 flex-1 overflow-auto">
                {visibleBrowserSections.map((section) => (
                  <div key={section.name} className="mb-3">
                    <div className="mb-1 flex items-center gap-2 px-1 text-xs font-bold text-muted">
                      <FolderOpen size={14} />
                      {section.name}
                    </div>
                    {section.items.map((item) => (
                      <button key={item} className="mb-1 flex h-8 w-full items-center gap-2 rounded-md px-2 text-left text-xs text-muted hover:bg-panel3 hover:text-paper">
                        <FileAudio size={13} />
                        <span className="truncate">{item}</span>
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </Panel>

          <div
            className="resize-handle-y border-y border-line bg-[#151617]"
            onMouseDown={(event) => startResize(event, "left-split")}
            role="separator"
            aria-orientation="horizontal"
            title="Resize browser and channel rack"
          />

          <Panel title="Channel Rack" right={<span className="text-xs text-muted">P{patternIndex.toString().padStart(2, "0")}</span>}>
            <div className="grid h-full min-h-0 grid-rows-[42px_28px_minmax(0,1fr)]">
              <div className="flex items-center gap-2 border-b border-line px-2">
                <button className="rounded-md border border-line bg-panel3 px-2 py-1 text-xs" onClick={() => setPatternIndex((value) => Math.max(1, value - 1))}>-</button>
                <div className="flex-1 rounded-md border border-line bg-[#151617] px-2 py-1 text-center text-xs font-bold">Pattern {patternIndex}</div>
                <button className="rounded-md border border-line bg-panel3 px-2 py-1 text-xs" onClick={() => setPatternIndex((value) => value + 1)}>+</button>
                <label className="flex items-center gap-2 text-xs text-muted">
                  Swing
                  <input className="w-20 accent-lead" type="range" min={0} max={75} value={swing} onChange={(event) => setSwing(Number(event.target.value))} />
                </label>
              </div>
              <div className="grid grid-cols-[78px_repeat(16,minmax(10px,1fr))] gap-1 border-b border-line px-2 text-[10px] text-muted">
                <span />
                {Array.from({ length: 16 }, (_, index) => <span key={index} className="self-center text-center">{index + 1}</span>)}
              </div>
              <div className="studio-scrollbar min-h-0 overflow-auto py-2">
                {tracks.map((track) => (
                  <div key={track.id} className="grid min-h-10 grid-cols-[78px_repeat(16,minmax(10px,1fr))] items-center gap-1 px-2">
                    <button className="truncate text-left text-xs text-muted hover:text-paper" onClick={() => setSelectedTrackId(track.id)}>{track.name}</button>
                    {Array.from({ length: 16 }, (_, step) => (
                      <button
                        key={step}
                        className={`aspect-square min-h-3 rounded border ${track.steps.includes(step) ? "border-current shadow-[inset_0_0_0_2px_rgba(255,255,255,0.18)]" : "border-[#4c4f54] bg-[#2a2c2f]"} ${activeStep === step && isPlaying ? "outline outline-2 outline-offset-1 outline-paper" : ""}`}
                        style={{ color: track.color, backgroundColor: track.steps.includes(step) ? `${track.color}55` : undefined }}
                        onClick={() => toggleStep(track.id, step)}
                        aria-label={`${track.name} step ${step + 1}`}
                        title={`${track.name} step ${step + 1}`}
                      />
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </Panel>
        </aside>

        <div
          className="resize-handle-x z-10 hidden border-r border-line bg-[#151617] xl:block"
          onMouseDown={(event) => startResize(event, "left")}
          role="separator"
          aria-orientation="vertical"
          title="Resize browser"
        />

        <section className={`studio-center-panel grid min-w-0 min-h-0 border-line bg-panel xl:border-r ${activeView === "recipe" ? "" : "has-lower"}`}>
          <div className="studio-scrollbar flex min-w-0 items-center justify-between gap-3 overflow-x-auto border-b border-line bg-panel2 px-3 py-2">
            <div className="flex shrink-0 items-center gap-1">
              {workViews.map((view) => (
                <button
                  key={view.id}
                  className={`flex h-8 items-center gap-2 rounded-md border px-2 text-xs font-bold ${activeView === view.id ? "border-lead bg-[#18303a] text-paper" : "border-line bg-panel3 text-muted hover:text-paper"}`}
                  onClick={() => setActiveView(view.id)}
                >
                  {view.icon}
                  {view.label}
                </button>
              ))}
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {tools.map((tool) => (
                <button
                  key={tool.id}
                  className={`grid h-8 w-8 place-items-center rounded-md border ${activeTool === tool.id ? "border-chords bg-[#41371b] text-chords" : "border-line bg-panel3 text-muted hover:text-paper"}`}
                  onClick={() => setActiveTool(tool.id)}
                  title={tool.label}
                  aria-label={tool.label}
                >
                  {tool.icon}
                </button>
              ))}
              <button className="grid h-8 w-8 place-items-center rounded-md border border-line bg-panel3 text-muted hover:text-paper" onClick={() => setZoom((value) => Math.max(32, value - 8))} title="Zoom out"><ZoomOut size={15} /></button>
              <button className="grid h-8 w-8 place-items-center rounded-md border border-line bg-panel3 text-muted hover:text-paper" onClick={() => setZoom((value) => Math.min(96, value + 8))} title="Zoom in"><ZoomIn size={15} /></button>
            </div>
          </div>

          <div className="min-h-0 overflow-hidden">
            {activeView === "playlist" && (
              <div className="grid h-full min-h-0 grid-cols-[116px_minmax(0,1fr)]">
                <div className="border-r border-line bg-[#191a1c] pt-8">
                  {tracks.map((track) => (
                    <button
                      key={track.id}
                      className={`flex w-full items-center justify-between border-b border-[#383b40] px-2 text-left text-xs ${selectedTrackId === track.id ? "bg-panel3 text-paper" : "text-muted"}`}
                      style={{ height: LANE_HEIGHT }}
                      onClick={() => setSelectedTrackId(track.id)}
                    >
                      <span className="truncate">{track.name}</span>
                      <span style={{ color: track.color }}>■</span>
                    </button>
                  ))}
                </div>
                <div ref={timelineRef} className="studio-scrollbar relative min-w-0 overflow-auto bg-[#171819]" onClick={handleTimelineClick}>
                  <canvas ref={rulerRef} className="block" />
                  <div className="relative" style={{ width: timelineWidth }}>
                    {tracks.map((track) => (
                      <div key={track.id} className="relative border-b border-[#383b40]" style={{ width: timelineWidth, height: LANE_HEIGHT }}>
                        {track.clips.map((clip) => (
                          <button
                            key={clip.id}
                            className={`absolute top-2 h-[60px] overflow-hidden rounded-md border px-2 text-left text-[11px] font-bold shadow-sm ${selectedClipId === clip.id ? "ring-2 ring-paper" : ""}`}
                            style={{
                              left: clip.startBar * zoom + 6,
                              width: Math.max(34, clip.bars * zoom - 12),
                              borderColor: clip.color,
                              backgroundColor: `${clip.color}42`,
                              color: "#fff"
                            }}
                            onClick={(event) => {
                              event.stopPropagation();
                              setSelectedClipId(clip.id);
                              setSelectedTrackId(track.id);
                            }}
                          >
                            <span className="block truncate">{clip.name}</span>
                          </button>
                        ))}
                        <canvas
                          ref={(element) => {
                            waveformRefs.current[track.id] = element;
                          }}
                          className="pointer-events-none absolute inset-0"
                        />
                      </div>
                    ))}
                    {loopEnabled && (
                      <div
                        className="pointer-events-none absolute top-0 h-full border-x-2 border-chords bg-chords/10"
                        style={{ left: loopStartBar * zoom, width: (loopEndBar - loopStartBar) * zoom }}
                      />
                    )}
                  </div>
                  <div className="pointer-events-none absolute top-0 h-full w-0.5 bg-paper shadow-glow" style={{ transform: `translateX(${playheadX}px)` }} />
                </div>
              </div>
            )}

            {activeView === "piano" && (
              <div className="grid h-full min-h-0 grid-rows-[44px_minmax(0,1fr)]">
                <div className="flex items-center gap-2 border-b border-line px-3 text-xs text-muted">
                  <Keyboard size={15} />
                  <span className="font-bold text-paper">{selectedTrack.name}</span>
                  <span>Velocity</span>
                  <input className="w-28 accent-lead" type="range" min={1} max={127} defaultValue={104} />
                  <span>Scale</span>
                  <select className="rounded border border-line bg-panel3 px-2 py-1 text-paper">
                    <option>E minor</option>
                    <option>G major</option>
                    <option>Chromatic</option>
                  </select>
                </div>
                <canvas ref={pianoRef} className="h-full w-full bg-[#171819]" onClick={handlePianoClick} />
              </div>
            )}

            {activeView === "mixer" && <MixerView tracks={tracks} controls={controls} levels={meterLevels} selectedTrackId={selectedTrackId} onSelect={setSelectedTrackId} onChange={updateControl} />}

            {activeView === "plugins" && (
              <PluginView
                track={selectedTrack}
                onToggle={(effectId) => updateTrack(selectedTrack.id, (track) => ({
                  ...track,
                  effects: track.effects.map((effect) => effect.id === effectId ? { ...effect, active: !effect.active } : effect)
                }))}
                onAmount={(effectId, amount) => updateTrack(selectedTrack.id, (track) => ({
                  ...track,
                  effects: track.effects.map((effect) => effect.id === effectId ? { ...effect, amount } : effect)
                }))}
              />
            )}

            {activeView === "sample" && (
              <div className="grid h-full min-h-0 grid-rows-[44px_minmax(0,1fr)_64px]">
                <div className="flex items-center gap-2 border-b border-line px-3 text-xs text-muted">
                  <AudioWaveform size={15} />
                  <span className="font-bold text-paper">{selectedTrack.name}</span>
                  <button className="rounded-md border border-line bg-panel3 px-2 py-1 hover:text-paper" onClick={normalizeSelected}>Normalize</button>
                  <button className="rounded-md border border-line bg-panel3 px-2 py-1 hover:text-paper" onClick={reverseSelected}>Reverse</button>
                  <button className="rounded-md border border-line bg-panel3 px-2 py-1 hover:text-paper" onClick={() => importAudioRef.current?.click()}>Import</button>
                </div>
                <canvas ref={sampleRef} className="h-full w-full bg-[#171819]" />
                <div className="grid grid-cols-4 gap-2 border-t border-line p-2 text-xs">
                  {["In", "Out", "Pitch", "Stretch"].map((label, index) => (
                    <label key={label} className="grid grid-cols-[54px_minmax(0,1fr)] items-center gap-2 rounded-md border border-line bg-[#151617] px-2">
                      <span className="text-muted">{label}</span>
                      <input className="w-full accent-lead" type="range" min={0} max={100} defaultValue={index < 2 ? (index === 0 ? 0 : 100) : 50} />
                    </label>
                  ))}
                </div>
              </div>
            )}

            {activeView === "recipe" && (
              <RecipeView
                recipe={recipe}
                tracks={tracks}
                onSelectTrack={(trackId) => {
                  setSelectedTrackId(trackId);
                  setActiveView("playlist");
                }}
              />
            )}
          </div>

          <div className={`min-h-0 border-t border-line max-lg:hidden ${activeView === "recipe" ? "hidden" : "grid grid-rows-[8px_minmax(0,1fr)]"}`}>
            <div
              className="resize-handle-y border-b border-line bg-[#151617]"
              onMouseDown={(event) => startResize(event, "lower")}
              role="separator"
              aria-orientation="horizontal"
              title="Resize lower editor"
            />
            <div className="grid min-h-0 grid-cols-[minmax(0,1fr)_330px]">
            <Panel title="Automation & Event Editor" right={<span className="text-xs text-muted">{selectedClip?.name ?? "No clip"}</span>}>
              <div className="grid h-full grid-cols-[170px_minmax(0,1fr)] max-md:grid-cols-1">
                <div className="border-r border-line p-2 text-xs text-muted">
                  {["Volume", "Pan", "Filter Cutoff", "Reverb Send", "Delay Send", "Sidechain Depth"].map((item, index) => (
                    <button key={item} className={`mb-1 flex h-8 w-full items-center justify-between rounded-md px-2 text-left hover:bg-panel3 ${index === 0 ? "bg-panel3 text-paper" : ""}`}>
                      <span>{item}</span>
                      <span>{index === 0 ? "●" : ""}</span>
                    </button>
                  ))}
                </div>
                <div className="checker relative overflow-hidden bg-[#171819]">
                  <svg className="h-full w-full" viewBox="0 0 800 220" preserveAspectRatio="none">
                    <polyline points="0,166 90,154 170,96 260,122 360,72 470,88 590,52 700,78 800,44" fill="none" stroke="#ffcd5a" strokeWidth="4" />
                    {[90, 170, 260, 360, 470, 590, 700].map((x) => <circle key={x} cx={x} cy={x === 90 ? 154 : x === 170 ? 96 : x === 260 ? 122 : x === 360 ? 72 : x === 470 ? 88 : x === 590 ? 52 : 78} r="8" fill="#ffcd5a" />)}
                  </svg>
                </div>
              </div>
            </Panel>

            <Panel title="Master Scope" right={<span className="text-xs text-muted">{status}</span>}>
              <canvas ref={scopeRef} className="h-full w-full bg-[#171819]" />
            </Panel>
            </div>
          </div>
        </section>

        <div
          className="resize-handle-x z-10 hidden border-r border-line bg-[#151617] xl:block"
          onMouseDown={(event) => startResize(event, "right")}
          role="separator"
          aria-orientation="vertical"
          title="Resize mixer and project panel"
        />

        <aside className="studio-desktop-pane min-h-0 grid-rows-[minmax(0,1fr)_262px] bg-panel">
          <MixerCompact tracks={tracks} controls={controls} levels={meterLevels} selectedTrackId={selectedTrackId} onSelect={setSelectedTrackId} onChange={updateControl} />
          <Panel title="Project" right={<Settings2 size={15} className="text-muted" />}>
            <div className="grid h-full grid-rows-[1fr_auto] gap-2 p-2 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <ActionTile icon={<Save size={17} />} label="Save" onClick={saveCurrentProject} />
                <ActionTile icon={<FolderOpen size={17} />} label="Projects" onClick={goHome} />
                <ActionTile icon={<Upload size={17} />} label="Import" onClick={() => importAudioRef.current?.click()} />
                <ActionTile icon={<Download size={17} />} label="Export" onClick={() => void exportMixdown()} />
                <ActionTile icon={<Mic size={17} />} label={isRecording ? "Stop Rec" : "Record"} onClick={() => void toggleRecording()} active={isRecording} />
                <ActionTile icon={<WandSparkles size={17} />} label="Vocal Lab" onClick={() => {
                  setVocalStartBar(readoutBar);
                  setShowVocalLab(true);
                }} active={isVocalProcessing} />
                <ActionTile icon={<Download size={17} />} label="Backup" onClick={() => void downloadProjectFile()} />
              </div>
              <div className="grid grid-cols-2 gap-2 rounded-md border border-line bg-[#151617] p-2 text-muted">
                <span>Status</span><span className="text-right text-paper">{status}</span>
                <span>Loop</span><button className="text-right text-paper" onClick={() => setLoopEnabled((value) => !value)}>{loopEnabled ? "On" : "Off"}</button>
                <span>Loop Bars</span>
                <span className="flex justify-end gap-1">
                  <input className="w-10 bg-panel3 text-right text-paper" type="number" min={1} max={TOTAL_BARS} value={loopStartBar + 1} onChange={(event) => setLoopStartBar(clamp(Number(event.target.value) - 1, 0, TOTAL_BARS - 1))} />
                  <input className="w-10 bg-panel3 text-right text-paper" type="number" min={1} max={TOTAL_BARS} value={loopEndBar} onChange={(event) => setLoopEndBar(clamp(Number(event.target.value), loopStartBar + 1, TOTAL_BARS))} />
                </span>
              </div>
            </div>
          </Panel>
        </aside>
      </main>

      {showVocalLab && (
        <VocalLabModal
          startBar={vocalStartBar}
          keyName={vocalKey}
          isProcessing={isVocalProcessing}
          dragActive={vocalDragActive}
          analysis={lastVocalAnalysis}
          onStartBarChange={setVocalStartBar}
          onKeyChange={setVocalKey}
          onClose={() => setShowVocalLab(false)}
          onPickFile={() => vocalUploadRef.current?.click()}
          onDrop={handleVocalDrop}
          onDragActive={setVocalDragActive}
        />
      )}
      {showHelp && <KeyboardHelpModal onClose={() => setShowHelp(false)} />}
    </div>
  );
}

function Panel({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="grid min-h-0 grid-rows-[38px_minmax(0,1fr)] border-b border-line">
      <div className="flex items-center justify-between border-b border-line bg-panel2 px-3 text-sm font-extrabold">
        <span>{title}</span>
        {right}
      </div>
      <div className="min-h-0">{children}</div>
    </section>
  );
}

function ProjectHome({
  projects,
  currentProjectId,
  isHydrated,
  onOpen,
  onCreate,
  onImport,
  onDelete,
  onSaveCurrent
}: {
  projects: LocalProject[];
  currentProjectId: string | null;
  isHydrated: boolean;
  onOpen: (project: LocalProject) => void;
  onCreate: () => void;
  onImport: () => void;
  onDelete: (projectId: string) => void;
  onSaveCurrent: () => void;
}) {
  return (
    <main className="min-h-dvh overflow-auto bg-[#141516] px-5 py-5 text-paper">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <header className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-line bg-[#1b1c1e] p-4">
          <div className="flex min-w-0 items-center gap-4">
            <span className="h-12 w-12 shrink-0 rounded-lg border border-[#5a5d63] bg-[linear-gradient(135deg,#ff8d5c_0_34%,transparent_34%),linear-gradient(45deg,#45d18e_0_48%,transparent_48%),linear-gradient(315deg,#60c8f8_0_52%,#303236_52%)]" />
            <div className="min-w-0">
              <h1 className="truncate text-2xl font-black">Neon Studio</h1>
              <p className="text-sm font-semibold text-muted">Local projects, stems, arrangements, and mix sessions.</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {currentProjectId && (
              <button className="flex h-10 items-center gap-2 rounded-md border border-line bg-panel3 px-3 text-sm font-bold text-muted hover:text-paper" onClick={onSaveCurrent}>
                <Save size={16} />
                Save Open Session
              </button>
            )}
            <button className="flex h-10 items-center gap-2 rounded-md border border-line bg-panel3 px-3 text-sm font-bold text-muted hover:text-paper" onClick={onImport}>
              <Upload size={16} />
              Import
            </button>
            <button className="flex h-10 items-center gap-2 rounded-md border border-chords bg-chords px-3 text-sm font-black text-[#24201a]" onClick={onCreate}>
              <Plus size={16} />
              New Project
            </button>
          </div>
        </header>

        <section>
          <div className="rounded-lg border border-line bg-panel p-4">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-black">Projects</h2>
                <p className="text-sm text-muted">{isHydrated ? `${projects.length} local project${projects.length === 1 ? "" : "s"}` : "Loading local projects"}</p>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {projects.map((project) => (
                <article key={project.id} className="group rounded-lg border border-line bg-[#18191b] p-3 transition hover:border-[#777b82]">
                  <button className="block w-full text-left" onClick={() => onOpen(project)}>
                    <div className="mb-3 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="truncate text-base font-black">{project.name}</h3>
                        <p className="text-xs font-semibold text-muted">{project.snapshot.bpm} BPM · {project.snapshot.tracks.length} tracks · {project.snapshot.recipe?.length ?? 0} recipe items</p>
                      </div>
                      <span className="rounded-md border border-line bg-panel3 px-2 py-1 text-[10px] font-black uppercase text-muted">{project.projectFile ? "File" : "Local"}</span>
                    </div>
                    <div className="mb-3 grid h-24 grid-cols-5 gap-1 overflow-hidden rounded-md border border-line bg-[#101112] p-2">
                      {project.snapshot.tracks.slice(0, 5).map((track) => (
                        <div key={track.id} className="relative rounded-sm bg-panel3">
                          <span className="absolute bottom-0 left-0 right-0 rounded-sm" style={{ height: `${24 + track.clips.length * 14}%`, maxHeight: "100%", backgroundColor: `${track.color}aa` }} />
                        </div>
                      ))}
                    </div>
                    <div className="flex items-center justify-between text-xs text-muted">
                      <span>Updated {new Date(project.updatedAt).toLocaleDateString()}</span>
                      <span className="font-bold text-lead">Open</span>
                    </div>
                  </button>
                  <div className="mt-3 flex justify-end border-t border-line pt-3">
                    <button className="grid h-8 w-8 place-items-center rounded-md border border-line bg-panel3 text-muted hover:border-[#ff5f71] hover:text-[#ff5f71]" onClick={() => onDelete(project.id)} title={`Delete ${project.name}`} aria-label={`Delete ${project.name}`}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

function IconButton({ label, children, onClick, primary = false, active = false }: { label: string; children: ReactNode; onClick?: () => void; primary?: boolean; active?: boolean }) {
  return (
    <button
      className={`grid h-10 w-10 place-items-center rounded-lg border text-sm transition ${primary ? "border-chords bg-chords text-[#24201a]" : active ? "border-lead bg-[#18303a] text-paper" : "border-line bg-panel3 text-muted hover:border-[#777b82] hover:text-paper"}`}
      onClick={onClick}
      title={label}
      aria-label={label}
    >
      {children}
    </button>
  );
}

function Readout({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid min-h-10 content-center rounded-lg border border-line bg-[#101112] px-2">
      <span className="text-[10px] font-black text-muted">{label}</span>
      <strong className="min-w-12 text-right font-mono text-sm leading-tight">{children}</strong>
    </div>
  );
}

function VocalLabModal({
  startBar,
  keyName,
  isProcessing,
  dragActive,
  analysis,
  onStartBarChange,
  onKeyChange,
  onClose,
  onPickFile,
  onDrop,
  onDragActive
}: {
  startBar: number;
  keyName: string;
  isProcessing: boolean;
  dragActive: boolean;
  analysis: VocalProcessResponse["analysis"] | null;
  onStartBarChange: (value: number) => void;
  onKeyChange: (value: string) => void;
  onClose: () => void;
  onPickFile: () => void;
  onDrop: (event: DragEvent<HTMLDivElement>) => void;
  onDragActive: (value: boolean) => void;
}) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-4" role="dialog" aria-modal="true" aria-label="Vocal Lab" onMouseDown={onClose}>
      <section className="w-full max-w-xl rounded-lg border border-line bg-panel shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-line bg-panel2 px-4 py-3">
          <div className="flex items-center gap-2 text-lg font-black">
            <WandSparkles size={18} className="text-[#f59fcb]" />
            Vocal Lab
          </div>
          <button className="rounded-md border border-line bg-panel3 px-3 py-1 text-sm font-bold text-muted hover:text-paper" onClick={onClose}>
            Esc
          </button>
        </div>
        <div className="grid gap-3 p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1 text-xs font-bold text-muted">
              Start Bar
              <input
                className="h-10 rounded-md border border-line bg-[#101112] px-3 text-paper"
                type="number"
                min={1}
                max={72}
                value={startBar}
                onChange={(event) => onStartBarChange(clamp(Number(event.target.value) || 1, 1, 72))}
              />
            </label>
            <label className="grid gap-1 text-xs font-bold text-muted">
              Key
              <select className="h-10 rounded-md border border-line bg-[#101112] px-3 text-paper" value={keyName} onChange={(event) => onKeyChange(event.target.value)}>
                <option value="e_minor">E minor / G major</option>
                <option value="g_major">G major</option>
                <option value="a_minor">A minor</option>
                <option value="c_major">C major</option>
                <option value="chromatic">Chromatic</option>
              </select>
            </label>
          </div>

          <div
            className={`grid min-h-44 place-items-center rounded-lg border border-dashed p-5 text-center transition ${dragActive ? "border-[#f59fcb] bg-[#3b1f31]" : "border-line bg-[#151617]"}`}
            onDragOver={(event) => {
              event.preventDefault();
              onDragActive(true);
            }}
            onDragLeave={() => onDragActive(false)}
            onDrop={onDrop}
          >
            <div className="grid gap-3 justify-items-center">
              <div className="grid h-14 w-14 place-items-center rounded-full border border-line bg-panel3 text-[#f59fcb]">
                <Mic size={24} />
              </div>
              <div>
                <div className="text-base font-black text-paper">{isProcessing ? "Processing vocal" : "Drop raw singing audio"}</div>
                <div className="mt-1 text-xs font-semibold text-muted">MP3, WAV, M4A, or browser-decodable audio</div>
              </div>
              <button
                className="flex h-10 items-center gap-2 rounded-md border border-[#f59fcb] bg-[#f59fcb] px-4 text-sm font-black text-[#241720] disabled:cursor-wait disabled:opacity-70"
                onClick={onPickFile}
                disabled={isProcessing}
              >
                <Upload size={15} />
                {isProcessing ? "Tuning" : "Choose File"}
              </button>
            </div>
          </div>

          {analysis && (
            <div className="grid grid-cols-3 gap-2 rounded-md border border-line bg-[#101112] p-3 text-xs">
              <div>
                <div className="font-black text-paper">{analysis.segments ?? 0}</div>
                <div className="text-muted">Segments</div>
              </div>
              <div>
                <div className="font-black text-paper">{analysis.averageCorrectionSemitones?.toFixed(2) ?? "0.00"} st</div>
                <div className="text-muted">Avg Tune</div>
              </div>
              <div>
                <div className="font-black text-paper">{analysis.durationSeconds?.toFixed(1) ?? "0.0"}s</div>
                <div className="text-muted">Stem</div>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function KeyboardHelpModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-4" role="dialog" aria-modal="true" aria-label="Keyboard help" onMouseDown={onClose}>
      <section className="w-full max-w-2xl rounded-lg border border-line bg-panel shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-line bg-panel2 px-4 py-3">
          <div className="flex items-center gap-2 text-lg font-black">
            <HelpCircle size={18} className="text-lead" />
            Help
          </div>
          <button className="rounded-md border border-line bg-panel3 px-3 py-1 text-sm font-bold text-muted hover:text-paper" onClick={onClose}>
            Esc
          </button>
        </div>
        <div className="grid gap-4 p-4 md:grid-cols-2">
          <ShortcutGroup title="Transport" items={[
            ["Space", "Play or pause"],
            ["Stop button", "Stop and return to start"],
            ["Record button", "Capture a mic take"],
            ["Export button", "Render a WAV mixdown"]
          ]} />
          <ShortcutGroup title="Editing" items={[
            ["Cmd+Z", "Undo"],
            ["Shift+Cmd+Z", "Redo"],
            ["Delete", "Delete selected clip, note, or track"],
            ["Cmd+S", "Save current project"]
          ]} />
          <ShortcutGroup title="Panels" items={[
            ["Drag splitters", "Resize browser, mixer, and lower editor"],
            ["Mouse wheel", "Scroll panels vertically"],
            ["Shift+wheel", "Scroll timelines horizontally"],
            ["Cmd+H", "Open or close this help menu"]
          ]} />
          <ShortcutGroup title="Persistence" items={[
            ["Autosave", "Edits save after a short pause"],
            ["Projects", "Open local project files from the home screen"],
            ["Backup", "Export a portable .neon.json project"],
            ["Import", "Load a shared .neon.json project"]
          ]} />
          <ShortcutGroup title="Vocal Lab" items={[
            ["Vocal Lab", "Tune and align raw singing audio"],
            ["Start Bar", "Rough placement for the first phrase"],
            ["Key", "Scale target for pitch correction"],
            ["Drop File", "Add the processed vocal as a track"]
          ]} />
        </div>
      </section>
    </div>
  );
}

function ShortcutGroup({ title, items }: { title: string; items: [string, string][] }) {
  return (
    <div className="rounded-lg border border-line bg-[#18191b] p-3">
      <h3 className="mb-2 text-sm font-black text-paper">{title}</h3>
      <div className="grid gap-2">
        {items.map(([key, label]) => (
          <div key={key} className="grid grid-cols-[112px_minmax(0,1fr)] items-center gap-3 text-sm">
            <kbd className="rounded-md border border-line bg-[#101112] px-2 py-1 text-center font-mono text-xs font-black text-chords">{key}</kbd>
            <span className="text-muted">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ActionTile({ icon, label, onClick, active = false }: { icon: ReactNode; label: string; onClick: () => void; active?: boolean }) {
  return (
    <button className={`flex h-10 items-center justify-center gap-2 rounded-md border px-2 font-bold ${active ? "border-[#f59fcb] bg-[#3b1f31] text-paper" : "border-line bg-panel3 text-muted hover:text-paper"}`} onClick={onClick}>
      {icon}
      {label}
    </button>
  );
}

function MixerCompact({
  tracks,
  controls,
  levels,
  selectedTrackId,
  onSelect,
  onChange
}: {
  tracks: Track[];
  controls: Record<string, MixerControl>;
  levels: Record<string, number>;
  selectedTrackId: string;
  onSelect: (id: string) => void;
  onChange: (id: string, patch: Partial<MixerControl>) => void;
}) {
  return (
    <section className="studio-scrollbar grid min-h-0 auto-cols-[70px] grid-flow-col overflow-x-auto border-b border-line bg-panel">
      {tracks.map((track) => {
        const control = controls[track.id];
        return (
          <div key={track.id} className={`grid min-w-[70px] grid-rows-[38px_104px_52px_1fr_40px] border-r border-line ${selectedTrackId === track.id ? "bg-[#242629]" : "bg-[#1d1e20]"}`}>
            <button className="truncate border-b border-line px-1 text-center text-[11px] font-black" style={{ borderTop: `3px solid ${track.color}` }} onClick={() => onSelect(track.id)}>{track.name}</button>
            <div className="mx-auto my-3 h-20 w-4 overflow-hidden rounded border border-[#565a60] bg-[#101112]">
              <div className="mt-auto w-full bg-gradient-to-t from-bass via-chords to-[#ff5f71]" style={{ height: `${levels[track.id] ?? 0}%`, transform: "translateY(calc(80px - 100%))" }} />
            </div>
            <div className="grid grid-cols-2 gap-1 px-1">
              <SmallToggle label="M" active={control?.mute} color={track.color} onClick={() => onChange(track.id, { mute: !control?.mute })} />
              <SmallToggle label="S" active={control?.solo} color={track.color} onClick={() => onChange(track.id, { solo: !control?.solo })} />
              <SmallToggle label="R" active={control?.arm} color={track.color} onClick={() => onChange(track.id, { arm: !control?.arm })} />
              <SmallToggle label="FX" active={track.effects.some((effect) => effect.active)} color={track.color} onClick={() => onSelect(track.id)} />
            </div>
            <div className="grid place-items-center">
              <input className="range-vertical accent-lead" type="range" min={0} max={1.4} step={0.01} value={control?.gain ?? track.gain} onChange={(event) => onChange(track.id, { gain: Number(event.target.value) })} />
            </div>
            <div className="grid grid-cols-[16px_minmax(0,1fr)_16px] items-center gap-1 px-1 text-[10px] text-muted">
              <span>L</span>
              <input className="w-full accent-chords" type="range" min={-1} max={1} step={0.01} value={control?.pan ?? 0} onChange={(event) => onChange(track.id, { pan: Number(event.target.value) })} />
              <span>R</span>
            </div>
          </div>
        );
      })}
    </section>
  );
}

function MixerView({
  tracks,
  controls,
  levels,
  selectedTrackId,
  onSelect,
  onChange
}: {
  tracks: Track[];
  controls: Record<string, MixerControl>;
  levels: Record<string, number>;
  selectedTrackId: string;
  onSelect: (id: string) => void;
  onChange: (id: string, patch: Partial<MixerControl>) => void;
}) {
  return (
    <div className="studio-scrollbar grid h-full min-h-0 grid-flow-col auto-cols-[112px] overflow-x-auto bg-[#171819]">
      {tracks.map((track) => {
        const control = controls[track.id];
        return (
          <div key={track.id} className={`grid grid-rows-[40px_108px_72px_1fr_58px] border-r border-line ${selectedTrackId === track.id ? "bg-panel2" : "bg-[#1d1e20]"}`}>
            <button className="truncate border-b border-line px-2 text-xs font-black" style={{ borderTop: `3px solid ${track.color}` }} onClick={() => onSelect(track.id)}>{track.name}</button>
            <div className="mx-auto my-3 h-20 w-6 overflow-hidden rounded border border-[#565a60] bg-[#101112]">
              <div className="mt-auto w-full bg-gradient-to-t from-bass via-chords to-[#ff5f71]" style={{ height: `${levels[track.id] ?? 0}%`, transform: "translateY(calc(80px - 100%))" }} />
            </div>
            <div className="grid grid-cols-3 gap-1 px-2">
              <SmallToggle label="M" active={control?.mute} color={track.color} onClick={() => onChange(track.id, { mute: !control?.mute })} />
              <SmallToggle label="S" active={control?.solo} color={track.color} onClick={() => onChange(track.id, { solo: !control?.solo })} />
              <SmallToggle label="R" active={control?.arm} color={track.color} onClick={() => onChange(track.id, { arm: !control?.arm })} />
              <SmallToggle label="A" active={(control?.sendA ?? 0) > 0.4} color={track.color} onClick={() => onChange(track.id, { sendA: control?.sendA ? 0 : 0.65 })} />
              <SmallToggle label="B" active={(control?.sendB ?? 0) > 0.4} color={track.color} onClick={() => onChange(track.id, { sendB: control?.sendB ? 0 : 0.55 })} />
              <SmallToggle label="FX" active={track.effects.some((effect) => effect.active)} color={track.color} onClick={() => onSelect(track.id)} />
            </div>
            <div className="grid place-items-center">
              <input className="range-vertical accent-lead" type="range" min={0} max={1.4} step={0.01} value={control?.gain ?? track.gain} onChange={(event) => onChange(track.id, { gain: Number(event.target.value) })} />
            </div>
            <div className="grid grid-cols-[18px_minmax(0,1fr)_18px] items-center gap-1 px-2 text-[10px] text-muted">
              <span>L</span>
              <input className="w-full accent-chords" type="range" min={-1} max={1} step={0.01} value={control?.pan ?? 0} onChange={(event) => onChange(track.id, { pan: Number(event.target.value) })} />
              <span>R</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SmallToggle({ label, active, color, onClick }: { label: string; active?: boolean; color: string; onClick: () => void }) {
  return (
    <button
      className="h-7 rounded border border-line bg-panel3 text-[10px] font-black text-muted"
      style={active ? { backgroundColor: color, color: "#141414", borderColor: color } : undefined}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function RecipeView({
  recipe,
  tracks,
  onSelectTrack
}: {
  recipe: RecipeItem[];
  tracks: Track[];
  onSelectTrack: (trackId: string) => void;
}) {
  const sections: RecipeItem["section"][] = ["Foundation", "Intro", "Verse", "Build", "Drop", "Mix", "Advanced"];
  const trackMap = new Map(tracks.map((track) => [track.id, track]));
  const implemented = recipe.filter((item) => item.status === "implemented").length;

  return (
    <div className="studio-scrollbar h-full min-h-0 overflow-auto bg-[#171819] p-4">
      <div className="mb-4 grid gap-3 lg:grid-cols-[1fr_auto] lg:items-end">
        <div>
          <div className="mb-2 flex items-center gap-2 text-lg font-black">
            <ListChecks size={18} className="text-lead" />
            Production Recipe Coverage
          </div>
          <p className="max-w-3xl text-sm font-semibold text-muted">
            Every production point from the walkthrough is mapped to an actual track, clip, effect slot, or automation area in this project file.
          </p>
        </div>
        <div className="rounded-lg border border-line bg-[#101112] px-4 py-3 text-right">
          <div className="text-2xl font-black text-paper">{recipe.length}/{recipe.length}</div>
          <div className="text-xs font-bold uppercase text-muted">{implemented} implemented · {recipe.length - implemented} mapped</div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {sections.map((section) => {
          const items = recipe.filter((item) => item.section === section);
          if (!items.length) return null;
          return (
            <section key={section} className="rounded-lg border border-line bg-panel p-3">
              <h3 className="mb-3 text-sm font-black uppercase text-paper">{section}</h3>
              <div className="grid gap-2">
                {items.map((item) => (
                  <article key={item.id} className="rounded-md border border-line bg-[#18191b] p-3">
                    <div className="mb-2 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-black text-paper">{item.label}</div>
                        <p className="mt-1 text-xs leading-5 text-muted">{item.detail}</p>
                      </div>
                      <span className={`shrink-0 rounded-md px-2 py-1 text-[10px] font-black uppercase ${item.status === "implemented" ? "bg-bass/20 text-bass" : "bg-chords/20 text-chords"}`}>
                        {item.status}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {item.trackIds.map((trackId) => {
                        const track = trackMap.get(trackId);
                        return (
                          <button
                            key={trackId}
                            className="rounded-md border border-line bg-panel3 px-2 py-1 text-xs font-bold text-muted hover:text-paper"
                            style={track ? { borderColor: `${track.color}88` } : undefined}
                            onClick={() => onSelectTrack(trackId)}
                          >
                            {track?.name ?? trackId}
                          </button>
                        );
                      })}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

function PluginView({
  track,
  onToggle,
  onAmount
}: {
  track: Track;
  onToggle: (effectId: string) => void;
  onAmount: (effectId: string, amount: number) => void;
}) {
  return (
    <div className="grid h-full min-h-0 grid-cols-[260px_minmax(0,1fr)] max-md:grid-cols-1">
      <div className="studio-scrollbar overflow-auto border-r border-line p-3">
        <div className="mb-3 rounded-md border border-line bg-[#151617] p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-black">
            <Boxes size={16} style={{ color: track.color }} />
            {track.instrument}
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs text-muted">
            {["Osc", "Filter", "Env", "LFO", "Voices", "Macros"].map((item) => (
              <button key={item} className="rounded-md border border-line bg-panel3 px-2 py-2 hover:text-paper">{item}</button>
            ))}
          </div>
        </div>
        <div className="space-y-2">
          {track.effects.map((effect) => (
            <div key={effect.id} className="rounded-md border border-line bg-[#151617] p-2">
              <div className="mb-2 flex items-center justify-between gap-2">
                <button className="flex items-center gap-2 text-xs font-black" onClick={() => onToggle(effect.id)}>
                  <span className={`h-2.5 w-2.5 rounded-full ${effect.active ? "bg-bass" : "bg-muted"}`} />
                  {effect.name}
                </button>
                <span className="text-[10px] text-muted">{Math.round(effect.amount * 100)}%</span>
              </div>
              <input className="w-full accent-lead" type="range" min={0} max={1} step={0.01} value={effect.amount} onChange={(event) => onAmount(effect.id, Number(event.target.value))} />
            </div>
          ))}
        </div>
      </div>
      <div className="grid min-h-0 grid-rows-[44px_minmax(0,1fr)]">
        <div className="flex items-center gap-2 border-b border-line px-3 text-xs text-muted">
          <PlugZap size={15} />
          <span className="font-bold text-paper">{track.name}</span>
          <span>Routing</span>
          <span className="rounded bg-panel3 px-2 py-1">Insert {track.id.toUpperCase()}</span>
        </div>
        <div className="grid grid-cols-2 gap-3 overflow-auto p-3 max-md:grid-cols-1">
          {["Frequency", "Resonance", "Attack", "Decay", "Sustain", "Release", "Width", "Drive"].map((label, index) => (
            <label key={label} className="rounded-md border border-line bg-[#151617] p-3 text-xs">
              <div className="mb-2 flex items-center justify-between">
                <span className="font-bold text-paper">{label}</span>
                <span className="text-muted">{index % 2 ? "42" : "68"}</span>
              </div>
              <input className="w-full accent-chords" type="range" min={0} max={100} defaultValue={index % 2 ? 42 : 68} />
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}

declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext;
  }
}
