"use client";

import { useRef, useState } from "react";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) setFile(dropped);
  }

  async function doUpload() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/upload", { method: "POST", body: form });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Upload failed.");
      setResult(json);
    } catch (e: any) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">Upload</h1>
        <p className="mt-1 text-sm text-slate-600">
          For social media conversations — no automated scraping is done there (no logged-in scraping, by design).
          Export what you have (e.g. from X/Instagram&apos;s own export tool) as a CSV with a <code>text</code>{" "}
          column,
          and optionally <code>author</code>, <code>rating</code>, <code>posted_at</code>, <code>url</code>.
        </p>
      </header>

      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-slate-300 bg-white p-10 text-center"
      >
        <p className="text-sm text-slate-600">Drag a CSV here, or</p>
        <button onClick={() => inputRef.current?.click()} className="rounded-md bg-slate-900 px-4 py-1.5 text-sm font-medium text-white">
          Choose file
        </button>
        <input ref={inputRef} type="file" accept=".csv" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        {file && <p className="mt-2 text-sm font-medium text-slate-900">{file.name}</p>}
      </div>

      <button
        disabled={!file || busy}
        onClick={doUpload}
        className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {busy ? "Uploading…" : "Upload"}
      </button>

      {error && <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      {result && (
        <div className="rounded-lg border border-green-300 bg-green-50 p-4 text-sm text-green-900">
          Added {result.inserted} new review(s) out of {result.fetched} rows in the file (duplicates skipped). Go to{" "}
          <a href="/" className="underline">
            Home
          </a>{" "}
          and press &quot;Sync reviews now&quot; to fold these into the answers.
        </div>
      )}
    </div>
  );
}
