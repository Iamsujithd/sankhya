// Global state variables
let isFileUploaded = false;
let activeFilename = "";

// DOM Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const datasetInfo = document.getElementById('dataset-info');
const columnsList = document.getElementById('columns-list');
const metaFilename = document.getElementById('meta-filename');
const metaShape = document.getElementById('meta-shape');
const statusText = document.getElementById('status-text');
const pulseDot = document.querySelector('.pulse-dot');
const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const suggestions = document.getElementById('suggestions');

// Drag and drop event handlers
dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        handleFileUpload(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
    }
});

// File Upload Logic
async function handleFileUpload(file) {
    statusText.textContent = "Uploading and analyzing dataset...";
    pulseDot.className = "pulse-dot blue";
    
    const formData = new FormData();
    formData.append("file", file);
    
    try {
        const response = await fetch("/upload", {
            method: "POST",
            body: formData
        });
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Upload failed");
        }
        
        const data = await response.json();
        
        // Update state
        isFileUploaded = true;
        activeFilename = data.filename;
        
        // Show metadata
        metaFilename.textContent = data.filename;
        metaShape.textContent = `${data.shape[0]} rows x ${data.shape[1]} columns`;
        
        // Populate column list
        columnsList.innerHTML = "";
        data.columns.forEach(col => {
            const token = document.createElement("div");
            token.className = "column-token";
            
            // Map types to categories
            let badgeClass = "text";
            let typeLabel = col.type;
            if (col.type.includes("int") || col.type.includes("float")) {
                badgeClass = "numeric";
                typeLabel = "num";
            } else if (col.type === "object" || col.type === "category") {
                badgeClass = "categorical";
                typeLabel = "cat";
            }
            
            token.innerHTML = `
                <span class="col-name" title="${col.name}">${col.name}</span>
                <span class="col-badge ${badgeClass}">${typeLabel}</span>
            `;
            columnsList.appendChild(token);
        });
        
        datasetInfo.classList.remove("hidden");
        
        // Enable chat inputs
        chatInput.removeAttribute("disabled");
        sendBtn.removeAttribute("disabled");
        suggestions.classList.remove("hidden");
        chatInput.placeholder = "Ask Sankhya about the dataset...";
        
        statusText.textContent = `Connected — ${data.filename} loaded successfully`;
        pulseDot.className = "pulse-dot green";
        
        // Push system greeting in chat
        addMessage("assistant", `Successfully loaded <strong>${data.filename}</strong>. Try asking suggestions like **Show Overview** or query specific columns!`);
        
    } catch (err) {
        console.error(err);
        statusText.textContent = "Upload failed — check file format";
        pulseDot.className = "pulse-dot red";
        addMessage("assistant", `⚠️ Failed to upload file. Details: ${err.message}`);
    }
}

// Chat submit handler
chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;
    
    // Clear input
    chatInput.value = "";
    
    submitQuery(message);
});

// Suggestion click
function sendSuggestion(text) {
    submitQuery(text);
}

// Submit chat query to FastAPI
async function submitQuery(message) {
    // Add user message
    addMessage("user", message);
    
    // Add loading message
    const loadingMessageId = addLoadingMessage();
    scrollToBottom();
    
    const formData = new FormData();
    formData.append("message", message);
    
    try {
        const response = await fetch("/chat", {
            method: "POST",
            body: formData
        });
        
        // Remove loading state
        removeMessage(loadingMessageId);
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Query execution failed");
        }
        
        const data = await response.json();
        
        // Add assistant response
        addAssistantResponse(data);
        
    } catch (err) {
        console.error(err);
        removeMessage(loadingMessageId);
        addMessage("assistant", `⚠️ Execution failed. Details: ${err.message}`);
    }
    scrollToBottom();
}

// Render message helper
function addMessage(role, content) {
    const msg = document.createElement("div");
    msg.className = `message ${role}`;
    
    const avatarSvg = role === "assistant" 
        ? `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color: #60a5fa; filter: drop-shadow(0 0 6px rgba(96, 165, 250, 0.6));"><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/><circle cx="12" cy="12" r="4"/></svg>`
        : `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color: #a3a3a3;"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
    
    msg.innerHTML = `
        <div class="avatar">${avatarSvg}</div>
        <div class="message-content">
            <p>${content}</p>
        </div>
    `;
    
    chatMessages.appendChild(msg);
    scrollToBottom();
    return msg;
}

// Add loading dots
function addLoadingMessage() {
    const id = "loading-" + Date.now();
    const msg = document.createElement("div");
    msg.className = "message assistant";
    msg.id = id;
    
    const avatarSvg = `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color: #60a5fa; filter: drop-shadow(0 0 6px rgba(96, 165, 250, 0.6));"><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/><circle cx="12" cy="12" r="4"/></svg>`;
    
    msg.innerHTML = `
        <div class="avatar">${avatarSvg}</div>
        <div class="message-content">
            <div class="chat-loading">
                <div class="loading-dot"></div>
                <div class="loading-dot"></div>
                <div class="loading-dot"></div>
            </div>
        </div>
    `;
    
    chatMessages.appendChild(msg);
    return id;
}

function removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

// Custom assistant response layout
function addAssistantResponse(data) {
    const msg = document.createElement("div");
    msg.className = "message assistant";
    
    const container = document.createElement("div");
    container.className = "message-content";
    
    // Add text explanation
    const textEl = document.createElement("p");
    textEl.innerHTML = data.explanation.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    container.appendChild(textEl);
    
    // Check if table answer exists
    if (data.answer && data.answer.type === "table") {
        const tableWrapper = document.createElement("div");
        tableWrapper.className = "results-table-container";
        
        const table = document.createElement("table");
        table.className = "results-table";
        
        // Build headers
        const trHeaders = document.createElement("tr");
        data.answer.columns.forEach(col => {
            const th = document.createElement("th");
            th.textContent = col;
            trHeaders.appendChild(th);
        });
        table.appendChild(trHeaders);
        
        // Build rows (limit to 10 rows for safety)
        const displayRecords = data.answer.records.slice(0, 10);
        displayRecords.forEach(rec => {
            const tr = document.createElement("tr");
            data.answer.columns.forEach(col => {
                const td = document.createElement("td");
                td.textContent = rec[col] === null ? "null" : rec[col];
                tr.appendChild(td);
            });
            table.appendChild(tr);
        });
        
        tableWrapper.appendChild(table);
        container.appendChild(tableWrapper);
        
        if (data.answer.records.length > 10) {
            const caption = document.createElement("caption");
            caption.style.fontSize = "11px";
            caption.style.color = "var(--text-muted)";
            caption.style.display = "block";
            caption.style.padding = "4px 8px";
            caption.textContent = `* Showing top 10 rows of ${data.answer.records.length} records`;
            container.appendChild(caption);
        }
    } else if (data.answer && data.answer.type === "text" && data.answer.value !== "None") {
        let isObj = false;
        let objVal = null;
        let strVal = data.answer.value.trim();
        
        if (strVal.startsWith("{") && strVal.endsWith("}")) {
            try {
                objVal = JSON.parse(strVal);
                isObj = true;
            } catch (e) {
                try {
                    let cleanStr = strVal
                        .replace(/'/g, '"')
                        .replace(/\(/g, '[')
                        .replace(/\)/g, ']')
                        .replace(/True/g, 'true')
                        .replace(/False/g, 'false')
                        .replace(/None/g, 'null');
                    objVal = JSON.parse(cleanStr);
                    isObj = true;
                } catch (err) {
                    isObj = false;
                }
            }
        }
        
        if (isObj && objVal && typeof objVal === "object") {
            const listContainer = document.createElement("div");
            listContainer.className = "kv-container";
            
            for (let [key, val] of Object.entries(objVal)) {
                const item = document.createElement("div");
                item.className = "kv-item";
                
                const keyEl = document.createElement("span");
                keyEl.className = "kv-key";
                keyEl.textContent = key;
                
                const valEl = document.createElement("span");
                valEl.className = "kv-value";
                if (typeof val === "object" && val !== null) {
                    valEl.textContent = JSON.stringify(val);
                } else {
                    valEl.textContent = String(val);
                }
                
                item.appendChild(keyEl);
                item.appendChild(valEl);
                listContainer.appendChild(item);
            }
            container.appendChild(listContainer);
        } else {
            const valueBox = document.createElement("div");
            valueBox.style.background = "rgba(255, 255, 255, 0.03)";
            valueBox.style.padding = "10px";
            valueBox.style.border = "1px solid var(--border-color)";
            valueBox.style.borderRadius = "6px";
            valueBox.style.fontFamily = "monospace";
            valueBox.style.fontSize = "13px";
            valueBox.style.color = "var(--accent-gold)";
            valueBox.style.margin = "10px 0";
            valueBox.style.whiteSpace = "pre-wrap";
            valueBox.textContent = data.answer.value;
            container.appendChild(valueBox);
        }
    }
    
    // Check if Matplotlib base64 image exists
    if (data.image) {
        const img = document.createElement("img");
        img.src = `data:image/png;base64,${data.image}`;
        img.style.width = "100%";
        img.style.borderRadius = "12px";
        img.style.border = "1px solid var(--border-color)";
        img.style.boxShadow = "0 10px 30px rgba(0, 0, 0, 0.25)";
        img.style.margin = "16px 0";
        img.style.display = "block";
        container.appendChild(img);
    }
    
    // Check if Plotly chart exists
    if (data.chart) {
        const chartId = "chart-" + Date.now();
        const chartDiv = document.createElement("div");
        chartDiv.id = chartId;
        chartDiv.className = "embedded-chart";
        container.appendChild(chartDiv);
        
        // Force dark styling on chart layout properties
        const chartLayout = data.chart.layout || {};
        chartLayout.paper_bgcolor = "rgba(0,0,0,0)";
        chartLayout.plot_bgcolor = "rgba(0,0,0,0)";
        chartLayout.font = { color: "#F3F4F6", family: 'Outfit' };
        
        // Adjust scales/gridcolors to show cleanly on dark bg
        if (chartLayout.xaxis) {
            chartLayout.xaxis.gridcolor = "rgba(255,255,255,0.06)";
            chartLayout.xaxis.linecolor = "rgba(255,255,255,0.1)";
        }
        if (chartLayout.yaxis) {
            chartLayout.yaxis.gridcolor = "rgba(255,255,255,0.06)";
            chartLayout.yaxis.linecolor = "rgba(255,255,255,0.1)";
        }
        
        // Plot chart using CDN Plotly library
        setTimeout(() => {
            try {
                Plotly.newPlot(chartId, data.chart.data, chartLayout, { responsive: true, displayModeBar: false });
            } catch (err) {
                console.error("Plotly render error: ", err);
            }
        }, 100);
    }
    
    // Code Inspector panel
    if (data.code) {
        const inspector = document.createElement("div");
        inspector.className = "code-inspector";
        
        const header = document.createElement("div");
        header.className = "inspector-header";
        header.innerHTML = `<span>⚙️ Executed Calculations Code</span><span>▼</span>`;
        
        const body = document.createElement("div");
        body.className = "inspector-body hidden";
        body.textContent = data.code;
        
        header.addEventListener("click", () => {
            body.classList.toggle("hidden");
            header.children[1].textContent = body.classList.contains("hidden") ? "▼" : "▲";
        });
        
        inspector.appendChild(header);
        inspector.appendChild(body);
        container.appendChild(inspector);
    }
    
    const avatarSvg = `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color: #60a5fa; filter: drop-shadow(0 0 6px rgba(96, 165, 250, 0.6));"><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/><circle cx="12" cy="12" r="4"/></svg>`;
    msg.innerHTML = `<div class="avatar">${avatarSvg}</div>`;
    msg.appendChild(container);
    
    chatMessages.appendChild(msg);
    scrollToBottom();
}

function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}
