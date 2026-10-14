import { divIcon, latLngBounds } from "leaflet";
import { Home, User } from "lucide-react";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MapContainer, Marker, Polygon, Polyline, TileLayer, Tooltip } from "react-leaflet";
import { GROUPS, groupOf, statusLabel } from "../lib/status";
import type { Case, Geometry, Incident, Resident, Shelter, Volunteer } from "../types.gen";

const toLatLngs = (g: Geometry) => g.points.map((p) => [p.lat, p.lng] as [number, number]);

function residentIcon(c: Case, label: string) {
  const status = c.status ?? "PENDING";
  const g = GROUPS[groupOf(status)];
  const Icon = g.icon;
  const pulse = status === "RINGING" || status === "CONTACTING" ? "marker-pulse" : "";
  const html = renderToStaticMarkup(
    <div
      role="img"
      aria-label={label}
      className={pulse}
      style={{
        background: g.color,
        borderRadius: 9999,
        width: 22,
        height: 22,
        display: "grid",
        placeItems: "center",
        border: "2px solid white",
        boxShadow: "0 1px 3px rgba(0,0,0,.4)",
      }}
    >
      <Icon size={13} color="white" aria-hidden="true" />
    </div>,
  );
  return divIcon({ html, className: "", iconSize: [22, 22], iconAnchor: [11, 11] });
}

function badgeIcon(content: ReactElement, label: string, bg: string) {
  const html = renderToStaticMarkup(
    <div
      role="img"
      aria-label={label}
      style={{
        background: bg,
        color: "white",
        borderRadius: 6,
        padding: "2px 5px",
        fontSize: 11,
        fontWeight: 700,
        display: "flex",
        alignItems: "center",
        gap: 3,
        whiteSpace: "nowrap",
        border: "2px solid white",
        boxShadow: "0 1px 3px rgba(0,0,0,.4)",
      }}
    >
      {content}
    </div>,
  );
  return divIcon({ html, className: "lm-badge" });
}

type Props = {
  incident: Incident;
  cases: Case[];
  residents: Map<string, Resident>;
  shelters: Shelter[];
  volunteers: Volunteer[];
  onSelect?: (rid: string) => void;
};

export function MapView({ incident, cases, residents, shelters, volunteers, onSelect }: Props) {
  const poly = toLatLngs(incident.polygon);
  const bounds = latLngBounds(poly).pad(0.25);
  return (
    <div className="relative h-full min-h-[420px] overflow-hidden rounded-lg shadow-sm">
      <MapContainer bounds={bounds} className="h-full w-full" scrollWheelZoom>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Polygon positions={poly} pathOptions={{ color: "#1d4ed8", fillOpacity: 0.12, weight: 2 }} />
        <Polyline positions={toLatLngs(incident.river_line)} pathOptions={{ color: "#0ea5e9", weight: 5 }} />
        {shelters.map((s) => (
          <Marker
            key={s.shelter_id}
            position={[s.location.lat, s.location.lng]}
            icon={badgeIcon(
              <>
                <Home size={12} aria-hidden="true" />
                {`${s.shelter_id} ${s.occupied}/${s.capacity}`}
              </>,
              `Shelter ${s.name}, ${s.occupied} of ${s.capacity} places used`,
              "#334155",
            )}
          >
            <Tooltip>
              {s.name}
              {s.wheelchair_accessible ? " · wheelchair accessible" : ""}
              {s.medical_support ? " · medical support" : ""}
            </Tooltip>
          </Marker>
        ))}
        {volunteers.map((v) => (
          <Marker
            key={v.volunteer_id}
            position={[v.location.lat, v.location.lng]}
            icon={badgeIcon(
              <>
                <User size={12} aria-hidden="true" />
                {v.volunteer_id}
              </>,
              `Volunteer ${v.display_name}, ${v.available ? "available" : "busy"}`,
              v.available ? "#0f766e" : "#94a3b8",
            )}
          >
            <Tooltip>
              {v.display_name} · {v.available ? "available" : "on a task"}
            </Tooltip>
          </Marker>
        ))}
        {cases.map((c) => {
          const r = residents.get(c.resident_id);
          if (!r) return null;
          const label = `${c.resident_id} ${r.display_name}: ${statusLabel(c.status ?? "PENDING")}`;
          return (
            <Marker
              key={c.resident_id}
              position={[r.location.lat, r.location.lng]}
              icon={residentIcon(c, label)}
              keyboard
              eventHandlers={{ click: () => onSelect?.(c.resident_id) }}
            >
              <Tooltip>{label}</Tooltip>
            </Marker>
          );
        })}
      </MapContainer>
      <span className="pointer-events-none absolute left-2 top-2 z-[1000] rounded bg-white/90 px-2 py-1 text-xs font-semibold text-slate-800 shadow">
        Illustrative scenario
      </span>
    </div>
  );
}
