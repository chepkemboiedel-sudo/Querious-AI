import { useEffect, useState } from "react";
import { ApiError, UNREACHABLE_MESSAGE, getActiveDataset, getTerms, type Dataset } from "./api";
import DataOverview, { type TermsState } from "./components/DataOverview";
import Sidebar from "./components/Sidebar";
import StartScreen from "./components/StartScreen";

type Screen = "checking" | "start" | "overview";

export default function App() {
  const [screen, setScreen] = useState<Screen>("checking");
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [terms, setTerms] = useState<TermsState>({ status: "loading" });

  // The last loaded dataset is kept after a restart (ARCHITECTURE §8), so reopen it.
  useEffect(() => {
    let cancelled = false;
    getActiveDataset()
      .then((active) => {
        if (cancelled) return;
        if (active) showDataset(active);
        else setScreen("start");
      })
      .catch(() => {
        if (!cancelled) setScreen("start");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function showDataset(loaded: Dataset) {
    setDataset(loaded);
    setScreen("overview");
    setTerms({ status: "loading" });
    getTerms()
      .then((layer) => setTerms({ status: "ready", layer }))
      .catch((error: unknown) =>
        setTerms({ status: "error", message: error instanceof ApiError ? error.message : UNREACHABLE_MESSAGE }),
      );
  }

  if (screen === "checking") {
    return (
      <main className="checking">
        <p role="status">Opening Querious…</p>
      </main>
    );
  }

  if (screen === "start" || !dataset) {
    return (
      <main className="start-main">
        <StartScreen onLoaded={showDataset} onCancel={dataset ? () => setScreen("overview") : undefined} />
      </main>
    );
  }

  return (
    <div className="workspace">
      <Sidebar dataset={dataset} onChangeDataset={() => setScreen("start")} />
      <main className="workspace-main" id="overview">
        <header className="page-header">
          <div>
            <span className="eyebrow">{dataset.name}</span>
            <h1>Data overview</h1>
          </div>
          <span className="badge">
            <span aria-hidden="true" className="badge-dot" />
            Local · Read-only
          </span>
        </header>
        <DataOverview dataset={dataset} terms={terms} />
      </main>
    </div>
  );
}
