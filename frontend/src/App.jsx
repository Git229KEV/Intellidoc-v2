import React, { useState, useRef, useEffect } from 'react';
import './index.css';

const highlightText = (text, entities) => {
  if (!text) return '';
  let highlighted = text;
  
  // Sort entities by length descending to avoid partial replacements messing up
  const allEntities = [
    ...(entities.names || []).map(n => ({ text: n, type: 'name' })),
    ...(entities.amounts || []).map(a => ({ text: a, type: 'amount' })),
    ...(entities.dates || []).map(d => ({ text: d, type: 'date' })),
    ...(entities.organizations || []).map(o => ({ text: o, type: 'main' })),
  ].sort((a, b) => b.text.length - a.text.length);

  // Use a unique marker to avoid recursive highlighting
  allEntities.forEach((entity, index) => {
    const escaped = entity.text.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
    const regex = new RegExp(`(${escaped})`, 'gi');
    highlighted = highlighted.replace(regex, `[[MARKER_${index}]]$1[[/MARKER]]`);
  });

  // Replace markers with actual HTML
  allEntities.forEach((entity, index) => {
    const className = `highlight-${entity.type}`;
    highlighted = highlighted.split(`[[MARKER_${index}]]`).join(`<span class="${className}">`);
    highlighted = highlighted.split('[[/MARKER]]').join('</span>');
  });

  return <div dangerouslySetInnerHTML={{ __html: highlighted }} />;
};

function App() {
  const [file, setFile] = useState(null);
  const [apiKey, setApiKey] = useState('sk_track2_987654321');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const [hoverActive, setHoverActive] = useState(false);
  const [progress, setProgress] = useState(0);
  const [activePage, setActivePage] = useState('analyzer');
  const [progressStage, setProgressStage] = useState('');
  const inputRef = useRef(null);

  // Aurora Mouse Follow (Parallax)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  
  useEffect(() => {
    const handleMouseMove = (e) => {
      setMousePos({ x: e.clientX, y: e.clientY });
      
      const target = e.target;
      const isInteractive = target.closest('button, .singularity-zone, .void-button, .neural-icon, .prism-chip, input');
      setHoverActive(!!isInteractive);
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  const handleDrag = function(e) {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = function(e) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  };

  const handleChange = function(e) {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      handleFileSelected(e.target.files[0]);
    }
  };

  const onUploadClick = () => {
    inputRef.current.click();
  };

  const handleFileSelected = (selectedFile) => {
    setError('');
    setResult(null);
    const validTypes = [
      'application/pdf', 
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
      'image/jpeg', 'image/png', 'image/webp'
    ];
    
    const maxSize = 4 * 1024 * 1024; // 4MB for Vercel
    if (selectedFile.size > maxSize) {
      setError('File too large');
      return;
    }
    
    setFile(selectedFile);
  };

  const getBase64 = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onerror = error => reject(error);
    });
  };

  const analyzeDocument = async () => {
    if (!file) return;
    if (!apiKey) {
      setError('Void Authority Key required.');
      return;
    }

    setLoading(true);
    setError('');
    setProgress(10);
    setProgressStage('Analyzing document...');
    
    // Simulate progress with stage updates
    const interval = setInterval(() => {
      setProgress((prev) => {
        let newProgress = prev + Math.random() * 15;
        
        if (newProgress < 35) {
          setProgressStage('Analyzing document... 📄');
        } else if (newProgress < 65) {
          setProgressStage('Generating summary... 📝');
        } else {
          setProgressStage('Extracting entities... 🔍');
        }
        
        if (newProgress >= 90) return prev;
        return newProgress;
      });
    }, 800);
    
    try {
      const base64 = await getBase64(file);
      setProgress(40);
      
      // Robust type detection using MIME and Extension fallback
      let fileTypeStr = 'image';
      const fileName = file.name.toLowerCase();
      
      if (file.type.includes('pdf') || fileName.endsWith('.pdf')) {
        fileTypeStr = 'pdf';
      } else if (file.type.includes('word') || fileName.endsWith('.docx') || fileName.endsWith('.doc')) {
        fileTypeStr = 'docx';
      } else {
        // For images, prioritize extension for backend MIME detection
        const ext = fileName.split('.').pop();
        if (['png', 'webp', 'jpg', 'jpeg'].includes(ext)) {
          fileTypeStr = ext === 'jpg' ? 'jpeg' : ext;
        } else {
          fileTypeStr = 'image';
        }
      }

      const payload = {
        fileName: file.name,
        fileType: fileTypeStr,
        fileBase64: base64
      };

      const response = await fetch('/api/document-analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': apiKey
        },
        body: JSON.stringify(payload)
      });

      const parseHttpError = async () => {
        const text = await response.text();
        try {
          const j = JSON.parse(text);
          if (j.detail !== undefined) {
            if (Array.isArray(j.detail)) {
              return j.detail.map((d) => d.msg || JSON.stringify(d)).join(' ');
            }
            return String(j.detail);
          }
        } catch {
          /* ignore */
        }
        return text?.slice(0, 500) || '';
      };

      if (!response.ok) {
        const detail = await parseHttpError();
        
        // Handle specific error conditions
        if (detail.includes('File too large') || response.status === 413) {
          throw new Error('File too large');
        }
        if (detail.includes('Unsupported file type') || response.status === 415) {
          throw new Error('Unsupported file type');
        }
        if (response.status === 404) {
          throw new Error('Neural Link Offline [404] — API route not found. Check deployment.');
        }
        if (response.status === 401) {
          throw new Error('Invalid API key (401). Set x-api-key to match server API_KEY.');
        }
        if (response.status === 422) {
          throw new Error(detail || 'Invalid request payload (422).');
        }
        if (response.status === 504 || response.status === 502) {
          throw new Error('Server timed out (gateway). Try a smaller file or retry.');
        }
        throw new Error(
          detail || `Request failed [${response.status}]. If 500: check Vercel env API_KEY and AI provider keys.`
        );
      }

      let data;
      try {
        data = await response.json();
      } catch {
        throw new Error('Invalid JSON from server. Check API deployment.');
      }
      setProgress(100);
      setProgressStage('✅ Complete!');
      setResult(data);
      
      if (data.status === 'failed' || data.status === 'error') {
        setError(data.summary || 'Neural synthesis partially failed.');
      }
    } catch (err) {
      console.error(err);
      const errorMsg = err.message || 'The nebula processor drifted out of phase.';
      
      // Set specific error type
      if (errorMsg === 'File too large' || errorMsg.includes('File too large')) {
        setError('File too large');
      } else if (errorMsg === 'Unsupported file type' || errorMsg.includes('Unsupported file type')) {
        setError('Unsupported file type');
      } else {
        setError('Processing Failed');
      }
    } finally {
      clearInterval(interval);
      setLoading(false);
    }
  };

  const resetAnalysis = () => {
    setFile(null);
    setResult(null);
    setError('');
    setProgress(0);
    setProgressStage('');
    if (inputRef.current) inputRef.current.value = '';
  };

  const copyToClipboard = (text, message = "Intelligence copied to local buffer.") => {
    navigator.clipboard.writeText(text);
    alert(message);
  };

  return (
    <>
      <div className="custom-cursor" style={{ left: `${mousePos.x}px`, top: `${mousePos.y}px` }}></div>
      <div className="custom-cursor-follower" style={{ left: `${mousePos.x}px`, top: `${mousePos.y}px` }}></div>

      {/* Fixed aurora background — sits behind everything, never scrolls */}
      <div className="aurora-bg">
        <div className="aurora-blob blob-1" style={{ transform: `translate(${(mousePos.x - window.innerWidth/2) * 0.05}px, ${(mousePos.y - window.innerHeight/2) * 0.05}px)` }}></div>
        <div className="aurora-blob blob-2" style={{ transform: `translate(${(mousePos.x - window.innerWidth/2) * -0.05}px, ${(mousePos.y - window.innerHeight/2) * -0.05}px)` }}></div>
        <div className="aurora-blob blob-3"></div>
      </div>

      {/* Scrollable app shell */}
      <div className={`nebula-container ${hoverActive ? 'cursor-hover' : ''}`}>
        <div className="app-shell">
          <header className="nebula-header" style={{ marginBottom: '2rem' }}>
            <div className="neon-slug">Neural Intel System v2.1</div>
            <h1 className="nebula-title">
              <span>IntelliDoc</span>
            </h1>
          </header>

          {activePage === 'analyzer' ? (
            <>
              <section className="hero-section">
                <p className="hero-tagline">
                  Extract <strong>intelligence</strong> from the noise. <br/>
                  The ultimate multi-modal document processing engine for 2026.
                </p>
                <div className="value-grid">
                  <div className="value-card">
                    <h3>High Precision</h3>
                    <p>99.9% accuracy in entity extraction using 4-layer neural fallback protocols.</p>
                  </div>
                  <div className="value-card">
                    <h3>Multi-Modal</h3>
                    <p>Native support for PDF, DOCX, and visual image formats with hybrid OCR.</p>
                  </div>
                  <div className="value-card">
                    <h3>Zero Latency</h3>
                    <p>Asynchronous processing pipelines designed for high-frequency data streams.</p>
                  </div>
                </div>
              </section>

              <div className="neural-key-portal">
                <div className="neural-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 15V17M6 21H18C19.1046 21 20 20.1046 20 19V5C20 3.89543 19.1046 3 18 3H6C4.89543 3 4 3.89543 4 5V19C4 20.1046 4.89543 21 6 21Z" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>
                <div className="neural-key-input">
                  <input 
                    type="text" 
                    placeholder="Authority API Key..." 
                    value={apiKey} 
                    onChange={(e) => setApiKey(e.target.value)}
                    className="nebula-input"
                  />
                </div>
              </div>

              <section 
                className={`singularity-zone ${dragActive ? "drag-active" : ""}`}
                onClick={onUploadClick}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
              >
                <div className="singularity-field"></div>
                <div className="singularity-content">
                  <div className="hologram-circle">
                    <img src="/logo.png" alt="IntelliDoc Logo" className="singularity-icon" style={{ filter: 'drop-shadow(0 0 10px var(--accent-void))', borderRadius: '50%', objectFit: 'cover' }} />
                  </div>
                  <h2 className="action-text">{dragActive ? "Inject Data" : "Initialize Source"}</h2>
                  <div className="supported-files-hero">
                    <div className="nebula-chip">📄 DOCX</div>
                    <div className="nebula-chip">📕 PDF</div>
                    <div className="nebula-chip">🖼️ IMAGE</div>
                  </div>
                  <p className="supported-formats-label">
                    🚀 <strong>Supported File Formats</strong> — Drop your document into the nebula.
                    <br />
                    ☁️ Max file upload: 4MB
                  </p>
                </div>
                <input 
                  ref={inputRef} 
                  type="file" 
                  className="file-input" 
                  style={{ display: 'none' }} 
                  onChange={handleChange} 
                  accept=".pdf,.docx,.jpg,.jpeg,.png"
                />
              </section>

              {file && !result && !loading && (
                <div className="floating-layer ready-layer">
                  <div className="nebula-card span-full ready-card">
                    <div style={{ fontSize: 'clamp(1.2rem, 4vw, 2rem)', marginBottom: '2rem', fontWeight: 500, color: 'var(--text-vibrant)', fontFamily: "'Bricolage Grotesque', sans-serif" }}>
                      Ready to analyze <span style={{ color: 'var(--accent-neon)' }}>{file.name}</span>
                    </div>
                    <button className="void-button" onClick={analyzeDocument}>Analyze Document</button>
                  </div>
                </div>
              )}

              {error && (
                <div className="nebula-card span-full" style={{ borderColor: 'var(--danger)', background: 'rgba(239, 68, 68, 0.05)' }}>
                  <h4 style={{ color: 'var(--danger)' }}>Neural Protocol Alert</h4>
                  <p style={{ fontSize: '1.4rem' }}>{error}</p>
                </div>
              )}

              {loading && (
                <div className="nebula-results">
                  <div className="nebula-skeleton span-full" style={{ height: 'auto' }}>
                    <div className="loader-content">
                      <div className="nebula-arc" />
                      <div className="loader-text">{progressStage}</div>
                      <div className="progress-container">
                        <div className="progress-bar" style={{ width: `${progress}%` }}></div>
                      </div>
                      <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                        {Math.round(progress)}% Complete — tuning cosmic neural matrix...
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {result && !loading && (
                <div className="nebula-results">
                  <div className="nebula-card span-full scanning">
                    <div className="scan-line"></div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div>
                        <h4>Core Synthesis</h4>
                        <div className="confidence-badge" style={{ borderColor: result.status === 'success' ? 'var(--accent-neon)' : 'var(--danger)' }}>
                          <span>{result.status === 'success' ? 'Neural Confidence:' : 'Protocol Status:'}</span>
                          <span>{result.status === 'success' ? `${(result.confidence_score * 100).toFixed(1)}%` : result.status.toUpperCase()}</span>
                        </div>
                      </div>
                      <div className="download-actions">
                        <button className="icon-button" onClick={() => copyToClipboard(result.summary)}>
                           COPY SUMMARY
                        </button>
                        <button className="icon-button" onClick={() => setActivePage('docs')}>
                          TECH SPECS
                        </button>
                        <button className="icon-button" style={{ borderColor: 'var(--accent-neon)', color: 'var(--accent-neon)' }} onClick={() => window.print()}>
                          PRINT / PDF
                        </button>
                      </div>
                    </div>
                    {result.error_details && (
                      <div style={{ marginTop: '1rem', padding: '0.8rem', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '4px', border: '1px solid rgba(239, 68, 68, 0.2)', fontSize: '0.8rem', color: 'var(--danger)', fontFamily: 'monospace' }}>
                        <strong>Diagnostic Trace:</strong> {result.error_details}
                      </div>
                    )}
                    <p className="summary-large" style={{ marginTop: '2rem' }}>{result.summary}</p>
                  </div>

                  <div className="floating-layer" id="printable-area">
                    <div className="nebula-card span-small" style={{ borderColor: result.sentiment?.toLowerCase() === 'positive' ? 'var(--accent-neon)' : 'var(--accent-ghost)' }}>
                      <h4>Sentiment Bias</h4>
                      <div style={{ fontSize: '4rem', fontWeight: 800, color: '#fff', textTransform: 'uppercase', letterSpacing: '-0.1em' }}>
                        {result.sentiment}
                      </div>
                    </div>
                    
                    <div className="nebula-card span-large">
                      <h4>Organizations identified</h4>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem' }}>
                        {result.entities?.organizations?.length > 0 
                          ? result.entities.organizations.map((org, i) => <span key={i} className="prism-chip">{org}</span>)
                          : <span style={{ opacity: 0.3 }}>Empty set</span>}
                      </div>
                      <div style={{ marginTop: '2rem', display: 'flex', gap: '2rem' }}>
                        {result.entities?.amounts?.length > 0 && (
                          <div>
                            <h4 style={{ fontSize: '0.6rem' }}>Monetary Factors</h4>
                            {result.entities.amounts.map((a, i) => <div key={i} className="highlight-amount" style={{ marginBottom: '0.4rem', display: 'inline-block', marginRight: '0.5rem' }}>{a}</div>)}
                          </div>
                        )}
                        {result.entities?.dates?.length > 0 && (
                          <div>
                            <h4 style={{ fontSize: '0.6rem' }}>Temporal Anchors</h4>
                            {result.entities.dates.map((d, i) => <div key={i} className="highlight-date" style={{ marginBottom: '0.4rem', display: 'inline-block', marginRight: '0.5rem' }}>{d}</div>)}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="floating-layer">
                    <div className="nebula-card span-large">
                      <h4>Unique Factor Extraction</h4>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem' }}>
                        {result.entities?.unique_identifiers?.length > 0 
                          ? result.entities.unique_identifiers.map((uid, i) => <span key={i} className="prism-chip" style={{ borderColor: 'var(--accent-neon)', background: 'rgba(206, 255, 0, 0.1)' }}>{uid}</span>)
                          : <span style={{ opacity: 0.3 }}>No unique IDs found</span>}
                      </div>
                      <div style={{ marginTop: '2rem', borderTop: '1px solid var(--glass-border)', paddingTop: '2rem', display: 'flex', gap: '3rem' }}>
                        <div>
                          <h4 style={{ fontSize: '0.6rem' }}>Locations identified</h4>
                          {result.entities?.locations?.map((l, i) => <div key={i} style={{ marginBottom: '0.4rem' }}>{l}</div>)}
                        </div>
                        <div>
                          <h4 style={{ fontSize: '0.6rem' }}>Contact mapping</h4>
                          {result.entities?.contact_details?.map((c, i) => <div key={i} style={{ marginBottom: '0.4rem' }}>{c}</div>)}
                        </div>
                      </div>
                    </div>
                    
                    <div className="nebula-card span-small">
                      <h4>Humans detected</h4>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        {result.entities?.names?.map((n, i) => <div key={i} style={{ fontWeight: 500 }}>{n}</div>)}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <section className="how-it-works-view">
              <div className="tech-header">
                <div className="real-time-badge">Technical Documentation</div>
                <h2>How it Works</h2>
                <p>Explore the neural protocols and API structures powering IntelliDoc.</p>
              </div>

              <div className="code-section">
                <div className="code-column">
                  <div className="code-title">
                    <span className="step-id">REQ</span>
                    <h4>cURL Request Simulation</h4>
                  </div>
                  <div className="code-block">
                    <div className="code-header">
                      <span>v1.0 / POST</span>
                      <span>HTTPS / REST</span>
                    </div>
                    <div className="code-content">
                      {`curl -X POST "https://intellidoc-v2.vercel.app/api/document-analyze" \\
  -H "x-api-key: ${apiKey || 'sk_track2_987654321'}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "fileName": "${file?.name || 'document.pdf'}",
    "fileType": "${file?.name?.split('.').pop() || 'pdf'}",
    "fileBase64": "JVBERi0xLjQKJ..."
  }'`}
                    </div>
                  </div>
                  
                  <div className="code-title" style={{ marginTop: '3rem' }}>
                    <span className="step-id">EXP</span>
                    <h4>Exemplar Response</h4>
                  </div>
                  <div className="code-block" style={{ opacity: 0.6 }}>
                    <div className="code-content" style={{ color: 'var(--accent-neon)' }}>
                      {`{
  "status": "success",
  "fileName": "sample1.pdf",
  "summary": "This document is an invoice issued by ABC Pvt Ltd to Ravi Kumar on 10 March 2026 for an amount of ₹10,000.",
  "entities": {
    "names": ["Ravi Kumar"],
    "dates": ["10 March 2026"],
    "organizations": ["ABC Pvt Ltd"],
    "amounts": ["₹10,000"]
  },
  "sentiment": "Neutral"
}`}
                    </div>
                  </div>
                </div>

                <div className="code-column">
                  <div className="code-title">
                    <span className="step-id">OUT</span>
                    <h4>Real-time Neural Output</h4>
                  </div>
                  <div className="code-block" style={{ border: result ? '1px solid var(--accent-neon)' : '1px solid var(--glass-border)' }}>
                    <div className="code-header">
                      <span>{result ? 'Sync Protocol: 200 OK' : 'Waiting for Synthesis...'}</span>
                    </div>
                    <div className="code-content" style={{ color: result ? 'var(--accent-neon)' : 'var(--text-muted)' }}>
                      {result ? JSON.stringify(result, null, 2) : '// Analyze a document to see output here...'}
                    </div>
                  </div>

                  {result && (
                    <div className="nebula-card" style={{ marginTop: '2rem' }}>
                      <h4>Analysis Quick Copy</h4>
                      <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Use the JSON below for your downstream applications.</p>
                      <button className="void-button" style={{ width: '100%', marginTop: '1rem' }} onClick={() => {
                          navigator.clipboard.writeText(JSON.stringify(result, null, 2));
                          alert("Neural trace copied to clipboard.");
                      }}>Copy JSON Trace</button>
                    </div>
                  )}
                </div>
              </div>
            </section>
          )}
        </div>

        <nav className="nebula-nav">
          <div className={`nav-link ${activePage === 'analyzer' ? 'active' : ''}`} onClick={() => setActivePage('analyzer')}>
            <span className="nav-icon">⬡</span>
            <span className="nav-text">Portal</span>
          </div>
          <div className={`nav-link ${activePage === 'docs' ? 'active' : ''}`} onClick={() => setActivePage('docs')}>
            <span className="nav-icon">⌬</span>
            <span className="nav-text">Neural Trace</span>
          </div>
        </nav>

        {result && (
          <div 
            className="neural-reset-portal" 
            onClick={resetAnalysis}
            style={{ 
              position: 'fixed', 
              bottom: '4rem', 
              right: '4rem', 
              zIndex: 1000,
              animation: 'pulseNebula 2s infinite alternate'
            }}
          >
            <button className="void-button" style={{ padding: '1rem 2rem', fontSize: '0.9rem', boxShadow: '0 0 30px var(--accent-neon)' }}>
              NEW ANALYSIS ⬡
            </button>
          </div>
        )}
      </div>
    </>
  );
}

export default App;
