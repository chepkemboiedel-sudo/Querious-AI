import { vi } from "vitest";
import type { Dataset, SemanticLayer } from "./api";

export const SAMPLE: Dataset = {
  name: "Sample dataset (customers and orders)",
  kind: "sample",
  loaded_at: "2026-11-21T10:00:00Z",
  fingerprint: "abc123",
  tables: [
    {
      name: "customers",
      row_count: 20,
      columns: [
        { name: "customer_id", type: "BIGINT" },
        { name: "segment", type: "VARCHAR" },
        { name: "signup_date", type: "DATE" },
      ],
    },
    {
      name: "orders",
      row_count: 80,
      columns: [
        { name: "order_id", type: "BIGINT" },
        { name: "status", type: "VARCHAR" },
        { name: "amount", type: "DOUBLE" },
      ],
    },
  ],
  examples: {
    customers: { segment: ["Consumer", "Corporate"] },
    orders: { status: ["cancelled", "completed"] },
  },
};

export const UPLOAD: Dataset = {
  name: "sales.csv",
  kind: "upload",
  loaded_at: "2026-11-21T10:05:00Z",
  fingerprint: "def456",
  tables: [
    {
      name: "sales",
      row_count: 1234,
      columns: [
        { name: "region", type: "VARCHAR" },
        { name: "revenue", type: "DECIMAL(10,2)" },
      ],
    },
  ],
  examples: { sales: { region: ["North", "South"] } },
};

export const SAMPLE_TERMS: SemanticLayer = {
  dataset_key: "sample",
  version: "semantic-v1:sha256:0000",
  terms: [
    { name: "active customer", description: "A customer with an order in the last 90 days." },
    { name: "revenue", description: "Sum of amount over completed orders." },
  ],
};

type Reply = { status?: number; body: unknown } | (() => Promise<Response>);

/** Replaces fetch with a mocked backend API keyed by "METHOD path". Returns the spy. */
export function mockApi(routes: Record<string, Reply>) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${(init?.method ?? "GET").toUpperCase()} ${String(input)}`;
    const reply = routes[key];
    if (!reply) throw new Error(`Unexpected request: ${key}`);
    if (typeof reply === "function") return reply();
    return new Response(JSON.stringify(reply.body), {
      status: reply.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

export function csvFile(name: string, content = "a,b\n1,2\n", size?: number): File {
  const file = new File([content], name, { type: "text/csv" });
  if (size !== undefined) Object.defineProperty(file, "size", { value: size });
  return file;
}
