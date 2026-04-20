import { mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { basename, join } from "node:path";
import { LocalProject, ProjectFile, ProjectSnapshot } from "@/lib/projectTypes";

const ROOT = process.cwd();
const DATA_ROOT = join(ROOT, "data");
const DATA_DIR = join(DATA_ROOT, "projects");
const DELETED_PATH = join(DATA_ROOT, "deleted-projects.json");
const FACTORY_INDEX = join(ROOT, "public", "projects", "index.json");
const PUBLIC_DIR = join(ROOT, "public");
const SAFE_ID = /^[a-zA-Z0-9][a-zA-Z0-9_-]*$/;

type ProjectIndex = {
  projects?: Array<{ id: string; file: string }>;
};

function cloneProject(project: LocalProject): LocalProject {
  return JSON.parse(JSON.stringify(project)) as LocalProject;
}

function safeProjectId(id: string) {
  const clean = basename(id).replace(/\.neon\.json$/i, "");
  if (!SAFE_ID.test(clean)) throw new Error("Invalid project id");
  return clean;
}

function projectPath(id: string) {
  return join(DATA_DIR, `${safeProjectId(id)}.neon.json`);
}

function makeStarterTrack() {
  return {
    id: "audio-1",
    name: "Audio 1",
    kind: "audio" as const,
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

function makeDefaultControls(tracks: ProjectSnapshot["tracks"]) {
  return Object.fromEntries(
    tracks.map((track) => [
      track.id,
      { gain: track.gain, pan: track.pan, mute: false, solo: false, arm: false, sendA: 0.15, sendB: 0.08 }
    ])
  );
}

function blankSnapshot(): ProjectSnapshot {
  const tracks = [makeStarterTrack()];
  return {
    version: 3,
    bpm: 142,
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

function normalizeProject(raw: Partial<ProjectFile> & Partial<ProjectSnapshot>, fallbackName: string, projectFile?: string): LocalProject {
  const now = new Date().toISOString();
  const base = blankSnapshot();
  const rawSnapshot = raw.snapshot ?? raw;
  const tracks = rawSnapshot.tracks ?? base.tracks;
  const snapshot: ProjectSnapshot = {
    ...base,
    ...rawSnapshot,
    version: 3,
    tracks,
    controls: rawSnapshot.controls ?? makeDefaultControls(tracks),
    notes: rawSnapshot.notes ?? [],
    recipe: rawSnapshot.recipe ?? [],
    selectedTrackId: rawSnapshot.selectedTrackId ?? tracks[0]?.id ?? "",
    selectedClipId: rawSnapshot.selectedClipId ?? tracks.flatMap((track) => track.clips)[0]?.id ?? "",
    activeView: rawSnapshot.activeView ?? "playlist",
    patternIndex: rawSnapshot.patternIndex ?? 1,
    arrangementMode: rawSnapshot.arrangementMode ?? "song"
  };
  return {
    id: raw.id || `project-${Date.now()}`,
    name: raw.name || fallbackName,
    createdAt: raw.createdAt || now,
    updatedAt: raw.updatedAt || now,
    projectFile,
    assets: raw.assets,
    description: raw.description,
    keyCenter: raw.keyCenter,
    snapshot
  };
}

async function readJsonFile<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as T;
  } catch {
    return null;
  }
}

async function readFactoryProjects() {
  const index = await readJsonFile<ProjectIndex>(FACTORY_INDEX);
  const entries = index?.projects ?? [];
  const projects = await Promise.all(entries.map(async (entry) => {
    const publicPath = entry.file.replace(/^\/+/, "");
    const raw = await readJsonFile<ProjectFile>(join(PUBLIC_DIR, publicPath.replace(/^projects\//, "projects/")));
    if (!raw) return null;
    return normalizeProject(raw, raw.name || entry.id, entry.file);
  }));
  return projects.filter(Boolean) as LocalProject[];
}

async function readStoredProjects() {
  await mkdir(DATA_DIR, { recursive: true });
  const files = await readdir(DATA_DIR);
  const projects = await Promise.all(files.filter((file) => file.endsWith(".neon.json")).map(async (file) => {
    const raw = await readJsonFile<ProjectFile>(join(DATA_DIR, file));
    if (!raw) return null;
    return normalizeProject(raw, raw.name || file.replace(/\.neon\.json$/, ""));
  }));
  return projects.filter(Boolean) as LocalProject[];
}

async function readDeletedIds() {
  return await readJsonFile<string[]>(DELETED_PATH) ?? [];
}

async function writeDeletedIds(ids: string[]) {
  await mkdir(DATA_ROOT, { recursive: true });
  await writeFile(DELETED_PATH, JSON.stringify([...new Set(ids)], null, 2) + "\n", "utf8");
}

export async function listProjects() {
  const [factoryProjectsRaw, storedProjects, deletedIds] = await Promise.all([readFactoryProjects(), readStoredProjects(), readDeletedIds()]);
  const deletedIdSet = new Set(deletedIds);
  const factoryProjects = factoryProjectsRaw.filter((project) => !deletedIdSet.has(project.id));
  const storedById = new Map(storedProjects.map((project) => [project.id, project]));
  const mergedFactories = factoryProjects.map((factoryProject) => {
    const storedProject = storedById.get(factoryProject.id);
    if (!storedProject) return factoryProject;
    return {
      ...factoryProject,
      ...storedProject,
      projectFile: storedProject.projectFile ?? factoryProject.projectFile,
      assets: storedProject.assets ?? factoryProject.assets,
      description: storedProject.description ?? factoryProject.description,
      keyCenter: storedProject.keyCenter ?? factoryProject.keyCenter
    };
  });
  const factoryIds = new Set(mergedFactories.map((project) => project.id));
  return [...mergedFactories, ...storedProjects.filter((project) => !factoryIds.has(project.id))].map(cloneProject);
}

export async function saveProject(project: LocalProject) {
  await mkdir(DATA_DIR, { recursive: true });
  const normalized = normalizeProject(project, project.name || "Project");
  await writeFile(projectPath(normalized.id), JSON.stringify({
    format: "neon-studio-project",
    formatVersion: 1,
    portable: true,
    assetMode: normalized.assets?.some((asset) => asset.data) ? "embedded" : "external",
    ...normalized
  }, null, 2) + "\n", "utf8");
  const deletedIds = await readDeletedIds();
  if (deletedIds.includes(normalized.id)) {
    await writeDeletedIds(deletedIds.filter((id) => id !== normalized.id));
  }
  return normalized;
}

export async function deleteProject(id: string) {
  const safeId = safeProjectId(id);
  const path = projectPath(safeId);
  if (existsSync(path)) {
    await rm(path);
  }
  const factoryProjects = await readFactoryProjects();
  if (factoryProjects.some((project) => project.id === safeId)) {
    const deletedIds = await readDeletedIds();
    if (!deletedIds.includes(safeId)) {
      await writeDeletedIds([...deletedIds, safeId]);
    }
  }
}
