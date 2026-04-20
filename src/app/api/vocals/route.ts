import { mkdir, writeFile } from "node:fs/promises";
import { basename, join } from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { NextRequest } from "next/server";
import { Track } from "@/lib/projectTypes";

const execFileAsync = promisify(execFile);
const SAFE_NAME = /^[a-z0-9][a-z0-9_-]*$/;

function safeStem(name: string) {
  const stem = basename(name)
    .replace(/\.[^.]+$/, "")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 42);
  return SAFE_NAME.test(stem) ? stem : "vocal";
}

function safeNumber(value: FormDataEntryValue | null, fallback: number, min: number, max: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

export async function POST(request: NextRequest) {
  const form = await request.formData();
  const file = form.get("file");
  if (!(file instanceof File)) {
    return Response.json({ error: "Missing vocal file" }, { status: 400 });
  }

  const bpm = safeNumber(form.get("bpm"), 104, 60, 220);
  const startBar = Math.round(safeNumber(form.get("startBar"), 17, 1, 72));
  const totalBars = Math.round(safeNumber(form.get("totalBars"), 72, 8, 144));
  const key = String(form.get("key") ?? "e_minor").replace(/[^a-z0-9_]/gi, "").toLowerCase() || "e_minor";
  const originalStem = safeStem(file.name);
  const stamp = new Date().toISOString().replace(/\D/g, "").slice(0, 14);
  const rawName = `${stamp}_${originalStem}.wav`;
  const outputName = `vocal_${stamp}_${originalStem}.wav`;
  const root = process.cwd();
  const inboxDir = join(root, "vocal_inbox");
  const exportsDir = join(root, "exports");
  const rawPath = join(inboxDir, rawName);
  const outputPath = join(exportsDir, outputName);

  await mkdir(inboxDir, { recursive: true });
  await mkdir(exportsDir, { recursive: true });
  await writeFile(rawPath, Buffer.from(await file.arrayBuffer()));

  try {
    const { stdout, stderr } = await execFileAsync("python3", [
      join(root, "tools", "vocal_autotune.py"),
      "--input", rawPath,
      "--output", outputPath,
      "--name", file.name,
      "--bpm", String(bpm),
      "--start-bar", String(startBar),
      "--total-bars", String(totalBars),
      "--key", key,
    ], { cwd: root, maxBuffer: 1024 * 1024 * 8 });

    const lastLine = stdout.trim().split("\n").at(-1) || "{}";
    const analysis = JSON.parse(lastLine) as {
      segments?: number;
      durationSeconds?: number;
      averageCorrectionSemitones?: number;
      placements?: Array<{ bar: number; beat: number; durationBeats: number }>;
    };
    const id = `vocal-${stamp}-${originalStem}`.slice(0, 64);
    const color = "#f59fcb";
    const placementEndBeat = Math.max(
      ...((analysis.placements ?? []).map((placement) => (
        (placement.bar - 1) * 4 + (placement.beat - 1) + placement.durationBeats
      ))),
      startBar * 4
    );
    const bars = Math.max(1, Math.min(totalBars - startBar + 1, Math.ceil((placementEndBeat - (startBar - 1) * 4) / 4)));
    const track: Track = {
      id,
      name: `Vocal ${originalStem.replace(/_/g, " ")}`.slice(0, 28),
      kind: "audio",
      file: `/api/audio/${outputName}`,
      color,
      gain: 0.82,
      pan: 0,
      steps: [0, 4, 8, 12],
      instrument: "AutoTune Vocal Chain",
      clips: [{
        id: `${id}-clip`,
        name: `${analysis.segments ?? 1} tuned segment${analysis.segments === 1 ? "" : "s"}`,
        startBar: startBar - 1,
        bars,
        lane: id,
        color,
        type: "audio"
      }],
      effects: [
        { id: "autotune", name: "Scale AutoTune", active: true, amount: 0.88 },
        { id: "comp", name: "Vocal Compressor", active: true, amount: 0.64 },
        { id: "air", name: "Air Shelf", active: true, amount: 0.42 },
        { id: "delay", name: "Stereo Delay Throws", active: true, amount: 0.34 },
        { id: "doubler", name: "Micro Doubler", active: true, amount: 0.30 }
      ]
    };

    return Response.json({ track, analysis, warnings: stderr.trim() ? [stderr.trim()] : [] });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Vocal processing failed";
    return Response.json({ error: message }, { status: 500 });
  }
}
