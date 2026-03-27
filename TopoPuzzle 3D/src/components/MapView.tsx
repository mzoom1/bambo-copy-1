import { useEffect } from 'react';
import * as L from 'leaflet';
import { FeatureGroup, MapContainer, TileLayer, useMapEvents } from 'react-leaflet';

import type { MapViewState } from '../types';
import type { UseBBoxResult } from '../hooks/useBBox';

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

type MapViewProps = {
  mapView: MapViewState;
  uiLocked: boolean;
  bbox: UseBBoxResult;
  onMapViewChange: (next: MapViewState) => void;
};

export function MapView({ mapView, uiLocked, bbox, onMapViewChange }: MapViewProps) {
  useEffect(() => {
    bbox.handleFeatureGroupReady();
  }, [bbox.handleFeatureGroupReady]);

  return (
    <div className={`absolute inset-0 z-0 ${uiLocked ? 'pointer-events-none' : ''}`}>
      <MapContainer
        center={[mapView.lat, mapView.lon]}
        zoom={mapView.zoom}
        style={{ width: '100%', height: '100%' }}
        zoomControl={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        />

        <FeatureGroup ref={bbox.featureGroupRef} />

        <MapEventBridge onViewChange={onMapViewChange} onMapReady={bbox.handleMapReady} />
      </MapContainer>

      <div className="absolute inset-0 bg-gradient-to-b from-slate-900/10 via-transparent to-white/20 pointer-events-none z-[1]" />
    </div>
  );
}
