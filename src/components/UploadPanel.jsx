import React, { useRef, useState } from 'react';
import { UploadCloud, FileImage, X, Check, Loader2, AlertTriangle } from 'lucide-react';
import { cn, Label, Badge, Button } from './ui/primitives';
import { uploadScene, needsBbox, UPLOAD_ACCEPT, UPLOAD_MAX_BYTES }
  from '../services/api';

/**
 * Bring your own scene: drop or pick a GeoTIFF, PNG or JPEG, send it to
 * /api/upload, and offer the prepared scene as a simulation target.
 *
 * A plain PNG or JPEG carries no coordinates, so its bounding box is asked
 * for up front. A GeoTIFF normally georeferences itself; if the server says
 * it does not, or that its bands are unlabelled, the matching field appears
 * with the server's own explanation. The server stays the authority on what
 * it can use -- the panel only gathers what it asks for.
 */

const SCALE_M = 10;
const MIN_PX = 64;       // backend limits on the 10 m grid
const MAX_PX = 1024;

const BBOX_FIELDS = [
  { key: 'minLon', label: 'Min lon', min: -180, max: 180 },
  { key: 'minLat', label: 'Min lat', min: -90, max: 90 },
  { key: 'maxLon', label: 'Max lon', min: -180, max: 180 },
  { key: 'maxLat', label: 'Max lat', min: -90, max: 90 },
];
const EMPTY_BBOX = { minLon: '', minLat: '', maxLon: '', maxLat: '' };

const BAND_PRESETS = [
  { label: 'NAIP', value: 'red,green,blue,nir' },
  { label: 'PlanetScope', value: 'blue,green,red,nir' },
];

const MODE_LABEL = { multispectral: 'Multispectral', rgb_nir: 'RGB + NIR',
                     rgb: 'RGB only' };

function extensionOk(name) {
  const ext = (name.match(/\.[^.]+$/) || [''])[0].toLowerCase();
  return UPLOAD_ACCEPT.split(',').includes(ext);
}

/** Parse and check the bbox; returns {value} or {error}, plus an extent. */
function readBbox(fields) {
  const v = Object.fromEntries(
    Object.entries(fields).map(([k, s]) => [k, s.trim() === '' ? NaN : Number(s)]));
  if (Object.values(v).some((x) => !Number.isFinite(x))) {
    return { error: 'Enter all four coordinates.' };
  }
  for (const f of BBOX_FIELDS) {
    if (v[f.key] < f.min || v[f.key] > f.max) {
      return { error: `${f.label} must be between ${f.min} and ${f.max}.` };
    }
  }
  if (v.minLon >= v.maxLon || v.minLat >= v.maxLat) {
    return { error: 'Each minimum must be smaller than its maximum.' };
  }
  const midLat = ((v.minLat + v.maxLat) / 2) * (Math.PI / 180);
  const widthKm = (v.maxLon - v.minLon) * 111.32 * Math.cos(midLat);
  const heightKm = (v.maxLat - v.minLat) * 110.54;
  const lo = (MIN_PX * SCALE_M) / 1000;
  const hi = (MAX_PX * SCALE_M) / 1000;
  const fits = [widthKm, heightKm].every((k) => k >= lo && k <= hi);
  return {
    value: [v.minLon, v.minLat, v.maxLon, v.maxLat],
    extent: { widthKm, heightKm, fits, lo, hi },
  };
}

function formatMB(bytes) {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadPanel({ uploads = [], selectedId = null,
                                      onUploaded, onSelect,
                                      disabled = false, backendOnline = true }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [showBbox, setShowBbox] = useState(false);
  const [bbox, setBbox] = useState(EMPTY_BBOX);
  const [showBands, setShowBands] = useState(false);
  const [bandOrder, setBandOrder] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const locked = disabled || busy || !backendOnline;
  const bboxCheck = showBbox ? readBbox(bbox) : null;
  const ready = file && !busy && (!showBbox || bboxCheck?.value)
    && (!showBands || bandOrder.trim());

  const reset = () => {
    setFile(null); setShowBbox(false); setBbox(EMPTY_BBOX);
    setShowBands(false); setBandOrder(''); setError(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  const choose = (picked) => {
    if (!picked) return;
    if (!extensionOk(picked.name)) {
      setError('Upload a GeoTIFF (.tif), PNG or JPEG.');
      return;
    }
    if (picked.size > UPLOAD_MAX_BYTES) {
      setError(`That file is ${formatMB(picked.size)}; the limit is `
        + `${formatMB(UPLOAD_MAX_BYTES)}.`);
      return;
    }
    setFile(picked);
    setError(null);
    setShowBbox(needsBbox(picked.name));
    setBbox(EMPTY_BBOX);
    setShowBands(false);
    setBandOrder('');
  };

  const submit = async () => {
    if (!ready) return;
    setBusy(true);
    setError(null);
    const res = await uploadScene({
      file,
      bbox: showBbox ? bboxCheck.value : null,
      bandOrder: showBands ? bandOrder.trim() : null,
    });
    setBusy(false);
    if (res.ok) {
      onUploaded?.(res.upload);
      reset();
      return;
    }
    setError(res.error);
    // Ask for exactly what the server says is missing.
    if (/bbox|georeferenc/i.test(res.error)) setShowBbox(true);
    if (/band_order/i.test(res.error)) setShowBands(true);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    if (!locked) choose(e.dataTransfer.files?.[0]);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <UploadCloud className="w-3.5 h-3.5 text-ink-tertiary" strokeWidth={1.75} />
          <Label>Your own scene</Label>
        </div>
        {!backendOnline && <Badge tone="caution">needs the backend</Badge>}
      </div>

      {/* Drop zone, also a button for keyboard and click users. */}
      {!file && (
        <button
          type="button"
          disabled={locked}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); if (!locked) setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            'w-full rounded-lg border border-dashed px-4 py-5 text-center',
            'transition-colors duration-150',
            dragging ? 'border-accent bg-accent-subtle'
              : 'border-line hover:border-line-strong hover:bg-surface-2/60',
            locked && 'opacity-50 cursor-not-allowed',
          )}
        >
          <UploadCloud className="w-5 h-5 mx-auto text-ink-tertiary" strokeWidth={1.5} />
          <div className="mt-2 text-label text-ink-primary">
            Drop an image, or choose a file
          </div>
          <div className="mt-0.5 text-micro text-ink-tertiary">
            GeoTIFF, PNG or JPEG · up to {formatMB(UPLOAD_MAX_BYTES)} ·
            {' '}0.64-10.24 km per side
          </div>
        </button>
      )}
      <input
        ref={inputRef}
        type="file"
        accept={UPLOAD_ACCEPT}
        className="hidden"
        onChange={(e) => choose(e.target.files?.[0])}
      />

      {file && (
        <div className="rounded-lg border border-line bg-surface-1 p-3.5 space-y-3">
          <div className="flex items-center gap-2.5">
            <FileImage className="w-4 h-4 text-ink-tertiary shrink-0" strokeWidth={1.75} />
            <div className="min-w-0 flex-1">
              <div className="text-label text-ink-primary truncate">{file.name}</div>
              <div className="text-micro text-ink-tertiary">{formatMB(file.size)}</div>
            </div>
            <button
              type="button"
              onClick={reset}
              disabled={busy}
              aria-label="Remove file"
              className="p-1 rounded text-ink-tertiary hover:text-ink-primary hover:bg-surface-2"
            >
              <X className="w-3.5 h-3.5" strokeWidth={2} />
            </button>
          </div>

          {showBbox && (
            <fieldset className="space-y-2" disabled={busy}>
              <legend className="text-micro text-ink-secondary leading-relaxed">
                {needsBbox(file.name)
                  ? 'A PNG or JPEG has no coordinates. Enter the area it covers, in degrees (WGS84).'
                  : 'This file has no georeferencing. Enter the area it covers, in degrees (WGS84).'}
              </legend>
              <div className="grid grid-cols-2 gap-2">
                {BBOX_FIELDS.map((f) => (
                  <label key={f.key} className="space-y-1">
                    <span className="block text-micro text-ink-tertiary">{f.label}</span>
                    <input
                      type="number"
                      inputMode="decimal"
                      step="any"
                      min={f.min}
                      max={f.max}
                      value={bbox[f.key]}
                      onChange={(e) => setBbox({ ...bbox, [f.key]: e.target.value })}
                      className="w-full h-8 px-2.5 rounded-md bg-surface-2 border border-line focus:border-accent focus:outline-none font-mono text-micro text-ink-primary"
                    />
                  </label>
                ))}
              </div>
              {bboxCheck?.error && Object.values(bbox).some((x) => x !== '') && (
                <p className="text-micro text-caution">{bboxCheck.error}</p>
              )}
              {bboxCheck?.extent && (
                <p className={cn('font-mono text-micro',
                  bboxCheck.extent.fits ? 'text-ink-tertiary' : 'text-caution')}>
                  {bboxCheck.extent.widthKm.toFixed(2)} x {bboxCheck.extent.heightKm.toFixed(2)} km
                  {!bboxCheck.extent.fits
                    && ` · the server accepts ${bboxCheck.extent.lo}-${bboxCheck.extent.hi} km per side`}
                </p>
              )}
            </fieldset>
          )}

          {showBands && (
            <div className="space-y-2">
              <label className="block space-y-1">
                <span className="block text-micro text-ink-secondary">
                  Band order, one name per band in file order
                </span>
                <input
                  type="text"
                  value={bandOrder}
                  onChange={(e) => setBandOrder(e.target.value)}
                  placeholder="red,green,blue,nir"
                  disabled={busy}
                  className="w-full h-8 px-2.5 rounded-md bg-surface-2 border border-line focus:border-accent focus:outline-none font-mono text-micro text-ink-primary"
                />
              </label>
              <div className="flex gap-1.5">
                {BAND_PRESETS.map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    onClick={() => setBandOrder(p.value)}
                    className="px-2 h-6 rounded border border-line text-micro text-ink-secondary hover:bg-surface-2"
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <Button
            variant="primary"
            className="w-full"
            onClick={submit}
            disabled={!ready || locked}
            icon={busy ? undefined : UploadCloud}
          >
            {busy ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={2} />
                Preparing scene
              </>
            ) : 'Upload and prepare'}
          </Button>
          {busy && (
            <p className="text-micro text-ink-tertiary">
              Reprojecting to the 10 m grid and fetching terrain. This can take
              a minute.
            </p>
          )}
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-md border border-caution/30 bg-caution/5 px-3 py-2">
          <AlertTriangle className="w-3.5 h-3.5 text-caution shrink-0 mt-0.5" strokeWidth={1.75} />
          <p className="text-micro text-ink-secondary leading-relaxed">{error}</p>
        </div>
      )}

      {uploads.length > 0 && (
        <ul className="space-y-1.5">
          {uploads.map((u) => {
            const selected = u.upload_id === selectedId;
            const disabledRules = Object.keys(u.critic_rules_disabled || {});
            return (
              <li key={u.upload_id}>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onSelect?.(u.upload_id)}
                  aria-pressed={selected}
                  className={cn(
                    'w-full flex items-center gap-3 rounded-lg border p-2 text-left',
                    'transition-colors duration-150',
                    selected ? 'border-accent/40 bg-accent-subtle'
                      : 'border-line hover:bg-surface-2/60',
                  )}
                >
                  <img
                    src={u.preview_url}
                    alt=""
                    className="w-12 h-12 rounded object-cover bg-surface-2 shrink-0"
                  />
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="text-label text-ink-primary truncate">{u.filename}</div>
                    <div className="flex flex-wrap items-center gap-1">
                      <Badge tone={u.spectral_mode === 'rgb' ? 'caution' : 'info'}>
                        {MODE_LABEL[u.spectral_mode] ?? u.spectral_mode}
                      </Badge>
                      <span className="font-mono text-micro text-ink-tertiary">
                        {u.shape?.[0]}x{u.shape?.[1]} px
                      </span>
                      {disabledRules.length > 0 && (
                        <span className="font-mono text-micro text-ink-tertiary">
                          · {disabledRules.join(', ')} not judged
                        </span>
                      )}
                    </div>
                  </div>
                  {selected && (
                    <Check className="w-4 h-4 text-positive shrink-0" strokeWidth={2} />
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
