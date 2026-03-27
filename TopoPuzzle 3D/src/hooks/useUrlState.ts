import { useEffect, useState } from 'react';

import type { Dispatch, SetStateAction } from 'react';

import type { BBoxState, GridSize, InitialState, MapViewState, QualityPreset } from '../types';

type UseUrlStateResult = {
  mapView: MapViewState;
  setMapView: Dispatch<SetStateAction<MapViewState>>;
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
};

export function useUrlState(initialState: InitialState, bboxBounds: BBoxState | null): UseUrlStateResult {
  const [mapView, setMapView] = useState<MapViewState>(initialState.mapView);
  const [physicalSize, setPhysicalSize] = useState<number>(initialState.physicalSize);
  const [gridSize, setGridSize] = useState<GridSize>(initialState.gridSize);
  const [qualityPreset, setQualityPreset] = useState<QualityPreset>(initialState.qualityPreset);
  const [zScale, setZScale] = useState<number>(initialState.zScale);
  const [smoothTerrain, setSmoothTerrain] = useState<boolean>(initialState.smoothTerrain);
  const [flattenSeaLevel, setFlattenSeaLevel] = useState<boolean>(initialState.flattenSeaLevel);
  const [includeBuildings, setIncludeBuildings] = useState<boolean>(initialState.includeBuildings);
  const [includeRoads, setIncludeRoads] = useState<boolean>(initialState.includeRoads);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const params = new URLSearchParams(window.location.search);
    params.set('lat', mapView.lat.toFixed(6));
    params.set('lon', mapView.lon.toFixed(6));
    params.set('zoom', String(mapView.zoom));
    params.set('size', String(physicalSize));
    params.set('grid', gridSize);
    params.set('quality', qualityPreset);
    params.set('vertical_exaggeration', zScale.toFixed(1));
    params.set('z', zScale.toFixed(1));
    params.set('smooth', smoothTerrain ? '1' : '0');
    params.set('sea', flattenSeaLevel ? '1' : '0');
    params.set('bldg', includeBuildings ? '1' : '0');
    params.set('roads', includeRoads ? '1' : '0');

    if (bboxBounds) {
      params.set(
        'bbox',
        [
          bboxBounds.south.toFixed(6),
          bboxBounds.west.toFixed(6),
          bboxBounds.north.toFixed(6),
          bboxBounds.east.toFixed(6),
        ].join(','),
      );
    } else {
      params.delete('bbox');
    }

    const next = `${window.location.pathname}?${params.toString()}`;
    const current = `${window.location.pathname}${window.location.search}`;
    if (next !== current) {
      window.history.replaceState(null, '', next);
    }
  }, [
    bboxBounds,
    flattenSeaLevel,
    gridSize,
    includeBuildings,
    includeRoads,
    mapView.lat,
    mapView.lon,
    mapView.zoom,
    physicalSize,
    qualityPreset,
    smoothTerrain,
    zScale,
  ]);

  return {
    mapView,
    setMapView,
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
  };
}
