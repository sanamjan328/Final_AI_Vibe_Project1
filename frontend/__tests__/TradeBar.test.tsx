import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import TradeBar from "@/components/TradeBar";

describe("TradeBar", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn();
  });

  afterEach(() => {
    (global as unknown as { fetch: typeof fetch }).fetch = originalFetch;
    jest.clearAllMocks();
  });

  it("calls /api/portfolio/trade with the buy payload when BUY is clicked", async () => {
    const fetchMock = global.fetch as jest.Mock;
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: true,
        trade: {
          ticker: "AAPL",
          side: "buy",
          quantity: 5,
          price: 190,
          executed_at: "2024-01-01T00:00:00Z",
        },
        cash_balance: 9050,
        error: null,
      }),
    });

    const onTradeComplete = jest.fn();
    render(
      <TradeBar
        selectedTicker="AAPL"
        currentPrice={190}
        onTradeComplete={onTradeComplete}
      />
    );

    fireEvent.change(screen.getByTestId("trade-ticker"), {
      target: { value: "AAPL" },
    });
    fireEvent.change(screen.getByTestId("trade-quantity"), {
      target: { value: "5" },
    });
    fireEvent.click(screen.getByTestId("trade-buy"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/portfolio/trade");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      ticker: "AAPL",
      side: "buy",
      quantity: 5,
    });

    await waitFor(() => {
      expect(onTradeComplete).toHaveBeenCalled();
    });
  });

  it("shows an error when the trade API responds with success=false", async () => {
    const fetchMock = global.fetch as jest.Mock;
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: false,
        trade: null,
        cash_balance: 100,
        error: "Insufficient cash",
      }),
    });

    render(
      <TradeBar
        selectedTicker="AAPL"
        currentPrice={190}
        onTradeComplete={() => {}}
      />
    );

    fireEvent.change(screen.getByTestId("trade-ticker"), {
      target: { value: "AAPL" },
    });
    fireEvent.change(screen.getByTestId("trade-quantity"), {
      target: { value: "10000" },
    });
    fireEvent.click(screen.getByTestId("trade-buy"));

    await waitFor(() => {
      expect(screen.getByTestId("trade-feedback")).toHaveTextContent(
        /insufficient cash/i
      );
    });
  });
});
