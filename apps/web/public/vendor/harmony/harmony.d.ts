// ergOS Harmony: window.ErgOS. Components are HTML with eg- classes (see each component's README);
// these functions draw the charts, icons and folder glass. Documentation, not type-checked.

export type SeriesKey = 'solar' | 'wind' | 'hydro' | 'iex' | 'grid' | 'battery' | 'gov' | 'demand';
export type Palette = 'harmony' | 'volt' | 'verdant' | 'aurora';

export interface HoverRow { slot: number; block: number; time: string; demand: number; iex?: number; grid?: number; [series: string]: number | string | undefined }

export interface SupplyChartOptions {
  demand?: number[];                     // 96 kW values, one per 15-minute block
  layers?: { key: SeriesKey; label: string; values?: number[] }[]; // stacked bottom-up; a layer without values fills to demand
  now?: number;                          // index of the latest block (0-95)
  height?: number;                       // px, default 340
  yMax?: number;                         // kW, default: nice step above the peak
  palette?: Palette;
  forecast?: boolean;                    // dotted demand after now, default true
  label?: string;                        // accessible name
  onHover?: (row: HoverRow) => void;     // drives a ReadoutStrip; called with the latest block at rest
}
export interface AreaSeries { key: SeriesKey; label?: string; values: (number | null)[]; dashed?: boolean; fill?: boolean }
export interface AreaChartOptions {
  series: AreaSeries[]; stacked?: boolean;
  line?: { label?: string; values: (number | null)[]; forecast?: boolean };  // dotted overlay, e.g. demand
  now?: number | null; cursor?: number; cursorMax?: number; focus?: SeriesKey;
  height?: number; yMax?: number; yAxis?: boolean; unit?: string; slots?: boolean;
  format?: (v: number) => string; xLabel?: (i: number) => string; label?: string;
  onHover?: (row: { index: number; label: string; focus: SeriesKey | null; line: number | null; [key: string]: unknown }) => void;
}
export interface ChartApi { redraw(): void; setCursor(i: number): void; palette(name: Palette): void; cursor: number }
export interface VoiceBarOptions {
  live?: boolean;                          // read the microphone level for the waveform
  demo?: boolean;                          // scripted demo when no onMic is given (default true)
  question?: string; answer?: string; placeholder?: string;
  onMic?: (state: 'idle' | 'listening' | 'thinking' | 'speaking', api: VoiceBarApi) => void;
  onKeyboard?: (api: VoiceBarApi) => void;
}
export interface VoiceBarApi { setState(s: 'idle' | 'listening' | 'thinking' | 'speaking', text?: string): void; setText(t: string): void; demo(): void; state(): string; stop(): void }
export interface SavingsChartOptions { labels?: string[]; savings?: number[]; volume?: number[]; height?: number }
export interface HeatmapOptions { rows?: { label: string; values: number[] }[]; max?: number; series?: SeriesKey; rowHeight?: number }
export interface RingOptions { parts?: { key: SeriesKey; value: number }[]; size?: number; stroke?: number; label?: string }
export interface SparklineOptions { series?: SeriesKey; height?: number; zero?: boolean; label?: string }

export interface ErgOS {
  /** Inline SVG string for a 24px line icon. */
  icon(name: string, size?: number): string;
  icons: string[];
  /** Mounts [data-icon] spans and shapes every .eg-folder__front under root. Runs once on load. */
  mount(root?: ParentNode): void;
  /** Cuts one folder front into the folder shape and keeps it shaped on resize. */
  folder(front: HTMLElement): void;
  supplyChart(host: HTMLElement, opts?: SupplyChartOptions): ChartApi;
  /** Overlaid series, e.g. actual vs forecast. */
  trendChart(host: HTMLElement, opts?: { series?: AreaSeries[]; now?: number; cursor?: number; height?: number; palette?: Palette; unit?: string; xLabel?: (i: number) => string; slots?: boolean; yAxis?: boolean; onHover?: AreaChartOptions['onHover'] }): ChartApi;
  /** The engine behind supplyChart and trendChart. */
  areaChart(host: HTMLElement, opts: AreaChartOptions): ChartApi;
  /** Applies a colour scheme class to a container. */
  palette(el: HTMLElement, name: Palette): void;
  palettes: Palette[];
  sources: Record<SeriesKey, { label: string; icon: string }>;
  /** AI real talk bar. */
  voiceBar(el: HTMLElement, opts?: VoiceBarOptions): VoiceBarApi;
  savingsChart(host: HTMLElement, opts?: SavingsChartOptions): { redraw(): void };
  heatmap(host: HTMLElement, opts?: HeatmapOptions): { redraw(): void };
  ring(host: HTMLElement, opts?: RingOptions): void;
  sparkline(host: HTMLElement, values: number[], opts?: SparklineOptions): { redraw(): void };
  miniBars(host: HTMLElement, values: number[], series?: SeriesKey): void;
  /** Indian digit grouping: inr(391192.06, 2) === "3,91,192.06". */
  inr(n: number, decimals?: number): string;
  /** Axis labels: 12.5k, 3.9 L, 1.2 Cr. */
  compact(n: number): string;
  /** Clock time at the start of a block index: slotTime(36) === "09:00". */
  slotTime(index: number): string;
  /** Example data used by the previews (HALDIRAM C1, 13 Oct 2026). Illustrative only. */
  sample: { demand: number[]; iex: number[]; solar: number[]; wind: number[]; hydro: number[]; forecast: number[]; now: number; days: string[]; savings: number[]; volume: number[]; heat: { label: string; values: number[] }[] };
}
declare global { interface Window { ErgOS: ErgOS } }
