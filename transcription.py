import os
import time
import random
import torch

class AudioTranscriber:
    def __init__(self, model_size="tiny", device="cpu", compute_type="default", use_mock=False, provider="whisper", api_key=None):
        """
        Initializes the transcription service.
        model_size: e.g., 'tiny', 'base', 'small', 'medium', 'large-v3'
        device: 'cuda' or 'cpu' (or auto-detects if 'auto')
        compute_type: CTranslate2 quantization precision (e.g., 'float16', 'int8', 'float32')
        use_mock: If True, uses mock transcription for quick testing and zero-dependency environments.
        provider: 'whisper' or 'gemini'
        api_key: Optional Google AI Studio (Gemini) API Key
        """
        self.use_mock = use_mock
        self.provider = provider
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = None
        
        if self.use_mock:
            print("[Transcriber] Running in MOCK mode (No Whisper or Gemini model will be downloaded or loaded).")
            return

        if self.provider == "gemini":
            if not self.api_key:
                print("[Transcriber] Warning: Gemini provider selected but no GEMINI_API_KEY found. Falling back to Whisper.")
                self.provider = "whisper"
            else:
                print("[Transcriber] Initializing Google Gemini audio transcriber (REST mode)...")
                return

        # Auto-detect device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
            
        # Determine compute type based on device
        if compute_type == "default":
            compute_type = "float16" if device == "cuda" else "int8"
            
        print(f"[Transcriber] Initializing faster-whisper model '{model_size}' on '{device}' ({compute_type})...")
        
        try:
            from faster_whisper import WhisperModel
            # Load the CTranslate2 model
            self.model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type
            )
            print("[Transcriber] Whisper model loaded successfully.")
        except Exception as e:
            print(f"[Transcriber] Failed to load Whisper model: {e}")
            print("[Transcriber] Falling back to MOCK transcription mode.")
            self.use_mock = True

    def transcribe_chunks(self, chunks):
        """
        Transcribes each audio chunk and maps the timestamps back to the global video timeline.
        
        Returns:
            List of dicts: [
                {"start": float, "end": float, "text": str},
                ...
            ]
        """
        if self.use_mock:
            return self._generate_mock_transcripts(chunks)
            
        if self.provider == "gemini":
            return self._transcribe_chunks_via_gemini(chunks)
            
        all_segments = []
        print(f"[Transcriber] Transcribing {len(chunks)} audio chunks...")
        
        for idx, chunk in enumerate(chunks):
            chunk_path = chunk["path"]
            chunk_start = chunk["start"]
            
            print(f"  [Chunk {idx+1}/{len(chunks)}] Transcribing: {os.path.basename(chunk_path)}")
            
            try:
                # Transcribe the single chunk
                segments, info = self.model.transcribe(chunk_path, beam_size=5)
                
                # Iterate and stitch segments using global offset
                for segment in segments:
                    global_start = chunk_start + segment.start
                    global_end = chunk_start + segment.end
                    all_segments.append({
                        "start": global_start,
                        "end": global_end,
                        "text": segment.text.strip()
                    })
            except Exception as e:
                print(f"  [Chunk {idx+1}/{len(chunks)}] Transcription failed: {e}")
                # Inject a brief placeholder segment to avoid breaking downstream analysis
                all_segments.append({
                    "start": chunk_start,
                    "end": chunk["end"],
                    "text": "[Transcription error occurred for this chunk]"
                })
                
        return all_segments

    def _transcribe_chunks_via_gemini(self, chunks):
        import json
        import base64
        import requests
        
        print(f"[Transcriber] Transcribing {len(chunks)} audio chunks via Google Gemini API (Direct REST)...")
        all_segments = []
        
        # We use the stable gemini-2.5-flash-lite model on the v1beta endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={self.api_key}"
        
        prompt = (
            "Transcribe the following audio chunk. Return a JSON array of segments, "
            "where each segment represents a sentence or natural clause. "
            "Each segment MUST have these keys:\n"
            "  - 'start': start time of the segment in seconds (float) relative to the audio start (0.0)\n"
            "  - 'end': end time of the segment in seconds (float) relative to the audio start (0.0)\n"
            "  - 'text': transcribed text of the segment (string)\n"
            "Be precise, accurate, and spell technical terms and acronyms (like JSON, JavaScript) correctly."
        )
        
        for idx, chunk in enumerate(chunks):
            chunk_path = chunk["path"]
            chunk_start = chunk["start"]
            
            print(f"  [Chunk {idx+1}/{len(chunks)}] Transcribing via Gemini (REST): {os.path.basename(chunk_path)}")
            
            try:
                # Read WAV file and convert to base64
                with open(chunk_path, "rb") as f:
                    audio_data = base64.b64encode(f.read()).decode("utf-8")
                
                # Construct raw REST payload
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {
                                    "text": prompt
                                },
                                {
                                    "inlineData": {
                                        "mimeType": "audio/wav",
                                        "data": audio_data
                                    }
                                }
                            ]
                        }
                    ],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "responseSchema": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "start": {"type": "NUMBER"},
                                    "end": {"type": "NUMBER"},
                                    "text": {"type": "STRING"}
                                },
                                "required": ["start", "end", "text"]
                            }
                        },
                        "temperature": 0.0
                    }
                }
                
                headers = {"Content-Type": "application/json"}
                response = requests.post(url, headers=headers, json=payload)
                
                if response.status_code != 200:
                    raise RuntimeError(f"Google API returned status code {response.status_code}: {response.text}")
                    
                response_data = response.json()
                raw_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
                chunk_segments = json.loads(raw_text)
                
                # Stitch segments with global offset
                for segment in chunk_segments:
                    global_start = chunk_start + float(segment.get("start", 0.0))
                    global_end = chunk_start + float(segment.get("end", 0.0))
                    all_segments.append({
                        "start": global_start,
                        "end": global_end,
                        "text": str(segment.get("text", "")).strip()
                    })
                    
            except Exception as e:
                print(f"  [Chunk {idx+1}/{len(chunks)}] Gemini transcription failed: {e}")
                all_segments.append({
                    "start": chunk_start,
                    "end": chunk["end"],
                    "text": "[Transcription error occurred for this chunk]"
                })
                
        return all_segments

    def _generate_mock_transcripts(self, chunks):
        """
        Generates highly realistic conversation-like transcripts for testing.
        Combines technical, culinary, and automotive topic dialogues to allow the LLM phase
        to show its categorization and ad recommendations capabilities.
        """
        print(f"[Transcriber] Generating mock transcripts for {len(chunks)} chunks...")
        
        # Sample conversational streams for different genres
        conversations = [
            # Topic: Tech / Cloud Programming
            [
                "Welcome back everyone. Today we are talking about cloud scalability and serverless functions.",
                "Basically, if you deploy microservices, you don't want to manage physical containers or VMs.",
                "That is why tools like Kubernetes are powerful, but sometimes they introduce too much complexity.",
                "Instead, cloud-native serverless functions let you execute code in response to API requests.",
                "Let's look at the database side. PostgreSQL is fantastic for structured relational schemas.",
                "However, if you have globally distributed, low-latency key-value requirements, DynamoDB excels.",
                "We need to write clean Python wrappers to automatically connect and retry queries.",
                "Let's pause here and discuss the architecture in detail."
            ],
            # Topic: Cooking / Baking
            [
                "Hey guys, today we are baking an authentic French sourdough bread from scratch.",
                "The key is the fermentation process, which depends heavily on the ambient temperature.",
                "You want your starter to be active and bubbling, ideally fed twelve hours prior.",
                "When mixing the flour and water, let it autolyse for about forty-five minutes.",
                "This allows the gluten network to form naturally before we even add the salt.",
                "Now we stretch and fold the dough every half hour for the first two hours.",
                "Make sure you preheat your Dutch oven to four-hundred-and-fifty degrees Fahrenheit.",
                "Let's take a quick break before we score the loaf and put it in the oven."
            ],
            # Topic: Automotive / Car Restoration
            [
                "Alright, in this episode we are restoring the cylinder head on this classic 1969 inline-six motor.",
                "First, we need to scrape off the old gasket residue without scratching the aluminum block.",
                "I am using a plastic scraper and some solvent to soften the carbon buildup.",
                "Then we will check the surface flatness using a precision straightedge and feeler gauges.",
                "If it's warped by more than three-thousandths of an inch, we'll have to send it to the machine shop.",
                "I also ordered new intake valves and double valve springs to handle the higher RPMs.",
                "Let's take a moment here to clean up our workspace and prepare the torque wrench."
            ]
        ]
        
        # Choose a random starting topic
        topic_idx = random.randint(0, len(conversations) - 1)
        conversation_flow = conversations[topic_idx]
        flow_idx = 0
        
        all_segments = []
        
        for chunk_idx, chunk in enumerate(chunks):
            chunk_start = chunk["start"]
            chunk_end = chunk["end"]
            chunk_duration = chunk_end - chunk_start
            
            # Subdivide the chunk into 3-4 segments of 5-8 seconds each
            # If not the first chunk, start with a 2.0s gap to simulate silence between chunks
            current_time = chunk_start
            if chunk_idx > 0:
                current_time += 2.0
            
            while current_time < chunk_end - 2.0:
                seg_duration = random.uniform(5.0, 8.0)
                seg_end = min(current_time + seg_duration, chunk_end)
                
                # Fetch next line of dialogue
                line = conversation_flow[flow_idx % len(conversation_flow)]
                flow_idx += 1
                
                # Sometimes add a trailing sentence ender
                all_segments.append({
                    "start": current_time,
                    "end": seg_end - random.uniform(0.3, 0.8), # leave a small silence gap between segments
                    "text": line
                })
                
                current_time = seg_end
                
        # Simulate processing time
        time.sleep(0.5)
        return all_segments
