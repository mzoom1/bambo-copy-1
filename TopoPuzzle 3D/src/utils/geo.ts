import * as L from 'leaflet';

import type { BBoxState, BBoxStats, GridSize, InitialState, QualityPreset } from '../types';

export const DEFAULT_STATE: InitialState = {
  mapView: { lat: 46.0207, lon: 7.7491, zoom: 12 },
  physicalSize: 400,
  gridSize: '5x5',
  qualityPreset: 'Very Low',
  zScale: 2.0,
  smoothTerrain: true,
  flattenSeaLevel: true,
  includeBuildings: false,
  includeRoads: false,
  bbox: null,
};

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function parseBool(value: string | null, fallback: boolean): boolean {
  if (value === null) return fallback;
  return value === '1' || value.toLowerCase() === 'true';
}

export function parseGrid(value: string | null): GridSize {
  if (value === '2x2' || value === '5x5' || value === '10x10') return value;
  return DEFAULT_STATE.gridSize;
}

export function parseQualityPreset(value: string | null): QualityPreset {
  if (!value) return DEFAULT_STATE.qualityPreset;
  const normalized = value.toLowerCase();
  if (normalized === 'very low' || normalized === 'very low (fastest)') return 'Very Low';
  if (normalized === 'low') return 'Low';
  if (normalized === 'average') return 'Average';
  if (normalized === 'high') return 'High';
  if (normalized === 'very high') return 'Very High';
  return DEFAULT_STATE.qualityPreset;
}

export function parseBBox(value: string | null): BBoxState | null {
  if (!value) return null;
  const parts = value.split(',').map((p) => Number(p.trim()));
  if (parts.length !== 4 || parts.some((n) => !Number.isFinite(n))) return null;

  const [south, west, north, east] = parts;
  if (south >= north || west >= east) return null;
  return { south, west, north, east };
}

export function parseInitialStateFromUrl(): InitialState {
  if (typeof window === 'undefined') return DEFAULT_STATE;

  const params = new URLSearchParams(window.location.search);
  const lat = Number(params.get('lat'));
  const lon = Number(params.get('lon'));
  const zoom = Number(params.get('zoom'));
  const size = Number(params.get('size'));
  const verticalExaggerationRaw =
    params.get('vertical_exaggeration') ?? params.get('verticalExaggeration') ?? params.get('zScale') ?? params.get('z');
  const verticalExaggeration = Number(verticalExaggerationRaw);

  return {
    mapView: {
      lat: Number.isFinite(lat) ? clamp(lat, -85, 85) : DEFAULT_STATE.mapView.lat,
      lon: Number.isFinite(lon) ? clamp(lon, -180, 180) : DEFAULT_STATE.mapView.lon,
      zoom: Number.isFinite(zoom) ? clamp(zoom, 2, 18) : DEFAULT_STATE.mapView.zoom,
    },
    physicalSize: Number.isFinite(size) ? clamp(Math.round(size), 200, 1000) : DEFAULT_STATE.physicalSize,
    gridSize: parseGrid(params.get('grid')),
    qualityPreset: parseQualityPreset(params.get('quality')),
    zScale: Number.isFinite(verticalExaggeration) ? clamp(Number(verticalExaggeration.toFixed(1)), 1, 3) : DEFAULT_STATE.zScale,
    smoothTerrain: parseBool(params.get('smooth'), DEFAULT_STATE.smoothTerrain),
    flattenSeaLevel: parseBool(params.get('sea'), DEFAULT_STATE.flattenSeaLevel),
    includeBuildings: parseBool(params.get('bldg'), DEFAULT_STATE.includeBuildings),
    includeRoads: parseBool(params.get('roads'), DEFAULT_STATE.includeRoads),
    bbox: parseBBox(params.get('bbox')),
  };
}

export function haversineMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const radiusMeters = 6_371_000;
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const phi1 = toRad(lat1);
  const phi2 = toRad(lat2);

  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.sin(dLon / 2) ** 2 * Math.cos(phi1) * Math.cos(phi2);

  return 2 * radiusMeters * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function calculateBBoxStats(bounds: L.LatLngBounds): BBoxStats {
  const northEast = bounds.getNorthEast();
  const southWest = bounds.getSouthWest();
  const bbox: BBoxState = {
    south: southWest.lat,
    west: southWest.lng,
    north: northEast.lat,
    east: northEast.lng,
  };

  const center = bounds.getCenter();

  let areaMeters = 0;
  const geometryUtil = (L as unknown as { GeometryUtil?: { geodesicArea?: (latLngs: L.LatLng[]) => number } }).GeometryUtil;
  if (geometryUtil?.geodesicArea) {
    const points = [
      L.latLng(bbox.south, bbox.west),
      L.latLng(bbox.south, bbox.east),
      L.latLng(bbox.north, bbox.east),
      L.latLng(bbox.north, bbox.west),
    ];
    areaMeters = geometryUtil.geodesicArea(points);
  } else {
    const width = haversineMeters(bbox.south, bbox.west, bbox.south, bbox.east);
    const height = haversineMeters(bbox.south, bbox.west, bbox.north, bbox.west);
    areaMeters = width * height;
  }

  return {
    center: { lat: center.lat, lng: center.lng },
    areaKm2: areaMeters / 1_000_000,
    bbox,
  };
}

export function normalizeGenerationErrorMessage(message: string): string {
  const trimmed = message.trim();
  if (!trimmed) return 'Generation failed.';
  const lower = trimmed.toLowerCase();
  if (lower.includes('failed to fetch') || lower.includes('networkerror')) {
    return 'Cannot connect to backend API. Start server.py first.';
  }
  return trimmed;
}

