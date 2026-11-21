import { useState, type ChangeEvent, type DragEvent } from "react";
import { ApiError, UNREACHABLE_MESSAGE, loadSample, uploadCsv, type Dataset } from "../api";
import { MAX_UPLOAD_MB, checkFile } from "../format";

interface Props {
  onLoaded: (dataset: Dataset) => void;
  /** Shown when a dataset is already loaded, so "Change dataset" can be cancelled. */
  onCancel?: () => void;
}

/** Screen 1 (Start): upload a CSV or use the sample dataset (US-01, POLICY D-6). */
export default function StartScreen({ onLoaded, onCancel }: Props) {
  const [busy, setBusy] = useState<"upload" | "sample" | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  async function load(kind: "upload" | "sample", run: () => Promise<Dataset>) {
    setFileError(null);
    setBusy(kind);
    try {
      onLoaded(await run());
    } catch (error) {
      setFileError(error instanceof ApiError ? error.message : UNREACHABLE_MESSAGE);
      setBusy(null);
    }
  }

  function handleFile(file: File | undefined) {
    if (!file || busy) return;
    const problem = checkFile(file);
    if (problem) {
      setFileError(problem);
      return;
    }
    void load("upload", () => uploadCsv(file));
  }

  function onInputChange(event: ChangeEvent<HTMLInputElement>) {
    handleFile(event.target.files?.[0]);
    // Allow choosing the same file again after fixing it.
    event.target.value = "";
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    handleFile(event.dataTransfer.files[0]);
  }

  return (
    <div className="start">
      <div className="start-intro">
        <div className="brand brand-light">
          <span aria-hidden="true" className="brand-mark">
            Q
          </span>
          <span className="brand-name">Querious</span>
        </div>
        <p className="tagline">Your data. Clear answers.</p>
        <h1 className="start-title">
          Ask <span className="accent">your data</span> a question. See how the answer was found.
        </h1>
        <p className="start-lead">
          Load a CSV file or explore the sample dataset. Get answers you can understand and trace.
        </p>
        <p className="start-point">
          <b>Read-only by design.</b> Querious only reads your data. It never changes it.
        </p>
      </div>

      <section aria-labelledby="source-title" className="card source-card">
        <h2 id="source-title">Choose your data source</h2>
        <p className="muted">Start with your own data or take a quick tour.</p>

        <div className="option">
          <h3>Upload CSV</h3>
          <p className="muted" id="upload-rules">
            Header row required · Up to {MAX_UPLOAD_MB} MB · .csv only
          </p>
          <label className="drop" onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
            <span className="drop-title">Choose a .csv file</span>
            <span className="drop-sub">or drag and drop it here</span>
            <span className="drop-note">Your file is checked before it loads.</span>
            <input
              type="file"
              accept=".csv,text/csv"
              className="visually-hidden-input"
              aria-label="Choose a .csv file to upload"
              aria-describedby="upload-rules"
              disabled={busy !== null}
              onChange={onInputChange}
            />
          </label>
          {busy === "upload" && (
            <p role="status" className="status-line">
              Reading the header row and column types…
            </p>
          )}
          {fileError && (
            <div role="alert" className="file-error">
              <span aria-hidden="true" className="error-icon">
                !
              </span>
              <span>
                <b>File not loaded.</b> {fileError}
              </span>
            </div>
          )}
        </div>

        <div aria-hidden="true" className="divider">
          OR
        </div>

        <div className="option">
          <h3>Use Sample Dataset</h3>
          <p className="muted">
            Retail orders 2025–2026, with customers, orders, and business terms already defined.
          </p>
          <button
            type="button"
            className="primary-button"
            disabled={busy !== null}
            onClick={() => void load("sample", loadSample)}
          >
            {busy === "sample" ? "Loading the sample dataset…" : "Use the sample dataset"}
          </button>
          {busy === "sample" && (
            <p role="status" className="visually-hidden">
              Loading the sample dataset…
            </p>
          )}
        </div>

        {onCancel && (
          <button type="button" className="secondary-button" onClick={onCancel} disabled={busy !== null}>
            Keep the current dataset
          </button>
        )}
      </section>
    </div>
  );
}
