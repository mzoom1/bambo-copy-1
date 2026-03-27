import { useCallback, useEffect, useRef, useState } from 'react';
import * as L from 'leaflet';
import type { RefObject } from 'react';

import type { BBoxState, BBoxStats } from '../types';
import { calculateBBoxStats } from '../utils/geo';

export type UseBBoxResult = {
  mapRef: RefObject<L.Map | null>;
  featureGroupRef: RefObject<L.FeatureGroup | null>;
  mapReady: boolean;
  featureGroupReady: boolean;
  bboxBounds: BBoxState | null;
  bboxArea: number | null;
  bboxCenter: { lat: number; lng: number } | null;
  handleMapReady: (map: L.Map) => void;
  handleFeatureGroupReady: () => void;
  createSelectionRectangle: () => void;
  clearBBox: () => void;
  onEdited: (e: { layers: L.LayerGroup }) => void;
  onEditMove: (e: { layer?: L.Layer; target?: L.Layer }) => void;
  onEditResize: (e: { layer?: L.Layer; target?: L.Layer }) => void;
  onDeleted: () => void;
};

function createSelectionBounds(map: L.Map): L.LatLngBounds {
  const viewBounds = map.getBounds();
  const center = viewBounds.getCenter();

  const latSpan = Math.abs(viewBounds.getNorth() - viewBounds.getSouth());
  const lngSpan = Math.abs(viewBounds.getEast() - viewBounds.getWest());
  const halfLat = Math.max(0.01, latSpan * 0.125);
  const halfLng = Math.max(0.01, lngSpan * 0.125);

  const south = Math.max(-85, Math.min(85, center.lat - halfLat));
  const north = Math.max(-85, Math.min(85, center.lat + halfLat));
  const west = Math.max(-180, Math.min(180, center.lng - halfLng));
  const east = Math.max(-180, Math.min(180, center.lng + halfLng));
  return L.latLngBounds([[south, west], [north, east]]);
}

export function useBBox(initialBBox: BBoxState | null): UseBBoxResult {
  const mapRef = useRef<L.Map | null>(null);
  const featureGroupRef = useRef<L.FeatureGroup | null>(null);
  const restoredBBoxRef = useRef(false);

  const [mapReady, setMapReady] = useState(false);
  const [featureGroupReady, setFeatureGroupReady] = useState(false);
  const [bboxBounds, setBBoxBounds] = useState<BBoxState | null>(initialBBox);
  const [bboxArea, setBBoxArea] = useState<number | null>(null);
  const [bboxCenter, setBBoxCenter] = useState<{ lat: number; lng: number } | null>(null);

  const applyStats = useCallback((bounds: L.LatLngBounds) => {
    const stats = calculateBBoxStats(bounds);
    setBBoxCenter(stats.center);
    setBBoxArea(stats.areaKm2);
    setBBoxBounds(stats.bbox);
  }, []);

  const updateBBoxFromLayer = useCallback((layer: L.Rectangle | L.Polygon) => {
    applyStats(layer.getBounds());
  }, [applyStats]);

  const syncBBoxFromEditEvent = useCallback((event: { layer?: L.Layer; target?: L.Layer }) => {
    const candidate = event.layer ?? event.target;
    if (!candidate) return;

    const maybeBoundsLayer = candidate as { getBounds?: () => L.LatLngBounds };
    if (typeof maybeBoundsLayer.getBounds !== 'function') return;

    applyStats(maybeBoundsLayer.getBounds());
  }, [applyStats]);

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
        // Best effort only.
      }

      anyLayer.on?.('click', () => {
        try {
          anyLayer.editing?.enable?.();
        } catch {
          // Best effort only.
        }
      });

      anyLayer.on?.('edit', () => updateBBoxFromLayer(candidate));
      anyLayer.on?.('editmove', () => updateBBoxFromLayer(candidate));
      anyLayer.on?.('editresize', () => updateBBoxFromLayer(candidate));
      anyLayer.on?.('dragend', () => updateBBoxFromLayer(candidate));
    },
    [updateBBoxFromLayer],
  );

  const createSelectionRectangle = useCallback(() => {
    const map = mapRef.current;
    const fg = featureGroupRef.current;
    if (!map || !fg) return;

    const bounds = createSelectionBounds(map);
    const rect = L.rectangle(bounds, {
      color: '#0f172a',
      weight: 2,
      fillOpacity: 0.1,
      dashArray: '5,5',
    });

    fg.clearLayers();
    fg.addLayer(rect);
    enableSelectionEditing(rect);
    updateBBoxFromLayer(rect);
    map.fitBounds(rect.getBounds(), { padding: [48, 48] });
  }, [enableSelectionEditing, updateBBoxFromLayer]);

  const clearBBox = useCallback(() => {
    setBBoxArea(null);
    setBBoxCenter(null);
    setBBoxBounds(null);
    featureGroupRef.current?.clearLayers();
  }, []);

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

      if (!updated && bboxBounds) {
        setBBoxBounds((prev) => prev);
      }
    },
    [bboxBounds, updateBBoxFromLayer],
  );

  const onEditMove = useCallback((e: { layer?: L.Layer; target?: L.Layer }) => {
    syncBBoxFromEditEvent(e);
  }, [syncBBoxFromEditEvent]);

  const onEditResize = useCallback((e: { layer?: L.Layer; target?: L.Layer }) => {
    syncBBoxFromEditEvent(e);
  }, [syncBBoxFromEditEvent]);

  const onDeleted = useCallback(() => {
    clearBBox();
  }, [clearBBox]);

  const handleMapReady = useCallback((map: L.Map) => {
    mapRef.current = map;
    setMapReady(true);
  }, []);

  const handleFeatureGroupReady = useCallback(() => {
    if (!featureGroupReady) {
      setFeatureGroupReady(true);
    }
  }, [featureGroupReady]);

  useEffect(() => {
    if (restoredBBoxRef.current) return;
    if (!mapReady || !featureGroupReady) return;

    const map = mapRef.current;
    const fg = featureGroupRef.current;
    if (!map || !fg) return;

    restoredBBoxRef.current = true;

    if (!initialBBox) {
      createSelectionRectangle();
      return;
    }

    const rect = L.rectangle(
      [
        [initialBBox.south, initialBBox.west],
        [initialBBox.north, initialBBox.east],
      ],
      {
        color: '#0f172a',
        weight: 2,
        fillOpacity: 0.1,
        dashArray: '5,5',
      },
    );

    fg.clearLayers();
    fg.addLayer(rect);
    enableSelectionEditing(rect);
    updateBBoxFromLayer(rect);
    map.fitBounds(rect.getBounds(), { padding: [48, 48] });
  }, [
    createSelectionRectangle,
    enableSelectionEditing,
    featureGroupReady,
    initialBBox,
    mapReady,
    updateBBoxFromLayer,
  ]);

  return {
    mapRef,
    featureGroupRef,
    mapReady,
    featureGroupReady,
    bboxBounds,
    bboxArea,
    bboxCenter,
    handleMapReady,
    handleFeatureGroupReady,
    createSelectionRectangle,
    clearBBox,
    onEdited,
    onEditMove,
    onEditResize,
    onDeleted,
  };
}
