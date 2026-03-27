/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
/// <reference types="vite/client" />

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Map as MapIcon,
  Layers,
  Maximize,
  Mountain,
  Download,
  Menu,
  CheckCircle2,
  Loader2,
  Sparkles,
} from 'lucide-react';
import { FeatureGroup, MapContainer, TileLayer, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet-draw';

type GridSize = '2x2' | '5x5' | '10x10';
type QualityPreset = 'Very Low' | 'Low' | 'Average' | 'High' | 'Very High';
const QUALITY_PRESET_OPTIONS: QualityPreset[] = ['Very Low', 'Low', 'Average', 'High', 'Very High'];

type JobState = 'queued' | 'running' | 'done' | 'failed';

interface JobResponse {
  jobId: string;
  status: 'queued';
}

interface JobStatus {
  job_id: string;
  status: JobState;
  progress: number;
  created_at: string;
  updated_at: string;
  output_path?: string | null;
  error?: string | null;
  filename?: string | null;
}

type MapViewState = {
  lat: number;
  lon: number;
  zoom: number;
};

type BBoxState = {
  south: number;
  west: number;
  north: number;
  east: number;
};

type InitialState = {
  mapView: MapViewState;
  physicalSize: number;
  gridSize: GridSize;
  qualityPreset: QualityPreset;
  zScale: number;
  smoothTerrain: boolean;
  flattenSeaLevel: boolean;
  includeBuildings: boolean;
  includeRoads: boolean;
  bbox: BBoxState | null;
};

const DEFAULT_STATE: InitialState = {
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

const DRAW_SHAPE_OPTIONS: L.PathOptions = {
  color: '#0f172a',
  weight: 2,
  fillOpacity: 0.1,
  dashArray: '5,5',
};

// Fix for default Leaflet icon paths
// eslint-disable-next-line @typescript-eslint/no-explicit-any
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function parseBool(value: string | null, fallback: boolean): boolean {
  if (value === null) return fallback;
  return value === '1' || value.toLowerCase() === 'true';
}

function parseGrid(value: string | null): GridSize {
  if (value === '2x2' || value === '5x5' || value === '10x10') return value;
  return DEFAULT_STATE.gridSize;
}

function parseQualityPreset(value: string | null): QualityPreset {
  if (!value) return DEFAULT_STATE.qualityPreset;
  const normalized = value.toLowerCase();
  if (normalized === 'very low' || normalized === 'very low (fastest)') return 'Very Low';
  if (normalized === 'low') return 'Low';
  if (normalized === 'average') return 'Average';
  if (normalized === 'high') return 'High';
  if (normalized === 'very high') return 'Very High';
  return DEFAULT_STATE.qualityPreset;
}

function parseBBox(value: string | null): BBoxState | null {
  if (!value) return null;
  const parts = value.split(',').map((p) => Number(p.trim()));
  if (parts.length !== 4 || parts.some((n) => !Number.isFinite(n))) return null;

  const [south, west, north, east] = parts;
  if (south >= north || west >= east) return null;
  return { south, west, north, east };
}

async function extractApiErrorMessage(response: Response): Promise<string> {
  const fallback = `HTTP ${response.status}`;
  const bodyText = await response.text().catch(() => '');
  const trimmed = bodyText.trim();
  if (!trimmed) return fallback;

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      const payload = JSON.parse(trimmed) as { detail?: unknown };
      if (typeof payload?.detail === 'string' && payload.detail.trim()) {
        return payload.detail;
      }
      if (Array.isArray(payload?.detail) && payload.detail.length > 0) {
        const first = payload.detail[0] as { msg?: string } | undefined;
        if (first?.msg) return first.msg;
      }
      if (payload?.detail) return JSON.stringify(payload.detail);
    } catch {
      // fall through to raw body text
    }
  }

  return trimmed;
}

function extractJobErrorMessage(job: JobStatus): string {
  return normalizeGenerationErrorMessage(job.error || 'Generation failed.');
}

function normalizeGenerationErrorMessage(message: string): string {
  const trimmed = message.trim();
  if (!trimmed) return 'Generation failed.';
  const lower = trimmed.toLowerCase();
  if (lower.includes('failed to fetch') || lower.includes('networkerror')) {
    return 'Cannot connect to backend API. Start server.py first.';
  }
  return trimmed;
}

function parseInitialStateFromUrl(): InitialState {
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

function haversineMeters(a: L.LatLng, b: L.LatLng): number {
  const R = 6371000;
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);

  const x =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.sin(dLon / 2) * Math.sin(dLon / 2) * Math.cos(lat1) * Math.cos(lat2);

  return 2 * R * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}

function calculateBBoxStats(bounds: L.LatLngBounds): {
  center: { lat: number; lng: number };
  areaKm2: number;
  bbox: BBoxState;
} {
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
    // Fallback approximation if GeometryUtil is unavailable.
    const width = haversineMeters(L.latLng(bbox.south, bbox.west), L.latLng(bbox.south, bbox.east));
    const height = haversineMeters(L.latLng(bbox.south, bbox.west), L.latLng(bbox.north, bbox.west));
    areaMeters = width * height;
  }

  return {
    center: { lat: center.lat, lng: center.lng },
    areaKm2: areaMeters / 1_000_000,
    bbox,
  };
}

type MapEventBridgeProps = {
  onViewChange: (next: MapViewState) => void;
  onMapReady: (map: L.Map) => void;
};

function MapEventBridge({ onViewChange, onMapReady }: MapEventBridgeProps) {
  const map = useMapEvents({
    moveend: () => {
      const c = map.getCenter();
      onViewChange({ lat: c.lat, lon: c.lng, zoom: map.getZoom() });
    },
    zoomend: () => {
      const c = map.getCenter();
      onViewChange({ lat: c.lat, lon: c.lng, zoom: map.getZoom() });
    },
  });

  useEffect(() => {
    onMapReady(map);
    const c = map.getCenter();
    onViewChange({ lat: c.lat, lon: c.lng, zoom: map.getZoom() });
  }, [map, onMapReady, onViewChange]);

  return null;
}

export default function App() {
  const initialStateRef = useRef<InitialState>(parseInitialStateFromUrl());
  const initial = initialStateRef.current;
  const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) || 'http://127.0.0.1:8000';

  const [mapView, setMapView] = useState<MapViewState>(initial.mapView);
  const [physicalSize, setPhysicalSize] = useState<number>(initial.physicalSize);
  const [gridSize, setGridSize] = useState<GridSize>(initial.gridSize);
  const [qualityPreset, setQualityPreset] = useState<QualityPreset>(initial.qualityPreset);
  const [zScale, setZScale] = useState<number>(initial.zScale);

  const [smoothTerrain, setSmoothTerrain] = useState<boolean>(initial.smoothTerrain);
  const [flattenSeaLevel, setFlattenSeaLevel] = useState<boolean>(initial.flattenSeaLevel);
  const [includeBuildings, setIncludeBuildings] = useState<boolean>(initial.includeBuildings);
  const [includeRoads, setIncludeRoads] = useState<boolean>(initial.includeRoads);

  const [bboxArea, setBboxArea] = useState<number | null>(null);
  const [bboxCenter, setBboxCenter] = useState<{ lat: number; lng: number } | null>(null);
  const [bboxBounds, setBboxBounds] = useState<BBoxState | null>(initial.bbox);
  const [mapReady, setMapReady] = useState<boolean>(false);
  const [featureGroupReady, setFeatureGroupReady] = useState<boolean>(false);

  // Generation state
  const [generationStepIndex, setGenerationStepIndex] = useState<number>(-1);
  const [generationReady, setGenerationReady] = useState<boolean>(false);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [pendingDownload, setPendingDownload] = useState<{ blob: Blob; fileName: string } | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const featureGroupRef = useRef<L.FeatureGroup | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const restoredBBoxRef = useRef<boolean>(false);

  useEffect(() => {
    if (!featureGroupReady && featureGroupRef.current) {
      setFeatureGroupReady(true);
    }
  });

  const gridParts = gridSize.split('x').map(Number);
  const piecesX = gridParts[0] || 1;
  const piecesY = gridParts[1] || 1;
  const pieceWidth = (physicalSize / piecesX).toFixed(1);
  const pieceHeight = (physicalSize / piecesY).toFixed(1);

  const generationSteps = useMemo(
    () => [
      'Submitting generation job...',
      'Generating full map model...',
      'Slicing mesh into puzzle grid...',
      'Packing multi-color 3MF...',
      'Done! Download starting.',
    ],
    []
  );

  const uiLocked = generationStepIndex >= 0 || generationReady;

  const writeUrlState = useCallback(() => {
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
        ].join(',')
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
    mapView,
    physicalSize,
    gridSize,
    qualityPreset,
    zScale,
    smoothTerrain,
    flattenSeaLevel,
    includeBuildings,
    includeRoads,
    bboxBounds,
  ]);

  useEffect(() => {
    writeUrlState();
  }, [writeUrlState]);

  const updateBBoxFromLayer = useCallback((layer: L.Rectangle | L.Polygon) => {
    const stats = calculateBBoxStats(layer.getBounds());
    setBboxCenter(stats.center);
    setBboxArea(stats.areaKm2);
    setBboxBounds(stats.bbox);
  }, []);

  const syncBBoxFromEditEvent = useCallback((event: { layer?: L.Layer; target?: L.Layer }) => {
    const candidate = event.layer ?? event.target;
    if (!candidate) return;

    const maybeBoundsLayer = candidate as { getBounds?: () => L.LatLngBounds };
    if (typeof maybeBoundsLayer.getBounds !== 'function') return;

    const bounds = maybeBoundsLayer.getBounds();
    const stats = calculateBBoxStats(bounds);
    setBboxCenter(stats.center);
    setBboxArea(stats.areaKm2);
    setBboxBounds(stats.bbox);
  }, []);

  const createCenteredSelectionBounds = useCallback((map: L.Map): L.LatLngBounds => {
    const viewBounds = map.getBounds();
    const center = viewBounds.getCenter();

    // Keep the starter box comfortably inside the viewport and centered.
    const latSpan = Math.abs(viewBounds.getNorth() - viewBounds.getSouth());
    const lngSpan = Math.abs(viewBounds.getEast() - viewBounds.getWest());
    // Start with a compact centered box so it feels easier to grab and resize.
    const halfLat = Math.max(0.01, latSpan * 0.125);
    const halfLng = Math.max(0.01, lngSpan * 0.125);

    const south = clamp(center.lat - halfLat, -85, 85);
    const north = clamp(center.lat + halfLat, -85, 85);
    const west = clamp(center.lng - halfLng, -180, 180);
    const east = clamp(center.lng + halfLng, -180, 180);
    return L.latLngBounds([[south, west], [north, east]]);
  }, []);

  const handleMapReady = useCallback((map: L.Map) => {
    mapRef.current = map;
    setMapReady(true);
  }, []);

  const handleMapViewChange = useCallback((next: MapViewState) => {
    setMapView((prev) => {
      if (
        Math.abs(prev.lat - next.lat) < 1e-7 &&
        Math.abs(prev.lon - next.lon) < 1e-7 &&
        prev.zoom === next.zoom
      ) {
        return prev;
      }
      return next;
    });
  }, []);

  const enableSelectionEditing = useCallback(
    (layer: L.Layer) => {
      const candidate = layer as L.Rectangle | L.Polygon;
      const anyLayer = candidate as unknown as {
        editing?: { enable?: () => void };
        on?: (event: string, handler: () => void) => void;
      };

      try {
        anyLayer.editing?.enable?.();
      } catch {
        // If the handler is unavailable on a transient render, keep the bbox logic working.
      }

      anyLayer.on?.('click', () => {
        try {
          anyLayer.editing?.enable?.();
        } catch {
          // Re-arming editing is best-effort only.
        }
      });

      anyLayer.on?.('edit', () => updateBBoxFromLayer(candidate));
      anyLayer.on?.('editmove', () => updateBBoxFromLayer(candidate));
      anyLayer.on?.('editresize', () => updateBBoxFromLayer(candidate));
      anyLayer.on?.('dragend', () => updateBBoxFromLayer(candidate));
    },
    [updateBBoxFromLayer]
  );

  const createSelectionRectangle = useCallback(() => {
    const map = mapRef.current;
    const fg = featureGroupRef.current;
    if (!map || !fg) return;

    const bounds = createCenteredSelectionBounds(map);
    const rect = L.rectangle(bounds, { ...DRAW_SHAPE_OPTIONS });

    fg.clearLayers();
    fg.addLayer(rect);
    enableSelectionEditing(rect);
    updateBBoxFromLayer(rect);
    map.fitBounds(rect.getBounds(), { padding: [48, 48] });
  }, [createCenteredSelectionBounds, enableSelectionEditing, updateBBoxFromLayer]);

  const onEdited = useCallback(
    (e: { layers: L.LayerGroup }) => {
      let updated = false;
      e.layers.eachLayer((layer) => {
        const candidate = layer as { getBounds?: () => L.LatLngBounds };
        if (typeof candidate.getBounds === 'function') {
          updateBBoxFromLayer(layer as L.Rectangle | L.Polygon);
          updated = true;
        }
      });

      // Some Leaflet-Draw flows can emit a layer subclass that doesn't satisfy
      // the instanceof checks reliably, so keep the authoritative bbox in state.
      if (!updated && bboxBounds) {
        setBboxBounds((prev) => prev);
      }
    },
    [bboxBounds, updateBBoxFromLayer]
  );

  const onEditMove = useCallback((e: { layer?: L.Layer; target?: L.Layer }) => {
    syncBBoxFromEditEvent(e);
  }, [syncBBoxFromEditEvent]);

  const onEditResize = useCallback((e: { layer?: L.Layer; target?: L.Layer }) => {
    syncBBoxFromEditEvent(e);
  }, [syncBBoxFromEditEvent]);

  const onDeleted = useCallback(() => {
    setBboxArea(null);
    setBboxCenter(null);
    setBboxBounds(null);
    featureGroupRef.current?.clearLayers();
  }, []);

  const resolveActiveBBox = useCallback((): BBoxState | null => {
    return bboxBounds;
  }, [bboxBounds]);

  // Restore rectangle from URL once map + FeatureGroup are mounted.
  useEffect(() => {
    if (restoredBBoxRef.current) return;
    if (!mapReady || !featureGroupReady) return;

    const map = mapRef.current;
    const fg = featureGroupRef.current;
    if (!map || !fg) return;

    restoredBBoxRef.current = true;

    if (!initial.bbox) {
      createSelectionRectangle();
      return;
    }

    const rect = L.rectangle(
      [
        [initial.bbox.south, initial.bbox.west],
        [initial.bbox.north, initial.bbox.east],
      ],
      { ...DRAW_SHAPE_OPTIONS }
    );

    fg.clearLayers();
    fg.addLayer(rect);
    enableSelectionEditing(rect);
    updateBBoxFromLayer(rect);
    map.fitBounds(rect.getBounds(), { padding: [48, 48] });
  }, [createSelectionRectangle, enableSelectionEditing, featureGroupReady, initial.bbox, mapReady, updateBBoxFromLayer]);

  const submitGenerationJob = useCallback(async () => {
    const currentBBox = resolveActiveBBox();
    if (!currentBBox) {
      throw new Error('Please draw a selection box first.');
    }

    const rawSouth = Number(currentBBox.south);
    const rawWest = Number(currentBBox.west);
    const rawNorth = Number(currentBBox.north);
    const rawEast = Number(currentBBox.east);

    if (![rawSouth, rawWest, rawNorth, rawEast].every(Number.isFinite)) {
      throw new Error('Invalid bounding box values. Please redraw the selection.');
    }

    // Normalize bounds to avoid ordering issues from draw direction/edit handles.
    let south = Math.min(rawSouth, rawNorth);
    let north = Math.max(rawSouth, rawNorth);
    let west = Math.min(rawWest, rawEast);
    let east = Math.max(rawWest, rawEast);

    // Defensive fix for occasional collapsed bounds from draw/edit events.
    const EPS = 1e-6;
    if (south === north) {
      south -= EPS;
      north += EPS;
    }
    if (west === east) {
      west -= EPS;
      east += EPS;
    }

    const response = await fetch(`${apiBaseUrl}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bbox: {
          minLon: west,
          minLat: south,
          maxLon: east,
          maxLat: north,
        },
        physicalSizeMm: physicalSize,
        rows: piecesY,
        columns: piecesX,
        qualityPreset,
        vertical_exaggeration: zScale,
        zScale,
        base_thickness_mm: 5.0,
        smoothTerrain,
        flattenSeaLevel,
        includeBuildings,
        includeRoads,
      }),
    });

    if (!response.ok) {
      throw new Error(await extractApiErrorMessage(response));
    }

    const submitPayload = (await response.json()) as JobResponse;
    if (!submitPayload?.jobId) {
      throw new Error('Backend did not return a job id.');
    }

    return submitPayload.jobId;
  }, [
    apiBaseUrl,
    resolveActiveBBox,
    physicalSize,
    piecesX,
    piecesY,
    qualityPreset,
    zScale,
    smoothTerrain,
    flattenSeaLevel,
    includeBuildings,
    includeRoads,
  ]);

  const downloadCompletedJob = useCallback(
    async (jobId: string) => {
      const downloadResponse = await fetch(`${apiBaseUrl}/jobs/${encodeURIComponent(jobId)}/download`);
      if (!downloadResponse.ok) {
        throw new Error(await extractApiErrorMessage(downloadResponse));
      }

      const blob = await downloadResponse.blob();
      if (!blob || blob.size === 0) {
        throw new Error('Backend returned an empty 3MF file.');
      }

      const defaultName = `topopuzzle_${piecesY}x${piecesX}_${physicalSize}mm.3mf`;
      const contentDisposition = downloadResponse.headers.get('content-disposition') || '';
      const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
      const asciiMatch = contentDisposition.match(/filename="?([^"]+)"?/i);

      let fileName = defaultName;
      if (utf8Match?.[1]) {
        fileName = decodeURIComponent(utf8Match[1]);
      } else if (asciiMatch?.[1]) {
        fileName = asciiMatch[1];
      }

      return { blob, fileName };
    },
    [apiBaseUrl, piecesX, piecesY, physicalSize]
  );

  const handleGenerate = useCallback(() => {
    if (!bboxBounds || uiLocked) return;

    setGenerationError(null);
    setGenerationReady(false);
    setPendingDownload(null);
    setGenerationStepIndex(0);
    setActiveJobId(null);

    void (async () => {
      try {
        const jobId = await submitGenerationJob();
        setActiveJobId(jobId);
      } catch (err) {
        const rawMessage = err instanceof Error ? err.message : 'Generation failed.';
        const message = normalizeGenerationErrorMessage(rawMessage);
        setGenerationError(message);
        setGenerationStepIndex(-1);
        setGenerationReady(false);
        setPendingDownload(null);
        setActiveJobId(null);
      }
    })();
  }, [bboxBounds, uiLocked, submitGenerationJob]);

  useEffect(() => {
    if (!activeJobId) return;

    let cancelled = false;
    let timeoutHandle: number | null = null;

    const pollJob = async () => {
      try {
        for (;;) {
          const jobResponse = await fetch(`${apiBaseUrl}/jobs/${encodeURIComponent(activeJobId)}`);
          if (!jobResponse.ok) {
            throw new Error(await extractApiErrorMessage(jobResponse));
          }

          const job = (await jobResponse.json()) as JobStatus;
          if (cancelled) return;

          if (job.status === 'failed') {
            throw new Error(extractJobErrorMessage(job));
          }

          if (job.status === 'done') {
            const result = await downloadCompletedJob(activeJobId);
            if (cancelled) return;
            setPendingDownload(result);
            setActiveJobId(null);
            return;
          }

          timeoutHandle = window.setTimeout(() => {
            timeoutHandle = null;
            void pollJob();
          }, 1500);
          return;
        }
      } catch (err) {
        if (cancelled) return;
        const rawMessage = err instanceof Error ? err.message : 'Generation failed.';
        const message = normalizeGenerationErrorMessage(rawMessage);
        setGenerationError(message);
        setGenerationStepIndex(-1);
        setGenerationReady(false);
        setPendingDownload(null);
        setActiveJobId(null);
      }
    };

    void pollJob();

    return () => {
      cancelled = true;
      if (timeoutHandle !== null) {
        window.clearTimeout(timeoutHandle);
      }
    };
  }, [activeJobId, apiBaseUrl, downloadCompletedJob]);

  useEffect(() => {
    if (generationStepIndex < 0) return;
    const preDoneMaxIndex = generationSteps.length - 2;

    if (generationStepIndex < preDoneMaxIndex) {
      const timer = window.setTimeout(() => {
        setGenerationStepIndex((prev) => Math.min(prev + 1, preDoneMaxIndex));
      }, 2300);
      return () => window.clearTimeout(timer);
    }

    if (generationStepIndex === preDoneMaxIndex && pendingDownload) {
      const timer = window.setTimeout(() => {
        setGenerationStepIndex(preDoneMaxIndex + 1);
      }, 900);
      return () => window.clearTimeout(timer);
    }
  }, [generationStepIndex, generationSteps.length, pendingDownload]);

  useEffect(() => {
    const doneIndex = generationSteps.length - 1;
    if (generationStepIndex !== doneIndex || !pendingDownload) return;

    const url = URL.createObjectURL(pendingDownload.blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = pendingDownload.fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    setPendingDownload(null);
    setGenerationStepIndex(-1);
    setGenerationReady(true);

    const doneTimer = window.setTimeout(() => {
      setGenerationReady(false);
    }, 1600);

    return () => window.clearTimeout(doneTimer);
  }, [generationStepIndex, generationSteps.length, pendingDownload]);

  return (
    <div className="relative w-full h-screen overflow-hidden font-inter text-slate-700 bg-slate-50">
      {/* Background Interactive Map */}
      <div className={`absolute inset-0 z-0 ${uiLocked ? 'pointer-events-none' : ''}`}>
        <MapContainer
          center={[initial.mapView.lat, initial.mapView.lon]}
          zoom={initial.mapView.zoom}
          style={{ width: '100%', height: '100%' }}
          zoomControl={false}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          />

          <FeatureGroup ref={featureGroupRef}>
            {featureGroupReady ? null : null}
          </FeatureGroup>

          <MapEventBridge onViewChange={handleMapViewChange} onMapReady={handleMapReady} />
        </MapContainer>

        <div className="absolute inset-0 bg-gradient-to-b from-slate-900/10 via-transparent to-white/20 pointer-events-none z-[1]"></div>
      </div>

      {/* Top Navbar */}
      <nav className="absolute top-0 left-0 right-0 z-40 p-6 flex justify-between items-center pointer-events-none">
        <div className="flex items-center gap-3 pointer-events-auto">
          <div className="w-10 h-10 rounded-xl bg-slate-900 flex items-center justify-center text-white shadow-[0_10px_25px_rgb(15,23,42,0.25)]">
            <MapIcon size={20} strokeWidth={2.5} />
          </div>
          <span className="font-bold text-xl tracking-tight text-slate-800 drop-shadow-sm bg-white/50 px-2 py-1 rounded backdrop-blur-sm">
            TopoPuzzle 3D
          </span>
        </div>

        <div className="hidden md:flex items-center gap-8 glass-panel px-6 py-3 rounded-full pointer-events-auto">
          <a href="#" className="text-sm font-medium text-slate-500 hover:text-slate-900 transition-colors">
            Gallery
          </a>
          <a href="#" className="text-sm font-medium text-slate-500 hover:text-slate-900 transition-colors">
            How to Print
          </a>
          <div className="w-px h-4 bg-slate-200"></div>
          <a href="#" className="text-sm font-medium text-slate-800 hover:text-slate-900 transition-colors">
            Login
          </a>
        </div>

        <button className="md:hidden glass-panel p-3 rounded-full pointer-events-auto">
          <Menu size={20} className="text-slate-800" />
        </button>
      </nav>

      {/* Floating Control Panel */}
      <div className="absolute top-24 right-6 bottom-6 w-full max-w-sm z-40 pointer-events-none flex flex-col justify-end md:justify-start">
        <motion.div
          initial={{ x: 50, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="glass-panel rounded-2xl p-6 flex flex-col gap-8 pointer-events-auto max-h-full overflow-y-auto custom-scrollbar"
        >
          {/* Step 1: Location */}
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
                  {bboxCenter ? `${bboxCenter.lat.toFixed(3)}° N, ${bboxCenter.lng.toFixed(3)}° E` : 'Draw a box'}
                </p>
              </div>
              <div className="text-right space-y-1">
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Area</p>
                <p className="font-mono text-sm font-medium text-slate-700">
                  {bboxArea !== null ? `${bboxArea.toFixed(1)} km²` : '-- km²'}
                </p>
              </div>
            </div>

            <button
              type="button"
              disabled={uiLocked}
              onClick={createSelectionRectangle}
              className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white shadow-[0_10px_24px_rgb(15,23,42,0.18)] transition-transform hover:translate-y-[-1px] hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0"
            >
              <Maximize size={16} />
              Draw Box
            </button>
            <p className="text-xs font-mono text-slate-500">
              Creates a new centered selection and replaces the current area.
            </p>
          </div>

          {/* Step 2: Grid & Size */}
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
                {(['2x2', '5x5', '10x10'] as GridSize[]).map((grid) => (
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
              <p className="text-xs text-center font-mono text-slate-500 mt-2">Each piece: {pieceWidth} x {pieceHeight} mm</p>
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

          {/* Step 3: Vertical Exaggeration */}
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

          {/* Pro Settings */}
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-slate-800">
              <span className="flex items-center justify-center w-6 h-6 rounded-full bg-slate-900/10 text-xs font-bold text-slate-800">
                4
              </span>
              <h2 className="font-semibold tracking-tight text-slate-800">Pro Settings</h2>
            </div>

            <label className="flex items-start justify-between gap-4">
              <div className="space-y-1 pr-2">
                <p className="text-sm font-medium text-slate-800">Smooth Terrain (Bilinear Interpolation)</p>
                <p className="text-xs text-slate-500">Eliminates 'staircase' artifacts on high zooms.</p>
              </div>
              <div className="relative inline-flex flex-shrink-0">
                <input
                  type="checkbox"
                  className="peer sr-only"
                  checked={smoothTerrain}
                  disabled={uiLocked}
                  onChange={(e) => setSmoothTerrain(e.target.checked)}
                />
                <span className="h-6 w-11 rounded-full bg-slate-300 transition-colors peer-checked:bg-slate-900 peer-disabled:opacity-50"></span>
                <span className="absolute left-[2px] top-[2px] h-5 w-5 rounded-full bg-white shadow-sm transition-transform peer-checked:translate-x-5"></span>
              </div>
            </label>

            <label className="flex items-start justify-between gap-4">
              <div className="space-y-1 pr-2">
                <p className="text-sm font-medium text-slate-800">Flatten Sea Level</p>
                <p className="text-xs text-slate-500">Forces 0m elevation to be perfectly flat for islands/coastlines.</p>
              </div>
              <div className="relative inline-flex flex-shrink-0">
                <input
                  type="checkbox"
                  className="peer sr-only"
                  checked={flattenSeaLevel}
                  disabled={uiLocked}
                  onChange={(e) => setFlattenSeaLevel(e.target.checked)}
                />
                <span className="h-6 w-11 rounded-full bg-slate-300 transition-colors peer-checked:bg-slate-900 peer-disabled:opacity-50"></span>
                <span className="absolute left-[2px] top-[2px] h-5 w-5 rounded-full bg-white shadow-sm transition-transform peer-checked:translate-x-5"></span>
              </div>
            </label>

            <label className="flex items-start justify-between gap-4">
              <div className="space-y-1 pr-2">
                <p className="text-sm font-medium text-slate-800">Include OSM Buildings</p>
                <p className="text-xs text-slate-500">Extrudes building volumes on top of the DEM terrain.</p>
              </div>
              <div className="relative inline-flex flex-shrink-0">
                <input
                  type="checkbox"
                  className="peer sr-only"
                  checked={includeBuildings}
                  disabled={uiLocked}
                  onChange={(e) => setIncludeBuildings(e.target.checked)}
                />
                <span className="h-6 w-11 rounded-full bg-slate-300 transition-colors peer-checked:bg-slate-900 peer-disabled:opacity-50"></span>
                <span className="absolute left-[2px] top-[2px] h-5 w-5 rounded-full bg-white shadow-sm transition-transform peer-checked:translate-x-5"></span>
              </div>
            </label>

            <label className="flex items-start justify-between gap-4">
              <div className="space-y-1 pr-2">
                <p className="text-sm font-medium text-slate-800">Include OSM Roads</p>
                <p className="text-xs text-slate-500">Adds raised road overlays clipped to the selected area.</p>
              </div>
              <div className="relative inline-flex flex-shrink-0">
                <input
                  type="checkbox"
                  className="peer sr-only"
                  checked={includeRoads}
                  disabled={uiLocked}
                  onChange={(e) => setIncludeRoads(e.target.checked)}
                />
                <span className="h-6 w-11 rounded-full bg-slate-300 transition-colors peer-checked:bg-slate-900 peer-disabled:opacity-50"></span>
                <span className="absolute left-[2px] top-[2px] h-5 w-5 rounded-full bg-white shadow-sm transition-transform peer-checked:translate-x-5"></span>
              </div>
            </label>
          </div>

          {/* Action Area */}
          <div className="pt-4 mt-auto border-t border-slate-200/50">
            <button
              onClick={handleGenerate}
              disabled={uiLocked || !bboxBounds}
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
              {!bboxBounds
                ? 'Please draw a selection box on the map first.'
                : 'Settings and map state are encoded in URL for shareable links.'}
            </p>
            {generationError && (
              <button
                type="button"
                onClick={() => setGenerationError(null)}
                className="mt-3 w-full rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-left text-sm text-rose-700 shadow-sm transition-colors hover:bg-rose-100"
              >
                <span className="block font-semibold">Generation failed</span>
                <span className="block mt-1 leading-6">{generationError}</span>
              </button>
            )}
          </div>
        </motion.div>
      </div>

      {/* Dynamic Generation Overlay */}
      <AnimatePresence>
        {(generationStepIndex >= 0 || generationReady) && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-50 flex items-center justify-center bg-slate-900/25 backdrop-blur-md"
          >
            <motion.div
              initial={{ scale: 0.94, y: 16 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.96, y: 12 }}
              className="w-full max-w-lg mx-4 rounded-2xl border border-white/30 bg-white/90 p-6 shadow-[0_8px_30px_rgb(0,0,0,0.08)]"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="h-10 w-10 rounded-xl bg-slate-900 text-white flex items-center justify-center shadow-[0_8px_18px_rgb(15,23,42,0.22)]">
                  {generationReady ? <CheckCircle2 size={20} /> : <Sparkles size={20} />}
                </div>
                <div>
                  <h3 className="text-base font-semibold text-slate-800">Terrain Generation Pipeline</h3>
                  <p className="text-xs text-slate-500">Optimized backend 3MF export sequence</p>
                </div>
              </div>

              {generationReady ? (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-700 font-medium flex items-center gap-2">
                  <CheckCircle2 size={18} />
                  Done! Download starting.
                </div>
              ) : (
                <>
                  <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-slate-700 font-medium flex items-center gap-2">
                    <Loader2 size={16} className="animate-spin text-slate-800" />
                    {generationStepIndex >= 0 ? generationSteps[generationStepIndex] : generationSteps[0]}
                  </div>

                  <div className="mt-4 space-y-2">
                    {generationSteps.map((step, idx) => {
                      const isDone = generationStepIndex > idx;
                      const isCurrent = generationStepIndex === idx;
                      return (
                        <div key={step} className="flex items-center gap-3">
                          <div
                            className={`h-5 w-5 rounded-full flex items-center justify-center ${
                              isDone
                                ? 'bg-emerald-100 text-emerald-600'
                                : isCurrent
                                ? 'bg-slate-200 text-slate-800'
                                : 'bg-slate-100 text-slate-300'
                            }`}
                          >
                            {isDone ? <CheckCircle2 size={13} /> : <span className="h-1.5 w-1.5 rounded-full bg-current"></span>}
                          </div>
                          <span className={`text-sm ${isCurrent ? 'text-slate-800 font-medium' : 'text-slate-500'}`}>{step}</span>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error Overlay */}
      <AnimatePresence>
        {generationError && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-[60] flex items-center justify-center bg-slate-950/45 backdrop-blur-[6px] px-4"
          >
            <motion.div
              initial={{ scale: 0.96, y: 18 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.98, y: 10 }}
              className="w-full max-w-md rounded-2xl border border-rose-200 bg-white/95 p-6 shadow-[0_18px_50px_rgba(15,23,42,0.18)]"
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-rose-100 text-rose-600">
                  <Sparkles size={18} />
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="text-base font-semibold text-slate-900">Generation failed</h3>
                  <p className="mt-1 text-sm leading-6 text-slate-600">{generationError}</p>
                </div>
              </div>

              <div className="mt-5 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setGenerationError(null)}
                  className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
                >
                  Dismiss
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setGenerationError(null);
                    handleGenerate();
                  }}
                  className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-slate-800"
                >
                  Try again
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Local styles */}
      <style
        dangerouslySetInnerHTML={{
          __html: `
          .custom-scrollbar::-webkit-scrollbar {
            width: 6px;
          }
          .custom-scrollbar::-webkit-scrollbar-track {
            background: transparent;
          }
          .custom-scrollbar::-webkit-scrollbar-thumb {
            background-color: #cbd5e1;
            border-radius: 20px;
          }
          .custom-scrollbar:hover::-webkit-scrollbar-thumb {
            background-color: #94a3b8;
          }

          .custom-slider {
            height: 8px;
            border-radius: 9999px;
            appearance: none;
            background: #e2e8f0;
            cursor: pointer;
          }
          .custom-slider::-webkit-slider-thumb {
            appearance: none;
            width: 18px;
            height: 18px;
            border-radius: 9999px;
            background: #0f172a;
            border: 2px solid #ffffff;
            box-shadow: 0 2px 8px rgb(15 23 42 / 0.24);
          }
          .custom-slider::-moz-range-thumb {
            width: 18px;
            height: 18px;
            border-radius: 9999px;
            background: #0f172a;
            border: 2px solid #ffffff;
            box-shadow: 0 2px 8px rgb(15 23 42 / 0.24);
          }

          .leaflet-draw-toolbar a {
            background-color: #ffffff;
            color: #0f172a;
            border-radius: 8px !important;
            border: 1px solid #e2e8f0 !important;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1) !important;
            margin-bottom: 8px !important;
          }
          .leaflet-draw-toolbar a:hover {
            background-color: #f8fafc;
          }
          .leaflet-container .leaflet-control-attribution {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(4px);
            border-radius: 4px;
            margin: 0 4px 4px 0;
          }
        `,
        }}
      />
    </div>
  );
}
