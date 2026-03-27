/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
/// <reference types="vite/client" />

import { useMemo } from 'react';

import { ControlPanel } from './components/ControlPanel';
import { GenerationProgress } from './components/GenerationProgress';
import { MapView } from './components/MapView';
import { Navbar } from './components/Navbar';
import { useBBox } from './hooks/useBBox';
import { useGenerationJob } from './hooks/useGenerationJob';
import { useUrlState } from './hooks/useUrlState';
import { parseInitialStateFromUrl } from './utils/geo';

export default function App() {
  const initialState = useMemo(() => parseInitialStateFromUrl(), []);
  const bbox = useBBox(initialState.bbox);
  const form = useUrlState(initialState, bbox.bboxBounds);

  const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) || 'http://127.0.0.1:8000';

  const generation = useGenerationJob({
    apiBaseUrl,
    bboxBounds: bbox.bboxBounds,
    physicalSize: form.physicalSize,
    gridSize: form.gridSize,
    qualityPreset: form.qualityPreset,
    zScale: form.zScale,
    smoothTerrain: form.smoothTerrain,
    flattenSeaLevel: form.flattenSeaLevel,
    includeBuildings: form.includeBuildings,
    includeRoads: form.includeRoads,
  });

  return (
    <div className="relative w-full h-screen overflow-hidden font-inter text-slate-700 bg-slate-50">
      <MapView mapView={form.mapView} uiLocked={generation.uiLocked} bbox={bbox} onMapViewChange={form.setMapView} />
      <Navbar />
      <ControlPanel
        bbox={bbox}
        physicalSize={form.physicalSize}
        setPhysicalSize={form.setPhysicalSize}
        gridSize={form.gridSize}
        setGridSize={form.setGridSize}
        qualityPreset={form.qualityPreset}
        setQualityPreset={form.setQualityPreset}
        zScale={form.zScale}
        setZScale={form.setZScale}
        smoothTerrain={form.smoothTerrain}
        setSmoothTerrain={form.setSmoothTerrain}
        flattenSeaLevel={form.flattenSeaLevel}
        setFlattenSeaLevel={form.setFlattenSeaLevel}
        includeBuildings={form.includeBuildings}
        setIncludeBuildings={form.setIncludeBuildings}
        includeRoads={form.includeRoads}
        setIncludeRoads={form.setIncludeRoads}
        uiLocked={generation.uiLocked}
        generationReady={generation.generationReady}
        generationStepIndex={generation.generationStepIndex}
        generationError={generation.generationError}
        onGenerate={generation.handleGenerate}
        onDismissError={generation.dismissError}
      />
      <GenerationProgress
        generationSteps={generation.generationSteps}
        generationStepIndex={generation.generationStepIndex}
        generationReady={generation.generationReady}
        generationError={generation.generationError}
        onDismissError={generation.dismissError}
        onRetry={generation.retry}
      />
    </div>
  );
}
