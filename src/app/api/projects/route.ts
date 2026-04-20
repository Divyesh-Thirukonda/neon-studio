import { NextRequest } from "next/server";
import { deleteProject, listProjects, saveProject } from "@/lib/projectStore";
import { LocalProject } from "@/lib/projectTypes";

export async function GET() {
  const projects = await listProjects();
  return Response.json({ projects });
}

export async function POST(request: NextRequest) {
  const project = await request.json() as LocalProject;
  const saved = await saveProject(project);
  return Response.json({ project: saved });
}

export async function DELETE(request: NextRequest) {
  const { id } = await request.json() as { id?: string };
  if (!id) {
    return Response.json({ error: "Missing project id" }, { status: 400 });
  }
  await deleteProject(id);
  return Response.json({ ok: true });
}
