import { auth } from "@clerk/nextjs/server";
import { NextRequest } from "next/server";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function forward(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  if (
    !process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ||
    !process.env.CLERK_SECRET_KEY
  )
    return Response.json(
      {
        detail:
          "Clerk is not configured. Ask the application owner to complete setup.",
      },
      { status: 503 },
    );
  const session = await auth();
  if (!session.userId)
    return Response.json(
      { detail: "Sign in to access your research." },
      { status: 401 },
    );
  const token = await session.getToken();
  if (!token)
    return Response.json(
      { detail: "Your session expired. Sign in again." },
      { status: 401 },
    );
  const { path } = await context.params;
  const base = process.env.BACKEND_API_URL || "http://127.0.0.1:8000/api";
  const url = `${base.replace(/\/$/, "")}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers({ Authorization: `Bearer ${token}` });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  if (Number(request.headers.get("content-length") || 0) > 21 * 1024 * 1024)
    return Response.json(
      { detail: "Request exceeds the 20 MB upload limit." },
      { status: 413 },
    );
  try {
    let body: ArrayBuffer | undefined;
    if (!["GET", "HEAD"].includes(request.method)) {
      const reader = request.body?.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      if (reader)
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > 21 * 1024 * 1024) {
            await reader.cancel();
            return Response.json(
              { detail: "Request exceeds the upload limit." },
              { status: 413 },
            );
          }
          chunks.push(value);
        }
      const joined = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) {
        joined.set(chunk, offset);
        offset += chunk.byteLength;
      }
      body = joined.buffer;
    }
    const response = await fetch(url, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: request.signal,
    });
    const resultHeaders = new Headers();
    for (const name of [
      "content-type",
      "content-disposition",
      "cache-control",
      "x-accel-buffering",
    ])
      if (response.headers.has(name))
        resultHeaders.set(name, response.headers.get(name)!);
    // Pass actual SSE through unchanged; never put tokens into download URLs.
    return new Response(response.body, {
      status: response.status,
      headers: resultHeaders,
    });

  } catch (error) {
    console.error("[backend-proxy] Upstream fetch failed", {
      url,
      method: request.method,
      error:
        error instanceof Error
          ? {
              name: error.name,
              message: error.message,
              cause:
                error.cause instanceof Error
                  ? error.cause.message
                  : String(error.cause ?? ""),
            }
          : String(error),
    });

    return Response.json(
      {
        detail: "Cannot reach the research backend.",
        diagnostic:
          error instanceof Error ? error.message : String(error),
      },
      { status: 502 },
    );
  }

}
export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const DELETE = forward;
