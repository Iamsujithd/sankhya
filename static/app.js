/* ═══════════════════════════════════════════
   SANKHYA AI — Application Logic
   Handles: file upload, chat, rendering
   ═══════════════════════════════════════════ */

'use strict';

// ── DOM refs ──
const dropZone     = document.getElementById('drop-zone');
const fileInput    = document.getElementById('file-input');
const datasetInfo  = document.getElementById('dataset-info');
const columnsList  = document.getElementById('columns-list');
const metaFilename = document.getElementById('meta-filename');
const metaShape    = document.getElementById('meta-shape');
const statusText   = document.getElementById('status-text');
const statusDot    = document.getElementById('status-dot');
const chatMessages = document.getElementById('chat-messages');
const chatForm     = document.getElementById('chat-form');
const chatInput    = document.getElementById('chat-input');
const sendBtn      = document.getElementById('send-btn');
const suggestions  = document.getElementById('suggestions');
const welcomeState = document.getElementById('welcome-state');

// ── State ──
let fileUploaded = false;
let isLoading    = false;

// ════════════════════════════
// STATUS HELPERS
// ════════════════════════════

function setStatus(text, color = 'green') {
    statusText.textContent = text;
    statusDot.className = `status-dot ${color}`;
}

// ════════════════════════════
// FILE UPLOAD
// ════════════════════════════

dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        fileInput.click();
    }
});

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', (e) => {
    if (!dropZone.contains(e.relatedTarget)) {
        dropZone.classList.remove('dragover');
    }
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) handleFileUpload(file);
});

fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) handleFileUpload(file);
    fileInput.value = '';
});

async function handleFileUpload(file) {
    const MAX_MB = 50;
    if (file.size > MAX_MB * 1024 * 1024) {
        appendAssistantError(`File too large (${(file.size / 1e6).toFixed(1)} MB). Please upload a file under ${MAX_MB} MB.`);
        return;
    }

    const allowed = ['.csv', '.xls', '.xlsx', '.json'];
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!allowed.includes(ext)) {
        appendAssistantError(`Unsupported format "${ext}". Please upload a CSV, Excel (.xls / .xlsx), or JSON file.`);
        return;
    }

    setStatus('Uploading and analyzing dataset…', 'blue');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/upload', { method: 'POST', body: formData });

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(err.detail || 'Upload failed');
        }

        const data = await res.json();

        // Populate sidebar metadata
        metaFilename.textContent = data.filename;
        metaFilename.title = data.filename;
        metaShape.textContent = `${data.shape[0]} × ${data.shape[1]}`;

        // Render column list
        columnsList.innerHTML = '';
        data.columns.forEach(col => {
            const row = document.createElement('div');
            row.className = 'column-row';
            row.setAttribute('role', 'listitem');

            let badgeClass = 'text';
            let label = col.type;
            if (/int|float|double|decimal|number/i.test(col.type)) {
                badgeClass = 'numeric'; label = 'num';
            } else if (/object|string|category|str/i.test(col.type)) {
                badgeClass = 'category'; label = 'cat';
            } else if (/date|time|datetime/i.test(col.type)) {
                badgeClass = 'date'; label = 'date';
            }

            row.innerHTML = `
                <span class="col-name" title="${escHtml(col.name)}">${escHtml(col.name)}</span>
                <span class="col-badge ${badgeClass}" aria-label="${label} type">${label}</span>
            `;
            columnsList.appendChild(row);
        });

        datasetInfo.classList.remove('hidden');

        // Enable chat
        chatInput.removeAttribute('disabled');
        sendBtn.removeAttribute('disabled');
        chatInput.placeholder = 'Ask anything about your data…';

        // Show suggestions
        suggestions.classList.remove('hidden');

        // Remove welcome state, show chat
        if (welcomeState) welcomeState.style.display = 'none';

        setStatus(`${data.filename} — ${data.shape[0]} rows · ${data.shape[1]} columns`, 'green');
        fileUploaded = true;

        // Greeting message
        appendAssistantMessage(
            `Dataset <strong>${escHtml(data.filename)}</strong> loaded successfully — ` +
            `<strong>${data.shape[0]}</strong> rows and <strong>${data.shape[1]}</strong> columns. ` +
            `I'm ready to analyze your data. Try the suggestion chips above, or ask me anything!`
        );

    } catch (err) {
        console.error('[Upload Error]', err);
        setStatus('Upload failed', 'red');
        appendAssistantError(`Upload error: ${err.message}`);
    }
}

// ════════════════════════════
// CHAT
// ════════════════════════════

chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text || isLoading) return;
    chatInput.value = '';
    submitQuery(text);
});

chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (text && !isLoading) {
            chatInput.value = '';
            submitQuery(text);
        }
    }
});

function sendSuggestion(text) {
    if (!fileUploaded || isLoading) return;
    submitQuery(text);
}

async function submitQuery(message) {
    if (!fileUploaded) {
        appendAssistantError('Please upload a dataset first before asking questions.');
        return;
    }

    isLoading = true;
    sendBtn.disabled = true;
    chatInput.disabled = true;
    setStatus('Thinking…', 'blue');

    // User bubble
    appendUserMessage(message);

    // Loading indicator
    const loadingId = appendLoadingMessage();
    scrollBottom();

    const formData = new FormData();
    formData.append('message', message);

    // Abort controller — prevents silent "Load failed" on slow responses
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 90_000); // 90s max

    try {
        const res = await fetch('/chat', {
            method: 'POST',
            body: formData,
            signal: controller.signal
        });

        clearTimeout(timeout);
        removeElement(loadingId);

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Query failed' }));
            throw new Error(err.detail || 'Query execution failed');
        }

        const data = await res.json();
        renderAssistantResponse(data);
        setStatus('Ready', 'green');

    } catch (err) {
        clearTimeout(timeout);
        console.error('[Chat Error]', err);
        removeElement(loadingId);

        let friendlyMsg;
        if (err.name === 'AbortError') {
            friendlyMsg = 'The request took too long and was cancelled. Try a simpler query or try again.';
        } else if (err.message.includes('Load failed') || err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
            friendlyMsg = 'Network error — the server may be restarting. Please wait a moment and try again.';
        } else {
            friendlyMsg = err.message || 'Something went wrong. Please try again.';
        }

        appendAssistantError(friendlyMsg);
        setStatus('Ready', 'green');
    } finally {
        isLoading = false;
        sendBtn.disabled = false;
        chatInput.disabled = false;
        chatInput.focus();
        scrollBottom();
    }
}

// ════════════════════════════
// RENDER HELPERS
// ════════════════════════════

function appendUserMessage(text) {
    const msg = document.createElement('div');
    msg.className = 'message user';
    msg.setAttribute('role', 'listitem');
    msg.innerHTML = `
        ${userAvatarSvg()}
        <div class="msg-bubble">${escHtml(text)}</div>
    `;
    chatMessages.appendChild(msg);
    scrollBottom();
}

function appendAssistantMessage(html) {
    const msg = document.createElement('div');
    msg.className = 'message assistant';
    msg.setAttribute('role', 'listitem');
    msg.innerHTML = `
        ${aiAvatarSvg()}
        <div class="msg-bubble">${html}</div>
    `;
    chatMessages.appendChild(msg);
    scrollBottom();
    return msg;
}

function appendAssistantError(text) {
    const msg = document.createElement('div');
    msg.className = 'message assistant';
    msg.setAttribute('role', 'listitem');
    msg.innerHTML = `
        ${aiAvatarSvg()}
        <div class="msg-bubble">
            <div class="error-box">${escHtml(text)}</div>
        </div>
    `;
    chatMessages.appendChild(msg);
    scrollBottom();
}

function appendLoadingMessage() {
    const id = 'loading-' + Date.now();
    const msg = document.createElement('div');
    msg.id = id;
    msg.className = 'message assistant';
    msg.setAttribute('role', 'listitem');
    msg.setAttribute('aria-label', 'Sankhya is thinking');
    msg.innerHTML = `
        ${aiAvatarSvg()}
        <div class="msg-bubble">
            <div class="thinking-row">
                <span class="thinking-label">Analyzing</span>
                <div class="dot-pulse" aria-hidden="true">
                    <span></span><span></span><span></span>
                </div>
            </div>
        </div>
    `;
    chatMessages.appendChild(msg);
    return id;
}

function renderAssistantResponse(data) {
    const msg = document.createElement('div');
    msg.className = 'message assistant';
    msg.setAttribute('role', 'listitem');

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';

    // ── Explanation text ──
    if (data.explanation) {
        const p = document.createElement('p');
        p.innerHTML = mdToHtml(data.explanation);
        bubble.appendChild(p);
    }

    // Subtle visual tint for error state (no text — explanation covers it)
    if (data.status === 'error') {
        bubble.style.borderLeftColor = 'rgba(244,63,94,0.35)';
        bubble.style.borderLeftWidth = '3px';
    }


    // ── Tabular result ──
    if (data.answer && data.answer.type === 'table') {
        const { columns, records } = data.answer;
        const displayRows = records.slice(0, 15);

        const wrap = document.createElement('div');
        wrap.className = 'result-table-wrap';

        const table = document.createElement('table');
        table.className = 'result-table';
        table.setAttribute('role', 'table');

        // Header
        const thead = document.createElement('thead');
        const trHead = document.createElement('tr');
        trHead.setAttribute('role', 'row');
        columns.forEach(col => {
            const th = document.createElement('th');
            th.setAttribute('role', 'columnheader');
            th.setAttribute('scope', 'col');
            th.textContent = col;
            trHead.appendChild(th);
        });
        thead.appendChild(trHead);
        table.appendChild(thead);

        // Body
        const tbody = document.createElement('tbody');
        displayRows.forEach(rec => {
            const tr = document.createElement('tr');
            tr.setAttribute('role', 'row');
            columns.forEach(col => {
                const td = document.createElement('td');
                td.setAttribute('role', 'cell');
                const val = rec[col];
                td.textContent = val === null || val === undefined ? '—' : formatValue(val);
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        wrap.appendChild(table);
        bubble.appendChild(wrap);

        if (records.length > 15) {
            const caption = document.createElement('div');
            caption.className = 'table-caption';
            caption.textContent = `Showing ${displayRows.length} of ${records.length} rows`;
            bubble.appendChild(caption);
        }
    }

    // ── Text / scalar result ──
    if (data.answer && data.answer.type === 'text' && data.answer.value && data.answer.value !== 'None') {
        const raw = data.answer.value.trim();

        // Try to parse as a dict → key-value grid
        const parsed = tryParseDict(raw);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            const grid = document.createElement('div');
            grid.className = 'kv-grid';

            Object.entries(parsed).forEach(([k, v]) => {
                const item = document.createElement('div');
                item.className = 'kv-item';

                const key = document.createElement('div');
                key.className = 'kv-key';
                key.textContent = k;

                const val = document.createElement('div');
                val.className = 'kv-val';
                val.textContent = (typeof v === 'object' && v !== null) ? JSON.stringify(v) : String(v);

                item.appendChild(key);
                item.appendChild(val);
                grid.appendChild(item);
            });

            bubble.appendChild(grid);
        } else {
            // Raw text/number result box
            const box = document.createElement('div');
            box.className = 'text-result';
            box.textContent = raw;
            bubble.appendChild(box);
        }
    }

    // ── Matplotlib image ──
    if (data.image) {
        const img = document.createElement('img');
        img.className = 'plot-img';
        img.src = `data:image/png;base64,${data.image}`;
        img.alt = 'Generated data visualization';
        bubble.appendChild(img);
    }

    // ── Plotly chart ──
    if (data.chart) {
        const chartId = 'chart-' + Date.now();
        const chartDiv = document.createElement('div');
        chartDiv.id = chartId;
        chartDiv.className = 'chart-container';
        bubble.appendChild(chartDiv);

        // Dark theme overrides
        const layout = Object.assign({}, data.chart.layout || {});
        layout.paper_bgcolor = 'rgba(0,0,0,0)';
        layout.plot_bgcolor  = 'rgba(0,0,0,0)';
        layout.font = { color: '#f1f5f9', family: 'Inter, system-ui, sans-serif', size: 12 };
        layout.margin = layout.margin || { t: 40, b: 40, l: 50, r: 20 };

        const axisStyle = {
            gridcolor: 'rgba(255,255,255,0.05)',
            linecolor: 'rgba(255,255,255,0.08)',
            tickcolor: 'rgba(255,255,255,0.15)',
            tickfont:  { color: '#94a3b8', size: 11 },
            zerolinecolor: 'rgba(255,255,255,0.07)',
        };

        if (layout.xaxis) Object.assign(layout.xaxis, axisStyle);
        else layout.xaxis = axisStyle;

        if (layout.yaxis) Object.assign(layout.yaxis, axisStyle);
        else layout.yaxis = axisStyle;

        if (layout.legend) {
            layout.legend.bgcolor = 'rgba(0,0,0,0)';
            layout.legend.font = { color: '#94a3b8', size: 11 };
        }

        // Colorize traces with nice palette
        const palette = ['#818cf8','#06b6d4','#10b981','#f59e0b','#f43f5e','#a78bfa','#38bdf8'];
        if (data.chart.data) {
            data.chart.data.forEach((trace, i) => {
                if (!trace.marker) trace.marker = {};
                if (!trace.marker.color || typeof trace.marker.color === 'string') {
                    trace.marker.color = palette[i % palette.length];
                }
                if (trace.type === 'scatter' || trace.type === 'scattergl') {
                    if (!trace.line) trace.line = {};
                    trace.line.color = trace.line.color || palette[i % palette.length];
                }
            });
        }

        setTimeout(() => {
            try {
                Plotly.newPlot(chartId, data.chart.data, layout, {
                    responsive: true,
                    displayModeBar: true,
                    modeBarButtonsToRemove: ['lasso2d','select2d'],
                    toImageButtonOptions: { format: 'png', scale: 2 }
                });
            } catch (e) {
                console.error('[Plotly]', e);
                const fallback = document.createElement('div');
                fallback.className = 'error-box';
                fallback.textContent = 'Could not render chart: ' + e.message;
                chartDiv.replaceWith(fallback);
            }
        }, 80);
    }

    // ── Code inspector (collapsible) ──
    if (data.code) {
        const inspector = document.createElement('div');
        inspector.className = 'code-inspector';

        const toggle = document.createElement('button');
        toggle.className = 'inspector-toggle';
        toggle.setAttribute('aria-expanded', 'false');
        toggle.setAttribute('aria-controls', 'inspector-body-' + Date.now());
        toggle.innerHTML = `
            <span>View executed code</span>
            <svg class="inspector-toggle-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                <polyline points="4 6 8 10 12 6"/>
            </svg>
        `;

        const body = document.createElement('div');
        body.className = 'inspector-body hidden';
        body.textContent = data.code;

        toggle.addEventListener('click', () => {
            const isOpen = !body.classList.contains('hidden');
            body.classList.toggle('hidden', isOpen);
            toggle.setAttribute('aria-expanded', String(!isOpen));
            toggle.querySelector('.inspector-toggle-icon').classList.toggle('open', !isOpen);
        });

        inspector.appendChild(toggle);
        inspector.appendChild(body);
        bubble.appendChild(inspector);
    }

    msg.innerHTML = aiAvatarSvg();
    msg.appendChild(bubble);
    chatMessages.appendChild(msg);
    scrollBottom();
}

// ════════════════════════════
// AVATAR SVGS
// ════════════════════════════

function aiAvatarSvg() {
    return `<div class="msg-avatar" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 3c0 0-5 3.5-5 9s5 9 5 9 5-3.5 5-9-5-9-5-9z"/>
            <ellipse cx="12" cy="12" rx="8" ry="4"/>
        </svg>
    </div>`;
}

function userAvatarSvg() {
    return `<div class="msg-avatar" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
        </svg>
    </div>`;
}

// ════════════════════════════
// UTILITIES
// ════════════════════════════

function scrollBottom() {
    requestAnimationFrame(() => {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    });
}

function removeElement(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function escHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/** Minimal markdown → html (bold, italic, inline code) */
function mdToHtml(text) {
    return escHtml(text)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g,     '<em>$1</em>')
        .replace(/`(.*?)`/g,       '<code style="font-family:var(--font-mono);font-size:12px;color:#a5b4fc;background:rgba(129,140,248,0.1);padding:1px 5px;border-radius:4px;">$1</code>')
        .replace(/\n/g, '<br>');
}

/** Try to parse Python-dict-like strings as JSON */
function tryParseDict(str) {
    if (!str.startsWith('{') || !str.endsWith('}')) return null;
    try { return JSON.parse(str); } catch (_) {}
    try {
        return JSON.parse(
            str.replace(/'/g, '"')
               .replace(/True/g, 'true')
               .replace(/False/g, 'false')
               .replace(/None/g, 'null')
               .replace(/\((\d+),\s*(\d+)\)/g, '[$1,$2]')
               .replace(/datetime\.dtype\('([^']+)'\)/g, '"$1"')
        );
    } catch (_) { return null; }
}

/** Format numeric values for display */
function formatValue(val) {
    if (val === null || val === undefined) return '—';
    if (typeof val === 'number') {
        if (!isFinite(val)) return String(val);
        if (Math.abs(val) >= 1e6 || (Math.abs(val) < 0.001 && val !== 0)) {
            return val.toExponential(3);
        }
        if (Number.isInteger(val)) return val.toLocaleString();
        return parseFloat(val.toFixed(4)).toString();
    }
    return String(val);
}
