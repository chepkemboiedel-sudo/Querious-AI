// The frontend talks only to the Querious backend API (ARCHITECTURE §4), over relative
// paths. In development Vite proxies them to the FastAPI server (vite.config.ts).

export interface ColumnProfile {
  name: string;
  type: string; // the DuckDB type inferred at load, e.g. VARCHAR, BIGINT, DOUBLE, DATE
}

export interface TableProfile {
  name: string;
  row_count: number;
  columns: ColumnProfile[];
}

/** The stored profile of the active dataset (GET /datasets/active and the load endpoints). */
export interface Dataset {
  name: string;
  kind: "upload" | "sample";
  loaded_at: string;
  fingerprint: string;
  tables: TableProfile[];
  /** table -> column -> example values (text columns only), shown locally on screen 2. */
  examples: Record<string, Record<string, string[]>>;
}

export interface Term {
  name: string;
  description: string;
}

export interface SemanticLayer {
  dataset_key: string;
  version: string;
  terms: Term[];
}

/** A rejection with the backend's plain-English message and its machine reason. */
export class ApiError extends Error {
  readonly reason: string;

  constructor(message: string, reason: string) {
    super(message);
    this.name = "ApiError";
    this.reason = reason;
  }
}

export const UNREACHABLE_MESSAGE =
  "Querious could not reach its local server. Check that the backend is running, then try again.";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(UNREACHABLE_MESSAGE, "unreachable");
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      const { message, reason } = detail as { message?: unknown; reason?: unknown };
      if (typeof message === "string") {
        throw new ApiError(message, typeof reason === "string" ? reason : "error");
      }
    }
    throw new ApiError(`The request was not completed (HTTP ${response.status}). Try again.`, "error");
  }
  return body as T;
}

export async function getActiveDataset(): Promise<Dataset | null> {
  const body = await request<{ dataset: Dataset | null }>("/datasets/active");
  return body.dataset;
}

export async function uploadCsv(file: File): Promise<Dataset> {
  const form = new FormData();
  form.append("file", file);
  const body = await request<{ dataset: Dataset }>("/datasets/upload", { method: "POST", body: form });
  return body.dataset;
}

export async function loadSample(): Promise<Dataset> {
  const body = await request<{ dataset: Dataset }>("/datasets/sample", { method: "POST" });
  return body.dataset;
}

/** The active dataset's business terms; null when no dataset is active. Read-only (US-12). */
export async function getTerms(): Promise<SemanticLayer | null> {
  const body = await request<{ semantic_layer: SemanticLayer | null }>("/semantic/terms");
  return body.semantic_layer;
}
