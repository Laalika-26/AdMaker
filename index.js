// --------------------------------------------------------
// Drag and Drop Uploader Elements & Events
// --------------------------------------------------------
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const uploadProgressState = document.getElementById("upload-progress-state");
const uploadSuccessState = document.getElementById("upload-success-state");
const dropZoneContent = dropZone.querySelector(".drop-zone-content");

const uploadFilename = document.getElementById("upload-filename");
const uploadFilesize = document.getElementById("upload-filesize");
const uploadProgressFill = document.getElementById("upload-progress-fill");
const uploadPercent = document.getElementById("upload-percent");

const successFilename = document.getElementById("success-filename");
const changeFileBtn = document.getElementById("change-file-btn");
const videoPathHidden = document.getElementById("video-path-hidden");
const submitBtn = document.getElementById("submit-btn");

// Prevent default drag behaviors
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
    document.body.addEventListener(eventName, preventDefaults, false);
});

// Highlight drop zone when item is dragged over it
['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, highlight, false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, unhighlight, false);
});

// Handle dropped files
dropZone.addEventListener('drop', handleDrop, false);

// Handle clicked zone (open browser dialog)
dropZone.addEventListener('click', () => {
    // Only open dialog if we are not currently uploading or successfully uploaded
    if (uploadProgressState.classList.contains("hidden") && uploadSuccessState.classList.contains("hidden")) {
        fileInput.click();
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
    }
});

changeFileBtn.addEventListener('click', (e) => {
    e.stopPropagation(); // prevent triggering dropzone click
    resetUploader();
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

function highlight() {
    if (uploadProgressState.classList.contains("hidden") && uploadSuccessState.classList.contains("hidden")) {
        dropZone.classList.add('active');
    }
}

function unhighlight() {
    dropZone.classList.remove('active');
}

function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0 && uploadProgressState.classList.contains("hidden") && uploadSuccessState.classList.contains("hidden")) {
        handleFileUpload(files[0]);
    }
}

// --------------------------------------------------------
// File Binary Upload Handler (Memory Safe & Chunked Progress)
// --------------------------------------------------------
function handleFileUpload(file) {
    // Hide initial message
    dropZoneContent.classList.add("hidden");
    // Show progress block
    uploadProgressState.classList.remove("hidden");
    
    // Set UI file details
    uploadFilename.textContent = file.name;
    const sizeInMB = (file.size / (1024 * 1024)).toFixed(1);
    uploadFilesize.textContent = `${sizeInMB} MB`;
    
    // Disable submit button during upload
    submitBtn.disabled = true;
    submitBtn.textContent = "Uploading File...";

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");
    
    // Set custom headers to communicate metadata
    xhr.setRequestHeader("X-Filename", file.name);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    
    // Track upload progress
    xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
            const percent = Math.round((e.loaded / e.total) * 100);
            uploadProgressFill.style.width = `${percent}%`;
            uploadPercent.textContent = `${percent}% Uploaded`;
        }
    };
    
    xhr.onload = () => {
        if (xhr.status === 200) {
            const response = JSON.parse(xhr.responseText);
            
            // Set hidden path value
            videoPathHidden.value = response.video_path;
            
            // Switch to success state
            uploadProgressState.classList.add("hidden");
            uploadSuccessState.classList.remove("hidden");
            successFilename.textContent = file.name;
            
            // Enable pipeline processing trigger button
            submitBtn.disabled = false;
            submitBtn.textContent = "Start Video Analysis";
            appendLogLine(`[v] Video file '${file.name}' uploaded successfully to server workspace.`, "success");
        } else {
            handleUploadError(`Server responded with status code ${xhr.status}`);
        }
    };
    
    xhr.onerror = () => {
        handleUploadError("A network/CORS error occurred. If you have not restarted your backend web server (python web_server.py) since the update, please restart it now to load the new file upload endpoint.");
    };
    
    // Send the raw file binary buffer
    xhr.send(file);
}

function handleUploadError(errMsg) {
    appendLogLine(`[ERROR] File upload failed: ${errMsg}`, "error");
    resetUploader();
}

function resetUploader() {
    fileInput.value = "";
    videoPathHidden.value = "";
    
    uploadProgressFill.style.width = "0%";
    uploadPercent.textContent = "0% Uploaded";
    
    uploadProgressState.classList.add("hidden");
    uploadSuccessState.classList.add("hidden");
    dropZoneContent.classList.remove("hidden");
    
    submitBtn.disabled = true;
    submitBtn.textContent = "Upload a Video to Begin";
}

// --------------------------------------------------------
// Parameter Bindings & Range Display
// --------------------------------------------------------
const minGapInput = document.getElementById("min-gap");
const minGapVal = document.getElementById("min-gap-val");

minGapInput.addEventListener("input", (e) => {
    minGapVal.textContent = `${e.target.value}s`;
});

// --------------------------------------------------------
// Terminal Console Logging Utilities
// --------------------------------------------------------
const terminalOutput = document.getElementById("terminal-output");
const resultsPanel = document.getElementById("results-panel");
const resultsTableBody = document.getElementById("results-table-body");
const breaksCount = document.getElementById("breaks-count");

function appendLogLine(text, type = "normal") {
    // Keep console output scroll clean
    const oldPrompt = document.querySelector(".console-line.prompt");
    if (oldPrompt) {
        oldPrompt.remove();
    }

    const line = document.createElement("div");
    line.className = "console-line";
    
    // Style lines automatically based on indicators
    if (text.includes("[ERROR]") || text.toLowerCase().includes("failed")) {
        line.classList.add("error");
    } else if (text.includes("[v]") || text.includes("complete") || text.includes("successful")) {
        line.classList.add("success");
    } else if (text.includes(">>>") || text.includes("---")) {
        line.classList.add("info");
    } else if (type === "system") {
        line.classList.add("system");
    }

    line.textContent = text;
    terminalOutput.appendChild(line);

    // Append mock blinking prompt
    const prompt = document.createElement("div");
    prompt.className = "console-line prompt";
    prompt.innerHTML = `guest@admarker:~$ <span class="typing-placeholder"></span>`;
    terminalOutput.appendChild(prompt);

    // Scroll to bottom
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

// --------------------------------------------------------
// Pipeline Progress Stages Dashboard Controller
// --------------------------------------------------------
const stageCards = {
    extract: document.getElementById("stage-extract"),
    vad: document.getElementById("stage-vad"),
    transcribe: document.getElementById("stage-transcribe"),
    analyze: document.getElementById("stage-analyze"),
    tag: document.getElementById("stage-tag")
};

function updateStage(stageKey, status) {
    const card = stageCards[stageKey];
    if (!card) return;
    
    card.className = "stage-card"; // Reset all state class modifiers
    const iconEl = card.querySelector(".stage-icon");
    
    if (status === "running") {
        card.classList.add("running");
        iconEl.textContent = "⚡";
    } else if (status === "success") {
        card.classList.add("success");
        iconEl.textContent = "✓";
    } else if (status === "error") {
        card.classList.add("error");
        iconEl.textContent = "✗";
    } else {
        iconEl.textContent = "⏳";
    }
}

function resetAllStages() {
    Object.keys(stageCards).forEach(key => updateStage(key, "pending"));
}

// Stream Parser driving the progress dashboard in real-time
function parseStageFromLog(logText) {
    if (logText.includes("Extracting audio stream")) {
        updateStage("extract", "running");
    } else if (logText.includes("extracted successfully") || logText.includes("extraction via moviepy completed") || logText.includes("Audio extraction via FFmpeg")) {
        updateStage("extract", "success");
    }
    
    if (logText.includes("Scanning voice activity") || logText.includes("VAD chunking") || logText.includes("Splitting")) {
        updateStage("vad", "running");
    } else if (logText.includes("VAD splitting complete") || logText.includes("Completed splitting")) {
        updateStage("vad", "success");
    }
    
    if (logText.includes("transcribing chunks") || logText.includes("Transcribing")) {
        updateStage("transcribe", "running");
    } else if (logText.includes("Transcribed") || logText.includes("transcription complete") || logText.includes("Generating mock transcripts")) {
        updateStage("transcribe", "success");
    }
    
    if (logText.includes("Searching linguistic breaks") || logText.includes("conversational boundaries") || logText.includes("BoundaryAnalyzer")) {
        updateStage("analyze", "running");
    } else if (logText.includes("optimal ad breaks") || logText.includes("optimal ad break positions") || logText.includes("Found") && logText.includes("ad breaks")) {
        updateStage("analyze", "success");
    }
    
    if (logText.includes("LLM classification") || logText.includes("tagging") || logText.includes("Querying") || logText.includes("Running contextual LLM")) {
        updateStage("tag", "running");
    } else if (logText.includes("tagging and classification complete")) {
        updateStage("tag", "success");
    }
}

// --------------------------------------------------------
// Pipeline Processing Form Trigger
// --------------------------------------------------------
document.getElementById("pipeline-form").addEventListener("submit", async (e) => {
    e.preventDefault();

    const videoPath = videoPathHidden.value;
    if (!videoPath) {
        appendLogLine("[ERROR] Cannot run analysis. No uploaded file path found.", "error");
        return;
    }

    // Lock controls
    submitBtn.disabled = true;
    submitBtn.textContent = "Analyzing Video...";
    resultsPanel.classList.add("hidden");
    resetAllStages();
    
    // Clear logs
    terminalOutput.innerHTML = "";
    appendLogLine("Establishing server node connection...", "system");
    appendLogLine("Launching python backend process...", "system");

    const params = {
        video_path: videoPath,
        trans_provider: document.getElementById("trans-provider").value,
        llm_provider: document.getElementById("llm-provider").value,
        min_gap: parseFloat(minGapInput.value),
        mock_whisper: document.getElementById("mock-whisper").checked
    };

    try {
        const response = await fetch("/api/process", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(params)
        });

        if (!response.ok) {
            throw new Error(`HTTP Error Status ${response.status}`);
        }

        // Establish Stream Reader for SSE
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        let finished = false;
        while (true) {
            const { done, value } = await reader.read();
            if (done || finished) break;

            buffer += decoder.decode(value, { stream: true });
            
            const lines = buffer.split("\n\n");
            buffer = lines.pop(); // Hold onto partial line chunk

            for (const line of lines) {
                if (line.trim().startsWith("data: ")) {
                    const dataStr = line.replace(/^data:\s*/, "");
                    const data = JSON.parse(dataStr);
                    
                    if (data.log) {
                        appendLogLine(data.log);
                        parseStageFromLog(data.log);
                    }
                    
                    // Use hasOwnProperty check — data.results can be an empty array []
                    // which is falsy-ish in boolean but still valid results payload
                    if (Object.prototype.hasOwnProperty.call(data, 'results')) {
                        renderAdBreaks(data.results);
                        finished = true;
                        // Silently cancel the stream — ignore AbortError
                        try { reader.cancel(); } catch (_) {}
                        break;
                    }
                }
            }
        }
        
        appendLogLine("[v] Pipeline analytics execution completed successfully.", "success");


    } catch (err) {
        appendLogLine(`[CRITICAL ERROR] Pipeline execution terminated: ${err.message}`, "error");
        
        // Update any running stages to error state
        Object.keys(stageCards).forEach(key => {
            const card = stageCards[key];
            if (card.classList.contains("running") || card.classList.contains("pending")) {
                updateStage(key, "error");
            }
        });
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Start Video Analysis";
    }
});

// Populate ad marker recommendation table
function renderAdBreaks(results) {
    resultsTableBody.innerHTML = "";
    
    if (!results || results.length === 0) {
        breaksCount.textContent = "0 Breaks Found";
        resultsTableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 2rem;">No logical conversational breaks detected. Try lowering the gap threshold slider.</td></tr>`;
        resultsPanel.classList.remove("hidden");
        resultsPanel.scrollIntoView({ behavior: 'smooth' });
        return;
    }

    breaksCount.textContent = `${results.length} Breaks Found`;

    results.forEach(item => {
        const row = document.createElement("tr");

        const adsListHtml = item.ad_suggestions.map(ad => `<li>${ad}</li>`).join("");
        
        row.innerHTML = `
            <td><span class="marker-badge">AD-${String(item.break_id).padStart(2, '0')}</span></td>
            <td><span class="timestamp-lbl">${item.timestamp_str}</span></td>
            <td><span class="gap-lbl">${item.gap_duration.toFixed(2)}s</span></td>
            <td><div style="max-width: 380px; color: #F3F4F6; font-size: 0.8rem;">"${item.preceding_context}"</div></td>
            <td>
                <span class="category-lbl">${item.category}</span>
                <span class="tone-lbl">Tone: ${item.tone}</span>
            </td>
            <td>
                <ul class="ads-list">
                    ${adsListHtml}
                </ul>
            </td>
        `;
        resultsTableBody.appendChild(row);
    });

    resultsPanel.classList.remove("hidden");
    resultsPanel.scrollIntoView({ behavior: 'smooth' });
}
