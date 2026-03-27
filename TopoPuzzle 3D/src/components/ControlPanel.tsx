import { Download, Layers, Maximize, Mountain, Sparkles, CheckCircle2, Loader2 } from 'lucide-react';
import type { Dispatch, SetStateAction } from 'react';

import type { GridSize, QualityPreset } from '../types';
import type { UseBBoxResult } from '../hooks/useBBox';

type ControlPanelProps = {
  bbox: UseBBoxResult;
  physicalSize: number;
  setPhysicalSize: Dispatch<SetStateAction<number>>;
  gridSize: GridSize;
  setGridSize: Dispatch<SetStateAction<GridSize>>;
  qualityPreset: QualityPreset;
  setQualityPreset: Dispatch<SetStateAction<QualityPreset>>;
  zScale: number;
  setZScale: Dispatch<SetStateAction<number>>;
  smoothTerrain: boolean;
  setSmoothTerrain: Dispatch<SetStateAction<boolean>>;
  flattenSeaLevel: boolean;
  setFlattenSeaLevel: Dispatch<SetStateAction<boolean>>;
  includeBuildings: boolean;
  setIncludeBuildings: Dispatch<SetStateAction<boolean>>;
  includeRoads: boolean;
  setIncludeRoads: Dispatch<SetStateAction<boolean>>;
  uiLocked: boolean;
  generationReady: boolean;
  generationStepIndex: number;
  generationError: string | null;
  onGenerate: () => void;
  onDismissError: () => void;
};

const QUALITY_PRESET_OPTIONS: QualityPreset[] = ['Very Low', 'Low', 'Average', 'High', 'Very High'];
const GRID_OPTIONS: GridSize[] = ['2x2', '5x5', '10x10'];

function SettingToggle({
  title,
  description,
  checked,
  disabled,
  onChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-start justify-between gap-4">
      <div className="space-y-1 pr-2">
        <p className="text-sm font-medium text-slate-800">{title}</p>
        <p className="text-xs text-slate-500">{description}</p>
      </div>
      <div className="relative inline-flex flex-shrink-0">
        <input
          type="checkbox"
          className="peer sr-only"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="h-6 w-11 rounded-full bg-slate-300 transition-colors peer-checked:bg-slate-900 peer-disabled:opacity-50"></span>
        <span className="absolute left-[2px] top-[2px] h-5 w-5 rounded-full bg-white shadow-sm transition-transform peer-checked:translate-x-5"></span>
      </div>
    </label>
  );
}

export function ControlPanel({
  bbox,
  physicalSize,
  setPhysicalSize,
  gridSize,
  setGridSize,
  qualityPreset,
  setQualityPreset,
  zScale,
  setZScale,
  smoothTerrain,
  setSmoothTerrain,
  flattenSeaLevel,
  setFlattenSeaLevel,
  includeBuildings,
  setIncludeBuildings,
  includeRoads,
  setIncludeRoads,
  uiLocked,
  generationReady,
  generationStepIndex,
  generationError,
  onGenerate,
  onDismissError,
}: ControlPanelProps) {
  const [piecesXRaw, piecesYRaw] = gridSize.split('x');
  const piecesX = Number(piecesXRaw) || 1;
  const piecesY = Number(piecesYRaw) || 1;
  const pieceWidth = (physicalSize / piecesX).toFixed(1);
  const pieceHeight = (physicalSize / piecesY).toFixed(1);

  return (
    <div className="absolute top-24 right-6 bottom-6 w-full max-w-sm z-40 pointer-events-none flex flex-col justify-end md:justify-start">
      <div className="glass-panel rounded-2xl p-6 flex flex-col gap-8 pointer-events-auto max-h-full overflow-y-auto custom-scrollbar">
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-slate-800">
            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-slate-900/10 text-xs font-bold text-slate-800">
              1
            </span>
            <h2 className="font-semibold tracking-tight text-slate-800">Select Area</h2>
          </div>

          <div className="bg-white/40 border border-slate-200/50 rounded-xl p-4 flex items-center justify-between shadow-sm">
            <div className="space-y-1">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Coordinates</p>
              <p className="font-mono text-sm font-medium text-slate-700">
                {bbox.bboxCenter ? `${bbox.bboxCenter.lat.toFixed(3)}° N, ${bbox.bboxCenter.lng.toFixed(3)}° E` : 'Draw a box'}
              </p>
            </div>
            <div className="text-right space-y-1">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Area</p>
              <p className="font-mono text-sm font-medium text-slate-700">
                {bbox.bboxArea !== null ? `${bbox.bboxArea.toFixed(1)} km²` : '-- km²'}
              </p>
            </div>
          </div>

          <button
            type="button"
            disabled={uiLocked}
            onClick={bbox.createSelectionRectangle}
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white shadow-[0_10px_24px_rgb(15,23,42,0.18)] transition-transform hover:translate-y-[-1px] hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0"
          >
            <Maximize size={16} />
            Draw Box
          </button>
          <p className="text-xs font-mono text-slate-500">
            Creates a new centered selection and replaces the current area.
          </p>
        </div>

        <div className="space-y-5">
          <div className="flex items-center gap-2 text-slate-800">
            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-slate-900/10 text-xs font-bold text-slate-800">
              2
            </span>
            <h2 className="font-semibold tracking-tight text-slate-800">Grid & Size</h2>
          </div>

          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
                <Maximize size={16} className="text-slate-400" />
                Physical Size
              </label>
              <span className="font-mono text-sm font-medium text-slate-800 bg-white/50 border border-slate-200/50 px-2 py-0.5 rounded-md">
                {physicalSize}mm
              </span>
            </div>
            <input
              type="range"
              min="200"
              max="1000"
              step="50"
              value={physicalSize}
              disabled={uiLocked}
              onChange={(e) => setPhysicalSize(Number(e.target.value))}
              className="custom-slider w-full"
            />
            <div className="flex justify-between text-xs font-mono text-slate-400">
              <span>200mm</span>
              <span>1000mm</span>
            </div>
          </div>

          <div className="space-y-3">
            <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
              <Layers size={16} className="text-slate-400" />
              Puzzle Grid
            </label>
            <div className="grid grid-cols-3 gap-2">
              {GRID_OPTIONS.map((grid) => (
                <button
                  key={grid}
                  disabled={uiLocked}
                  onClick={() => setGridSize(grid)}
                  className={`py-2 px-3 rounded-xl text-sm font-medium transition-all disabled:opacity-50 ${
                    gridSize === grid
                      ? 'bg-slate-900 text-white shadow-[0_8px_24px_rgb(15,23,42,0.22)]'
                      : 'bg-white/50 border border-slate-200/50 text-slate-600 hover:border-slate-400 hover:bg-white'
                  }`}
                >
                  {grid}
                </button>
              ))}
            </div>
            <p className="text-xs text-center font-mono text-slate-500 mt-2">
              Each piece: {pieceWidth} x {pieceHeight} mm
            </p>
          </div>

          <div className="space-y-3">
            <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
              <Sparkles size={16} className="text-slate-400" />
              Quality Preset
            </label>
            <select
              value={qualityPreset}
              disabled={uiLocked}
              onChange={(e) => setQualityPreset(e.target.value as QualityPreset)}
              className="w-full rounded-xl border border-slate-200/70 bg-white/70 px-3 py-2 text-sm text-slate-700 shadow-sm focus:border-slate-400 focus:outline-none disabled:opacity-50"
            >
              {QUALITY_PRESET_OPTIONS.map((preset) => (
                <option key={preset} value={preset}>
                  {preset}
                </option>
              ))}
            </select>
            <p className="text-xs text-slate-500">Controls DEM sample resolution for terrain detail.</p>
          </div>
        </div>

        <div className="space-y-5">
          <div className="flex items-center gap-2 text-slate-800">
            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-slate-900/10 text-xs font-bold text-slate-800">
              3
            </span>
            <h2 className="font-semibold tracking-tight text-slate-800">Vertical Exaggeration</h2>
          </div>

          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
                <Mountain size={16} className="text-slate-400" />
                Vertical Exaggeration
              </label>
              <span className="font-mono text-sm font-medium text-slate-800 bg-white/50 border border-slate-200/50 px-2 py-0.5 rounded-md">
                {zScale.toFixed(1)}x
              </span>
            </div>
            <input
              type="range"
              min="1"
              max="3"
              step="0.1"
              value={zScale}
              disabled={uiLocked}
              onChange={(e) => setZScale(Number(e.target.value))}
              className="custom-slider w-full"
            />
          </div>
        </div>

        <div className="space-y-4">
          <div className="flex items-center gap-2 text-slate-800">
            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-slate-900/10 text-xs font-bold text-slate-800">
              4
            </span>
            <h2 className="font-semibold tracking-tight text-slate-800">Pro Settings</h2>
          </div>

          <SettingToggle
            title="Smooth Terrain (Bilinear Interpolation)"
            description="Eliminates 'staircase' artifacts on high zooms."
            checked={smoothTerrain}
            disabled={uiLocked}
            onChange={setSmoothTerrain}
          />

          <SettingToggle
            title="Flatten Sea Level"
            description="Forces 0m elevation to be perfectly flat for islands/coastlines."
            checked={flattenSeaLevel}
            disabled={uiLocked}
            onChange={setFlattenSeaLevel}
          />

          <SettingToggle
            title="Include OSM Buildings"
            description="Extrudes building volumes on top of the DEM terrain."
            checked={includeBuildings}
            disabled={uiLocked}
            onChange={setIncludeBuildings}
          />

          <SettingToggle
            title="Include OSM Roads"
            description="Adds raised road overlays clipped to the selected area."
            checked={includeRoads}
            disabled={uiLocked}
            onChange={setIncludeRoads}
          />
        </div>

        <div className="pt-4 mt-auto border-t border-slate-200/50">
          <button
            onClick={onGenerate}
            disabled={uiLocked || !bbox.bboxBounds}
            className="w-full relative group overflow-hidden rounded-xl bg-slate-900 text-white font-semibold py-4 px-6 shadow-[0_10px_30px_rgb(15,23,42,0.26)] transition-all hover:bg-slate-800 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100"
          >
            <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAiIGhlaWdodD0iMjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMiIgY3k9IjIiIHI9IjIiIGZpbGw9IiNmZmZmZmYiIGZpbGwtb3BhY2l0eT0iMC4xIi8+PC9zdmc+')] opacity-0 group-hover:opacity-100 transition-opacity"></div>
            <span className="relative flex items-center justify-center gap-2">
              {generationReady ? (
                <>
                  <CheckCircle2 size={20} className="text-emerald-300" />
                  Ready!
                </>
              ) : generationStepIndex >= 0 ? (
                <>
                  <Loader2 size={20} className="animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <Download size={20} className="group-hover:-translate-y-0.5 transition-transform" />
                  Generate 3MF
                </>
              )}
            </span>
          </button>

          <p className="text-center text-xs text-slate-500 mt-4 leading-relaxed">
            {!bbox.bboxBounds
              ? 'Please draw a selection box on the map first.'
              : 'Settings and map state are encoded in URL for shareable links.'}
          </p>
          {generationError && (
            <button
              type="button"
              onClick={onDismissError}
              className="mt-3 w-full rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-left text-sm text-rose-700 shadow-sm transition-colors hover:bg-rose-100"
            >
              <span className="block font-semibold">Generation failed</span>
              <span className="block mt-1 leading-6">{generationError}</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
