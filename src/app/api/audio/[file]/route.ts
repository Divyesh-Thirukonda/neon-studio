import { createReadStream, existsSync, statSync } from "node:fs";
import { basename, join } from "node:path";
import { Readable } from "node:stream";
import { NextRequest } from "next/server";

const SAFE_WAV_NAME = /^[a-z0-9][a-z0-9_-]*\.wav$/;

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ file: string }> }
) {
  const { file } = await params;
  const safeName = basename(file);
  if (!SAFE_WAV_NAME.test(safeName)) {
    return new Response("Not found", { status: 404 });
  }

  const path = join(process.cwd(), "exports", safeName);
  if (!existsSync(path)) {
    return new Response("Missing audio asset", { status: 404 });
  }

  const stat = statSync(path);
  const range = request.headers.get("range");

  if (range) {
    const match = /bytes=(\d+)-(\d*)/.exec(range);
    const start = match ? Number(match[1]) : 0;
    const end = match && match[2] ? Number(match[2]) : stat.size - 1;
    const size = end - start + 1;
    const stream = createReadStream(path, { start, end });
    return new Response(Readable.toWeb(stream) as ReadableStream, {
      status: 206,
      headers: {
        "Accept-Ranges": "bytes",
        "Content-Length": String(size),
        "Content-Range": `bytes ${start}-${end}/${stat.size}`,
        "Content-Type": "audio/wav"
      }
    });
  }

  const stream = createReadStream(path);
  return new Response(Readable.toWeb(stream) as ReadableStream, {
    headers: {
      "Accept-Ranges": "bytes",
      "Content-Length": String(stat.size),
      "Content-Type": "audio/wav"
    }
  });
}
