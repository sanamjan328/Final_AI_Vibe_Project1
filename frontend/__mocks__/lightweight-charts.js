// Jest mock for lightweight-charts to avoid pulling in canvas-based code in jsdom.
const mkSeries = () => ({
  setData: jest.fn(),
  applyOptions: jest.fn(),
  update: jest.fn(),
});

const mkChart = () => ({
  addSeries: jest.fn(mkSeries),
  applyOptions: jest.fn(),
  remove: jest.fn(),
  timeScale: () => ({ fitContent: jest.fn() }),
});

module.exports = {
  createChart: jest.fn(mkChart),
  LineSeries: "LineSeries",
  AreaSeries: "AreaSeries",
  CandlestickSeries: "CandlestickSeries",
};
