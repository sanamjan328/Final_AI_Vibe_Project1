import { render, screen } from "@testing-library/react";
import WatchlistPanel from "@/components/WatchlistPanel";
import type { WatchlistRow } from "@/lib/types";

const rows: WatchlistRow[] = [
  {
    ticker: "AAPL",
    price: 190.5,
    prev_price: 190.0,
    change_pct: 0.26,
    direction: "up",
  },
  {
    ticker: "GOOGL",
    price: 175.25,
    prev_price: 176.0,
    change_pct: -0.43,
    direction: "down",
  },
  {
    ticker: "MSFT",
    price: 410.1,
    prev_price: 410.1,
    change_pct: 0.0,
    direction: "flat",
  },
];

describe("WatchlistPanel", () => {
  it("renders all ticker symbols passed in", () => {
    render(
      <WatchlistPanel
        rows={rows}
        prices={{}}
        sparklines={{}}
        selected={null}
        onSelect={() => {}}
        onChange={() => {}}
      />
    );
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("GOOGL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText(/3 symbols/i)).toBeInTheDocument();
  });

  it("shows the add input and add button", () => {
    render(
      <WatchlistPanel
        rows={rows}
        prices={{}}
        sparklines={{}}
        selected={"AAPL"}
        onSelect={() => {}}
        onChange={() => {}}
      />
    );
    expect(screen.getByTestId("watchlist-add-input")).toBeInTheDocument();
    expect(screen.getByTestId("watchlist-add-submit")).toBeInTheDocument();
  });
});
