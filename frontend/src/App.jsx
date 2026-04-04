import React, { useState, useRef, useEffect } from 'react';
import { supabase } from './supabaseClient';
import jsPDF from 'jspdf';
import './index.css';const highlightText = (text, entities) => {
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
  const [stepIndex, setStepIndex] = useState(0);
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [dashboardFiles, setDashboardFiles] = useState([]);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [dashboardTab, setDashboardTab] = useState('uploaded'); // 'uploaded' or 'results'
  // In-page modal state
  const [modal, setModal] = useState({ visible: false, type: 'info', title: '', message: '', onConfirm: null });
  const inputRef = useRef(null);

  const showModal = (type, title, message, onConfirm = null) => {
    setModal({ visible: true, type, title, message, onConfirm });
  };
  const closeModal = () => setModal(m => ({ ...m, visible: false, onConfirm: null }));

  const nebulaSteps = [
    { id: 0, title: 'Analyzing document...' },
    { id: 1, title: 'Extracting entities...' },
    { id: 2, title: 'Generating summary...' },
  ];

  // Aurora Mouse Follow (Parallax)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setAuthLoading(false);
    });
    
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });

    return () => subscription.unsubscribe();
  }, []);

  const fetchDashboardFiles = async () => {
    if (!user) return;
    setDashboardLoading(true);
    
    const targetBucket = dashboardTab === 'uploaded' ? 'documents' : 'analysis-results';
    
    const { data, error } = await supabase.storage
      .from(targetBucket)
      .list(user.id, {
        limit: 100,
        offset: 0,
        sortBy: { column: 'created_at', order: 'desc' },
      });
      
    if (error) {
      console.error("Error fetching dashboard files", error);
      showModal('error', 'Cloud Storage Error', 'Failed to fetch files. Please ensure your bucket has a SELECT policy for authenticated users.');
    } else {
      setDashboardFiles(data || []);
    }
    setDashboardLoading(false);
  };

  useEffect(() => {
    if (activePage === 'dashboard') {
      fetchDashboardFiles();
    }
  }, [activePage, dashboardTab, user]);

  const handleAccessFile = async (fileName) => {
    try {
      const targetBucket = dashboardTab === 'uploaded' ? 'documents' : 'analysis-results';
      const { data, error } = await supabase.storage
        .from(targetBucket)
        .createSignedUrl(`${user.id}/${fileName}`, 3600);
        
      if (error) throw error;
      window.open(data.signedUrl, '_blank');
    } catch (err) {
      console.error(err);
      showModal('error', 'Access Failed', 'Failed to securely open file: ' + err.message);
    }
  };

  const handleDeleteFile = (fileName) => {
    const targetBucket = dashboardTab === 'uploaded' ? 'documents' : 'analysis-results';
    showModal('confirm', 'Confirm Deletion', `Are you sure you want to permanently delete "${fileName.split('_').slice(1).join('_') || fileName}" from ${targetBucket}?`, async () => {
      try {
        const { error } = await supabase.storage
          .from(targetBucket)
          .remove([`${user.id}/${fileName}`]);
          
        if (error) throw error;
        closeModal();
        fetchDashboardFiles();
      } catch (err) {
        console.error(err);
        showModal('error', 'Delete Failed', 'Could not delete file. Ensure you have DELETE policies configured on your Supabase bucket.');
      }
    });
  };

  const generateAndUploadAnalysisPDF = async (analysisResult, originalFileName) => {
    if (!user || !analysisResult) return;
    try {
      const doc = new jsPDF();
      const pageW = doc.internal.pageSize.getWidth();
      const margin = 14;
      const maxW = pageW - margin * 2;
      let y = 20;

      // Header
      doc.setFillColor(10, 10, 30);
      doc.rect(0, 0, pageW, 30, 'F');
      doc.setTextColor(0, 230, 118);
      doc.setFontSize(18);
      doc.setFont('helvetica', 'bold');
      doc.text('IntelliDoc — Analysis Report', margin, y);
      y += 12;

      doc.setTextColor(100, 100, 120);
      doc.setFontSize(9);
      doc.setFont('helvetica', 'normal');
      doc.text(`File: ${originalFileName}  |  Generated: ${new Date().toLocaleString()}`, margin, y);
      y += 12;

      // Summary
      if (analysisResult.summary) {
        doc.setTextColor(30, 30, 30);
        doc.setFontSize(11);
        doc.setFont('helvetica', 'bold');
        doc.text('Summary', margin, y); y += 7;
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(10);
        const summaryLines = doc.splitTextToSize(analysisResult.summary, maxW);
        summaryLines.forEach(line => {
          if (y > 270) { doc.addPage(); y = 20; }
          doc.text(line, margin, y); y += 6;
        });
        y += 4;
      }

      // Entities
      const entities = analysisResult.entities || {};
      const entityGroups = [
        { label: 'Names', items: entities.names },
        { label: 'Organizations', items: entities.organizations },
        { label: 'Dates', items: entities.dates },
        { label: 'Amounts', items: entities.amounts },
      ];
      entityGroups.forEach(({ label, items }) => {
        if (items && items.length > 0) {
          if (y > 270) { doc.addPage(); y = 20; }
          doc.setFontSize(11); doc.setFont('helvetica', 'bold'); doc.setTextColor(30, 30, 30);
          doc.text(label, margin, y); y += 7;
          doc.setFontSize(10); doc.setFont('helvetica', 'normal');
          const txt = items.join(', ');
          const lines = doc.splitTextToSize(txt, maxW);
          lines.forEach(line => { if (y > 270) { doc.addPage(); y = 20; } doc.text(line, margin, y); y += 6; });
          y += 4;
        }
      });

      // Key facts
      if (analysisResult.key_facts && analysisResult.key_facts.length > 0) {
        if (y > 270) { doc.addPage(); y = 20; }
        doc.setFontSize(11); doc.setFont('helvetica', 'bold'); doc.setTextColor(30, 30, 30);
        doc.text('Key Facts', margin, y); y += 7;
        doc.setFontSize(10); doc.setFont('helvetica', 'normal');
        analysisResult.key_facts.forEach(fact => {
          if (y > 270) { doc.addPage(); y = 20; }
          const lines = doc.splitTextToSize(`• ${fact}`, maxW);
          lines.forEach(line => { doc.text(line, margin, y); y += 6; });
        });
      }

      const pdfBlob = doc.output('blob');
      const timestamp = new Date().getTime();
      const pdfName = `${timestamp}_analysis_${originalFileName}.pdf`;

      const { error: uploadErr } = await supabase.storage
        .from('analysis-results')
        .upload(`${user.id}/${pdfName}`, pdfBlob, { contentType: 'application/pdf' });

      if (uploadErr) throw uploadErr;
      showModal('success', 'Analysis Saved!', `Analysis PDF has been saved to your cloud archive as "${pdfName}".`);
    } catch (err) {
      console.error('PDF generation/upload error:', err);
      showModal('error', 'PDF Upload Failed', 'Could not save analysis PDF: ' + err.message);
    }
  };

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

  const signInWithGoogle = async () => {
    try {
      await supabase.auth.signInWithOAuth({ provider: 'google' });
    } catch (err) {
      console.error(err);
      setError('Failed to authenticate');
    }
  };

  const handleSignOut = async () => {
    await supabase.auth.signOut();
  };

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

  const handleFileSelected = async (selectedFile) => {
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

    // Auto-upload the source document immediately
    if (user) {
      try {
        const timestamp = new Date().getTime();
        const basePath = `${user.id}`;
        const { data, error } = await supabase.storage
          .from('documents')
          .upload(`${basePath}/${timestamp}_${selectedFile.name}`, selectedFile);
          
        if (error) {
          console.error("Supabase Upload Error:", error);
          showModal('error', 'Upload Failed', `Failed to auto-upload to Supabase! Reason: ${error.message}. Did you set up Storage Policies/RLS?`);
        } else {
          console.log("File auto-uploaded to Supabase successfully.");
        }
      } catch (err) {
        console.error("Auto-upload exception", err);
      }
    }
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
    setProgressStage('Initializing neural synth protocols...');
    
    // Simulate progress with stage updates
    const interval = setInterval(() => {
      setProgress((prev) => {
        let newProgress = prev + Math.random() * 15;
        if (newProgress > 99) newProgress = 99;

        const newStepIndex = newProgress < 35 ? 0 : newProgress < 65 ? 1 : 2;
        setStepIndex(newStepIndex);
        setProgressStage('Initializing neural synth protocols...');
        
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
    showModal('success', 'Copied!', message);
  };

  if (authLoading) {
    return <div style={{height: '100vh', display: 'flex', justifyContent: 'center', alignItems: 'center', color: 'var(--accent-neon)'}}>Initializing Neural Auth...</div>;
  }

  return (
    <>
      <div className="custom-cursor" style={{ left: `${mousePos.x}px`, top: `${mousePos.y}px` }}></div>
      <div className="custom-cursor-follower" style={{ left: `${mousePos.x}px`, top: `${mousePos.y}px` }}></div>

      {/* In-Page Modal */}
      {modal.visible && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 9999,
          background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(6px)',
          display: 'flex', justifyContent: 'center', alignItems: 'center',
        }} onClick={modal.type !== 'confirm' ? closeModal : undefined}>
          <div style={{
            background: 'rgba(15,15,35,0.98)', border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: '16px', padding: '2rem 2.5rem', maxWidth: '420px', width: '90%',
            boxShadow: modal.type === 'error' ? '0 0 40px rgba(255,50,50,0.2)' :
                       modal.type === 'success' ? '0 0 40px rgba(0,230,118,0.2)' :
                       '0 0 40px rgba(0,150,255,0.15)',
            borderColor: modal.type === 'error' ? 'rgba(255,50,50,0.3)' :
                         modal.type === 'success' ? 'rgba(0,230,118,0.3)' :
                         'rgba(0,150,255,0.3)',
          }} onClick={e => e.stopPropagation()}>
            <div style={{
              fontSize: '1.5rem', marginBottom: '0.5rem',
              color: modal.type === 'error' ? '#ff4444' : modal.type === 'success' ? 'var(--accent-neon)' : '#4da6ff'
            }}>
              {modal.type === 'error' ? '⚠' : modal.type === 'success' ? '✓' : '◈'}
            </div>
            <h3 style={{ marginBottom: '0.75rem', fontSize: '1.1rem' }}>{modal.title}</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1.5rem', lineHeight: 1.6 }}>{modal.message}</p>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              {modal.type === 'confirm' && (
                <button className="icon-button" style={{ borderColor: 'rgba(255,50,50,0.4)', color: 'rgba(255,80,80,0.9)' }} onClick={modal.onConfirm}>
                  Confirm Delete
                </button>
              )}
              <button className="void-button" style={{ fontSize: '0.85rem', padding: '0.5rem 1.25rem' }} onClick={closeModal}>
                {modal.type === 'confirm' ? 'Cancel' : 'Close'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Fixed aurora background — sits behind everything, never scrolls */}
      <div className="aurora-bg">
        <div className="aurora-blob blob-1" style={{ transform: `translate(${(mousePos.x - window.innerWidth/2) * 0.05}px, ${(mousePos.y - window.innerHeight/2) * 0.05}px)` }}></div>
        <div className="aurora-blob blob-2" style={{ transform: `translate(${(mousePos.x - window.innerWidth/2) * -0.05}px, ${(mousePos.y - window.innerHeight/2) * -0.05}px)` }}></div>
        <div className="aurora-blob blob-3"></div>
      </div>

      {/* Scrollable app shell */}
      <div className={`nebula-container ${hoverActive ? 'cursor-hover' : ''}`}>
        <div className="app-shell">
          <header className="nebula-header" style={{ marginBottom: '2rem', position: 'relative' }}>
            <div className="neon-slug">Neural Intel System v2.1</div>
            <h1 className="nebula-title">
              <span>IntelliDoc</span>
            </h1>
            {user && (
              <button className="void-button" onClick={handleSignOut} style={{ position: 'absolute', right: '0', top: '50%', transform: 'translateY(-50%)', fontSize: '0.8rem', padding: '0.5rem 1rem' }}>Sign Out</button>
            )}
          </header>

          {!user ? (
            <div className="login-portal" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: '10vh' }}>
              <div className="nebula-card" style={{ maxWidth: '400px', textAlign: 'center' }}>
                <h2 style={{ marginBottom: '1rem', color: 'var(--accent-neon)' }}>Neural Identity Required</h2>
                <p style={{ color: 'var(--text-muted)', marginBottom: '2rem' }}>Authorize access to the Nebula dashboard to initialize scanning protocols.</p>
                <button className="void-button" onClick={signInWithGoogle} style={{ width: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '1rem', fontSize: '1rem' }}>
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M22.56 12.25C22.56 11.47 22.49 10.73 22.36 10H12V14.26H17.92C17.66 15.63 16.88 16.78 15.72 17.56V20.35H19.28C21.36 18.43 22.56 15.6 22.56 12.25Z" fill="#4285F4"/>
                    <path d="M12 23C14.97 23 17.46 22.02 19.28 20.35L15.72 17.56C14.73 18.22 13.48 18.63 12 18.63C9.13 18.63 6.7 16.69 5.82 14.12H2.17V16.94C3.99 20.53 7.7 23 12 23Z" fill="#34A853"/>
                    <path d="M5.82 14.12C5.59 13.45 5.46 12.74 5.46 12C5.46 11.26 5.59 10.55 5.82 9.88V7.06H2.17C1.43 8.55 1 10.22 1 12C1 13.78 1.43 15.45 2.17 16.94L5.82 14.12Z" fill="#FBBC05"/>
                    <path d="M12 5.38C13.62 5.38 15.06 5.93 16.2 7.02L19.35 3.87C17.46 2.11 14.97 1 12 1C7.7 1 3.99 3.47 2.17 7.06L5.82 9.88C6.7 7.31 9.13 5.38 12 5.38Z" fill="#EA4335"/>
                  </svg>
                  Connect with Google Identity
                </button>
              </div>
            </div>
          ) : activePage === 'dashboard' ? (
            <section className="dashboard-section" style={{ padding: '2rem 0' }}>
              <div className="tech-header" style={{ marginBottom: '2rem' }}>
                <div className="real-time-badge">Cloud Storage</div>
                <h2>Neural Data Archives</h2>
                <p>All previously initialized sources synchronized with the Nebula network.</p>
              </div>

              {/* Navigation Tabs */}
              <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '1rem' }}>
                <button 
                  style={{
                    padding: '0.5rem 1.2rem',
                    borderRadius: '8px',
                    border: dashboardTab === 'uploaded' ? '1px solid var(--accent-neon)' : '1px solid rgba(255,255,255,0.15)',
                    background: dashboardTab === 'uploaded' ? 'rgba(0,0,0,0.6)' : 'rgba(255,255,255,0.04)',
                    color: dashboardTab === 'uploaded' ? 'var(--accent-neon)' : 'rgba(255,255,255,0.45)',
                    cursor: 'pointer',
                    fontWeight: dashboardTab === 'uploaded' ? 700 : 400,
                    letterSpacing: '0.05em',
                    fontSize: '0.85rem',
                    transition: 'all 0.2s ease',
                  }}
                  onClick={() => setDashboardTab('uploaded')}
                >
                  Uploaded Files
                </button>
                <button 
                  style={{
                    padding: '0.5rem 1.2rem',
                    borderRadius: '8px',
                    border: dashboardTab === 'results' ? '1px solid var(--accent-neon)' : '1px solid rgba(255,255,255,0.15)',
                    background: dashboardTab === 'results' ? 'rgba(0,0,0,0.6)' : 'rgba(255,255,255,0.04)',
                    color: dashboardTab === 'results' ? 'var(--accent-neon)' : 'rgba(255,255,255,0.45)',
                    cursor: 'pointer',
                    fontWeight: dashboardTab === 'results' ? 700 : 400,
                    letterSpacing: '0.05em',
                    fontSize: '0.85rem',
                    transition: 'all 0.2s ease',
                  }}
                  onClick={() => setDashboardTab('results')}
                >
                  Document Analysis Results
                </button>
              </div>

              {dashboardLoading ? (
                <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--accent-neon)' }}>Querying network...</div>
              ) : dashboardFiles.length === 0 ? (
                <div className="nebula-card" style={{ textAlign: 'center', opacity: 0.6 }}>
                  <p>No localized data fragments found.</p>
                </div>
              ) : (
                <div className="value-grid">
                  {dashboardFiles.map((f, i) => {
                    // Supabase list can return the ".emptyFolderPlaceholder" if folder is empty.
                    if (f.name === ".emptyFolderPlaceholder") return null;
                    return (
                      <div key={i} className="nebula-card span-small" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        <div style={{ wordBreak: 'break-all', fontWeight: 600 }}>{f.name.split('_').slice(1).join('_') || f.name}</div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Created: {new Date(f.created_at).toLocaleString()}</div>
                        
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: 'auto' }}>
                          <button className="void-button" style={{ width: '100%', fontSize: '0.8rem' }} onClick={() => handleAccessFile(f.name)}>
                            {dashboardTab === 'uploaded' ? "ACCESS DATA" : "ACCESS RESULT"}
                          </button>
                          
                          {dashboardTab === 'uploaded' && (
                            <button 
                              className="icon-button" 
                              style={{ width: '100%', fontSize: '0.8rem', justifyContent: 'center' }} 
                              onClick={() => {
                                if (result && file) {
                                  generateAndUploadAnalysisPDF(result, file.name);
                                } else {
                                  setActivePage('analyzer');
                                }
                              }}
                            >
                              {result ? 'SAVE ANALYSIS AS PDF' : 'GO TO ANALYZER'}
                            </button>
                          )}
                          
                          <button className="icon-button" style={{ width: '100%', fontSize: '0.8rem', justifyContent: 'center', borderColor: 'rgba(255, 50, 50, 0.4)', color: 'rgba(255, 50, 50, 0.8)' }} onClick={() => handleDeleteFile(f.name)}>
                            DELETE
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          ) : activePage === 'analyzer' ? (
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
                  <div className="supported-formats-line">Supported formats:</div>
                  <div className="supported-files-hero">
                    <div className="nebula-chip format-chip">
                      <span className="chip-icon pdf-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M6 2h9l5 5v15a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" />
                          <path d="M15 2v5h5" />
                          <path d="M8 14h4" />
                          <path d="M8 18h4" />
                          <path d="M8 10h4" />
                        </svg>
                      </span>
                      <span>PDF</span>
                    </div>
                    <div className="nebula-chip format-chip">
                      <span className="chip-icon docx-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M6 2h9l5 5v15a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" />
                          <path d="M15 2v5h5" />
                          <path d="M8 17v-6l2 4 2-4v6" />
                          <path d="M18 17h-2v-6" />
                        </svg>
                      </span>
                      <span>DOCX</span>
                    </div>
                    <div className="nebula-chip format-chip">
                      <span className="chip-icon image-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="3" y="4" width="18" height="16" rx="2" />
                          <circle cx="8.5" cy="8.5" r="1.5" />
                          <path d="M21 15l-5-5-4 4-3-3-4 4" />
                        </svg>
                      </span>
                      <span>IMAGE</span>
                    </div>
                  </div>
                  <div className="max-file-size">Max file upload size 4MB</div>
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
                  <div className="nebula-card span-full loader-card">
                    <div className="loader-header">
                      <h2>Analyzing document using AI...</h2>
                    </div>
                    <div className="loader-stages">
                      {nebulaSteps.map((step, index) => {
                        const statusClass = index < stepIndex ? 'completed' : index === stepIndex ? 'active' : '';
                        const icon = index < stepIndex ? '✓' : index === stepIndex ? '•' : '○';
                        return (
                          <div key={step.id} className={`stage-item ${statusClass}`}>
                            <span className="stage-icon">{icon}</span>
                            <span>{step.title}</span>
                          </div>
                        );
                      })}
                    </div>
                    <div className="progress-container">
                      <div className="progress-bar" style={{ width: `${progress}%` }}></div>
                    </div>
                    <div className="loader-footer">
                      <span>{progressStage}</span>
                      <span>{Math.round(progress)}%</span>
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
                    <div className="summary-large" style={{ marginTop: '2rem' }}>
                      <p>{result.summary}</p>
                    </div>
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
          <div className={`nav-link ${activePage === 'dashboard' ? 'active' : ''}`} onClick={() => setActivePage('dashboard')}>
            <span className="nav-icon">◱</span>
            <span className="nav-text">Dashboard</span>
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
