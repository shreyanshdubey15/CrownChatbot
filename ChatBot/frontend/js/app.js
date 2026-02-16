/* =============================================================
   DocIntel — Document Intelligence Platform
   Main Application JavaScript
   ============================================================= */

const API_BASE = window.location.origin;

/* =============================================================
   UTILITIES
   ============================================================= */

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type = "info") {
    const container = document.getElementById("toastContainer");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

/* =============================================================
   CHAT HISTORY — localStorage persistence
   ============================================================= */
const STORAGE_KEY = "docintel_chat_history";

function loadHistory() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) return JSON.parse(raw);
    } catch {}
    return { chats: [], activeId: null };
}

function saveHistory(h) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(h)); } catch {}
}

let history = loadHistory();

if (history.chats.length === 0) {
    const newChat = makeChat();
    history.chats.push(newChat);
    history.activeId = newChat.id;
    saveHistory(history);
}
if (!history.activeId) {
    history.activeId = history.chats[0].id;
    saveHistory(history);
}

function makeChat() {
    return {
        id: "chat_" + Date.now() + "_" + Math.random().toString(36).slice(2, 7),
        title: "New Chat",
        createdAt: new Date().toISOString(),
        messages: []
    };
}

function getActiveChat() {
    return history.chats.find(c => c.id === history.activeId) || history.chats[0];
}

/* ── Date grouping ── */
function getDateGroup(isoDate) {
    const d = new Date(isoDate);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
    const weekAgo = new Date(today); weekAgo.setDate(weekAgo.getDate() - 7);
    const monthAgo = new Date(today); monthAgo.setDate(monthAgo.getDate() - 30);

    if (d >= today) return "Today";
    if (d >= yesterday) return "Yesterday";
    if (d >= weekAgo) return "This Week";
    if (d >= monthAgo) return "This Month";
    return "Older";
}

function formatRelativeDate(iso) {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "now";
    if (diffMins < 60) return diffMins + "m ago";
    const diffHrs = Math.floor(diffMins / 60);
    if (diffHrs < 24) return diffHrs + "h ago";
    const diffDays = Math.floor(diffHrs / 24);
    if (diffDays < 7) return diffDays + "d ago";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

let historySearchTerm = "";

function renderHistoryList() {
    const list = document.getElementById("chatHistoryList");
    const empty = document.getElementById("historyEmpty");

    list.querySelectorAll(".history-item, .history-date-group, .history-no-results").forEach(el => el.remove());

    if (history.chats.length === 0) {
        if (empty) empty.style.display = "";
        return;
    }
    if (empty) empty.style.display = "none";

    const term = historySearchTerm.toLowerCase().trim();
    let filtered = [...history.chats];
    if (term) {
        filtered = filtered.filter(c =>
            c.title.toLowerCase().includes(term) ||
            c.messages.some(m => m.content && m.content.toLowerCase().includes(term))
        );
    }

    if (filtered.length === 0) {
        const noResults = document.createElement("div");
        noResults.className = "history-no-results";
        noResults.textContent = "No matching chats";
        list.appendChild(noResults);
        return;
    }

    const sorted = filtered.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));

    let lastGroup = "";
    for (const chat of sorted) {
        const group = getDateGroup(chat.createdAt);
        if (group !== lastGroup) {
            const header = document.createElement("div");
            header.className = "history-date-group";
            header.textContent = group;
            list.appendChild(header);
            lastGroup = group;
        }

        const item = document.createElement("div");
        item.className = "history-item" + (chat.id === history.activeId ? " active" : "");
        item.dataset.chatId = chat.id;

        const dateStr = formatRelativeDate(chat.createdAt);
        const msgCount = chat.messages.filter(m => m.type === "user").length;
        const lastBotMsg = [...chat.messages].reverse().find(m => m.type === "bot");
        const preview = lastBotMsg ? lastBotMsg.content.slice(0, 60) : "";

        item.innerHTML = `
            <span class="history-icon">&#128172;</span>
            <div class="history-body">
                <span class="history-title">${escapeHtml(chat.title)}</span>
                ${preview ? `<span class="history-preview">${escapeHtml(preview)}</span>` : ""}
            </div>
            <span class="history-meta">
                ${msgCount > 0 ? `<span class="history-count">${msgCount}</span>` : ""}
                <span class="history-date">${dateStr}</span>
            </span>
            <span class="history-actions">
                <button class="history-action-btn rename" title="Rename" onclick="event.stopPropagation(); startRenameChat('${chat.id}')">&#9998;</button>
                <button class="history-action-btn delete" title="Delete" onclick="event.stopPropagation(); deleteChatById('${chat.id}')">&times;</button>
            </span>
        `;
        item.addEventListener("click", () => switchToChat(chat.id));
        list.appendChild(item);
    }
}

function filterHistory(term) {
    historySearchTerm = term;
    renderHistoryList();
}

function startRenameChat(chatId) {
    const item = document.querySelector(`.history-item[data-chat-id="${chatId}"]`);
    if (!item) return;
    const chat = history.chats.find(c => c.id === chatId);
    if (!chat) return;

    const body = item.querySelector(".history-body");
    const oldTitle = chat.title;
    body.innerHTML = `<input class="history-rename-input" type="text" value="${escapeHtml(oldTitle)}" maxlength="80">`;
    const inp = body.querySelector("input");
    inp.focus();
    inp.select();

    function commit() {
        const newTitle = inp.value.trim() || oldTitle;
        chat.title = newTitle;
        saveHistory(history);
        renderHistoryList();
        if (chat.id === history.activeId) {
            document.getElementById("chatHeaderTitle").textContent = newTitle;
        }
    }

    inp.addEventListener("blur", commit);
    inp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); inp.blur(); }
        if (e.key === "Escape") { inp.value = oldTitle; inp.blur(); }
    });
}

function switchToChat(chatId) {
    history.activeId = chatId;
    saveHistory(history);
    renderHistoryList();
    renderActiveChat();
    switchPanel("chat");
}

function createNewChat() {
    const newChat = makeChat();
    history.chats.push(newChat);
    history.activeId = newChat.id;
    saveHistory(history);
    renderHistoryList();
    renderActiveChat();
    switchPanel("chat");
    document.getElementById("questionInput").focus();
}

function deleteChatById(chatId) {
    history.chats = history.chats.filter(c => c.id !== chatId);
    if (history.activeId === chatId) {
        if (history.chats.length === 0) {
            const newChat = makeChat();
            history.chats.push(newChat);
            history.activeId = newChat.id;
        } else {
            history.activeId = history.chats[history.chats.length - 1].id;
        }
    }
    saveHistory(history);
    renderHistoryList();
    renderActiveChat();
}

function clearAllChats() {
    if (!confirm("Delete all chat history? This cannot be undone.")) return;
    history.chats = [];
    const newChat = makeChat();
    history.chats.push(newChat);
    history.activeId = newChat.id;
    saveHistory(history);
    renderHistoryList();
    renderActiveChat();
    showToast("Chat history cleared", "info");
}

function renderActiveChat() {
    const chat = getActiveChat();
    const chatMessages = document.getElementById("chatMessages");
    const headerTitle = document.getElementById("chatHeaderTitle");

    headerTitle.textContent = chat.title;
    chatMessages.innerHTML = "";

    if (chat.messages.length === 0) {
        chatMessages.innerHTML = `
            <div class="empty-state" id="emptyState">
                <div class="empty-icon">&#128172;</div>
                <p>No messages yet</p>
                <p class="hint">Upload a document first, then ask a question</p>
            </div>
        `;
        return;
    }

    for (const m of chat.messages) {
        if (m.type === "bot" && m.sources) {
            addBotAnswerToDOM(m.content, m.sources, false);
        } else {
            addMessageToDOM(m.content, m.type, false, false);
        }
    }

    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function autoTitleChat(chat, firstQuestion) {
    let title = firstQuestion.length > 50 ? firstQuestion.slice(0, 47) + "..." : firstQuestion;
    chat.title = title;
}

/* =============================================================
   PANEL SWITCHING
   ============================================================= */
const PANEL_STORAGE_KEY = "docintel_active_panel";

function switchPanel(name) {
    document.querySelectorAll('.panel, .chat-panel').forEach(p => p.classList.remove('active'));
    const target = document.getElementById(`panel-${name}`);
    if (target) target.classList.add('active');
    document.querySelectorAll('.nav-item').forEach(n => {
        n.classList.toggle('active', n.dataset.panel === name);
    });
    document.querySelectorAll('.mob-item').forEach(n => {
        n.classList.toggle('active', n.dataset.panel === name);
    });
    try { localStorage.setItem(PANEL_STORAGE_KEY, name); } catch {}
}

function restoreActivePanel() {
    try {
        const saved = localStorage.getItem(PANEL_STORAGE_KEY);
        if (saved && document.getElementById(`panel-${saved}`)) {
            switchPanel(saved);
        }
    } catch {}
}

/* =============================================================
   HEALTH CHECK
   ============================================================= */
async function checkHealth() {
    const badge = document.getElementById("statusBadge");
    const text = document.getElementById("statusText");
    badge.className = "status-indicator checking";
    text.textContent = "Checking...";
    try {
        const res = await fetch(`${API_BASE}/health`, { method: "GET" });
        if (res.ok) {
            badge.className = "status-indicator online";
            text.textContent = "Online";
        } else { throw new Error(); }
    } catch {
        badge.className = "status-indicator offline";
        text.textContent = "Offline";
    }
}

/* =============================================================
   LLM PROVIDER SWITCHER
   ============================================================= */
async function loadLLMProvider() {
    try {
        const res = await fetch(`${API_BASE}/llm-provider`);
        if (res.ok) {
            const data = await res.json();
            updateProviderUI(data.provider, data.chat_model);
        }
    } catch {}
}

async function switchLLMProvider(provider) {
    const groqBtn = document.getElementById('providerBtnGroq');
    const ollamaBtn = document.getElementById('providerBtnOllama');
    const statusEl = document.getElementById('providerStatus');

    groqBtn.classList.add('switching');
    ollamaBtn.classList.add('switching');
    statusEl.textContent = 'Switching...';

    try {
        const formData = new FormData();
        formData.append('provider', provider);
        const res = await fetch(`${API_BASE}/llm-provider`, { method: 'POST', body: formData });
        const data = await res.json();
        if (res.ok) {
            updateProviderUI(data.provider, data.chat_model);
            showToast(`Switched to ${provider === 'groq' ? 'Groq (Cloud)' : 'Ollama (Local)'}`, 'success');
        } else {
            statusEl.textContent = data.detail || 'Switch failed';
            showToast(data.detail || 'Switch failed', 'error');
        }
    } catch {
        statusEl.textContent = 'Network error';
        showToast('Failed to switch provider', 'error');
    } finally {
        groqBtn.classList.remove('switching');
        ollamaBtn.classList.remove('switching');
    }
}

function updateProviderUI(provider, modelName) {
    const groqBtn = document.getElementById('providerBtnGroq');
    const ollamaBtn = document.getElementById('providerBtnOllama');
    const statusEl = document.getElementById('providerStatus');

    groqBtn.classList.toggle('active', provider === 'groq');
    ollamaBtn.classList.toggle('active', provider === 'ollama');
    statusEl.textContent = modelName ? `Model: ${modelName}` : '';
}

/* =============================================================
   DELETE ALL
   ============================================================= */
async function deleteAllData() {
    if (!confirm("This will permanently delete all uploaded documents and indexed data. Continue?")) return;
    try {
        const res = await fetch(`${API_BASE}/delete-all`, { method: "DELETE" });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, "success");
        } else {
            showToast(data.detail || "Delete failed", "error");
        }
    } catch {
        showToast("Network error", "error");
    }
}

/* =============================================================
   FILE UPLOAD
   ============================================================= */
function initUpload() {
    const uploadZone = document.getElementById("uploadZone");
    const fileInput = document.getElementById("fileInput");

    uploadZone.addEventListener("dragover", (e) => { e.preventDefault(); uploadZone.classList.add("dragover"); });
    uploadZone.addEventListener("dragleave", () => uploadZone.classList.remove("dragover"));
    uploadZone.addEventListener("drop", (e) => {
        e.preventDefault();
        uploadZone.classList.remove("dragover");
        handleFiles(e.dataTransfer.files);
    });
    fileInput.addEventListener("change", () => { handleFiles(fileInput.files); fileInput.value = ""; });
}

function handleFiles(files) {
    const supported = [
        "pdf", "docx", "doc", "rtf",
        "txt", "md", "markdown",
        "xlsx", "xls", "csv", "tsv",
        "jpg", "jpeg", "png", "webp", "heic", "heif", "svg", "ico", "jfif"
    ];
    for (const file of files) {
        const ext = file.name.split(".").pop().toLowerCase();
        if (!supported.includes(ext)) {
            showToast(`Unsupported: ${file.name}`, "error");
            continue;
        }
        uploadFile(file);
    }
}

async function uploadFile(file) {
    const uploadStatus = document.getElementById("uploadStatus");
    const item = document.createElement("div");
    item.className = "upload-item";
    item.innerHTML = `
        <span style="opacity:0.4;">&#128196;</span>
        <span class="file-name">${file.name}</span>
        <span class="file-status uploading"><span class="spinner"></span> Uploading</span>
    `;
    uploadStatus.prepend(item);
    const statusEl = item.querySelector(".file-status");
    try {
        const fd = new FormData();
        fd.append("file", file);
        const res = await fetch(`${API_BASE}/upload-doc`, { method: "POST", body: fd });
        const data = await res.json();
        if (res.ok || res.status === 200) {
            if (data.is_duplicate) {
                statusEl.className = "file-status";
                statusEl.style.color = "var(--yellow)";
                statusEl.innerHTML = "&#9888; Duplicate";
                showToast(data.message, "info");
            } else {
                statusEl.className = "file-status done";
                statusEl.innerHTML = `&#10003; Done${data.version_number > 1 ? ' (v' + data.version_number + ')' : ''}`;
                showToast(data.message, "success");
            }
        } else {
            statusEl.className = "file-status fail";
            statusEl.textContent = "Failed";
            showToast(data.detail || "Upload failed", "error");
        }
    } catch {
        statusEl.className = "file-status fail";
        statusEl.textContent = "Error";
        showToast(`Network error uploading ${file.name}`, "error");
    }
}

/* =============================================================
   CHAT — Ask Questions
   ============================================================= */
let messageCounter = 0;

function initChat() {
    const questionInput = document.getElementById("questionInput");
    questionInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); askQuestion(); }
    });
}

async function askQuestion() {
    const questionInput = document.getElementById("questionInput");
    const askBtn = document.getElementById("askBtn");
    const chatMessages = document.getElementById("chatMessages");
    const question = questionInput.value.trim();
    if (!question) return;

    const chat = getActiveChat();
    const emptyState = document.getElementById("emptyState");
    if (emptyState) emptyState.remove();

    if (chat.messages.length === 0) {
        autoTitleChat(chat, question);
        document.getElementById("chatHeaderTitle").textContent = chat.title;
        saveHistory(history);
        renderHistoryList();
    }

    chat.messages.push({ type: "user", content: question });
    saveHistory(history);
    addMessageToDOM(question, "user", false, true);
    questionInput.value = "";

    const typingId = addMessageToDOM('<span class="spinner"></span> Thinking...', "bot", true, true);
    askBtn.disabled = true;
    questionInput.disabled = true;

    const chatHistoryForAPI = [];
    const priorMessages = chat.messages.slice(0, -1);
    for (const m of priorMessages) {
        if (m.type === "user") chatHistoryForAPI.push({ role: "user", content: m.content });
        else if (m.type === "bot") chatHistoryForAPI.push({ role: "assistant", content: m.content });
    }

    try {
        const res = await fetch(`${API_BASE}/ask`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question,
                chat_history: chatHistoryForAPI.length > 0 ? chatHistoryForAPI : null
            }),
        });
        removeMessage(typingId);
        if (res.ok) {
            const data = await res.json();
            chat.messages.push({ type: "bot", content: data.answer, sources: data.sources || [] });
            saveHistory(history);
            addBotAnswerToDOM(data.answer, data.sources, true);
        } else {
            const err = await res.json();
            const errMsg = err.detail || "Something went wrong";
            chat.messages.push({ type: "error", content: errMsg });
            saveHistory(history);
            addMessageToDOM(errMsg, "error", false, true);
        }
    } catch {
        removeMessage(typingId);
        const errMsg = "Network error — is the server running?";
        chat.messages.push({ type: "error", content: errMsg });
        saveHistory(history);
        addMessageToDOM(errMsg, "error", false, true);
    }

    askBtn.disabled = false;
    questionInput.disabled = false;
    questionInput.focus();
}

function addMessageToDOM(content, type, isHtml = false, animate = true) {
    const chatMessages = document.getElementById("chatMessages");
    const id = `msg-${++messageCounter}`;
    const msg = document.createElement("div");
    msg.className = `msg ${type}` + (animate ? "" : " no-anim");
    msg.id = id;
    if (isHtml) msg.innerHTML = content;
    else msg.textContent = content;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return id;
}

function addBotAnswerToDOM(answer, sources, animate = true) {
    const chatMessages = document.getElementById("chatMessages");
    const msg = document.createElement("div");
    msg.className = "msg bot" + (animate ? "" : " no-anim");
    let html = `<div class="answer-text">${renderMarkdown(answer)}</div>`;
    if (sources && sources.length > 0) {
        const sourceMap = new Map();
        sources.forEach(src => {
            const name = src.source || "Unknown";
            if (!sourceMap.has(name)) {
                sourceMap.set(name, { name, pages: new Set(), methods: new Set() });
            }
            const entry = sourceMap.get(name);
            if (src.page != null && src.page > 0) entry.pages.add(src.page);
            if (src.retrieval_source) entry.methods.add(src.retrieval_source);
        });

        html += `<div class="sources-section"><div class="sources-label">Sources (${sourceMap.size} document${sourceMap.size > 1 ? 's' : ''})</div>`;
        sourceMap.forEach(entry => {
            const pages = [...entry.pages].sort((a, b) => a - b);
            const pageStr = pages.length > 0 ? ` p.${pages.join(', ')}` : "";
            html += `<span class="source-chip">&#128196; ${escapeHtml(entry.name)}${pageStr}</span>`;
        });
        html += `</div>`;
    }
    msg.innerHTML = html;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

/* =============================================================
   VOICE INPUT — Enhanced Speech Recognition
   ============================================================= */
let recognition = null;
let isListening = false;
let recognitionRunning = false;
let voiceTimerInterval = null;
let voiceStartTime = 0;
let silenceTimeout = null;
let userStoppedManually = false;
let gotAnyResult = false;
let finalizedText = "";
let currentInterim = "";
let preVoiceText = "";
let restartAttempts = 0;
const SILENCE_DELAY = 4000;
const MAX_RECORD_TIME = 120000;
const MAX_RESTARTS = 15;
let maxRecordTimeout = null;

function initVoiceInput() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const voiceBtn = document.getElementById("voiceBtn");

    if (!SpeechRecognition) {
        voiceBtn.style.display = "none";
        return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
        recognitionRunning = true;
        console.log("[Voice] recognition started, attempt:", restartAttempts);
    };

    recognition.onaudiostart = () => {
        console.log("[Voice] audio capture started");
        showVoiceStatus("Listening — speak now…", true);
    };

    recognition.onspeechstart = () => {
        console.log("[Voice] speech detected!");
        showVoiceStatus("Hearing you…", true);
    };

    recognition.onresult = (event) => {
        gotAnyResult = true;
        restartAttempts = 0;
        resetSilenceTimer();

        let interim = "";
        let finalChunk = "";

        for (let i = event.resultIndex; i < event.results.length; i++) {
            const t = event.results[i][0].transcript;
            if (event.results[i].isFinal) finalChunk += t;
            else interim += t;
        }

        if (finalChunk) {
            finalizedText += (finalizedText ? " " : "") + finalChunk.trim();
            currentInterim = "";
        }

        if (interim) currentInterim = interim.trim();

        renderVoiceTranscript();
        showVoiceStatus("Listening…", true);
    };

    recognition.onend = () => {
        recognitionRunning = false;
        console.log("[Voice] recognition ended. isListening:", isListening, "userStopped:", userStoppedManually);

        if (isListening && !userStoppedManually) {
            if (restartAttempts < MAX_RESTARTS) {
                restartAttempts++;
                console.log("[Voice] auto-restarting... attempt", restartAttempts);
                try {
                    setTimeout(() => {
                        if (isListening && !userStoppedManually) recognition.start();
                    }, 150);
                } catch (e) {
                    console.warn("[Voice] restart failed:", e);
                    finishVoice();
                }
                return;
            } else {
                console.log("[Voice] max restarts reached, finishing");
            }
        }

        finishVoice();
    };

    recognition.onerror = (event) => {
        console.warn("[Voice] error:", event.error);

        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
            userStoppedManually = true;
            finishVoice();
            showVoiceStatus("⚠ Microphone blocked — allow mic in browser", false);
            fadeVoiceStatus(4000);
            return;
        }

        if (event.error === "no-speech") {
            showVoiceStatus("Waiting for speech…", true);
            return;
        }

        if (event.error === "network") {
            userStoppedManually = true;
            finishVoice();
            showVoiceStatus("⚠ Network error — check connection", false);
            fadeVoiceStatus(3500);
            return;
        }

        if (event.error === "audio-capture") {
            userStoppedManually = true;
            finishVoice();
            showVoiceStatus("⚠ No microphone found", false);
            fadeVoiceStatus(3500);
            return;
        }
    };
}

function toggleVoiceInput() {
    if (!recognition) {
        alert("Voice input requires Chrome, Edge, or Safari.\nYour browser doesn't support the Web Speech API.");
        return;
    }
    if (isListening) {
        userStoppedManually = true;
        stopVoice();
    } else {
        startVoice();
    }
}

function startVoice() {
    const questionInput = document.getElementById("questionInput");
    const voiceBtn = document.getElementById("voiceBtn");

    preVoiceText = questionInput.value.trim();
    finalizedText = "";
    currentInterim = "";
    gotAnyResult = false;
    restartAttempts = 0;
    userStoppedManually = false;
    isListening = true;

    voiceBtn.classList.add("listening");
    questionInput.classList.add("voice-active");
    questionInput.placeholder = "Listening — speak now…";
    showVoiceStatus("Starting mic…", true);
    startVoiceTimer();

    clearTimeout(maxRecordTimeout);
    maxRecordTimeout = setTimeout(() => {
        if (isListening) {
            showVoiceStatus("Max time reached", true);
            userStoppedManually = true;
            stopVoice();
        }
    }, MAX_RECORD_TIME);

    try {
        recognition.start();
    } catch (e) {
        console.warn("[Voice] start error:", e);
        finishVoice();
        showVoiceStatus("⚠ Could not start mic", false);
        fadeVoiceStatus(2500);
    }
}

function stopVoice() {
    isListening = false;
    clearSilenceTimer();
    try { recognition.stop(); } catch (e) { /* ok */ }
}

function finishVoice() {
    const questionInput = document.getElementById("questionInput");
    const voiceBtn = document.getElementById("voiceBtn");

    isListening = false;
    recognitionRunning = false;
    clearSilenceTimer();
    clearInterval(voiceTimerInterval);
    clearTimeout(maxRecordTimeout);
    voiceBtn.classList.remove("listening");
    questionInput.classList.remove("voice-active");
    questionInput.classList.remove("has-interim");
    questionInput.placeholder = "Ask something about your documents...";

    const fullText = buildFullText();
    questionInput.value = fullText;

    if (fullText.trim()) {
        showVoiceStatus("✓ Ready — press Send or Enter", false);
        fadeVoiceStatus(2500);
    }

    questionInput.focus();
}

function buildFullText() {
    let parts = [];
    if (preVoiceText) parts.push(preVoiceText);
    if (finalizedText) parts.push(finalizedText);
    if (currentInterim) parts.push(currentInterim);
    return parts.join(" ").trim();
}

function renderVoiceTranscript() {
    const questionInput = document.getElementById("questionInput");
    const full = buildFullText();
    questionInput.value = full;
    questionInput.classList.toggle("has-interim", !!currentInterim);
}

function resetSilenceTimer() {
    clearSilenceTimer();
    silenceTimeout = setTimeout(() => {
        if (isListening && gotAnyResult) {
            showVoiceStatus("Done — stopped listening", true);
            userStoppedManually = true;
            stopVoice();
        }
    }, SILENCE_DELAY);
}

function clearSilenceTimer() {
    if (silenceTimeout) { clearTimeout(silenceTimeout); silenceTimeout = null; }
}

function startVoiceTimer() {
    const voiceTimerEl = document.getElementById("voiceTimer");
    voiceStartTime = Date.now();
    voiceTimerEl.textContent = "0:00";
    clearInterval(voiceTimerInterval);
    voiceTimerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - voiceStartTime) / 1000);
        const m = Math.floor(elapsed / 60);
        const s = String(elapsed % 60).padStart(2, "0");
        voiceTimerEl.textContent = `${m}:${s}`;
    }, 500);
}

function showVoiceStatus(text, isRecording) {
    const voiceStatus = document.getElementById("voiceStatus");
    const voiceStatusText = document.getElementById("voiceStatusText");
    voiceStatusText.textContent = text;
    voiceStatus.classList.toggle("recording", isRecording);
    voiceStatus.classList.add("visible");
}

function fadeVoiceStatus(delay) {
    const voiceStatus = document.getElementById("voiceStatus");
    setTimeout(() => { voiceStatus.classList.remove("visible"); }, delay);
}

/* =============================================================
   MARKDOWN RENDERER
   ============================================================= */
function renderMarkdown(text) {
    let html = escapeHtml(text);

    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/(?<!\*)\*([^*]+?)\*(?!\*)/g, '<em>$1</em>');
    html = html.replace(/`([^`]+?)`/g, '<code>$1</code>');

    const lines = html.split('\n');
    let result = [];
    let inUl = false;
    let inOl = false;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmed = line.trim();

        if (/^###\s+/.test(trimmed)) {
            if (inUl) { result.push('</ul>'); inUl = false; }
            if (inOl) { result.push('</ol>'); inOl = false; }
            result.push('<h3>' + trimmed.replace(/^###\s+/, '') + '</h3>');
        }
        else if (/^##\s+/.test(trimmed)) {
            if (inUl) { result.push('</ul>'); inUl = false; }
            if (inOl) { result.push('</ol>'); inOl = false; }
            result.push('<h2>' + trimmed.replace(/^##\s+/, '') + '</h2>');
        }
        else if (/^#\s+/.test(trimmed)) {
            if (inUl) { result.push('</ul>'); inUl = false; }
            if (inOl) { result.push('</ol>'); inOl = false; }
            result.push('<h1>' + trimmed.replace(/^#\s+/, '') + '</h1>');
        }
        else if (/^[-*]\s+/.test(trimmed) && !/^(\*\*|<strong>)/.test(trimmed)) {
            if (inOl) { result.push('</ol>'); inOl = false; }
            if (!inUl) { result.push('<ul>'); inUl = true; }
            result.push('<li>' + trimmed.replace(/^[-*]\s+/, '') + '</li>');
        }
        else if (/^\d+[\.\)]\s+/.test(trimmed)) {
            if (inUl) { result.push('</ul>'); inUl = false; }
            if (!inOl) { result.push('<ol>'); inOl = true; }
            result.push('<li>' + trimmed.replace(/^\d+[\.\)]\s+/, '') + '</li>');
        }
        else {
            if (inUl) { result.push('</ul>'); inUl = false; }
            if (inOl) { result.push('</ol>'); inOl = false; }

            if (/^&gt;\s*/.test(trimmed)) {
                result.push('<blockquote>' + trimmed.replace(/^&gt;\s*/, '') + '</blockquote>');
            }
            else if (/^(---+|\*\*\*+)$/.test(trimmed)) {
                result.push('<hr>');
            }
            else if (trimmed === '') {
                result.push('');
            }
            else {
                result.push('<p>' + trimmed + '</p>');
            }
        }
    }
    if (inUl) result.push('</ul>');
    if (inOl) result.push('</ol>');

    return result.join('\n').replace(/(<\/p>\n*<p>)/g, '</p><p>');
}

/* =============================================================
   AUTOFILL
   ============================================================= */
let autofillFile = null;
let lastAutofillData = null;

function initAutofill() {
    const autofillZone = document.getElementById("autofillUploadZone");
    const autofillInput = document.getElementById("autofillFileInput");
    const autofillRemoveBtn = document.getElementById("autofillRemoveFile");

    autofillZone.addEventListener("dragover", (e) => { e.preventDefault(); autofillZone.classList.add("dragover"); });
    autofillZone.addEventListener("dragleave", () => autofillZone.classList.remove("dragover"));
    autofillZone.addEventListener("drop", (e) => {
        e.preventDefault();
        autofillZone.classList.remove("dragover");
        if (e.dataTransfer.files.length) selectAutofillFile(e.dataTransfer.files[0]);
    });

    autofillInput.addEventListener("change", () => {
        if (autofillInput.files.length) selectAutofillFile(autofillInput.files[0]);
        autofillInput.value = "";
    });

    autofillRemoveBtn.addEventListener("click", clearAutofillFile);
}

function selectAutofillFile(file) {
    const ext = file.name.split(".").pop().toLowerCase();
    if (!["pdf", "docx", "doc"].includes(ext)) {
        showToast("Unsupported: " + file.name, "error");
        return;
    }
    autofillFile = file;
    document.getElementById("autofillFileName").textContent = file.name;
    document.getElementById("autofillSelectedFile").style.display = "flex";
    document.getElementById("autofillUploadZone").style.display = "none";
    document.getElementById("autofillBtn").disabled = false;
    document.getElementById("compareBtn").disabled = false;
}

function clearAutofillFile() {
    autofillFile = null;
    document.getElementById("autofillSelectedFile").style.display = "none";
    document.getElementById("autofillUploadZone").style.display = "";
    document.getElementById("autofillBtn").disabled = true;
    document.getElementById("compareBtn").disabled = true;
    document.getElementById("submitApprovalBtn").style.display = "none";
}

function showAutofillProgress(text) {
    const p = document.getElementById("autofillProgress");
    const t = document.getElementById("autofillProgressText");
    const b = document.getElementById("autofillProgressBar");
    p.classList.add("visible");
    t.textContent = text || "Processing...";
    b.style.width = "30%";
}

function updateAutofillProgress(pct, text) {
    document.getElementById("autofillProgressBar").style.width = pct + "%";
    if (text) document.getElementById("autofillProgressText").textContent = text;
}

function hideAutofillProgress() {
    document.getElementById("autofillProgress").classList.remove("visible");
    document.getElementById("autofillProgressBar").style.width = "0%";
}

async function runAutofill() {
    if (!autofillFile) return;
    document.getElementById("autofillBtn").disabled = true;
    document.getElementById("buildProfileBtn").disabled = true;
    document.getElementById("autofillResults").style.display = "none";
    showAutofillProgress("Uploading form & detecting fields...");

    const formData = new FormData();
    formData.append("file", autofillFile);
    const companyId = document.getElementById("companyIdInput").value.trim();
    if (companyId) formData.append("company_id", companyId);

    updateAutofillProgress(40, "Retrieving data from knowledge base...");

    try {
        const res = await fetch(`${API_BASE}/autofill-form`, { method: "POST", body: formData });
        updateAutofillProgress(80, "Validating results...");
        if (res.ok) {
            const data = await res.json();
            lastAutofillData = data;
            updateAutofillProgress(100, "Complete!");
            setTimeout(() => hideAutofillProgress(), 600);
            renderAutofillResults(data);
            const filled100 = (data.fields || []).filter(f => f.value && f.confidence >= 1.0).length;
            showToast(`Autofill complete — ${filled100} fields filled at 100% confidence`, "success");
        } else {
            const err = await res.json();
            hideAutofillProgress();
            showToast(err.detail || "Autofill failed", "error");
        }
    } catch {
        hideAutofillProgress();
        showToast("Network error during autofill", "error");
    }
    document.getElementById("autofillBtn").disabled = false;
    document.getElementById("buildProfileBtn").disabled = false;
}

async function buildProfile() {
    const companyId = document.getElementById("companyIdInput").value.trim();
    if (!companyId) { showToast("Enter a Company ID first", "error"); return; }

    document.getElementById("buildProfileBtn").disabled = true;
    document.getElementById("autofillBtn").disabled = true;
    showAutofillProgress("Building master company profile...");
    updateAutofillProgress(50, "Extracting entity data...");

    try {
        const res = await fetch(`${API_BASE}/build-profile`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ company_id: companyId }),
        });
        updateAutofillProgress(90, "Finalizing...");
        if (res.ok) {
            const data = await res.json();
            updateAutofillProgress(100, "Done!");
            setTimeout(() => hideAutofillProgress(), 600);
            renderProfileResults(data);
            showToast(`Profile built — ${data.fields_extracted} fields`, "success");
        } else {
            const err = await res.json();
            hideAutofillProgress();
            showToast(err.detail || "Profile build failed", "error");
        }
    } catch {
        hideAutofillProgress();
        showToast("Network error", "error");
    }
    document.getElementById("buildProfileBtn").disabled = false;
    document.getElementById("autofillBtn").disabled = !autofillFile;
}

function renderAutofillResults(data) {
    const fields = data.fields || [];
    const filled = fields.filter(f => f.value && f.confidence >= 1.0);
    const partial = fields.filter(f => f.value && f.confidence < 1.0);
    const empty = fields.filter(f => !f.value);
    const sb = (data.metadata && data.metadata.source_breakdown) || {};
    const memOnly = sb.memory_only || 0;
    const vecOnly = sb.vector_only || 0;
    const combined = sb.combined_verified || 0;

    let html = `
        <div class="results-header">
            <h3>${escapeHtml(data.document)}</h3>
            <div class="stats-row">
                <span class="stat-chip filled">&#10003; ${filled.length} filled (100%)</span>
                <span class="stat-chip empty">&#9888; ${empty.length + partial.length} not filled</span>
                <span class="stat-chip" style="background:var(--surface-2);color:var(--text-muted);font-size:0.68rem;">Only 100% confidence data from documents is filled</span>
            </div>
        </div>
        ${(memOnly + vecOnly + combined > 0) ? `
        <div class="source-breakdown">
            <span style="color:var(--green);">&#9889; ${combined} cross-verified</span>
            <span style="color:var(--blue);">&#9632; ${memOnly} memory</span>
            <span style="color:var(--yellow);">&#9632; ${vecOnly} vector DB</span>
        </div>` : ''}
        <table class="data-table">
            <thead><tr><th>Field</th><th>Value</th><th>Confidence</th><th>Source</th></tr></thead>
            <tbody>
    `;

    for (let i = 0; i < fields.length; i++) {
        const f = fields[i];
        const confPct = (f.confidence * 100).toFixed(0);
        const is100 = f.confidence >= 1.0;
        const confClass = is100 ? "high" : "low";
        const rowStyle = is100 ? '' : 'opacity:0.6;';
        const val = (f.value && is100) ? escapeHtml(f.value) : '';
        const src = f.source_document ? escapeHtml(f.source_document) : "—";
        const statusLabel = is100 ? '&#10003; Verified' : (f.confidence > 0 ? '&#9888; Not 100%' : '—');
        html += `<tr style="${rowStyle}">
            <td style="font-weight:500;">${escapeHtml(f.field)}</td>
            <td>
                <div class="af-value-cell" style="display:flex;align-items:center;gap:4px;">
                    <input type="text" class="af-edit-input" id="af_val_${i}" value="${val.replace(/"/g, '&quot;')}" placeholder="${is100 ? '' : '(not filled — below 100%)'}" data-field-idx="${i}" style="flex:1;background:transparent;border:1px solid transparent;padding:3px 6px;border-radius:4px;font-size:0.8rem;color:var(--text-primary);outline:none;transition:border-color 0.15s;" onfocus="this.style.borderColor='var(--accent)'" onblur="this.style.borderColor='transparent';updateAutofillField(${i}, this.value)" onkeydown="if(event.key==='Enter'){this.blur();}">
                    <button class="feedback-btn" onclick="openFeedback('${escapeHtml(f.field).replace(/'/g, "\\'")}', document.getElementById('af_val_${i}').value, ${f.confidence})" title="Submit correction to memory" style="flex-shrink:0;">&#9998;</button>
                </div>
            </td>
            <td>
                <span class="conf-badge ${confClass}">${confPct}%</span>
                <span style="font-size:0.68rem;margin-left:4px;color:${is100 ? 'var(--green)' : 'var(--text-muted)'};">${statusLabel}</span>
            </td>
            <td style="color:var(--text-muted);font-size:0.75rem;">${src}</td>
        </tr>`;
    }

    html += `</tbody></table>`;
    const dlExt = (data.metadata && data.metadata.file_ext) ? data.metadata.file_ext.toUpperCase() : "DOCX";
    html += `<div class="results-actions" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;">
        <button class="btn btn-download" onclick="downloadAutofillReport()">&#8615; Download Filled Form (.${dlExt.toLowerCase()})</button>
        <button class="btn btn-accent" onclick="refillAndDownload()">&#128190; Save Edits &amp; Re-fill</button>
        <button class="btn btn-ghost" onclick="saveAsTemplate()">&#128203; Save as Template</button>
    </div>`;

    document.getElementById("submitApprovalBtn").style.display = "";
    const resultsEl = document.getElementById("autofillResults");
    resultsEl.innerHTML = html;
    resultsEl.style.display = "block";
}

function updateAutofillField(idx, newValue) {
    if (!lastAutofillData || !lastAutofillData.fields) return;
    if (idx >= 0 && idx < lastAutofillData.fields.length) {
        lastAutofillData.fields[idx].value = newValue.trim() || null;
    }
}

async function refillAndDownload() {
    if (!lastAutofillData || !autofillFile) {
        showToast("No autofill data or file to re-fill", "error");
        return;
    }

    // Sync all edited values from inputs into lastAutofillData
    const inputs = document.querySelectorAll('.af-edit-input[data-field-idx]');
    inputs.forEach(inp => {
        const idx = parseInt(inp.dataset.fieldIdx, 10);
        if (lastAutofillData.fields[idx]) {
            lastAutofillData.fields[idx].value = inp.value.trim() || null;
        }
    });

    // Re-run autofill with the edited data by re-uploading the form
    // and sending the corrected fields via a dedicated re-fill endpoint
    showAutofillProgress("Re-filling form with your edits...");
    updateAutofillProgress(40, "Applying corrections to document...");

    const formData = new FormData();
    formData.append("file", autofillFile);
    formData.append("fields_json", JSON.stringify(lastAutofillData.fields));

    try {
        const res = await fetch(`${API_BASE}/refill-form`, { method: "POST", body: formData });
        updateAutofillProgress(80, "Generating document...");
        if (res.ok) {
            const blob = await res.blob();
            const ext = (lastAutofillData.metadata && lastAutofillData.metadata.file_ext) || "docx";
            const safeName = (lastAutofillData.document || "Form").replace(/[^a-zA-Z0-9 _-]/g, "_");
            const filename = `${safeName}_Autofilled.${ext}`;
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url; a.download = filename;
            document.body.appendChild(a); a.click(); a.remove();
            URL.revokeObjectURL(url);
            updateAutofillProgress(100, "Done!");
            setTimeout(() => hideAutofillProgress(), 600);
            showToast("Re-filled form downloaded!", "success");
        } else {
            hideAutofillProgress();
            const err = await res.json();
            showToast(err.detail || "Re-fill failed", "error");
        }
    } catch {
        hideAutofillProgress();
        showToast("Network error during re-fill", "error");
    }
}

async function downloadAutofillReport() {
    if (!lastAutofillData) { showToast("No data to download", "error"); return; }
    try {
        const res = await fetch(`${API_BASE}/download-autofill-report`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(lastAutofillData),
        });
        if (res.ok) {
            const blob = await res.blob();
            const disposition = res.headers.get("Content-Disposition") || "";
            const ext = (lastAutofillData.metadata && lastAutofillData.metadata.file_ext) || "docx";
            let filename = `Autofilled_Form.${ext}`;
            const match = disposition.match(/filename="?([^"]+)"?/);
            if (match) filename = match[1];
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url; a.download = filename;
            document.body.appendChild(a); a.click(); a.remove();
            URL.revokeObjectURL(url);
            showToast("Downloaded!", "success");
        } else {
            const err = await res.json();
            showToast(err.detail || "Download failed", "error");
        }
    } catch {
        showToast("Network error", "error");
    }
}

function renderProfileResults(data) {
    const profile = data.profile || {};
    const keys = Object.keys(profile);

    let html = `
        <div class="results-header">
            <h3>Profile — ${escapeHtml(data.company_id)}</h3>
            <div class="stats-row"><span class="stat-chip filled">&#10003; ${keys.length} fields</span></div>
        </div>
        <table class="data-table">
            <thead><tr><th>Field</th><th>Value</th><th>Confidence</th><th>Source</th></tr></thead>
            <tbody>
    `;

    for (const key of keys) {
        const entry = profile[key];
        const confClass = entry.confidence >= 0.90 ? "high" : entry.confidence >= 0.80 ? "mid" : "low";
        html += `<tr>
            <td>${escapeHtml(key)}</td>
            <td>${escapeHtml(entry.value)}</td>
            <td><span class="conf-badge ${confClass}">${(entry.confidence * 100).toFixed(0)}%</span></td>
            <td style="color:var(--text-muted);font-size:0.75rem;">${escapeHtml(entry.source || "—")}</td>
        </tr>`;
    }

    html += `</tbody></table>`;
    const resultsEl = document.getElementById("autofillResults");
    resultsEl.innerHTML = html;
    resultsEl.style.display = "block";
}

/* =============================================================
   DICTIONARY — Term Lookup
   ============================================================= */
const DICT_STORAGE_KEY = "docintel_dict_history";
let dictLookupHistory = [];

function initDictionary() {
    try {
        const raw = localStorage.getItem(DICT_STORAGE_KEY);
        if (raw) dictLookupHistory = JSON.parse(raw);
    } catch {}

    document.getElementById("dictInput").addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); lookupTerm(); }
    });

    renderDictHistory();
}

function saveDictHistory() {
    try { localStorage.setItem(DICT_STORAGE_KEY, JSON.stringify(dictLookupHistory)); } catch {}
}

function renderDictHistory() {
    const el = document.getElementById("dictHistory");
    const chips = document.getElementById("dictHistoryChips");
    if (dictLookupHistory.length === 0) { el.style.display = "none"; return; }
    el.style.display = "block";
    chips.innerHTML = "";
    const items = [...dictLookupHistory].reverse().slice(0, 20);
    for (const term of items) {
        const chip = document.createElement("button");
        chip.className = "dict-chip";
        chip.textContent = term;
        chip.onclick = () => { document.getElementById("dictInput").value = term; lookupTerm(); };
        chips.appendChild(chip);
    }
}

async function lookupTerm() {
    const dictInput = document.getElementById("dictInput");
    const dictBtn = document.getElementById("dictBtn");
    const dictResultArea = document.getElementById("dictResultArea");
    const term = dictInput.value.trim();
    if (!term) return;

    dictBtn.disabled = true;
    dictInput.disabled = true;

    dictResultArea.innerHTML = `
        <div class="dict-result-card" style="text-align:center;color:var(--text-muted);">
            <span class="spinner"></span>&nbsp; Looking up "${escapeHtml(term)}"...
        </div>
    `;

    try {
        const res = await fetch(`${API_BASE}/define`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ term }),
        });

        if (res.ok) {
            const data = await res.json();
            renderDictResult(data);
            const idx = dictLookupHistory.findIndex(t => t.toLowerCase() === term.toLowerCase());
            if (idx !== -1) dictLookupHistory.splice(idx, 1);
            dictLookupHistory.push(term);
            if (dictLookupHistory.length > 50) dictLookupHistory.shift();
            saveDictHistory();
            renderDictHistory();
        } else {
            const err = await res.json();
            dictResultArea.innerHTML = `<div class="dict-result-card" style="color:#fca5a5;">${escapeHtml(err.detail || "Lookup failed")}</div>`;
        }
    } catch {
        dictResultArea.innerHTML = `<div class="dict-result-card" style="color:#fca5a5;">Network error — is the server running?</div>`;
    }

    dictBtn.disabled = false;
    dictInput.disabled = false;
    dictInput.focus();
}

function renderDictResult(data) {
    let html = `<div class="dict-result"><div class="dict-result-card">`;
    html += `<div class="dict-term-header">`;
    html += `<span class="dict-term-word">${escapeHtml(data.term)}</span>`;
    html += `<span class="dict-term-badge">from documents</span></div>`;
    html += `<div class="dict-definition">${renderMarkdown(data.definition)}</div>`;

    if (data.sources && data.sources.length > 0) {
        html += `<div class="dict-sources"><div class="sources-label">Found in</div>`;
        data.sources.forEach(src => {
            const name = src.source || "Unknown";
            const page = src.page != null ? ` p.${src.page}` : "";
            html += `<span class="source-chip">&#128196; ${escapeHtml(name)}${page}</span>`;
        });
        html += `</div>`;
    }

    html += `</div></div>`;
    document.getElementById("dictResultArea").innerHTML = html;
}

/* =============================================================
   COMPARISON MODE
   ============================================================= */
async function runCompare() {
    if (!autofillFile) return;
    const compareBtn = document.getElementById("compareBtn");
    compareBtn.disabled = true;
    document.getElementById("autofillBtn").disabled = true;
    document.getElementById("autofillResults").style.display = "none";
    showAutofillProgress("Running comparison analysis...");

    const formData = new FormData();
    formData.append("file", autofillFile);
    const companyId = document.getElementById("companyIdInput").value.trim();
    if (companyId) formData.append("company_id", companyId);

    try {
        updateAutofillProgress(50, "Comparing original vs autofill...");
        const res = await fetch(`${API_BASE}/autofill-compare`, { method: "POST", body: formData });
        updateAutofillProgress(90, "Building comparison...");

        if (res.ok) {
            const data = await res.json();
            updateAutofillProgress(100, "Done!");
            setTimeout(() => hideAutofillProgress(), 600);
            renderComparisonResults(data);
        } else {
            const err = await res.json();
            hideAutofillProgress();
            showToast(err.detail || "Comparison failed", "error");
        }
    } catch {
        hideAutofillProgress();
        showToast("Network error during comparison", "error");
    }
    compareBtn.disabled = false;
    document.getElementById("autofillBtn").disabled = false;
}

function renderComparisonResults(data) {
    const cmp = data.comparison || [];
    let html = `
        <div class="results-header">
            <h3>Comparison: ${escapeHtml(data.document)}</h3>
            <div class="stats-row">
                <span class="stat-chip filled">&#10003; ${data.filled_fields} filled</span>
                <span class="stat-chip empty">&#9888; ${data.empty_fields} empty</span>
            </div>
        </div>
        <table class="comparison-table">
            <thead><tr><th>Field</th><th>Original</th><th>Autofilled</th><th>Confidence</th></tr></thead>
            <tbody>
    `;
    for (const c of cmp) {
        const confClass = c.confidence >= 0.90 ? "high" : c.confidence >= 0.80 ? "mid" : "low";
        const confPct = (c.confidence * 100).toFixed(0);
        const orig = c.original_value ? escapeHtml(c.original_value) : '<span class="comparison-original">(empty)</span>';
        const filled = c.autofilled_value ? `<span class="comparison-filled">${escapeHtml(c.autofilled_value)}</span>` : '<span style="color:var(--text-muted);">—</span>';
        html += `<tr>
            <td>${escapeHtml(c.field)}</td>
            <td>${orig}</td>
            <td>${filled}</td>
            <td><span class="conf-badge ${confClass}">${confPct}%</span>
                <span class="conf-bar-bg"><span class="conf-bar-fill ${confClass}" style="width:${confPct}%"></span></span></td>
        </tr>`;
    }
    html += `</tbody></table>`;
    const resultsEl = document.getElementById("autofillResults");
    resultsEl.innerHTML = html;
    resultsEl.style.display = "block";
}

/* =============================================================
   FEEDBACK / ACTIVE LEARNING
   ============================================================= */
function openFeedback(fieldName, originalValue, confidence) {
    const corrected = prompt(`Correct value for "${fieldName}":\n\nCurrent: ${originalValue}\n\nEnter the correct value:`);
    if (corrected === null || corrected.trim() === "") return;

    const companyId = document.getElementById("companyIdInput").value.trim() || "unknown";

    fetch(`${API_BASE}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            company_id: companyId,
            field_name: fieldName,
            original_value: originalValue,
            corrected_value: corrected.trim(),
            original_confidence: confidence,
            source_document: lastAutofillData?.document || null,
        }),
    })
    .then(r => r.json())
    .then(data => {
        showToast(`Correction saved for "${fieldName}"`, "success");
        const fieldId = fieldName.replace(/[^a-zA-Z0-9]/g, '_');
        const el = document.getElementById(`val_${fieldId}`);
        if (el) el.textContent = corrected.trim();
    })
    .catch(() => showToast("Failed to save correction", "error"));
}

/* =============================================================
   DOCUMENT LIBRARY
   ============================================================= */
async function loadDocumentList() {
    const container = document.getElementById("docListContainer");
    try {
        const res = await fetch(`${API_BASE}/documents`);
        const data = await res.json();
        const files = data.files || [];

        if (files.length === 0) {
            container.innerHTML = '<p style="color:var(--text-muted);font-size:0.82rem;">No documents uploaded yet. Go to Upload to add files.</p>';
            return;
        }

        let html = `<div style="font-size:0.75rem;color:var(--text-muted);margin-bottom:8px;">${files.length} document(s)</div><div class="doc-list">`;
        for (const f of files) {
            const imgExts = ['jpg','jpeg','png','webp','heic','heif','svg','ico','jfif'];
            const icon = f.ext === 'pdf' ? '&#128196;'
                : (f.ext === 'csv' || f.ext === 'tsv') ? '&#128200;'
                : (f.ext === 'xlsx' || f.ext === 'xls') ? '&#128202;'
                : f.ext === 'txt' ? '&#128221;'
                : (f.ext === 'md' || f.ext === 'markdown') ? '&#128209;'
                : f.ext === 'rtf' ? '&#128196;'
                : imgExts.includes(f.ext) ? '&#128247;'
                : '&#128196;';
            const sizeKB = (f.size / 1024).toFixed(1);
            html += `
                <div class="doc-list-item" onclick="previewDocument('${escapeHtml(f.filename)}')">
                    <span class="doc-icon">${icon}</span>
                    <span class="doc-name">${escapeHtml(f.filename)}</span>
                    <span class="doc-meta"><span>${sizeKB} KB</span><span>.${f.ext}</span></span>
                </div>`;
        }
        html += `</div>`;

        const versioned = data.versioned_documents || [];
        if (versioned.length > 0) {
            html += `<div style="margin-top:16px;"><div class="section-label" style="margin-bottom:8px;">Version History</div>`;
            for (const v of versioned) {
                html += `
                    <div class="doc-list-item" onclick="showVersions('${v.document_id}')">
                        <span class="doc-icon">&#128194;</span>
                        <span class="doc-name">${escapeHtml(v.filename)}</span>
                        <span class="doc-meta">
                            ${v.version_count > 1 ? `<span class="doc-version-badge">v${v.version_count}</span>` : ''}
                            <span>${v.document_type}</span>
                        </span>
                    </div>`;
            }
            html += `</div>`;
        }

        container.innerHTML = html;
    } catch {
        container.innerHTML = '<p style="color:var(--red);font-size:0.82rem;">Failed to load documents.</p>';
    }
}

async function previewDocument(filename) {
    const previewContainer = document.getElementById("docPreviewContainer");
    const previewContent = document.getElementById("docPreviewContent");
    const previewTitle = document.getElementById("docPreviewTitle");

    previewTitle.textContent = filename;
    previewContent.innerHTML = '<p style="color:var(--text-muted);"><span class="spinner"></span> Loading preview...</p>';
    previewContainer.style.display = "block";

    try {
        const res = await fetch(`${API_BASE}/document-preview/${encodeURIComponent(filename)}`);
        const data = await res.json();

        if (data.type === "pdf") {
            previewContent.innerHTML = `<iframe class="doc-viewer-frame" src="data:application/pdf;base64,${data.content}"></iframe>`;
        } else if (data.type === "image") {
            const mimeType = data.mime_type || "image/png";
            let html = `<div style="text-align:center;padding:16px;">
                <img src="data:${mimeType};base64,${data.content}" alt="${escapeHtml(filename)}" style="max-width:100%;max-height:500px;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,0.2);" />
            </div>`;
            if (data.ocr_text) {
                html += `<div style="margin-top:12px;padding:0 16px;">
                    <div style="font-size:0.75rem;font-weight:600;color:var(--text-muted);margin-bottom:6px;">Extracted Text (OCR)</div>
                    <div class="doc-text-preview">${escapeHtml(data.ocr_text)}</div>
                </div>`;
            }
            previewContent.innerHTML = html;
        } else {
            previewContent.innerHTML = `<div class="doc-text-preview">${escapeHtml(data.content)}</div>`;
        }
    } catch {
        previewContent.innerHTML = '<p style="color:var(--red);">Preview failed.</p>';
    }
}

function closeDocPreview() {
    document.getElementById("docPreviewContainer").style.display = "none";
}

async function showVersions(documentId) {
    try {
        const res = await fetch(`${API_BASE}/document-versions/${documentId}`);
        const data = await res.json();
        const versions = data.versions || [];

        let html = `<div style="margin-top:16px;"><h3 style="font-size:0.88rem;margin-bottom:8px;">Versions of: ${escapeHtml(data.original_filename)}</h3>`;
        for (const v of versions) {
            html += `<div class="doc-list-item">
                <span class="doc-icon">&#128196;</span>
                <span class="doc-name">${escapeHtml(v.filename)}</span>
                <span class="doc-meta">
                    <span class="doc-version-badge">v${v.version_id.slice(0,4)}</span>
                    <span>${new Date(v.upload_timestamp).toLocaleDateString()}</span>
                    <span>${(v.file_size/1024).toFixed(1)} KB</span>
                </span>
            </div>`;
        }
        html += `</div>`;

        document.getElementById("docPreviewContainer").innerHTML = html;
        document.getElementById("docPreviewContainer").style.display = "block";
    } catch {
        showToast("Failed to load versions", "error");
    }
}

/* =============================================================
   SEMANTIC SEARCH
   ============================================================= */
function switchSearchTab(tab) {
    document.querySelectorAll('#panel-search .tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('#panel-search .tab-content').forEach(c => c.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById(`searchTab-${tab}`).classList.add('active');
}

function initSearch() {
    document.getElementById("searchQueryInput").addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); runSemanticSearch(); }
    });
    document.getElementById("entitySearchQuery").addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); runEntitySearch(); }
    });
}

async function runSemanticSearch() {
    const query = document.getElementById("searchQueryInput").value.trim();
    if (!query) return;

    const container = document.getElementById("searchResults");
    container.innerHTML = '<p style="color:var(--text-muted);"><span class="spinner"></span> Searching...</p>';

    try {
        const res = await fetch(`${API_BASE}/search`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query, top_k: 15 }),
        });

        if (res.ok) {
            const data = await res.json();
            const results = data.results || [];

            if (results.length === 0) {
                container.innerHTML = '<p style="color:var(--text-muted);">No results found.</p>';
                return;
            }

            let html = `<div style="font-size:0.72rem;color:var(--text-muted);margin-bottom:8px;">${results.length} result(s)</div>`;
            for (const r of results) {
                const source = r.source || r.metadata?.source || "Unknown";
                const page = r.page || r.metadata?.page || "";
                const text = r.text || r.page_content || r.content || "";
                const score = r.score ? r.score.toFixed(3) : "";
                html += `
                    <div class="search-result-card">
                        <div class="search-result-source">&#128196; ${escapeHtml(source)}${page ? ' p.' + page : ''}</div>
                        <div class="search-result-text">${escapeHtml(text.slice(0, 500))}${text.length > 500 ? '...' : ''}</div>
                        ${score ? `<div class="search-result-score">Score: ${score}</div>` : ''}
                    </div>`;
            }
            container.innerHTML = html;
        } else {
            const err = await res.json();
            container.innerHTML = `<p style="color:var(--red);">${escapeHtml(err.detail || 'Search failed')}</p>`;
        }
    } catch {
        container.innerHTML = '<p style="color:var(--red);">Network error during search.</p>';
    }
}

async function runEntitySearch() {
    const query = document.getElementById("entitySearchQuery").value.trim();
    if (!query) return;

    const container = document.getElementById("entitySearchResults");
    container.innerHTML = '<p style="color:var(--text-muted);"><span class="spinner"></span> Searching entities...</p>';

    try {
        const res = await fetch(`${API_BASE}/entity-search?q=${encodeURIComponent(query)}&limit=20`);
        if (res.ok) {
            const data = await res.json();
            const results = data.results || [];

            if (results.length === 0) {
                container.innerHTML = '<p style="color:var(--text-muted);">No entities found.</p>';
                return;
            }

            let html = `<div style="font-size:0.72rem;color:var(--text-muted);margin-bottom:8px;">${results.length} entity(s)</div>`;
            for (const r of results) {
                html += `
                    <div class="search-result-card">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                            <strong style="font-size:0.85rem;">${escapeHtml(r.company_name || r.company_id || 'Unknown')}</strong>
                            ${r.entity_type ? `<span style="font-size:0.68rem;color:var(--purple);background:var(--purple-dim);padding:1px 6px;border-radius:3px;">${escapeHtml(r.entity_type)}</span>` : ''}
                        </div>
                        <div style="font-size:0.78rem;color:var(--text-secondary);">
                            ${r.ein ? `EIN: ${escapeHtml(r.ein)} &nbsp; ` : ''}
                            ${r.fcc_499_id ? `FCC: ${escapeHtml(r.fcc_499_id)} &nbsp; ` : ''}
                            ${r.phone ? `&#128222; ${escapeHtml(r.phone)} &nbsp; ` : ''}
                            ${r.email ? `&#9993; ${escapeHtml(r.email)}` : ''}
                        </div>
                        ${r.address ? `<div style="font-size:0.72rem;color:var(--text-muted);margin-top:4px;">&#128205; ${escapeHtml(r.address)}</div>` : ''}
                        <div style="font-size:0.68rem;color:var(--text-muted);margin-top:4px;">${r.field_count} fields, ${r.document_count} docs</div>
                    </div>`;
            }
            container.innerHTML = html;
        } else {
            const err = await res.json();
            container.innerHTML = `<p style="color:var(--red);">${escapeHtml(err.detail || 'Entity search failed')}</p>`;
        }
    } catch {
        container.innerHTML = '<p style="color:var(--red);">Network error.</p>';
    }
}

/* =============================================================
   TEMPLATE LIBRARY
   ============================================================= */
async function loadTemplates() {
    const container = document.getElementById("templateListContainer");
    try {
        const res = await fetch(`${API_BASE}/templates`);
        const data = await res.json();
        const templates = data.templates || [];

        if (templates.length === 0) {
            container.innerHTML = '<p style="color:var(--text-muted);font-size:0.82rem;">No templates saved yet. Autofill a form and click "Save as Template" to create one.</p>';
            return;
        }

        let html = `<div style="font-size:0.72rem;color:var(--text-muted);margin-bottom:8px;">${templates.length} template(s)</div><div class="template-grid">`;
        for (const t of templates) {
            html += `
                <div class="template-card" onclick="viewTemplate('${t.template_id}')">
                    <div class="tc-name">${escapeHtml(t.name)}</div>
                    <div class="tc-type">${escapeHtml(t.form_type)}</div>
                    <div class="tc-meta">
                        <span>${t.field_count} fields</span>
                        <span>Used ${t.usage_count}x</span>
                        <span>${new Date(t.created_at).toLocaleDateString()}</span>
                    </div>
                    ${t.description ? `<div style="font-size:0.72rem;color:var(--text-muted);margin-top:6px;">${escapeHtml(t.description)}</div>` : ''}
                </div>`;
        }
        html += `</div>`;
        container.innerHTML = html;
    } catch {
        container.innerHTML = '<p style="color:var(--red);font-size:0.82rem;">Failed to load templates.</p>';
    }
}

async function viewTemplate(templateId) {
    try {
        const res = await fetch(`${API_BASE}/templates/${templateId}`);
        const t = await res.json();

        let html = `<div class="results-header"><h3>${escapeHtml(t.name)}</h3>
            <div class="stats-row"><span class="stat-chip filled">${t.form_type}</span><span class="stat-chip empty">${t.fields.length} fields</span></div></div>`;
        html += `<table class="data-table"><thead><tr><th>Field</th><th>Type</th></tr></thead><tbody>`;
        for (const f of t.fields) {
            html += `<tr><td>${escapeHtml(f.field || f.name || '')}</td><td style="color:var(--text-muted);">${escapeHtml(f.type || 'text')}</td></tr>`;
        }
        html += `</tbody></table>`;
        html += `<div style="margin-top:12px;"><button class="btn btn-ghost" onclick="deleteTemplate('${templateId}')">&#128465; Delete Template</button></div>`;

        document.getElementById("templateListContainer").innerHTML = html;
    } catch {
        showToast("Failed to load template", "error");
    }
}

async function saveAsTemplate() {
    if (!lastAutofillData) { showToast("No autofill data", "error"); return; }

    const name = prompt("Template name:", lastAutofillData.document || "Form Template");
    if (!name) return;
    const formType = prompt("Form type (e.g. kyc, tax, agreement):", "unknown") || "unknown";

    const fields = (lastAutofillData.fields || []).map(f => ({ field: f.field, type: f.field_type || "text" }));

    try {
        const res = await fetch(`${API_BASE}/templates`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, form_type: formType, fields, description: `Auto-saved from ${lastAutofillData.document}` }),
        });
        if (res.ok) showToast("Template saved!", "success");
        else showToast("Failed to save template", "error");
    } catch {
        showToast("Network error", "error");
    }
}

async function deleteTemplate(templateId) {
    if (!confirm("Delete this template?")) return;
    try {
        await fetch(`${API_BASE}/templates/${templateId}`, { method: "DELETE" });
        showToast("Template deleted", "success");
        loadTemplates();
    } catch {
        showToast("Delete failed", "error");
    }
}

/* =============================================================
   APPROVAL WORKFLOW
   ============================================================= */
let currentApprovalFilter = "pending";

function switchApprovalTab(tab) {
    currentApprovalFilter = tab;
    document.querySelectorAll('#panel-approvals .tab-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    loadApprovals();
}

async function loadApprovals() {
    const container = document.getElementById("approvalListContainer");
    const statusParam = currentApprovalFilter === "all" ? "" : `?approval_status=${currentApprovalFilter}`;

    try {
        const res = await fetch(`${API_BASE}/approvals${statusParam}`);
        const data = await res.json();
        const requests = data.requests || [];

        const badge = document.getElementById("approvalBadge");
        if (data.pending > 0) { badge.textContent = data.pending; badge.style.display = ""; }
        else { badge.style.display = "none"; }

        if (requests.length === 0) {
            container.innerHTML = `<p style="color:var(--text-muted);font-size:0.82rem;">No ${currentApprovalFilter === 'all' ? '' : currentApprovalFilter} approval requests.</p>`;
            return;
        }

        let html = '';
        for (const r of requests) {
            html += `
                <div class="approval-card" onclick="viewApproval('${r.request_id}')">
                    <span class="approval-status ${r.status}">${r.status.replace('_', ' ')}</span>
                    <div class="approval-info">
                        <div class="ai-doc">${escapeHtml(r.document_name)}</div>
                        <div class="ai-meta">${r.filled_count}/${r.field_count} fields filled &bull; ${r.step_count} step(s) &bull; ${new Date(r.created_at).toLocaleDateString()}</div>
                    </div>
                </div>`;
        }
        container.innerHTML = html;
    } catch {
        container.innerHTML = '<p style="color:var(--red);font-size:0.82rem;">Failed to load approvals.</p>';
    }
}

async function viewApproval(requestId) {
    const detail = document.getElementById("approvalDetailContainer");
    detail.style.display = "block";

    try {
        const res = await fetch(`${API_BASE}/approvals/${requestId}`);
        const r = await res.json();

        let html = `
            <div class="results-header">
                <h3>${escapeHtml(r.document_name)}</h3>
                <div class="stats-row"><span class="approval-status ${r.status}">${r.status.replace('_', ' ')}</span></div>
            </div>
            <table class="data-table"><thead><tr><th>Field</th><th>Value</th><th>Confidence</th></tr></thead><tbody>`;

        for (const f of r.fields) {
            const confClass = (f.confidence||0) >= 0.90 ? "high" : (f.confidence||0) >= 0.80 ? "mid" : "low";
            const confPct = ((f.confidence||0) * 100).toFixed(0);
            html += `<tr>
                <td>${escapeHtml(f.field || '')}</td>
                <td>${escapeHtml(f.value || '—')}</td>
                <td><span class="conf-badge ${confClass}">${confPct}%</span>
                    <span class="conf-bar-bg"><span class="conf-bar-fill ${confClass}" style="width:${confPct}%"></span></span></td>
            </tr>`;
        }
        html += `</tbody></table>`;

        if (r.steps && r.steps.length > 0) {
            html += `<div style="margin-top:16px;"><div class="section-label">Approval History</div>`;
            for (const s of r.steps) {
                html += `<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:0.78rem;">
                    <strong>${escapeHtml(s.action)}</strong> by ${escapeHtml(s.user_id)} — ${new Date(s.timestamp).toLocaleString()}
                    ${s.comment ? `<div style="color:var(--text-muted);margin-top:2px;">${escapeHtml(s.comment)}</div>` : ''}
                </div>`;
            }
            html += `</div>`;
        }

        if (r.status === "pending" || r.status === "reviewed") {
            html += `<div style="margin-top:16px;display:flex;gap:8px;">
                <button class="btn btn-accent" onclick="approvalAction('${requestId}', 'approve')">&#10003; Approve</button>
                <button class="btn btn-ghost" style="border-color:var(--red);color:var(--red);" onclick="approvalAction('${requestId}', 'reject')">&#10007; Reject</button>
            </div>`;
        } else if (r.status === "approved") {
            html += `<div style="margin-top:16px;">
                <button class="btn btn-accent" onclick="approvalAction('${requestId}', 'final_approve')">&#9989; Final Approve</button>
            </div>`;
        }

        detail.innerHTML = html;
    } catch {
        detail.innerHTML = '<p style="color:var(--red);">Failed to load approval details.</p>';
    }
}

async function approvalAction(requestId, action) {
    const comment = prompt(`Comment for ${action}:`, "") || "";
    try {
        const res = await fetch(`${API_BASE}/approvals/${requestId}/step`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, user_id: "analyst", comment }),
        });
        if (res.ok) {
            showToast(`${action} recorded`, "success");
            viewApproval(requestId);
            loadApprovals();
        } else {
            showToast("Action failed", "error");
        }
    } catch {
        showToast("Network error", "error");
    }
}

async function submitForApproval() {
    if (!lastAutofillData) { showToast("No autofill data", "error"); return; }
    const companyId = document.getElementById("companyIdInput").value.trim() || null;

    try {
        const res = await fetch(`${API_BASE}/approvals`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                document_name: lastAutofillData.document || "Unknown Form",
                company_id: companyId,
                fields: lastAutofillData.fields || [],
                file_id: lastAutofillData.metadata?.file_id || null,
                file_ext: lastAutofillData.metadata?.file_ext || null,
                created_by: "analyst",
            }),
        });
        if (res.ok) {
            showToast("Submitted for approval!", "success");
            document.getElementById("submitApprovalBtn").style.display = "none";
        } else {
            showToast("Submission failed", "error");
        }
    } catch {
        showToast("Network error", "error");
    }
}

/* =============================================================
   RESTRICTED ITEMS — CRUD
   ============================================================= */
let riAllItems = [];
let riCurrentFilter = "all";
let riExtractedItems = [];
const CATEGORY_LABELS = {
    not_provided: "Not Provided",
    illegal: "Illegal",
    scam_fraud: "Scam / Fraud",
};

function initRestrictedItems() {
    const riUploadZone = document.getElementById("riUploadZone");
    riUploadZone.addEventListener("dragover", (e) => { e.preventDefault(); riUploadZone.classList.add("dragover"); });
    riUploadZone.addEventListener("dragleave", () => riUploadZone.classList.remove("dragover"));
    riUploadZone.addEventListener("drop", (e) => {
        e.preventDefault();
        riUploadZone.classList.remove("dragover");
        if (e.dataTransfer.files.length > 0) handleRiFileUploadFromFile(e.dataTransfer.files[0]);
    });
}

async function loadRestrictedItems() {
    try {
        const res = await fetch(`${API_BASE}/restricted-items`);
        if (!res.ok) throw new Error("Failed to load");
        const data = await res.json();
        riAllItems = data.items || [];

        const c = data.counts || {};
        document.getElementById("riCountNP").textContent = c.not_provided || 0;
        document.getElementById("riCountIL").textContent = c.illegal || 0;
        document.getElementById("riCountSF").textContent = c.scam_fraud || 0;

        renderRestrictedItems();
    } catch (e) {
        console.error("[Restricted]", e);
        document.getElementById("riListContainer").innerHTML =
            `<div class="ri-empty"><p style="color:var(--red);">Failed to load restricted items</p></div>`;
    }
}

function renderRestrictedItems() {
    const container = document.getElementById("riListContainer");
    const searchQ = (document.getElementById("riSearchInput").value || "").toLowerCase().trim();

    let filtered = riAllItems;
    if (riCurrentFilter !== "all") filtered = filtered.filter(i => i.category === riCurrentFilter);
    if (searchQ) {
        filtered = filtered.filter(i =>
            i.title.toLowerCase().includes(searchQ) ||
            (i.description || "").toLowerCase().includes(searchQ)
        );
    }

    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="ri-empty">
                <div class="ri-empty-icon">&#128683;</div>
                <p>${searchQ || riCurrentFilter !== 'all' ? 'No matching items' : 'No restricted items yet'}</p>
                <p class="hint">Click "+ Add Item" to add services not provided, illegal activities, or scam/fraud patterns</p>
            </div>`;
        return;
    }

    let html = "";
    for (const item of filtered) {
        const cat = item.category || "not_provided";
        const date = item.created_at ? new Date(item.created_at).toLocaleDateString() : "";
        const source = item.source_document ? ` · from ${escapeHtml(item.source_document)}` : "";
        html += `
        <div class="ri-item" data-id="${item.id}">
            <span class="ri-item-badge ${cat}">${CATEGORY_LABELS[cat] || cat}</span>
            <div class="ri-item-body">
                <div class="ri-item-title">${escapeHtml(item.title)}</div>
                ${item.description ? `<div class="ri-item-desc">${escapeHtml(item.description)}</div>` : ''}
                <div class="ri-item-meta">Added ${date} by ${escapeHtml(item.added_by || 'admin')}${source}</div>
            </div>
            <div class="ri-item-actions">
                <button title="Edit" onclick="editRiItem('${item.id}')">&#9998;</button>
                <button class="del" title="Delete" onclick="deleteRiItem('${item.id}', '${escapeHtml(item.title).replace(/'/g, "\\'")}')">&#128465;</button>
            </div>
        </div>`;
    }
    container.innerHTML = html;
}

function setRiFilter(cat, btn) {
    riCurrentFilter = cat;
    document.querySelectorAll(".ri-filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    renderRestrictedItems();
}

function filterRestrictedItems() {
    renderRestrictedItems();
}

function openRiModal(editItem = null) {
    document.getElementById("riEditId").value = editItem ? editItem.id : "";
    document.getElementById("riModalTitle").textContent = editItem ? "Edit Restricted Item" : "Add Restricted Item";
    document.getElementById("riFormTitle").value = editItem ? editItem.title : "";
    document.getElementById("riFormCategory").value = editItem ? editItem.category : "not_provided";
    document.getElementById("riFormDesc").value = editItem ? (editItem.description || "") : "";
    document.getElementById("riFormSource").value = editItem ? (editItem.source_document || "") : "";
    document.getElementById("riModalOverlay").classList.add("open");
    document.getElementById("riFormTitle").focus();
}

function closeRiModal() {
    document.getElementById("riModalOverlay").classList.remove("open");
}

async function saveRiItem() {
    const editId = document.getElementById("riEditId").value;
    const title = document.getElementById("riFormTitle").value.trim();
    const category = document.getElementById("riFormCategory").value;
    const description = document.getElementById("riFormDesc").value.trim();
    const source = document.getElementById("riFormSource").value.trim();

    if (!title) { showToast("Title is required", "error"); return; }

    try {
        let res;
        if (editId) {
            res = await fetch(`${API_BASE}/restricted-items/${editId}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title, category, description }),
            });
        } else {
            res = await fetch(`${API_BASE}/restricted-items`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title, category, description, source_document: source || null, added_by: "admin" }),
            });
        }

        if (res.ok) {
            showToast(editId ? "Item updated" : "Item added", "success");
            closeRiModal();
            loadRestrictedItems();
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to save", "error");
        }
    } catch (e) {
        showToast("Network error", "error");
    }
}

function editRiItem(id) {
    const item = riAllItems.find(i => i.id === id);
    if (item) openRiModal(item);
}

async function deleteRiItem(id, title) {
    if (!confirm(`Delete "${title}" from the restricted list?`)) return;
    try {
        const res = await fetch(`${API_BASE}/restricted-items/${id}`, { method: "DELETE" });
        if (res.ok) { showToast("Item removed", "success"); loadRestrictedItems(); }
        else showToast("Failed to delete", "error");
    } catch {
        showToast("Network error", "error");
    }
}

/* ── File Upload & AI Extraction ── */
function handleRiFileUpload(input) {
    if (input.files.length > 0) {
        handleRiFileUploadFromFile(input.files[0]);
        input.value = "";
    }
}

async function handleRiFileUploadFromFile(file) {
    const progress = document.getElementById("riUploadProgress");
    const statusEl = document.getElementById("riUploadStatus");

    progress.classList.add("active");
    statusEl.textContent = `Uploading ${file.name}…`;

    const formData = new FormData();
    formData.append("file", file);

    try {
        statusEl.textContent = `Extracting restricted items from ${file.name}… (AI processing)`;
        const res = await fetch(`${API_BASE}/restricted-items/extract-from-file`, { method: "POST", body: formData });
        progress.classList.remove("active");

        if (!res.ok) {
            const err = await res.json();
            showToast(err.detail || "Extraction failed", "error");
            return;
        }

        const data = await res.json();
        riExtractedItems = data.items || [];

        if (riExtractedItems.length === 0) {
            showToast(`No restricted items found in ${file.name}`, "info");
            return;
        }

        showToast(`Found ${riExtractedItems.length} items in ${file.name}`, "success");
        openRiReview();
    } catch (e) {
        progress.classList.remove("active");
        showToast("Network error during extraction", "error");
    }
}

/* ── Review Modal ── */
function openRiReview() {
    const list = document.getElementById("riReviewList");
    const count = document.getElementById("riReviewCount");
    count.textContent = `${riExtractedItems.length} items found`;

    let html = "";
    for (let i = 0; i < riExtractedItems.length; i++) {
        const item = riExtractedItems[i];
        html += `
        <div class="ri-review-item" id="riReview-${i}">
            <input type="checkbox" checked onchange="toggleRiReviewItem(${i}, this.checked)">
            <div class="ri-review-item-body">
                <div class="ri-review-item-title">${escapeHtml(item.title)}</div>
                ${item.description ? `<div class="ri-review-item-desc">${escapeHtml(item.description)}</div>` : ''}
                <div class="ri-review-item-cat">
                    <select onchange="riExtractedItems[${i}].category=this.value">
                        <option value="not_provided" ${item.category === 'not_provided' ? 'selected' : ''}>Not Provided</option>
                        <option value="illegal" ${item.category === 'illegal' ? 'selected' : ''}>Illegal</option>
                        <option value="scam_fraud" ${item.category === 'scam_fraud' ? 'selected' : ''}>Scam / Fraud</option>
                    </select>
                </div>
            </div>
        </div>`;
    }
    list.innerHTML = html;
    document.getElementById("riReviewOverlay").classList.add("open");
}

function closeRiReview() {
    document.getElementById("riReviewOverlay").classList.remove("open");
}

function toggleRiReviewItem(idx, checked) {
    const el = document.getElementById(`riReview-${idx}`);
    el.classList.toggle("deselected", !checked);
    riExtractedItems[idx]._selected = checked;
}

function toggleAllRiReview() {
    const checkboxes = document.querySelectorAll("#riReviewList input[type='checkbox']");
    const allChecked = [...checkboxes].every(cb => cb.checked);
    checkboxes.forEach((cb, i) => {
        cb.checked = !allChecked;
        toggleRiReviewItem(i, !allChecked);
    });
}

async function addSelectedRiItems() {
    const toAdd = riExtractedItems.filter((item, i) => item._selected !== false);

    if (toAdd.length === 0) { showToast("No items selected", "info"); return; }

    let added = 0;
    let failed = 0;

    for (const item of toAdd) {
        try {
            const res = await fetch(`${API_BASE}/restricted-items`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: item.title,
                    category: item.category,
                    description: item.description || "",
                    source_document: item.source_document || null,
                    added_by: "file_import",
                }),
            });
            if (res.ok) added++;
            else failed++;
        } catch {
            failed++;
        }
    }

    closeRiReview();
    loadRestrictedItems();

    if (failed === 0) showToast(`Added ${added} items to restricted list`, "success");
    else showToast(`Added ${added} items, ${failed} failed`, "info");
}

/* =============================================================
   INITIALIZATION
   ============================================================= */
document.addEventListener("DOMContentLoaded", () => {
    // Initialize all modules
    initUpload();
    initChat();
    initVoiceInput();
    initAutofill();
    initDictionary();
    initSearch();
    initRestrictedItems();

    // Startup checks
    checkHealth();
    loadLLMProvider();
    renderHistoryList();
    renderActiveChat();
    restoreActivePanel();
});

