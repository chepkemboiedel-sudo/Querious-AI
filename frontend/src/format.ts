import type { Dataset } from "./api";

/** Upload limits checked in the browser before sending (POLICY D-6). The backend checks them again. */
export const MAX_UPLOAD_MB = 50;
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

/** Returns the reason a file can't be uploaded, or null. Header checks happen on the backend. */
export function checkFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".csv")) {
    return "Only .csv files can be uploaded. Choose a CSV file with a header row.";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `The file is larger than ${MAX_UPLOAD_MB} MB. Upload a CSV of ${MAX_UPLOAD_MB} MB or less.`;
  }
  if (file.size === 0) {
    return "The file is empty. Upload a CSV with a header row and data.";
  }
  return null;
}

/** Plain-English name for a DuckDB column type, as on the prototype's Data overview. */
export function friendlyType(duckdbType: string): string {
  const t = duckdbType.toUpperCase();
  if (/^(TINYINT|SMALLINT|INTEGER|INT|BIGINT|HUGEINT|UTINYINT|USMALLINT|UINTEGER|UBIGINT|UHUGEINT)$/.test(t)) {
    return "Integer";
  }
  if (/^(DOUBLE|FLOAT|REAL)$/.test(t) || t.startsWith("DECIMAL")) return "Decimal";
  if (t === "DATE") return "Date";
  if (t.startsWith("TIMESTAMP")) return "Date and time";
  if (t === "TIME") return "Time";
  if (t === "BOOLEAN") return "Yes / No";
  if (t === "VARCHAR") return "Text";
  return duckdbType;
}

const numberFormat = new Intl.NumberFormat("en-US");

export function rowsLabel(count: number): string {
  return `${numberFormat.format(count)} ${count === 1 ? "row" : "rows"}`;
}

export function datasetMeta(dataset: Dataset): string {
  const n = dataset.tables.length;
  return `${n} ${n === 1 ? "table" : "tables"} · Read-only`;
}
