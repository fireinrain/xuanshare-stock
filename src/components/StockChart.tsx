import { useEffect, useRef, useState, useCallback } from 'react';
import { createChart, CandlestickSeries, HistogramSeries, type IChartApi, type CandlestickData, type HistogramData, type Time, ColorType } from 'lightweight-charts';
import { AncientCard } from './ui/AncientUI';

interface KlineItem {
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  volume: number;
  amount: number;
}

function getSinaSymbol(code: string): string {
  if (code.startsWith('6')) return `sh${code}`;
  if (code.startsWith('4') || code.startsWith('8')) return `bj${code}`;
  return `sz${code}`;
}

interface SinaKlineRaw {
  day: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

function parseSinaKlines(raw: SinaKlineRaw[]): KlineItem[] {
  return raw.map(item => ({
    date: item.day,
    open: parseFloat(item.open),
    close: parseFloat(item.close),
    high: parseFloat(item.high),
    low: parseFloat(item.low),
    volume: parseFloat(item.volume),
    amount: 0,
  }));
}

async function fetchWithTimeout(url: string, timeoutMs = 8000): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function fetchKlineData(code: string, count = 60): Promise<KlineItem[]> {
  const symbol = getSinaSymbol(code);
  const url = `/api/sina/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=${symbol}&scale=240&ma=no&datalen=${count}`;
  const resp = await fetchWithTimeout(url);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const raw: SinaKlineRaw[] = await resp.json();
  if (!Array.isArray(raw) || raw.length === 0) throw new Error('暂无K线数据');
  return parseSinaKlines(raw);
}

function formatVolume(vol: number): string {
  if (vol >= 1e8) return `${(vol / 1e8).toFixed(2)}亿`;
  if (vol >= 1e4) return `${(vol / 1e4).toFixed(0)}万`;
  return String(vol);
}

interface StockChartProps {
  code: string;
  name: string;
}

export function StockChart({ code, name }: StockChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [data, setData] = useState<KlineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const klines = await fetchKlineData(code, 60);
      setData(klines);
      if (klines.length === 0) setError('暂无K线数据');
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [code]);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    if (!chartContainerRef.current || data.length === 0) return;
    if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }
    const container = chartContainerRef.current;
    const chart = createChart(container, {
      width: container.clientWidth,
      height: 340,
      layout: {
        background: { type: ColorType.Solid, color: '#1A1A1A' },
        textColor: '#F5E6D370',
      },
      grid: {
        vertLines: { color: '#C9A96215' },
        horzLines: { color: '#C9A96215' },
      },
      crosshair: { mode: 0 },
      rightPriceScale: {
        borderColor: '#C9A96230',
        scaleMargins: { top: 0.05, bottom: 0.25 },
      },
      timeScale: {
        borderColor: '#C9A96230',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#C9A96230',
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#DC143C',
      downColor: '#228B22',
      borderUpColor: '#DC143C',
      borderDownColor: '#228B22',
      wickUpColor: '#DC143C',
      wickDownColor: '#228B22',
    });

    const candleData: CandlestickData[] = [];
    const volumeData: HistogramData[] = [];
    for (const item of data) {
      const time = item.date as Time;
      candleData.push({ time, open: item.open, high: item.high, low: item.low, close: item.close });
      volumeData.push({ time, value: item.volume, color: item.close >= item.open ? '#DC143C30' : '#228B2230' });
    }
    candleSeries.setData(candleData);
    volumeSeries.setData(volumeData);
    chart.timeScale().fitContent();
    chartRef.current = chart;

    const handleResize = () => {
      if (container.clientWidth > 0) chart.applyOptions({ width: container.clientWidth });
    };
    const observer = new ResizeObserver(handleResize);
    observer.observe(container);
    return () => { observer.disconnect(); chart.remove(); chartRef.current = null; };
  }, [data]);

  const lastPrice = data.length > 0 ? data[data.length - 1].close : null;
  const prevPrice = data.length > 1 ? data[data.length - 2].close : null;
  const change = lastPrice !== null && prevPrice !== null ? lastPrice - prevPrice : 0;
  const changePercent = prevPrice ? (change / prevPrice) * 100 : 0;
  const recentHigh = data.length > 0 ? Math.max(...data.map(d => d.high)) : 0;
  const recentLow = data.length > 0 ? Math.min(...data.map(d => d.low)) : 0;

  return (
    <AncientCard className="!p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-base font-bold text-[#C9A962]">{name} K线图</h3>
          <p className="text-xs text-[#F5E6D3]/40">{code}</p>
        </div>
        {lastPrice !== null && (
          <div className="text-right">
            <div className="text-lg font-bold text-[#F5E6D3]">{lastPrice.toFixed(2)}</div>
            <div className={`text-xs ${change >= 0 ? 'text-red-400' : 'text-green-400'}`}>
              {change >= 0 ? '+' : ''}{change.toFixed(2)} ({changePercent >= 0 ? '+' : ''}{changePercent.toFixed(2)}%)
            </div>
          </div>
        )}
      </div>
      <div className="relative">
        {loading && data.length === 0 && (
          <div className="flex items-center justify-center h-[340px]">
            <div className="w-8 h-8 border-2 border-[#C9A962]/30 border-t-[#C9A962] rounded-full animate-spin" />
          </div>
        )}
        {error && (
          <div className="flex items-center justify-center h-[340px] text-[#F5E6D3]/40 text-sm">{error}</div>
        )}
        <div ref={chartContainerRef} className={data.length === 0 ? 'hidden' : ''} />
      </div>
      {data.length > 0 && (
        <div className="grid grid-cols-4 gap-2 mt-3 text-center text-xs">
          <div className="bg-[#1A1A1A] rounded px-2 py-1.5">
            <div className="text-[#F5E6D3]/40">最高</div>
            <div className="text-red-400">{recentHigh.toFixed(2)}</div>
          </div>
          <div className="bg-[#1A1A1A] rounded px-2 py-1.5">
            <div className="text-[#F5E6D3]/40">最低</div>
            <div className="text-green-400">{recentLow.toFixed(2)}</div>
          </div>
          <div className="bg-[#1A1A1A] rounded px-2 py-1.5">
            <div className="text-[#F5E6D3]/40">成交量</div>
            <div className="text-[#F5E6D3]">{formatVolume(data[data.length - 1].volume)}</div>
          </div>
          <div className="bg-[#1A1A1A] rounded px-2 py-1.5">
            <div className="text-[#F5E6D3]/40">数据量</div>
            <div className="text-[#F5E6D3]">{data.length} 日</div>
          </div>
        </div>
      )}
    </AncientCard>
  );
}