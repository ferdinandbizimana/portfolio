import { errorMessage } from "./api-errors";

export interface UploadState {
  id: string;
  filename: string;
  size_bytes: number;
  chunk_size: number;
  chunk_count: number;
  received_chunks: number[];
}

export interface DataFile {
  id: number;
  filename: string;
  size_bytes: number;
  sha256: string;
  status: "received" | "parsing" | "ready" | "failed";
  message: string;
  sheets: {
    name: string;
    header_row: number;
    columns: string[];
    row_count: number;
    matches: { dataset: string; title: string }[];
  }[];
  created_at: string;
  used_by_runs: number;
}

const RETRIES = 3;

class UploadError extends Error {}

async function json<T>(response: Response): Promise<T> {
  const body: unknown = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new UploadError(errorMessage(body));
  return body as T;
}

function resumeKey(file: File): string {
  return `upload:${file.name}:${file.size}:${file.lastModified}`;
}

function storedId(file: File): string | null {
  try {
    return window.localStorage.getItem(resumeKey(file));
  } catch {
    return null;
  }
}

function remember(file: File, id: string | null) {
  try {
    if (id) window.localStorage.setItem(resumeKey(file), id);
    else window.localStorage.removeItem(resumeKey(file));
  } catch {
    // Private browsing: resuming is not possible, uploading still works.
  }
}

async function startOrResume(file: File): Promise<UploadState> {
  const previous = storedId(file);
  if (previous) {
    const response = await fetch(`/api/admin/uploads/${previous}`, { credentials: "same-origin" });
    if (response.ok) return json<UploadState>(response);
  }
  const state = await json<UploadState>(
    await fetch("/api/admin/uploads", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, size_bytes: file.size }),
    }),
  );
  remember(file, state.id);
  return state;
}

/** Chunks still to send, in order. */
export function missingChunks(state: UploadState): number[] {
  const received = new Set(state.received_chunks);
  return Array.from({ length: state.chunk_count }, (_, i) => i).filter((i) => !received.has(i));
}

/**
 * Upload a file in chunks. If the page is reloaded or the connection drops,
 * calling this again with the same file continues where it stopped.
 */
export async function uploadFile(
  file: File,
  onProgress: (fraction: number, text: string) => void,
  signal?: AbortSignal,
): Promise<DataFile> {
  const state = await startOrResume(file);
  const todo = missingChunks(state);
  let done = state.chunk_count - todo.length;
  onProgress(done / state.chunk_count, done ? "Resuming upload" : "Uploading");
  for (const index of todo) {
    const blob = file.slice(index * state.chunk_size, (index + 1) * state.chunk_size);
    for (let attempt = 1; ; attempt++) {
      try {
        await json<null>(
          await fetch(`/api/admin/uploads/${state.id}/chunks/${index}`, {
            method: "PUT",
            credentials: "same-origin",
            body: blob,
            signal,
          }),
        );
        break;
      } catch (error) {
        if (signal?.aborted || attempt >= RETRIES) throw error;
        await new Promise((r) => setTimeout(r, 1000 * attempt));
      }
    }
    done += 1;
    onProgress(done / state.chunk_count, "Uploading");
  }
  onProgress(1, "Checking the file");
  const dataFile = await json<DataFile>(
    await fetch(`/api/admin/uploads/${state.id}/complete`, {
      method: "POST",
      credentials: "same-origin",
    }),
  );
  remember(file, null);
  return dataFile;
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}
