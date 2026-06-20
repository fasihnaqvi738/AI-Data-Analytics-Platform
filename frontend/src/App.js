import { useCallback, useEffect, useMemo, useState } from 'react';
import './App.css';

const API_URL = 'http://127.0.0.1:8000';

function buildChartSvg(chart) {
  const width = 760;
  const height = 360;
  const padding = 54;
  const values = chart.values.map(Number);
  const max = Math.max(...values, 1);
  const colors = ['#14b8a6', '#38bdf8', '#a78bfa', '#f59e0b', '#f43f5e', '#84cc16'];

  if (chart.type === 'pie') {
    let total = values.reduce((sum, value) => sum + value, 0) || 1;
    let offset = 0;
    const circles = values.map((value, index) => {
      const dash = (value / total) * 100;
      const circle = `<circle r="90" cx="190" cy="178" fill="transparent" stroke="${colors[index % colors.length]}" stroke-width="52" stroke-dasharray="${dash} ${100 - dash}" stroke-dashoffset="${-offset}" transform="rotate(-90 190 178)" />`;
      offset += dash;
      return circle;
    }).join('');
    const legend = chart.labels.map((label, index) => `
      <rect x="360" y="${96 + index * 34}" width="14" height="14" rx="3" fill="${colors[index % colors.length]}" />
      <text x="386" y="${108 + index * 34}" fill="#dbeafe" font-size="14">${label}: ${values[index]}</text>
    `).join('');
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
      <rect width="100%" height="100%" fill="#0f172a"/>
      <text x="28" y="34" fill="#f8fafc" font-size="20" font-weight="700">${chart.title}</text>
      ${circles}
      ${legend}
    </svg>`;
  }

  const points = values.map((value, index) => {
    const x = padding + (index * (width - padding * 2)) / Math.max(values.length - 1, 1);
    const y = height - padding - (value / max) * (height - padding * 2);
    return { x, y, value };
  });

  const marks = chart.type === 'line'
    ? `<polyline points="${points.map((point) => `${point.x},${point.y}`).join(' ')}" fill="none" stroke="#14b8a6" stroke-width="4" />`
      + points.map((point) => `<circle cx="${point.x}" cy="${point.y}" r="5" fill="#38bdf8" />`).join('')
    : values.map((value, index) => {
      const barWidth = Math.max((width - padding * 2) / values.length - 16, 16);
      const barHeight = (value / max) * (height - padding * 2);
      const x = padding + index * ((width - padding * 2) / values.length) + 8;
      const y = height - padding - barHeight;
      return `<rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="6" fill="${colors[index % colors.length]}" />`;
    }).join('');

  const labels = chart.labels.map((label, index) => {
    const x = padding + (index * (width - padding * 2)) / Math.max(chart.labels.length - 1, 1);
    return `<text x="${x}" y="${height - 18}" text-anchor="middle" fill="#94a3b8" font-size="12">${label}</text>`;
  }).join('');

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    <rect width="100%" height="100%" fill="#0f172a"/>
    <text x="28" y="34" fill="#f8fafc" font-size="20" font-weight="700">${chart.title}</text>
    <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" stroke="#334155" />
    <line x1="${padding}" y1="${padding}" x2="${padding}" y2="${height - padding}" stroke="#334155" />
    ${marks}
    ${labels}
  </svg>`;
}

function ChartCard({ chart }) {
  const svg = buildChartSvg(chart);

  const downloadChart = () => {
    const blob = new Blob([svg], { type: 'image/svg+xml' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${chart.title.replace(/[^a-z0-9]+/gi, '-').toLowerCase() || 'chart'}.svg`;
    link.click();
    window.URL.revokeObjectURL(url);
  };

  return (
    <article className="chart-card">
      <div className="panel-heading">
        <h3>{chart.title}</h3>
        <button className="ghost-button" type="button" onClick={downloadChart}>
          Download chart
        </button>
      </div>
      <div className="chart-frame" dangerouslySetInnerHTML={{ __html: svg }} />
    </article>
  );
}

function App() {
  const [mode, setMode] = useState('login');
  const [token, setToken] = useState(() => localStorage.getItem('token') || '');
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('user');
    return saved ? JSON.parse(saved) : null;
  });
  const [authForm, setAuthForm] = useState({ username: '', email: '', password: '' });
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedAnalysisFileId, setSelectedAnalysisFileId] = useState(null);
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState([]);
  const [reports, setReports] = useState([]);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);

  const isLoggedIn = Boolean(token && user);
  const selectedAnalysisFile = files.find((file) => file.id === selectedAnalysisFileId);

  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const handleAuthChange = (event) => {
    const { name, value } = event.target;
    setAuthForm((current) => ({ ...current, [name]: value }));
  };

  const saveSession = (data) => {
    localStorage.setItem('token', data.access_token);
    localStorage.setItem('user', JSON.stringify(data.user));
    setToken(data.access_token);
    setUser(data.user);
  };

  const fetchFiles = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/files`, { headers: authHeaders });
      if (!response.ok) throw new Error('Could not load files');
      const data = await response.json();
      setFiles(data);
      setSelectedAnalysisFileId((current) => {
        if (current && data.some((file) => file.id === current)) return current;
        return data[0]?.id || null;
      });
    } catch (error) {
      setMessage(error.message);
    }
  }, [authHeaders]);

  const fetchReports = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/reports`, { headers: authHeaders });
      if (!response.ok) throw new Error('Could not load reports');
      setReports(await response.json());
    } catch (error) {
      setMessage(error.message);
    }
  }, [authHeaders]);

  useEffect(() => {
    if (isLoggedIn) {
      fetchFiles();
      fetchReports();
    }
  }, [fetchFiles, fetchReports, isLoggedIn]);

  const submitAuth = async (event) => {
    event.preventDefault();
    setLoading(true);
    setMessage('');

    try {
      if (mode === 'register') {
        const registerResponse = await fetch(`${API_URL}/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(authForm),
        });
        if (!registerResponse.ok) {
          const error = await registerResponse.json();
          throw new Error(error.detail || 'Registration failed');
        }
      }

      const loginResponse = await fetch(`${API_URL}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: authForm.username, password: authForm.password }),
      });
      if (!loginResponse.ok) {
        const error = await loginResponse.json();
        throw new Error(error.detail || 'Login failed');
      }

      saveSession(await loginResponse.json());
      setAuthForm({ username: '', email: '', password: '' });
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  };

  const uploadFile = async (event) => {
    event.preventDefault();
    if (!selectedFile) {
      setMessage('Choose an Excel or CSV file first');
      return;
    }

    setLoading(true);
    setMessage('');
    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const response = await fetch(`${API_URL}/files`, {
        method: 'POST',
        headers: authHeaders,
        body: formData,
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Upload failed');
      }
      setSelectedFile(null);
      event.target.reset();
      await fetchFiles();
      setMessage('File uploaded successfully');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  };

  const deleteFile = async (fileId) => {
    setLoading(true);
    setMessage('');
    try {
      const response = await fetch(`${API_URL}/files/${fileId}`, {
        method: 'DELETE',
        headers: authHeaders,
      });
      if (!response.ok) throw new Error('Delete failed');
      await fetchFiles();
      setMessage('File deleted');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  };

  const renameFile = async (file) => {
    const newName = window.prompt('Rename file', file.original_filename);
    if (!newName || newName.trim() === file.original_filename) return;

    setLoading(true);
    setMessage('');
    try {
      const response = await fetch(`${API_URL}/files/${file.id}`, {
        method: 'PUT',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ original_filename: newName.trim() }),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Rename failed');
      }
      await fetchFiles();
      setMessage('File renamed');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  };

  const downloadFile = async (file) => {
    setMessage('');
    try {
      const response = await fetch(`${API_URL}/files/${file.id}/download`, { headers: authHeaders });
      if (!response.ok) throw new Error('Download failed');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = file.original_filename;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      setMessage(error.message);
    }
  };

  const sendPrompt = async (event) => {
    event.preventDefault();
    const prompt = chatInput.trim();
    if (!selectedAnalysisFileId) {
      setMessage('Select one uploaded file for analysis');
      return;
    }
    if (!prompt) return;

    const userMessage = { role: 'user', content: prompt };
    const nextMessages = [...chatMessages, userMessage];
    setChatMessages(nextMessages);
    setChatInput('');
    setChatLoading(true);
    setMessage('');

    try {
      const response = await fetch(`${API_URL}/analysis/chat`, {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: selectedAnalysisFileId,
          prompt,
          history: chatMessages.map(({ role, content }) => ({ role, content })),
        }),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'AI analysis failed');
      }
      const data = await response.json();
      setChatMessages([
        ...nextMessages,
        { role: 'assistant', content: data.answer, charts: data.charts || [] },
      ]);
    } catch (error) {
      setChatMessages([
        ...nextMessages,
        { role: 'assistant', content: error.message, charts: [] },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  const clearChat = () => {
    setChatMessages([]);
    setMessage('Chat cleared');
  };

  const generateReport = async () => {
    if (chatMessages.length === 0) {
      setMessage('Chat is empty');
      return;
    }

    setLoading(true);
    setMessage('');
    try {
      const response = await fetch(`${API_URL}/reports`, {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: selectedAnalysisFileId,
          messages: chatMessages.map(({ role, content }) => ({ role, content })),
        }),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Report generation failed');
      }
      await fetchReports();
      setMessage('Report generated and saved');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  };

  const downloadReport = async (report) => {
    try {
      const response = await fetch(`${API_URL}/reports/${report.id}/download`, { headers: authHeaders });
      if (!response.ok) throw new Error('Report download failed');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${report.title}.docx`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      setMessage(error.message);
    }
  };

  const deleteReport = async (reportId) => {
    setLoading(true);
    setMessage('');
    try {
      const response = await fetch(`${API_URL}/reports/${reportId}`, {
        method: 'DELETE',
        headers: authHeaders,
      });
      if (!response.ok) throw new Error('Report delete failed');
      await fetchReports();
      setMessage('Report deleted');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setToken('');
    setUser(null);
    setFiles([]);
    setReports([]);
    setChatMessages([]);
    setMessage('');
  };

  if (isLoggedIn) {
    return (
      <main className="shell">
        <section className="topbar">
          <div>
            <p className="eyebrow">AI Data Analytics Platform</p>
            <h1>Welcome {user.username}</h1>
          </div>
          <button className="ghost-button" type="button" onClick={logout}>Logout</button>
        </section>

        <section className="dashboard-grid">
          <form className="panel upload-panel" onSubmit={uploadFile}>
            <div>
              <p className="eyebrow">Upload data</p>
              <h2>Add a new workbook</h2>
            </div>
            <input type="file" accept=".xls,.xlsx,.csv" onChange={(event) => setSelectedFile(event.target.files[0])} />
            <button type="submit" disabled={loading}>{loading ? 'Working...' : 'Upload file'}</button>
            {message && <p className="status-message">{message}</p>}
          </form>

          <section className="panel files-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Your files</p>
                <h2>Select one file for analysis</h2>
              </div>
              <button className="ghost-button" type="button" onClick={fetchFiles}>Refresh</button>
            </div>

            {files.length === 0 ? (
              <p className="empty-state">No files uploaded yet.</p>
            ) : (
              <div className="file-list">
                {files.map((file) => (
                  <article className={`file-row ${selectedAnalysisFileId === file.id ? 'selected-file' : ''}`} key={file.id}>
                    <label className="file-select">
                      <input
                        type="checkbox"
                        checked={selectedAnalysisFileId === file.id}
                        onChange={() => setSelectedAnalysisFileId(selectedAnalysisFileId === file.id ? null : file.id)}
                      />
                      <span>
                        <strong>{file.original_filename}</strong>
                        <small>{(file.size / 1024).toFixed(1)} KB uploaded on {new Date(file.uploaded_at).toLocaleString()}</small>
                      </span>
                    </label>
                    <div className="file-actions">
                      <button type="button" onClick={() => downloadFile(file)}>Download</button>
                      <button type="button" onClick={() => renameFile(file)}>Rename</button>
                      <button type="button" onClick={() => deleteFile(file.id)}>Delete</button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </section>

        <section className="panel chat-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">AI analysis chat</p>
              <h2>{selectedAnalysisFile ? `Analyzing ${selectedAnalysisFile.original_filename}` : 'Choose a file to begin'}</h2>
            </div>
            <div className="chat-actions">
              <button className="ghost-button" type="button" onClick={clearChat}>Clear chat</button>
              <button type="button" onClick={generateReport} disabled={loading || chatMessages.length === 0}>
                Generate Report
              </button>
            </div>
          </div>

          <div className="chat-window">
            {chatMessages.length === 0 ? (
              <p className="empty-state">Ask for insights, trends, outliers, summary statistics, or charts from the selected file.</p>
            ) : (
              chatMessages.map((chat, index) => (
                <article className={`chat-message ${chat.role}`} key={`${chat.role}-${index}`}>
                  <strong>{chat.role === 'user' ? 'You' : 'AI Assistant'}</strong>
                  <p>{chat.content}</p>
                  {chat.charts?.length > 0 && (
                    <div className="charts-grid">
                      {chat.charts.map((chart, chartIndex) => (
                        <ChartCard chart={chart} key={`${chart.title}-${chartIndex}`} />
                      ))}
                    </div>
                  )}
                </article>
              ))
            )}
            {chatLoading && <p className="status-message">AI is analyzing your file...</p>}
          </div>

          <form className="chat-form" onSubmit={sendPrompt}>
            <textarea
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              placeholder="Ask for insights, anomalies, trends, or a chart..."
              rows="4"
            />
            <button type="submit" disabled={chatLoading || !selectedAnalysisFileId}>
              {chatLoading ? 'Analyzing...' : 'Send prompt'}
            </button>
          </form>
        </section>

        <section className="panel reports-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Saved reports</p>
              <h2>Word report history</h2>
            </div>
            <button className="ghost-button" type="button" onClick={fetchReports}>Refresh</button>
          </div>
          {reports.length === 0 ? (
            <p className="empty-state">No reports generated yet.</p>
          ) : (
            <div className="report-list">
              {reports.map((report) => (
                <article className="report-row" key={report.id}>
                  <div>
                    <strong>{report.title}</strong>
                    <span>{new Date(report.created_at).toLocaleString()}</span>
                  </div>
                  <div className="file-actions">
                    <button type="button" onClick={() => downloadReport(report)}>Download</button>
                    <button type="button" onClick={() => deleteReport(report.id)}>Delete</button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </main>
    );
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div>
          <p className="eyebrow">AI Data Analytics Platform</p>
          <h1>{mode === 'login' ? 'Login' : 'Create account'}</h1>
        </div>

        <form onSubmit={submitAuth}>
          <label>
            Username
            <input name="username" value={authForm.username} onChange={handleAuthChange} required />
          </label>

          {mode === 'register' && (
            <label>
              Email
              <input name="email" type="email" value={authForm.email} onChange={handleAuthChange} required />
            </label>
          )}

          <label>
            Password
            <input name="password" type="password" value={authForm.password} onChange={handleAuthChange} required />
          </label>

          <button type="submit" disabled={loading}>
            {loading ? 'Please wait...' : mode === 'login' ? 'Login' : 'Register'}
          </button>
        </form>

        <button
          className="text-button"
          type="button"
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login');
            setMessage('');
          }}
        >
          {mode === 'login' ? 'Need an account? Register' : 'Already have an account? Login'}
        </button>

        {message && <p className="status-message">{message}</p>}
      </section>
    </main>
  );
}

export default App;
