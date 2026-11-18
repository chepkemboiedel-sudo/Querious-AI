import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it('shows "Querious AI"', () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Querious AI" })).toBeInTheDocument();
  });
});
