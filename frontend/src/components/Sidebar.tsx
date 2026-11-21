import type { Dataset } from "../api";
import { datasetMeta } from "../format";

interface Props {
  dataset: Dataset;
  onChangeDataset: () => void;
}

/** Screens that exist so far. Ask (TMP-15a) and History come in later Issues. */
const NAV = [
  { id: "ask", label: "Ask", built: false },
  { id: "overview", label: "Data overview", built: true },
  { id: "history", label: "History", built: false },
] as const;

/** The navy sidebar, shown once a dataset is loaded (prototype screens 2–10). */
export default function Sidebar({ dataset, onChangeDataset }: Props) {
  return (
    <nav aria-label="Main" className="sidebar">
      <div className="brand">
        <span aria-hidden="true" className="brand-mark">
          Q
        </span>
        <span className="brand-name">Querious</span>
      </div>

      <div className="current-dataset">
        <span className="eyebrow-dark">Current dataset</span>
        <span className="current-name">{dataset.name}</span>
        <span className="current-meta">{datasetMeta(dataset)}</span>
        <button type="button" className="change-dataset" onClick={onChangeDataset}>
          Change dataset
        </button>
      </div>

      <ul className="nav-list">
        {NAV.map((item) =>
          item.built ? (
            <li key={item.id}>
              <a href="#overview" className="nav-item" aria-current="page">
                {item.label}
              </a>
            </li>
          ) : (
            <li key={item.id}>
              {/* Disabled but still focusable, so screen-reader users hear that it exists. */}
              <button
                type="button"
                className="nav-item"
                aria-disabled="true"
                aria-describedby={`${item.id}-unavailable`}
                onClick={(event) => event.preventDefault()}
              >
                {item.label}
                <span aria-hidden="true" className="nav-note">
                  Not available yet
                </span>
                <span id={`${item.id}-unavailable`} hidden>
                  Not available yet
                </span>
              </button>
            </li>
          ),
        )}
      </ul>

      <p className="sidebar-note">Your rows stay local. Only your question, the schema and the terms go to the AI.</p>
    </nav>
  );
}
