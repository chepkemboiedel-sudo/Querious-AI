import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { SAMPLE, SAMPLE_TERMS, UPLOAD, csvFile, mockApi } from "./test-helpers";

const NO_ACTIVE = { "GET /datasets/active": { body: { dataset: null } } };

afterEach(() => {
  vi.unstubAllGlobals();
});

async function openStart() {
  render(<App />);
  return screen.findByRole("heading", { name: "Choose your data source" });
}

function fileInput(): HTMLInputElement {
  return screen.getByLabelText("Choose a .csv file to upload") as HTMLInputElement;
}

function chooseFile(file: File) {
  fireEvent.change(fileInput(), { target: { files: [file] } });
}

describe("Screen 1: Start", () => {
  it("shows the upload card with its rules and the sample-dataset button, and no sidebar", async () => {
    mockApi(NO_ACTIVE);
    await openStart();
    expect(screen.getByRole("heading", { name: "Upload CSV" })).toBeInTheDocument();
    expect(screen.getByText(/Header row required · Up to 50 MB · \.csv only/)).toBeInTheDocument();
    expect(fileInput()).toHaveAttribute("type", "file");
    expect(fileInput()).toHaveAccessibleDescription(/Header row required/);
    expect(screen.getByRole("button", { name: "Use the sample dataset" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
  });

  it("rejects a file that is not a .csv in the browser, without uploading it", async () => {
    const api = mockApi(NO_ACTIVE);
    await openStart();
    chooseFile(new File(["hello"], "notes.txt", { type: "text/plain" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("File not loaded.");
    expect(alert).toHaveTextContent("Only .csv files can be uploaded");
    expect(api).toHaveBeenCalledTimes(1); // only GET /datasets/active
  });

  it("rejects a file over 50 MB in the browser, without uploading it", async () => {
    const api = mockApi(NO_ACTIVE);
    await openStart();
    chooseFile(csvFile("big.csv", "a\n1\n", 50 * 1024 * 1024 + 1));
    expect(await screen.findByRole("alert")).toHaveTextContent("larger than 50 MB");
    expect(api).toHaveBeenCalledTimes(1);
  });

  it("shows the backend's header-check message as a clear file error", async () => {
    const message = "The first row must be a header row with a name for every column.";
    mockApi({
      ...NO_ACTIVE,
      "POST /datasets/upload": { status: 422, body: { detail: { reason: "no_header", message } } },
    });
    await openStart();
    chooseFile(csvFile("headerless.csv", "1,2\n3,4\n"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("File not loaded.");
    expect(alert).toHaveTextContent(message);
    expect(screen.getByRole("heading", { name: "Choose your data source" })).toBeInTheDocument();
  });

  it("says plainly when the local server can't be reached", async () => {
    mockApi({ ...NO_ACTIVE, "POST /datasets/sample": () => Promise.reject(new TypeError("Failed to fetch")) });
    await openStart();
    fireEvent.click(screen.getByRole("button", { name: "Use the sample dataset" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not reach its local server");
  });

  it("accepts a dropped .csv file", async () => {
    mockApi({
      ...NO_ACTIVE,
      "POST /datasets/upload": { body: { dataset: UPLOAD } },
      "GET /semantic/terms": { body: { semantic_layer: { dataset_key: "sales.csv", version: "v", terms: [] } } },
    });
    await openStart();
    const drop = screen.getByText("Choose a .csv file").closest("label")!;
    fireEvent.drop(drop, { dataTransfer: { files: [csvFile("sales.csv")] } });
    expect(await screen.findByRole("heading", { name: "Data overview" })).toBeInTheDocument();
  });
});

describe("Loading a valid dataset (US-01)", () => {
  it("shows a loading status while the file is checked", async () => {
    mockApi({ ...NO_ACTIVE, "POST /datasets/upload": () => new Promise<Response>(() => {}) });
    await openStart();
    chooseFile(csvFile("sales.csv"));
    expect(await screen.findByRole("status")).toHaveTextContent("Reading the header row and column types…");
    expect(fileInput()).toBeDisabled();
    expect(screen.getByRole("button", { name: "Use the sample dataset" })).toBeDisabled();
  });

  it("shows the uploaded table and columns straight from the upload response", async () => {
    const api = mockApi({
      ...NO_ACTIVE,
      "POST /datasets/upload": { body: { dataset: UPLOAD } },
      "GET /semantic/terms": { body: { semantic_layer: { dataset_key: "sales.csv", version: "v", terms: [] } } },
    });
    await openStart();
    chooseFile(csvFile("sales.csv"));

    const table = await screen.findByRole("table", { name: "Columns of the sales table" });
    expect(within(table).getByText("region")).toBeInTheDocument();
    expect(within(table).getByText("revenue")).toBeInTheDocument();
    expect(screen.getByText("1,234 rows")).toBeInTheDocument();

    // The table is shown from the load response itself: no extra dataset request is needed.
    const calls = api.mock.calls.map(([url, init]) => `${init?.method ?? "GET"} ${String(url)}`);
    expect(calls).toEqual(["GET /datasets/active", "POST /datasets/upload", "GET /semantic/terms"]);
    const body = api.mock.calls[1][1]?.body as FormData;
    expect((body.get("file") as File).name).toBe("sales.csv");
  });

  it("shows the tables while the terms are still loading", async () => {
    mockApi({
      ...NO_ACTIVE,
      "POST /datasets/sample": { body: { dataset: SAMPLE } },
      "GET /semantic/terms": () => new Promise<Response>(() => {}),
    });
    await openStart();
    fireEvent.click(screen.getByRole("button", { name: "Use the sample dataset" }));
    expect(await screen.findByRole("table", { name: "Columns of the orders table" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Loading business terms…");
  });

  it("ignores a late terms reply from a dataset that was replaced", async () => {
    let releaseOld: (r: Response) => void = () => {};
    const replies = [
      () => new Promise<Response>((resolve) => (releaseOld = resolve)),
      async () => new Response(JSON.stringify({ semantic_layer: SAMPLE_TERMS }), { status: 200 }),
    ];
    mockApi({
      "GET /datasets/active": { body: { dataset: UPLOAD } },
      "GET /semantic/terms": () => replies.shift()!(),
      "POST /datasets/sample": { body: { dataset: SAMPLE } },
    });
    render(<App />);
    await screen.findByRole("table", { name: "Columns of the sales table" });
    fireEvent.click(screen.getByRole("button", { name: "Change dataset" }));
    fireEvent.click(screen.getByRole("button", { name: "Use the sample dataset" }));
    const section = await screen.findByRole("region", { name: "Business terms" });
    await within(section).findByText("active customer");
    releaseOld(
      new Response(JSON.stringify({ semantic_layer: { dataset_key: "sales.csv", version: "v", terms: [] } }), {
        status: 200,
      }),
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(within(section).getByText("active customer")).toBeInTheDocument();
    expect(within(section).queryByText(/No business terms/)).not.toBeInTheDocument();
  });

  it("reopens the dataset kept from the last session", async () => {
    mockApi({
      "GET /datasets/active": { body: { dataset: SAMPLE } },
      "GET /semantic/terms": { body: { semantic_layer: SAMPLE_TERMS } },
    });
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Data overview" })).toBeInTheDocument();
  });
});

async function openOverview(terms: unknown = { body: { semantic_layer: SAMPLE_TERMS } }) {
  mockApi({
    "GET /datasets/active": { body: { dataset: SAMPLE } },
    "GET /semantic/terms": terms as { body: unknown },
  });
  render(<App />);
  await screen.findByRole("heading", { name: "Data overview" });
}

describe("Screen 2: Data overview (US-02)", () => {
  it("lists every table and column with its type and example values", async () => {
    await openOverview();
    for (const table of SAMPLE.tables) {
      const grid = screen.getByRole("table", { name: `Columns of the ${table.name} table` });
      const rows = within(grid).getAllByRole("row").slice(1);
      expect(rows.map((row) => within(row).getAllByRole("cell")[0].textContent)).toEqual(
        table.columns.map((c) => c.name),
      );
    }
    const orders = screen.getByRole("table", { name: "Columns of the orders table" });
    const statusRow = within(orders).getByText("status").closest("tr")!;
    expect(statusRow).toHaveTextContent("Text");
    expect(statusRow).toHaveTextContent("cancelled, completed");
    const amountRow = within(orders).getByText("amount").closest("tr")!;
    expect(amountRow).toHaveTextContent("Decimal");
    expect(amountRow).toHaveTextContent("No example values shown");
    const customers = screen.getByRole("table", { name: "Columns of the customers table" });
    expect(within(customers).getByText("signup_date").closest("tr")).toHaveTextContent("Date");
    expect(within(customers).getByText("customer_id").closest("tr")).toHaveTextContent("Integer");
  });

  it("lists every semantic-layer term with its plain-English description", async () => {
    await openOverview();
    const section = screen.getByRole("region", { name: "Business terms" });
    for (const term of SAMPLE_TERMS.terms) {
      const name = await within(section).findByText(term.name);
      expect(name.tagName).toBe("DT");
      expect(name.nextElementSibling).toHaveTextContent(term.description);
    }
  });

  it("shows terms read-only: no inputs, editable text or edit buttons", async () => {
    await openOverview();
    const section = screen.getByRole("region", { name: "Business terms" });
    await within(section).findByText("active customer");
    expect(within(section).getByText(/read-only/)).toBeInTheDocument();
    expect(within(section).queryAllByRole("textbox")).toHaveLength(0);
    expect(within(section).queryAllByRole("button")).toHaveLength(0);
    expect(section.querySelectorAll("input, textarea, select, [contenteditable]")).toHaveLength(0);
  });

  it("says so when the dataset has no terms", async () => {
    await openOverview({ body: { semantic_layer: { dataset_key: "x.csv", version: "v", terms: [] } } });
    const section = screen.getByRole("region", { name: "Business terms" });
    expect(await within(section).findByText(/No business terms are defined for this dataset yet/)).toBeInTheDocument();
  });

  it("shows the reason when the terms can't be loaded", async () => {
    await openOverview({
      status: 422,
      body: { detail: { reason: "semantic_layer", message: "semantic_layer.yaml has an error in section 'sample'." } },
    });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Business terms not loaded.");
    expect(alert).toHaveTextContent("section 'sample'");
  });
});

describe("Navy sidebar", () => {
  it("shows the current dataset and the four links, with unbuilt screens disabled", async () => {
    await openOverview();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByText(SAMPLE.name)).toBeInTheDocument();
    expect(within(nav).getByText("2 tables · Read-only")).toBeInTheDocument();

    expect(within(nav).getByRole("link", { name: "Data overview" })).toHaveAttribute("aria-current", "page");
    for (const label of ["Ask", "History"]) {
      const link = within(nav).getByRole("button", { name: new RegExp(`^${label}`) });
      expect(link).toHaveAttribute("aria-disabled", "true");
      expect(link).toHaveAccessibleDescription("Not available yet"); // not shown by colour alone
    }
    expect(within(nav).getByRole("button", { name: "Change dataset" })).toBeEnabled();
  });

  it("disabled links do nothing", async () => {
    await openOverview();
    const nav = screen.getByRole("navigation", { name: "Main" });
    fireEvent.click(within(nav).getByRole("button", { name: /^Ask/ }));
    fireEvent.click(within(nav).getByRole("button", { name: /^History/ }));
    expect(screen.getByRole("heading", { name: "Data overview" })).toBeInTheDocument();
  });

  it("Change dataset returns to Start, and can be cancelled", async () => {
    await openOverview();
    fireEvent.click(screen.getByRole("button", { name: "Change dataset" }));
    expect(screen.getByRole("heading", { name: "Choose your data source" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Keep the current dataset" }));
    expect(screen.getByRole("heading", { name: "Data overview" })).toBeInTheDocument();
  });

  it("Change dataset then the sample replaces the current dataset", async () => {
    mockApi({
      "GET /datasets/active": { body: { dataset: UPLOAD } },
      "GET /semantic/terms": { body: { semantic_layer: SAMPLE_TERMS } },
      "POST /datasets/sample": { body: { dataset: SAMPLE } },
    });
    render(<App />);
    await screen.findByRole("table", { name: "Columns of the sales table" });
    fireEvent.click(screen.getByRole("button", { name: "Change dataset" }));
    fireEvent.click(screen.getByRole("button", { name: "Use the sample dataset" }));
    await screen.findByRole("table", { name: "Columns of the orders table" });
    expect(screen.queryByRole("table", { name: "Columns of the sales table" })).not.toBeInTheDocument();
  });
});

describe("Accessibility (RC-14)", () => {
  it("every Start control is a native, focusable control with a label", async () => {
    mockApi(NO_ACTIVE);
    await openStart();
    for (const control of [fileInput(), screen.getByRole("button", { name: "Use the sample dataset" })]) {
      control.focus();
      expect(control).toHaveFocus();
      expect(control).toHaveAccessibleName();
    }
  });

  it("every sidebar control is focusable and labelled, including disabled links", async () => {
    await openOverview();
    const nav = screen.getByRole("navigation", { name: "Main" });
    const controls = [...within(nav).getAllByRole("button"), ...within(nav).getAllByRole("link")];
    expect(controls).toHaveLength(4);
    for (const control of controls) {
      control.focus();
      expect(control).toHaveFocus();
      expect(control).toHaveAccessibleName();
    }
  });

  it("file errors are announced in words, not colour alone", async () => {
    mockApi(NO_ACTIVE);
    await openStart();
    chooseFile(new File(["x"], "data.xlsx"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/File not loaded\. Only \.csv files/);
  });
});
