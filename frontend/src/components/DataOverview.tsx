import type { Dataset, SemanticLayer } from "../api";
import { friendlyType, rowsLabel } from "../format";

export type TermsState =
  | { status: "loading" }
  | { status: "ready"; layer: SemanticLayer | null }
  | { status: "error"; message: string };

interface Props {
  dataset: Dataset;
  terms: TermsState;
}

/**
 * Screen 2 (Data overview): every table and column with its type and example values, and
 * every business term with its description (US-02). Terms are read-only (US-12): a data
 * steward edits them offline in semantic_layer.yaml, so nothing here can change them.
 */
export default function DataOverview({ dataset, terms }: Props) {
  return (
    <div className="overview">
      <p className="lead">These are the tables, columns and business terms Querious can use to answer questions.</p>

      {dataset.tables.map((table) => {
        const examples = dataset.examples[table.name] ?? {};
        return (
          <section key={table.name} className="card table-card" aria-labelledby={`table-${table.name}`}>
            <div className="table-head">
              <h2 id={`table-${table.name}`} className="mono">
                {table.name}
              </h2>
              <span className="muted">{rowsLabel(table.row_count)}</span>
            </div>
            <div className="table-scroll">
              <table>
                <caption className="visually-hidden">Columns of the {table.name} table</caption>
                <thead>
                  <tr>
                    <th scope="col">Column</th>
                    <th scope="col">Type</th>
                    <th scope="col">Example values</th>
                  </tr>
                </thead>
                <tbody>
                  {table.columns.map((column) => {
                    const values = examples[column.name] ?? [];
                    return (
                      <tr key={column.name}>
                        <td className="mono">{column.name}</td>
                        <td>{friendlyType(column.type)}</td>
                        <td className="muted">
                          {values.length > 0 ? (
                            values.join(", ")
                          ) : (
                            <>
                              <span aria-hidden="true">—</span>
                              <span className="visually-hidden">No example values shown</span>
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}

      <section className="card terms-card" aria-labelledby="terms-title">
        <div className="table-head terms-head">
          <h2 id="terms-title">Business terms</h2>
          <span className="small muted">Defined by your data steward in semantic_layer.yaml · read-only</span>
        </div>
        <TermsBody terms={terms} />
      </section>
    </div>
  );
}

function TermsBody({ terms }: { terms: TermsState }) {
  if (terms.status === "loading") {
    return <p role="status">Loading business terms…</p>;
  }
  if (terms.status === "error") {
    return (
      <p role="alert" className="file-error">
        <b>Business terms not loaded.</b> {terms.message}
      </p>
    );
  }
  const list = terms.layer?.terms ?? [];
  if (list.length === 0) {
    return (
      <p>
        No business terms are defined for this dataset yet. A data steward can add them in semantic_layer.yaml;
        until then, questions are matched to column names only.
      </p>
    );
  }
  return (
    <dl className="terms">
      {list.map((term) => (
        <div key={term.name} className="term">
          <dt>{term.name}</dt>
          <dd>{term.description}</dd>
        </div>
      ))}
    </dl>
  );
}
