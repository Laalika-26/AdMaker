import http.server
import socketserver
import json
import os
import subprocess
import tempfile
import sys
import re

# Render assigns a dynamic port via the PORT environment variable
PORT = int(os.environ.get("PORT", 8000))

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class PipelineHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        """Append CORS headers to every request and response."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Filename')
        self.send_header('Access-Control-Max-Age', '86400')
        super().end_headers()

    def do_OPTIONS(self):
        """Handle CORS pre-flight requests from browsers."""
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        # --------------------------------------------------------
        # Endpoint: Raw Binary File Upload
        # --------------------------------------------------------
        if self.path == "/api/upload":
            filename = self.headers.get('X-Filename', 'uploaded_video.mp4')
            # Clean filename to avoid directory traversal
            filename = os.path.basename(filename)
            
            upload_dir = "./uploads"
            os.makedirs(upload_dir, exist_ok=True)
            upload_path = os.path.join(upload_dir, filename)
            
            content_length = int(self.headers.get('Content-Length', 0))
            print(f"[Server] Uploading file '{filename}' ({content_length} bytes) to '{upload_path}'...")
            
            # Read and write in blocks of 64KB to maintain flat memory usage
            chunk_size = 64 * 1024
            bytes_read = 0
            try:
                with open(upload_path, "wb") as f:
                    while bytes_read < content_length:
                        read_len = min(chunk_size, content_length - bytes_read)
                        chunk = self.rfile.read(read_len)
                        if not chunk:
                            break
                        f.write(chunk)
                        bytes_read += len(chunk)
                        
                print(f"[Server] Upload completed successfully: '{upload_path}'")
                
                # Respond with the local server path of the uploaded file
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"video_path": upload_path}).encode('utf-8'))
                
            except Exception as e:
                print(f"[Server] Error during file upload: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return

        # --------------------------------------------------------
        # Endpoint: Start Pipeline Execution
        # --------------------------------------------------------
        elif self.path == "/api/process":
            # Read post request body
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data.decode('utf-8'))
            
            # Extract parameters
            video_path = params.get("video_path", "")
            min_gap = params.get("min_gap", "1.5")
            trans_provider = params.get("trans_provider", "whisper")
            llm_provider = params.get("llm_provider", "fallback")
            mock_whisper = params.get("mock_whisper", False)
            
            # Read credentials from backend environment variables to keep them hidden from frontend
            gemini_key = os.environ.get("GEMINI_API_KEY", "")
            hf_token = os.environ.get("HF_TOKEN", "")
            
            # Locate python executable
            python_exe = sys.executable
            
            # Temporary JSON file to collect results from main.py
            temp_json_path = os.path.join(tempfile.gettempdir(), f"ad_breaks_{os.getpid()}.json")
            if os.path.exists(temp_json_path):
                os.remove(temp_json_path)
                
            cmd = [
                python_exe, "main.py", video_path,
                "--min-gap", str(min_gap),
                "--transcription-provider", trans_provider,
                "--llm-provider", llm_provider,
                "--json-output", temp_json_path
            ]
            
            if mock_whisper:
                cmd.append("--mock-whisper")
            if gemini_key:
                cmd.extend(["--gemini-api-key", gemini_key])
            if hf_token:
                cmd.extend(["--hf-token", hf_token])
                
            # Send SSE text-event-stream headers
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            
            # Execute main.py in a subprocess with piped stdout
            print(f"[Server] Spawning command: {' '.join(cmd)}")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Regex to clean ANSI coloring codes
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            
            # Stream stdout lines back to JavaScript Event Reader
            for line in process.stdout:
                clean_line = ansi_escape.sub('', line)
                # Ignore duplicate empty lines to keep terminal clean
                if clean_line.strip() == "" and line.strip() == "":
                    continue
                # Stream log line
                log_payload = json.dumps({"log": clean_line})
                self.wfile.write(f"data: {log_payload}\n\n".encode('utf-8'))
                self.wfile.flush()
                
            process.wait()
            
            # Read the JSON markers written by the pipeline
            ad_breaks = []
            if os.path.exists(temp_json_path):
                try:
                    with open(temp_json_path, "r") as f:
                        ad_breaks = json.load(f)
                    os.remove(temp_json_path)
                except Exception as e:
                    print(f"[Server] Error reading output JSON file: {e}")
                    
            # Stream the final result markers array
            results_payload = json.dumps({"results": ad_breaks})
            self.wfile.write(f"data: {results_payload}\n\n".encode('utf-8'))
            self.wfile.flush()
            return
            
        else:
            self.send_error(404, "Endpoint not found")

# Start Multi-threaded Web Server
Handler = PipelineHTTPHandler
socketserver.TCPServer.allow_reuse_address = True
# Using http.server.ThreadingHTTPServer to allow concurrent uploads and status polling
with http.server.ThreadingHTTPServer(("", PORT), Handler) as httpd:
    print(f"Web server running on http://localhost:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
