'use client';

import { useRef, useState } from 'react';
import { upload } from '@vercel/blob/client';

function fmt(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export default function Home() {
  const [file, setFile] = useState(null);
  const [keywords, setKeywords] = useState('');
  const [phase, setPhase] = useState('idle'); // idle | uploading | processing | done | error
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const [clips, setClips] = useState([]);
  const timer = useRef(null);

  function poll(jobId, startedAt) {
    timer.current = setTimeout(async () => {
      try {
        const res = await fetch(`/api/status?id=${jobId}`, { cache: 'no-store' });
        const data = await res.json();
        if (data.status === 'done') {
          setClips(data.clips);
          setPhase('done');
          return;
        }
        if (data.status === 'error') {
          setError(data.error || 'Processing failed.');
          setPhase('error');
          return;
        }
      } catch (e) {
        // network blip: keep polling
      }
      if (Date.now() - startedAt > 3 * 60 * 60 * 1000) {
        setError('Timed out waiting for clips. Check the Actions tab on your GitHub repo.');
        setPhase('error');
        return;
      }
      poll(jobId, startedAt);
    }, 10000);
  }

  async function start() {
    if (!file) return;
    clearTimeout(timer.current);
    setClips([]);
    setError('');
    setProgress(0);
    setPhase('uploading');
    try {
      const jobId = crypto.randomUUID();
      const blob = await upload(`uploads/${jobId}/${file.name}`, file, {
        access: 'public',
        handleUploadUrl: '/api/upload',
        multipart: true,
        onUploadProgress: ({ percentage }) => setProgress(Math.round(percentage)),
      });
      const res = await fetch('/api/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jobId, videoUrl: blob.url, keywords }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Could not start the job.');
      setPhase('processing');
      poll(jobId, Date.now());
    } catch (e) {
      setError(e.message || 'Upload failed.');
      setPhase('error');
    }
  }

  const busy = phase === 'uploading' || phase === 'processing';

  return (
    <main>
      <h1>Turn one long video into vertical clips</h1>
      <p className="lead">
        Upload a podcast, stream, or interview you own. Clipper finds the strongest 30 to 60
        second moments, crops them to 9:16, and burns in captions.
      </p>

      <label className="drop">
        <input
          type="file"
          accept="video/*"
          disabled={busy}
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
        <strong>{file ? file.name : 'Choose a video'}</strong>
        <span>{file ? `${(file.size / 1024 / 1024).toFixed(0)} MB` : 'MP4 or MOV, up to 2 GB'}</span>
      </label>

      <label className="field">
        Words to look for
        <small>Optional. Separate with commas, for example: launch, secret, price</small>
        <input
          type="text"
          value={keywords}
          disabled={busy}
          onChange={(e) => setKeywords(e.target.value)}
        />
      </label>

      <button className="go" onClick={start} disabled={!file || busy}>
        {busy ? 'Working...' : 'Make clips'}
      </button>

      {phase === 'uploading' && (
        <>
          <div className="bar"><div style={{ width: `${progress}%` }} /></div>
          <p className="status">Uploading your video: {progress}%</p>
        </>
      )}

      {phase === 'processing' && (
        <p className="status">
          Finding the best moments and rendering clips. A one-hour video can take 15 to 30
          minutes. Keep this tab open.
        </p>
      )}

      {phase === 'error' && <p className="error">{error}</p>}

      {phase === 'done' && (
        <>
          <p className="status">{clips.length} clips ready.</p>
          <div className="grid">
            {clips.map((c) => (
              <div className="clip" key={c.file}>
                <video src={c.url} controls preload="metadata" playsInline />
                <p>{c.hook}</p>
                <span className="time">{fmt(c.start)} to {fmt(c.end)}</span>
                <p><a href={`${c.url}?download=1`}>Download</a></p>
              </div>
            ))}
          </div>
        </>
      )}
    </main>
  );
}
