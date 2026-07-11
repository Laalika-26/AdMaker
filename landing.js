/* ==========================================================================
   AdMarker Landing Page Script
   Handles the Interactive Demo Simulator showing pipeline execution
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    const simBtn = document.getElementById('sim-run-btn');
    const simConsole = document.getElementById('sim-console-output');
    const simResults = document.getElementById('sim-results-panel');
    const simTableBody = document.getElementById('sim-table-body');
    const waveVis = document.getElementById('sim-wave-vis');

    const stageCards = {
        extract: document.getElementById('sim-stage-extract'),
        vad: document.getElementById('sim-stage-vad'),
        transcribe: document.getElementById('sim-stage-transcribe'),
        analyze: document.getElementById('sim-stage-analyze'),
        tag: document.getElementById('sim-stage-tag')
    };

    // Helper: Delay function
    const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

    // Helper: Append log line with typing effect
    async function appendLog(text, type = 'normal', delay = 15) {
        const line = document.createElement('div');
        line.className = `sim-log-line ${type}`;
        simConsole.appendChild(line);
        simConsole.scrollTop = simConsole.scrollHeight;

        // Typewriter effect
        for (let i = 0; i < text.length; i++) {
            line.textContent += text[i];
            await sleep(delay);
        }
        await sleep(100);
    }

    // Helper: Reset simulator UI
    function resetSimulator() {
        simConsole.innerHTML = '';
        simResults.style.display = 'none';
        simTableBody.innerHTML = '';
        waveVis.classList.remove('playing');
        
        Object.keys(stageCards).forEach(key => {
            stageCards[key].className = 'sim-stage-card';
            const icon = stageCards[key].querySelector('.sim-stage-icon');
            if (key === 'extract') icon.textContent = '▲';
            if (key === 'vad') icon.textContent = '∿';
            if (key === 'transcribe') icon.textContent = '✍';
            if (key === 'analyze') icon.textContent = '⚖';
            if (key === 'tag') icon.textContent = '🏷';
        });
    }

    // Main Simulation Pipeline Loop
    async function runSimulation() {
        simBtn.disabled = true;
        simBtn.textContent = "Pipeline Running...";
        resetSimulator();

        // --------------------------------------------------------
        // Stage 1: Audio Extraction
        // --------------------------------------------------------
        stageCards.extract.classList.add('active');
        await appendLog("guest@admarker:~$ python main.py --video sample_clip.mp4 --min-gap 1.5", "system", 10);
        await appendLog(">>> Initiating file checks & workspace loading...", "normal", 10);
        await sleep(400);
        await appendLog(">>> Launching audio extraction node subprocess...", "normal", 10);
        await sleep(500);
        await appendLog("FFmpeg: Splitting audio channel 0 (AAC -> PCM 16kHz WAV)...", "normal", 8);
        await sleep(600);
        await appendLog("[v] Audio track extracted. Output: './uploads/extracted_audio.wav' (1.84 MB, 32.5 seconds)", "success", 8);
        stageCards.extract.classList.remove('active');
        stageCards.extract.classList.add('success');
        stageCards.extract.querySelector('.sim-stage-icon').textContent = '✓';
        await sleep(500);

        // --------------------------------------------------------
        // Stage 2: Voice Activity Detection (VAD)
        // --------------------------------------------------------
        stageCards.vad.classList.add('active');
        waveVis.classList.add('playing');
        await appendLog(">>> Initializing SoundFile RMS silence analyzer...", "normal", 10);
        await sleep(400);
        await appendLog("VAD: Reading audio in 100ms blocks. RMS Energy threshold set at < 0.008...", "normal", 8);
        await sleep(700);
        await appendLog("VAD: Analyzing RMS contours. Splitting speech fragments at silent intervals...", "normal", 8);
        await sleep(800);
        await appendLog("[v] Voice activity detection finished. Split file into 4 main conversational blocks. Memory usage: Flat 2.4MB.", "success", 8);
        waveVis.classList.remove('playing');
        stageCards.vad.classList.remove('active');
        stageCards.vad.classList.add('success');
        stageCards.vad.querySelector('.sim-stage-icon').textContent = '✓';
        await sleep(500);

        // --------------------------------------------------------
        // Stage 3: Speech Transcription
        // --------------------------------------------------------
        stageCards.transcribe.classList.add('active');
        await appendLog(">>> Submitting speech segments to AI transcription backend...", "normal", 10);
        await sleep(500);
        await appendLog("Google Gemini: Invoking REST API request with structured prompt schema...", "normal", 8);
        await sleep(800);
        await appendLog("Google Gemini: Transcribing speech waveforms. Aligning start/end times with global timestamps...", "normal", 8);
        await sleep(1000);
        await appendLog("[v] Transcription successful. Stitched 4 segments together on timeline.", "success", 8);
        stageCards.transcribe.classList.remove('active');
        stageCards.transcribe.classList.add('success');
        stageCards.transcribe.querySelector('.sim-stage-icon').textContent = '✓';
        await sleep(500);

        // --------------------------------------------------------
        // Stage 4: Boundary Scoring Heuristics
        // --------------------------------------------------------
        stageCards.analyze.classList.add('active');
        await appendLog(">>> Scanning timeline silence gaps and evaluating punctuation boundaries...", "normal", 10);
        await sleep(400);
        await appendLog("BoundaryAnalyzer: Found silence gap at 12.4s (Duration: 2.1s). Preceding: '...run LLMs faster.' -> Ends in period (+3.0 score).", "normal", 8);
        await sleep(500);
        await appendLog("BoundaryAnalyzer: Found silence gap at 28.1s (Duration: 1.8s). Preceding: '...block-by-block.' -> Ends in period (+3.0 score).", "normal", 8);
        await sleep(600);
        await appendLog("[v] Boundary evaluation complete. Found 2 high-score ad breaks (Score >= 4.5).", "success", 8);
        stageCards.analyze.classList.remove('active');
        stageCards.analyze.classList.add('success');
        stageCards.analyze.querySelector('.sim-stage-icon').textContent = '✓';
        await sleep(500);

        // --------------------------------------------------------
        // Stage 5: Context Tagging & Product Suggestions
        // --------------------------------------------------------
        stageCards.tag.classList.add('active');
        await appendLog(">>> Running contextual AI tagging on preceding segments...", "normal", 10);
        await sleep(500);
        await appendLog("Google Gemini: Classifying topics, tone and generating native product ad listings...", "normal", 8);
        await sleep(900);
        await appendLog("[v] Structured JSON classification and recommendations loaded.", "success", 8);
        stageCards.tag.classList.remove('active');
        stageCards.tag.classList.add('success');
        stageCards.tag.querySelector('.sim-stage-icon').textContent = '✓';
        await sleep(400);

        // --------------------------------------------------------
        // Results Rendering
        // --------------------------------------------------------
        await appendLog(">>> Writing pipeline output JSON data...", "normal", 10);
        await sleep(300);
        await appendLog("[v] Execution complete! Displaying results in table below.", "success", 10);

        // Render mock data in the table
        const mockResults = [
            {
                id: 'AD-01',
                timestamp: '00:12.40',
                gap: '2.10s',
                context: '...so this new GPU architecture enables parallel calculations in a single clock cycle. That\'s how we run LLMs faster.',
                category: 'Technology',
                tone: 'Professional / Informational',
                suggestions: ['NVIDIA H200 Workstation GPU', 'High-Performance Serverless Cloud Hosting']
            },
            {
                id: 'AD-02',
                timestamp: '00:28.10',
                gap: '1.80s',
                context: '...and if you want to implement this in Python, you can use the SoundFile library. It makes it super easy to read block-by-block.',
                category: 'Software Engineering',
                tone: 'Instructional / Tech-savvy',
                suggestions: ['JetBrains IDE Premium Subscription', 'Advanced Python Audio Programming Course']
            }
        ];

        mockResults.forEach(item => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><span class="sim-badge">${item.id}</span></td>
                <td><strong>${item.timestamp}</strong></td>
                <td>${item.gap}</td>
                <td><div style="max-width: 250px; color: var(--text-secondary); text-overflow: ellipsis; overflow: hidden; white-space: nowrap;" title="${item.context}">"${item.context}"</div></td>
                <td>
                    <span style="color: var(--pink-light); font-weight: 600;">${item.category}</span>
                    <div style="font-size: 0.65rem; color: var(--text-muted);">${item.tone}</div>
                </td>
                <td>
                    <ul class="sim-ad-list" style="font-size: 0.7rem; color: #a855f7;">
                        ${item.suggestions.map(s => `<li>${s}</li>`).join('')}
                    </ul>
                </td>
            `;
            simTableBody.appendChild(row);
        });

        simResults.style.display = 'block';
        simResults.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

        simBtn.disabled = false;
        simBtn.textContent = "Run Demo Again";
    }

    // Attach event listener
    simBtn.addEventListener('click', runSimulation);
});
