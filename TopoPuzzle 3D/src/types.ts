export type GridSize = '2x2' | '5x5' | '10x10';
export type QualityPreset = 'Very Low' | 'Low' | 'Average' | 'High' | 'Very High';
export const QUALITY_PRESET_OPTIONS: QualityPreset[] = ['Very Low', 'Low', 'Average', 'High', 'Very High'];

export type JobState = 'queued' | 'running' | 'done' | 'failed';

export interface MapViewState {
  lat: number;
  lon: number;
  zoom: number;
}

export interface BBoxState {
  south: number;
  west: number;
  north: number;
  east: number;
}

export interface InitialState {
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
}

export interface JobResponse {
  jobId: string;
  status: 'queued';
}

export interface JobStatus {
  job_id: string;
  status: JobState;
  progress: number;
  created_at: string;
  updated_at: string;
  output_path?: string | null;
  error?: string | null;
  filename?: string | null;
}

export interface BBoxStats {
  center: { lat: number; lng: number };
  areaKm2: number;
  bbox: BBoxState;
}

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

