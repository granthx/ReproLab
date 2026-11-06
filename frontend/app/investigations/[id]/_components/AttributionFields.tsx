"use client";

import * as React from "react";
import type { AttributionInput, RecordAttribution, Scientist } from "../../../lib/api";

export function emptyAttribution(): AttributionInput {
  return {
    recorder_id: null,
    recorder_label: "",
    entry_method: "manual_entry",
    associated_role_id: null,
    role_association_note: null,
  };
}

export type AttributionFieldsProps = {
  value: AttributionInput;
  onChange: (value: AttributionInput) => void;
  scientists: Scientist[];
  disabled?: boolean;
};

export default function AttributionFields({ value, onChange, scientists, disabled = false }: AttributionFieldsProps) {
  const id = React.useId();
  function update(patch: Partial<AttributionInput>) {
    onChange({ ...value, ...patch, entry_method: "manual_entry" });
  }

  return <fieldset className="records-form" disabled={disabled} aria-describedby={`${id}-assurance`}>
    <legend>Manual entry attribution</legend>
    <p className="records-note" id={`${id}-assurance`}>Caller-asserted human identity; entry method: manual_entry. Associating a registered role records context, not active agent participation or verified identity.</p>
    <label htmlFor={`${id}-label`}>Human recorder label (required)</label>
    <input id={`${id}-label`} value={value.recorder_label} maxLength={200} required pattern=".*\S.*" onChange={(event) => update({ recorder_label: event.target.value })} />
    <label htmlFor={`${id}-recorder`}>Recorder ID (optional)</label>
    <input id={`${id}-recorder`} value={value.recorder_id ?? ""} maxLength={200} onChange={(event) => update({ recorder_id: event.target.value || null })} />
    <label htmlFor={`${id}-role`}>Associated registered role (optional)</label>
    <select id={`${id}-role`} value={value.associated_role_id ?? ""} onChange={(event) => update({ associated_role_id: event.target.value || null, role_association_note: event.target.value ? value.role_association_note : null })}>
      <option value="">No role association</option>
      {value.associated_role_id && !scientists.some((scientist) => scientist.role_id === value.associated_role_id) && <option value={value.associated_role_id} disabled>{value.associated_role_id} (not in loaded registry)</option>}
      {scientists.map((scientist) => <option key={scientist.role_id} value={scientist.role_id}>{scientist.name} · {scientist.role_id} · {scientist.version}</option>)}
    </select>
    {value.associated_role_id && <>
      <label htmlFor={`${id}-role-note`}>Role association note (required for a role)</label>
      <textarea id={`${id}-role-note`} value={value.role_association_note ?? ""} maxLength={2000} required onChange={(event) => update({ role_association_note: event.target.value || null })} />
    </>}
  </fieldset>;
}

export function AttributionDisplay({ value }: { value: RecordAttribution }) {
  const snapshot = value.constitution_snapshot;
  return <div className="records-card">
    <p><strong>{value.recorder_label}</strong>{value.recorder_id ? ` · ${value.recorder_id}` : ""}</p>
    <p className="records-meta">Entry: {value.entry_method} · Identity assurance: {value.identity_assurance}</p>
    {value.associated_role_id && <p>Caller-associated role: {value.associated_role_id}</p>}
    {value.role_association_note && <p className="records-note">{value.role_association_note}</p>}
    {snapshot ? <>
      <p className="records-meta">Original constitution snapshot: {snapshot.role_id} · version {snapshot.constitution_version}</p>
      <p className="records-hash">Constitution hash: {snapshot.constitution_hash}</p>
      <details><summary>Original constitution snapshot contents</summary><pre>{JSON.stringify(snapshot.constitution_json, null, 2)}</pre></details>
    </> : <p className="records-meta">No constitution snapshot recorded.</p>}
  </div>;
}
