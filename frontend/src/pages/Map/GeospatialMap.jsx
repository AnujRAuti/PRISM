import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useApp } from '../../context/AppContext';
import { useI18n } from '../../i18n/I18nContext';
import { getProjectImage } from '../../data/mockDataset';
import { IntegrityArc } from '../../components/ui/IntegrityArc';
import {
  MapPin,
  Layers,
  Filter,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  ShieldAlert,
  Search,
  Maximize2,
  Crosshair,
  Compass,
  Radio,
} from 'lucide-react';

// Carto Baseline API Key for authenticated government GIS basemap access
const CARTO_API_KEY = import.meta.env.VITE_CARTO_API_KEY || 'cb1_52ac_1_23a45a3df023cdfec7891751';

// Tile Layer Configurations
const BASE_LAYERS = {
  STREET: {
    id: 'STREET',
    label: 'Street Map',
    icon: '🗺️',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    options: {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
  },
  SATELLITE: {
    id: 'SATELLITE',
    label: 'High-Res Satellite',
    icon: '🛰️',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    options: {
      maxZoom: 19,
      attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    },
  },
  CARTO: {
    id: 'CARTO',
    label: 'Government GIS',
    icon: '🏛️',
    url: `https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png?key=${CARTO_API_KEY}&api_key=${CARTO_API_KEY}`,
    options: {
      maxZoom: 19,
      subdomains: 'abcd',
      attribution: '&copy; <a href="https://carto.com/attributions">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
  },
};

export default function GeospatialMap() {
  const { projects, evidenceList } = useApp();
  const { t, formatNumber } = useI18n();

  const [selectedScheme, setSelectedScheme] = useState('ALL');
  const [selectedProjectId, setSelectedProjectId] = useState(projects?.[0]?.id || 'PRJ-PMGSY-MH-401');
  const [showAnomaliesOnly, setShowAnomaliesOnly] = useState(false);
  const [showGeofences, setShowGeofences] = useState(true);
  const [activeBaseLayer, setActiveBaseLayer] = useState('STREET');
  const [searchQuery, setSearchQuery] = useState('');

  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const tileLayerRef = useRef(null);
  const markersLayerGroupRef = useRef(null);
  const geofencesLayerGroupRef = useRef(null);

  const filteredProjects = (projects || []).filter((p) => {
    if (selectedScheme !== 'ALL' && !p.scheme?.includes(selectedScheme)) return false;
    if (showAnomaliesOnly && p.flaggedCount === 0) return false;
    if (
      searchQuery.trim() &&
      !p.name?.toLowerCase().includes(searchQuery.toLowerCase()) &&
      !p.district?.toLowerCase().includes(searchQuery.toLowerCase()) &&
      !p.id?.toLowerCase().includes(searchQuery.toLowerCase())
    ) {
      return false;
    }
    return true;
  });

  const activeProject =
    (projects || []).find((p) => p.id === selectedProjectId) ||
    projects?.[0] || {
      id: 'PRJ-PMGSY-MH-401',
      name: 'Purandar Taluka Rural Bitumen Road Reconstruction',
      scheme: 'PMGSY (Rural Roads)',
      district: 'Pune',
      state: 'Maharashtra',
      budgetInr: 34500000,
      geofenceRadiusMeters: 150,
      evidenceHealthScore: 94,
      totalSubmissions: 12,
      flaggedCount: 0,
      centroid: { lat: 18.2812, lng: 74.0154 },
      requiredEvidenceList: [],
    };

  // 1. Initialize Real Leaflet Map
  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!mapInstanceRef.current) {
      const map = L.map(mapContainerRef.current, {
        center: [21.5, 78.9], // Center of India
        zoom: 5,
        minZoom: 4,
        maxZoom: 18,
        zoomControl: false,
      });

      // Scale indicator in metric meters/km
      L.control.scale({ imperial: false, position: 'bottomright' }).addTo(map);

      // Dedicated layer groups for clean updates
      const tile = L.tileLayer(BASE_LAYERS[activeBaseLayer].url, BASE_LAYERS[activeBaseLayer].options).addTo(map);
      tileLayerRef.current = tile;

      const geofenceGroup = L.layerGroup().addTo(map);
      const markerGroup = L.layerGroup().addTo(map);
      geofencesLayerGroupRef.current = geofenceGroup;
      markersLayerGroupRef.current = markerGroup;

      mapInstanceRef.current = map;
    }

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, []);

  // 2. Switch Real Map Tile Provider (Street vs Satellite vs Clean GIS)
  useEffect(() => {
    if (!mapInstanceRef.current) return;
    if (tileLayerRef.current) {
      mapInstanceRef.current.removeLayer(tileLayerRef.current);
    }
    const layerConfig = BASE_LAYERS[activeBaseLayer];
    const newTile = L.tileLayer(layerConfig.url, layerConfig.options).addTo(mapInstanceRef.current);
    newTile.bringToBack();
    tileLayerRef.current = newTile;
  }, [activeBaseLayer]);

  // 3. Render Real Geofences & Dynamic SVG Markers
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !markersLayerGroupRef.current || !geofencesLayerGroupRef.current) return;

    const markersGroup = markersLayerGroupRef.current;
    const geofencesGroup = geofencesLayerGroupRef.current;

    markersGroup.clearLayers();
    geofencesGroup.clearLayers();

    filteredProjects.forEach((project) => {
      const lat = project.centroid?.lat || 20.5937;
      const lng = project.centroid?.lng || 78.9629;
      const isSelected = project.id === selectedProjectId;
      const hasFlags = project.flaggedCount > 0;

      const strokeColor = hasFlags
        ? '#dc2626'
        : project.evidenceHealthScore > 80
        ? '#059669'
        : '#d97706';

      const fillColor = hasFlags
        ? '#ef4444'
        : project.evidenceHealthScore > 80
        ? '#10b981'
        : '#f59e0b';

      // 3A. Real Physical Geofence Circular Buffer
      if (showGeofences) {
        const circle = L.circle([lat, lng], {
          radius: project.geofenceRadiusMeters || 150,
          color: strokeColor,
          weight: isSelected ? 2.5 : 1.5,
          opacity: isSelected ? 0.95 : 0.65,
          fillColor: fillColor,
          fillOpacity: isSelected ? 0.25 : 0.12,
          dashArray: isSelected ? undefined : '4, 4',
        });

        circle.bindTooltip(
          `<strong>${project.id}</strong><br/>Geofence Buffer: ${project.geofenceRadiusMeters || 150}m`,
          { direction: 'top', offset: [0, -10] }
        );

        circle.on('click', () => {
          setSelectedProjectId(project.id);
        });

        geofencesGroup.addLayer(circle);
      }

      // 3B. Real Project Marker with Custom Dynamic SVG Icon
      const markerHtml = `
        <div class="prism-map-pin ${isSelected ? 'selected' : ''}" style="
          position: relative;
          width: 38px;
          height: 38px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
        ">
          ${
            isSelected
              ? `<div style="
                  position: absolute;
                  inset: -8px;
                  border-radius: 50%;
                  background: ${strokeColor};
                  opacity: 0.35;
                  animation: prism-pin-pulse 2s infinite ease-out;
                "></div>`
              : ''
          }
          <div style="
            width: ${isSelected ? '32px' : '28px'};
            height: ${isSelected ? '32px' : '28px'};
            border-radius: 50%;
            background: #ffffff;
            border: 2.5px solid ${strokeColor};
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 11px;
            color: ${strokeColor};
            font-family: monospace;
            transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
          ">
            ${hasFlags ? '!' : project.evidenceHealthScore}
          </div>
          <div style="
            position: absolute;
            bottom: -6px;
            left: 50%;
            transform: translateX(-50%);
            width: 0;
            height: 0;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid ${strokeColor};
          "></div>
        </div>
      `;

      const customIcon = L.divIcon({
        html: markerHtml,
        className: 'prism-leaflet-custom-icon',
        iconSize: [38, 38],
        iconAnchor: [19, 38],
        popupAnchor: [0, -36],
      });

      const marker = L.marker([lat, lng], { icon: customIcon });

      // Interactive popup
      const popupHtml = `
        <div style="min-width: 220px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 2px;">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px;">
            <span style="font-family: monospace; font-size: 11px; font-weight: 700; color: #64748b;">${project.id}</span>
            <span style="
              font-size: 10px;
              font-weight: 800;
              padding: 2px 6px;
              border-radius: 999px;
              background: ${hasFlags ? '#fef2f2' : '#ecfdf5'};
              color: ${hasFlags ? '#dc2626' : '#059669'};
            ">
              ${hasFlags ? `${project.flaggedCount} FLAG` : `${project.evidenceHealthScore}% INTEGRITY`}
            </span>
          </div>
          <div style="font-weight: 700; font-size: 13px; color: #0f172a; line-height: 1.3; margin-bottom: 6px;">
            ${project.name}
          </div>
          <div style="font-size: 11px; color: #475569; margin-bottom: 4px;">
            <strong>Scheme:</strong> ${project.scheme}
          </div>
          <div style="font-size: 11px; color: #475569; margin-bottom: 10px;">
            <strong>Location:</strong> ${project.district}, ${project.state}
          </div>
          <div style="display: flex; gap: 6px;">
            <button id="prism-popup-select-${project.id}" style="
              flex: 1;
              padding: 6px 10px;
              background: #1d4ed8;
              color: #ffffff;
              border: none;
              border-radius: 4px;
              font-size: 11px;
              font-weight: 700;
              cursor: pointer;
            ">
              Inspect on Map
            </button>
          </div>
        </div>
      `;

      marker.bindPopup(popupHtml);

      marker.on('click', () => {
        setSelectedProjectId(project.id);
      });

      marker.on('popupopen', () => {
        const btn = document.getElementById(`prism-popup-select-${project.id}`);
        if (btn) {
          btn.onclick = () => {
            setSelectedProjectId(project.id);
          };
        }
      });

      markersGroup.addLayer(marker);
    });
  }, [filteredProjects, selectedProjectId, showGeofences]);

  // 4. Smooth Fly-To Animation when Active Project Changes
  const flyToProject = (proj, zoomLevel = 14) => {
    if (!mapInstanceRef.current || !proj) return;
    const lat = proj.centroid?.lat || 20.5937;
    const lng = proj.centroid?.lng || 78.9629;
    mapInstanceRef.current.flyTo([lat, lng], zoomLevel, {
      duration: 1.2,
      easeLinearity: 0.25,
    });
  };

  // Zoom to all projects bounding box
  const fitAllProjects = () => {
    if (!mapInstanceRef.current || filteredProjects.length === 0) return;
    const bounds = L.latLngBounds(
      filteredProjects.map((p) => [p.centroid?.lat || 20.5937, p.centroid?.lng || 78.9629])
    );
    mapInstanceRef.current.fitBounds(bounds, { padding: [40, 40], maxZoom: 12 });
  };

  return (
    <div style={{ padding: '1.5rem 2rem', maxWidth: '1440px', margin: '0 auto' }}>
      {/* Top Header */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          paddingBottom: '1rem',
          borderBottom: '1px solid var(--govt-gray-medium, #e2e8f0)',
          marginBottom: '1.5rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h1
              style={{
                margin: 0,
                fontSize: '1.5rem',
                fontWeight: 700,
                color: 'var(--govt-blue-dark, #0f172a)',
                letterSpacing: '-0.02em',
              }}
            >
              {t('nav_map', 'Geofence GIS & Multi-Scheme Spatial Map')}
            </h1>
            <span
              style={{
                fontSize: '0.75rem',
                padding: '0.2rem 0.6rem',
                borderRadius: '4px',
                backgroundColor: 'var(--govt-gray-light)',
                border: '1px solid var(--govt-gray-medium)',
                color: 'var(--govt-gray-dark)',
                fontWeight: 600,
                fontFamily: 'monospace',
              }}
            >
              WGS84 EPSG:4326 • Live GIS
            </span>
          </div>
          <p style={{ margin: '0.35rem 0 0', fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
            Real-time geospatial telemetry for public works project geofences, satellite boundaries, and verified evidence pins.
          </p>
        </div>

        {/* Filter Toolbar */}
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.4rem 0.75rem',
              borderRadius: '6px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
            }}
          >
            <Search size={14} color="var(--govt-gray-dark)" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search district or ID..."
              style={{
                border: 'none',
                outline: 'none',
                fontSize: '0.8rem',
                color: 'var(--govt-gray-title)',
                width: '140px',
              }}
            />
          </div>

          <select
            value={selectedScheme}
            onChange={(e) => setSelectedScheme(e.target.value)}
            style={{
              padding: '0.4rem 0.75rem',
              borderRadius: '6px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              fontSize: '0.8rem',
              fontWeight: 600,
              color: 'var(--govt-gray-title)',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="ALL">All National Schemes</option>
            <option value="PMGSY">PMGSY (Rural Roads)</option>
            <option value="Jal Jeevan">Jal Jeevan Mission</option>
            <option value="Samagra">Samagra Shiksha (SSA)</option>
            <option value="KUSUM">PM-KUSUM (Solar)</option>
          </select>

          <button
            type="button"
            onClick={() => setShowAnomaliesOnly(!showAnomaliesOnly)}
            style={{
              padding: '0.4rem 0.75rem',
              borderRadius: '6px',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
              border: showAnomaliesOnly ? '1px solid var(--govt-danger)' : '1px solid var(--govt-gray-medium)',
              backgroundColor: showAnomaliesOnly ? 'var(--govt-danger-light)' : '#ffffff',
              color: showAnomaliesOnly ? 'var(--govt-danger)' : 'var(--govt-gray-text)',
            }}
          >
            {showAnomaliesOnly ? 'Showing Flagged Only' : 'Filter Anomalies'}
          </button>
        </div>
      </div>

      {/* Main Map Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '1.5rem' }}>
        {/* Left 8 Cols: Real GIS Map Canvas */}
        <div
          style={{
            gridColumn: 'span 8',
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-lg, 12px)',
            boxShadow: 'var(--shadow-sm)',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Map Top Status Bar & Basemap Switcher */}
          <div
            style={{
              padding: '0.65rem 1rem',
              backgroundColor: 'var(--govt-gray-off-white)',
              borderBottom: '1px solid var(--govt-gray-medium)',
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '0.75rem',
              fontSize: '0.8rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <MapPin size={15} color="var(--govt-blue-primary)" />
              <span style={{ fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                National Real-Time Geofence Map
              </span>
              <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.75rem' }}>
                ({filteredProjects.length} Verified GPS Nodes)
              </span>
            </div>

            {/* Real Map Layer Switcher & Tools */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              {/* Layer switch buttons */}
              <div
                style={{
                  display: 'flex',
                  backgroundColor: '#ffffff',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: '6px',
                  padding: '2px',
                }}
              >
                {Object.values(BASE_LAYERS).map((layer) => (
                  <button
                    key={layer.id}
                    type="button"
                    onClick={() => setActiveBaseLayer(layer.id)}
                    style={{
                      border: 'none',
                      backgroundColor: activeBaseLayer === layer.id ? 'var(--govt-blue-primary)' : 'transparent',
                      color: activeBaseLayer === layer.id ? '#ffffff' : 'var(--govt-gray-title)',
                      padding: '0.25rem 0.6rem',
                      borderRadius: '4px',
                      fontSize: '0.72rem',
                      fontWeight: activeBaseLayer === layer.id ? 700 : 500,
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    {layer.icon} {layer.label}
                  </button>
                ))}
              </div>

              {/* Geofence buffer toggle */}
              <button
                type="button"
                onClick={() => setShowGeofences(!showGeofences)}
                title="Toggle Geofence Buffer Circles"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.3rem',
                  padding: '0.3rem 0.65rem',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: '6px',
                  backgroundColor: showGeofences ? 'var(--govt-blue-light)' : '#ffffff',
                  color: showGeofences ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
                  fontSize: '0.72rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <Radio size={12} />
                <span>Geofences</span>
              </button>

              {/* Reset to fit all */}
              <button
                type="button"
                onClick={fitAllProjects}
                title="Fit All Project Locations"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.3rem',
                  padding: '0.3rem 0.65rem',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: '6px',
                  backgroundColor: '#ffffff',
                  color: 'var(--govt-gray-title)',
                  fontSize: '0.72rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <Maximize2 size={12} />
                <span>Fit All</span>
              </button>

              {/* Focus on active project */}
              <button
                type="button"
                onClick={() => flyToProject(activeProject, 15)}
                title="Focus Camera on Active Site"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.3rem',
                  padding: '0.3rem 0.65rem',
                  border: '1px solid var(--govt-blue-primary)',
                  borderRadius: '6px',
                  backgroundColor: 'var(--govt-blue-primary)',
                  color: '#ffffff',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                <Crosshair size={12} />
                <span>Focus Site</span>
              </button>
            </div>
          </div>

          {/* Real Map Container */}
          <div style={{ position: 'relative', width: '100%', height: '560px' }}>
            {/* The Real Leaflet Map DOM Node */}
            <div
              ref={mapContainerRef}
              style={{
                width: '100%',
                height: '100%',
                backgroundColor: '#e5e7eb',
                zIndex: 1,
              }}
            />

            {/* Custom On-Map Zoom Controls */}
            <div
              style={{
                position: 'absolute',
                top: '1rem',
                left: '1rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.25rem',
                zIndex: 500,
              }}
            >
              <button
                type="button"
                onClick={() => mapInstanceRef.current?.zoomIn()}
                aria-label="Zoom in"
                style={{
                  width: '32px',
                  height: '32px',
                  backgroundColor: '#ffffff',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: '6px',
                  boxShadow: 'var(--shadow-sm)',
                  fontSize: '1.1rem',
                  fontWeight: 700,
                  color: 'var(--govt-blue-dark)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                }}
              >
                +
              </button>
              <button
                type="button"
                onClick={() => mapInstanceRef.current?.zoomOut()}
                aria-label="Zoom out"
                style={{
                  width: '32px',
                  height: '32px',
                  backgroundColor: '#ffffff',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: '6px',
                  boxShadow: 'var(--shadow-sm)',
                  fontSize: '1.1rem',
                  fontWeight: 700,
                  color: 'var(--govt-blue-dark)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                }}
              >
                −
              </button>
            </div>

            {/* Quick Active Coordinates HUD Badge */}
            <div
              style={{
                position: 'absolute',
                top: '1rem',
                right: '1rem',
                backgroundColor: 'rgba(15, 23, 42, 0.85)',
                color: '#ffffff',
                backdropFilter: 'blur(4px)',
                padding: '0.4rem 0.75rem',
                borderRadius: '6px',
                fontSize: '0.72rem',
                fontFamily: 'monospace',
                zIndex: 500,
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                boxShadow: '0 4px 10px rgba(0, 0, 0, 0.25)',
              }}
            >
              <Compass size={14} color="#38bdf8" />
              <span>
                {activeProject.centroid?.lat?.toFixed(4)}°N, {activeProject.centroid?.lng?.toFixed(4)}°E
              </span>
              <span style={{ color: '#94a3b8' }}>•</span>
              <span style={{ color: '#38bdf8' }}>±{activeProject.geofenceRadiusMeters}m Geofence</span>
            </div>

            {/* Map Legend Overlay */}
            <div
              style={{
                position: 'absolute',
                bottom: '1.25rem',
                left: '1.25rem',
                backgroundColor: 'rgba(255, 255, 255, 0.95)',
                backdropFilter: 'blur(6px)',
                border: '1px solid var(--govt-gray-medium)',
                padding: '0.75rem 1rem',
                borderRadius: '8px',
                fontSize: '0.75rem',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.4rem',
                zIndex: 500,
              }}
            >
              <span style={{ fontWeight: 700, color: 'var(--govt-blue-dark)', textTransform: 'uppercase', fontSize: '0.68rem', letterSpacing: '0.04em' }}>
                GIS Health Status
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ width: '9px', height: '9px', borderRadius: '50%', backgroundColor: 'var(--govt-success)' }} />
                <span style={{ color: 'var(--govt-gray-dark)', fontWeight: 500 }}>Consistent (Score &gt; 80)</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ width: '9px', height: '9px', borderRadius: '50%', backgroundColor: 'var(--govt-warning)' }} />
                <span style={{ color: 'var(--govt-gray-dark)', fontWeight: 500 }}>Minor Deviation (Score 50–80)</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ width: '9px', height: '9px', borderRadius: '50%', backgroundColor: 'var(--govt-danger)' }} />
                <span style={{ color: 'var(--govt-danger)', fontWeight: 700 }}>Flagged Anomaly / Mismatch</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right 4 Cols: Project Inspection Drawer */}
        <div style={{ gridColumn: 'span 4' }}>
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: 'var(--radius-lg, 12px)',
              padding: '1.5rem',
              boxShadow: 'var(--shadow-sm)',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.25rem',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                justifyContent: 'space-between',
                gap: '0.75rem',
                borderBottom: '1px solid var(--govt-gray-medium)',
                paddingBottom: '0.85rem',
              }}
            >
              <div>
                <span
                  style={{
                    fontFamily: 'monospace',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    color: 'var(--govt-gray-dark)',
                    display: 'block',
                  }}
                >
                  {activeProject.id}
                </span>
                <h3
                  style={{
                    margin: '0.2rem 0 0',
                    fontSize: '0.95rem',
                    fontWeight: 700,
                    color: 'var(--govt-gray-title)',
                    lineHeight: 1.35,
                  }}
                >
                  {activeProject.name}
                </h3>
              </div>
              <IntegrityArc score={activeProject.evidenceHealthScore} size="sm" showLabel />
            </div>

            <div
              style={{
                aspectRatio: '16/9',
                width: '100%',
                borderRadius: '8px',
                overflow: 'hidden',
                backgroundColor: '#0f172a',
                border: '1px solid var(--govt-gray-medium)',
              }}
            >
              <img
                src={activeProject.imageUrl || getProjectImage(activeProject.id)}
                alt={activeProject.name}
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', fontSize: '0.8rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Scheme Track:</span>
                <span style={{ fontWeight: 600, color: 'var(--govt-blue-primary)' }}>{activeProject.scheme}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Jurisdiction:</span>
                <span style={{ fontWeight: 500, color: 'var(--govt-gray-title)' }}>
                  {activeProject.district}, {activeProject.state}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>GPS Centroid:</span>
                <span style={{ fontFamily: 'monospace', fontWeight: 600, color: 'var(--govt-blue-primary)' }}>
                  {activeProject.centroid?.lat?.toFixed(4)}°, {activeProject.centroid?.lng?.toFixed(4)}°
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Sanctioned Budget:</span>
                <span style={{ fontFamily: 'monospace', fontWeight: 700, color: 'var(--govt-gray-title)' }}>
                  ₹{(activeProject.budgetInr / 10000000).toFixed(2)} Cr
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Geofence Radius:</span>
                <span style={{ fontFamily: 'monospace', fontWeight: 600, color: 'var(--govt-gray-title)' }}>
                  {activeProject.geofenceRadiusMeters}m
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Total Submissions:</span>
                <span style={{ fontWeight: 600 }}>{activeProject.totalSubmissions} records</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Flagged Anomalies:</span>
                <span
                  style={{
                    fontWeight: 700,
                    color: activeProject.flaggedCount > 0 ? 'var(--govt-danger)' : 'var(--govt-success)',
                  }}
                >
                  {activeProject.flaggedCount > 0 ? `${activeProject.flaggedCount} issues detected` : '0 issues'}
                </span>
              </div>
            </div>

            {/* Mandatory Evidence Checklist */}
            <div style={{ borderTop: '1px solid var(--govt-gray-medium)', paddingTop: '0.85rem' }}>
              <h4
                style={{
                  margin: '0 0 0.5rem',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  color: 'var(--govt-gray-dark)',
                }}
              >
                Mandatory Evidence Checklist
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.75rem' }}>
                {(activeProject.requiredEvidenceList || []).map((req) => (
                  <div
                    key={req.key}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '0.45rem 0.65rem',
                      backgroundColor: 'var(--govt-gray-off-white)',
                      borderRadius: '4px',
                      border: '1px solid var(--govt-gray-light)',
                    }}
                  >
                    <span style={{ color: 'var(--govt-gray-title)', fontWeight: 500 }}>{req.label}</span>
                    <span
                      style={{
                        fontSize: '0.7rem',
                        fontWeight: 700,
                        padding: '0.1rem 0.4rem',
                        borderRadius: '3px',
                        backgroundColor:
                          req.status === 'FULFILLED'
                            ? 'rgba(5, 150, 105, 0.12)'
                            : req.status === 'PARTIAL'
                            ? 'rgba(217, 119, 6, 0.12)'
                            : 'rgba(220, 38, 38, 0.12)',
                        color:
                          req.status === 'FULFILLED'
                            ? 'var(--govt-success)'
                            : req.status === 'PARTIAL'
                            ? 'var(--govt-warning)'
                            : 'var(--govt-danger)',
                      }}
                    >
                      {req.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <button
                type="button"
                onClick={() => flyToProject(activeProject, 15)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.5rem',
                  padding: '0.6rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--govt-blue-light)',
                  color: 'var(--govt-blue-primary)',
                  border: '1px solid var(--govt-blue-primary)',
                  fontSize: '0.825rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                  transition: 'background 0.15s ease',
                }}
              >
                <Crosshair size={14} />
                <span>Fly Camera to Project Geofence</span>
              </button>

              <Link
                to={`/projects/${activeProject.id}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.5rem',
                  padding: '0.65rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--govt-blue-primary)',
                  color: '#ffffff',
                  fontSize: '0.825rem',
                  fontWeight: 700,
                  textDecoration: 'none',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                <span>Inspect Full Project Dossier</span>
                <ExternalLink size={14} />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
