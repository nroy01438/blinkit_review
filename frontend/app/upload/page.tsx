"use client";

import { useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_AISLE_API_URL || "http://localhost:8000";

interface PreviewResponse {
  suggested_mapping: Record<string, string | null>;
  validation: Record<string, unknown>;
  preview_rows: Record<string, unknown>[];
}

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [sourceName, setSourceName] = useState("");
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [commitResult, setCommitResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) setFile(dropped);
  }

  async function doPreview() {
    if (!file || !sourceName) return;
    setBusy(true);
    setError(null);
    setCommitResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("source_name", sourceName);
      const res = await fetch(`${API_BASE}/upload/preview`, { method: "POST", body: form });
      if (!res.ok) throw new Error(await res.text());
      const data: PreviewResponse = await res.json();
      setPreview(data);
      setMapping(
        Object.fromEntries(Object.entries(data.suggested_mapping).filter(([, v]) => v != null)) as Record<string, string>
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doCommit() {
    if (!file || !sourceName) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("source_name", sourceName);
      form.append("mapping_json", JSON.stringify(mapping));
      const res = await fetch(`${API_BASE}/upload/commit`, { method: "POST", body: form });
      if (!res.ok) throw new Error(await res.text());
      setCommitResult(await res.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">Upload</h1>
        <p className="mt-1 text-sm text-slate-600">
          CSV / XLSX / JSON / JSONL / TXT. Preview and validate before committing — re-uploading the same file is a
          no-op.
        </p>
      </header>

      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-slate-300 bg-white p-10 text-center"
      >
        <p className="text-sm text-slate-600">Drag a file here, or</p>
        <button onClick={() => inputRef.current?.click()} className="rounded-md bg-slate-900 px-4 py-1.5 text-sm font-medium text-white">
          Choose file
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.tsv,.xlsx,.json,.jsonl,.txt"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
        {file && <p className="mt-2 text-sm font-medium text-slate-900">{file.name}</p>}
      </div>

      <div className="flex items-center gap-2">
        <input
          value={sourceName}
          onChange={(e) => setSourceName(e.target.value)}
          placeholder="Source name, e.g. Instagram export"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
        <button
          disabled={!file || !sourceName || busy}
          onClick={doPreview}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Preview
        </button>
      </div>

      {error && <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      {preview && (
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Column mapping</h2>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {Object.keys(preview.suggested_mapping).map((canonical) => (
                <label key={canonical} className="text-xs">
                  <span className="block text-slate-500">{canonical}</span>
                  <input
                    value={mapping[canonical] || ""}
                    onChange={(e) => setMapping({ ...mapping, [canonical]: e.target.value })}
                    className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1"
                  />
                </label>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Validation</h2>
            <pre className="overflow-auto rounded bg-slate-950 p-3 text-xs text-slate-100">
              {JSON.stringify(preview.validation, null, 2)}
            </pre>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Preview (first {preview.preview_rows.length} rows)
            </h2>
            <div className="max-h-64 overflow-auto">
              <table className="w-full text-xs">
                <tbody>
                  {preview.preview_rows.map((row, i) => (
                    <tr key={i} className="border-b border-slate-100">
                      <td className="p-1 text-slate-800">{JSON.stringify(row)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <button
            disabled={busy}
            onClick={doCommit}
            className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Commit
          </button>
        </div>
      )}

      {commitResult && (
        <div className="rounded-lg border border-green-300 bg-green-50 p-4 text-sm text-green-900">
          <p className="font-medium">Committed.</p>
          <p>
            inserted={commitResult.inserted}, exact_dupe_skipped={commitResult.exact_dupe_skipped}, near_dupe_flagged=
            {commitResult.near_dupe_flagged}, rejected={commitResult.rejected_rows?.length ?? 0}
          </p>
          {commitResult.rejected_rows?.length > 0 && (
            <pre className="mt-2 max-h-40 overflow-auto rounded bg-slate-950 p-2 text-xs text-slate-100">
              {JSON.stringify(commitResult.rejected_rows, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
