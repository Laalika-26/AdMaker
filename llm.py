import os
import json
import re

class ContextualTagger:
    def __init__(self, provider="fallback", hf_token=None, local_model_id="Qwen/Qwen2.5-0.5B-Instruct", gemini_api_key=None):
        """
        Initializes the ContextualTagger.
        provider: 'hf_api', 'local', 'gemini', or 'fallback'
        hf_token: Optional token for Hugging Face Inference API
        local_model_id: The local model repository ID to load if using local provider
        gemini_api_key: Optional Google AI Studio (Gemini) API Key
        """
        self.provider = provider
        self.hf_token = hf_token or os.environ.get("HF_TOKEN")
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        self.local_model_id = local_model_id
        self.local_pipeline = None
        self.gemini_model = None

        if self.provider == "gemini":
            if not self.gemini_api_key:
                print("[LLM] Warning: Gemini provider selected but no GEMINI_API_KEY found. Falling back to heuristic tagger.")
                self.provider = "fallback"
            else:
                print("[LLM] Initializing Google Gemini contextual tagger (REST mode)...")

        # If user chose hf_api but has no token, warn and adjust
        if self.provider == "hf_api" and not self.hf_token:
            print("[LLM] Warning: 'hf_api' selected but no HF token provided. Falling back to heuristic tagger.")
            self.provider = "fallback"

        if self.provider == "local":
            print(f"[LLM] Loading local LLM pipeline with model '{self.local_model_id}'...")
            try:
                import torch
                from transformers import pipeline
                device = 0 if torch.cuda.is_available() else -1
                # Load text-generation pipeline
                self.local_pipeline = pipeline(
                    "text-generation",
                    model=self.local_model_id,
                    torch_dtype=torch.float16 if device >= 0 else torch.float32,
                    device_map="auto" if device >= 0 else None,
                    device=device if device < 0 else None
                )
                print("[LLM] Local pipeline loaded successfully.")
            except Exception as e:
                print(f"[LLM] Error loading local pipeline: {e}. Falling back to heuristic tagger.")
                self.provider = "fallback"

    def tag_context(self, context_text):
        """
        Classifies the conversation category, tone, and suggests ads based on the context.
        Returns a dict: {
            "category": str,
            "tone": str,
            "ad_suggestions": list of str
        }
        """
        if self.provider == "gemini" and self.gemini_model:
            return self._tag_via_gemini(context_text)
        elif self.provider == "hf_api" and self.hf_token:
            return self._tag_via_hf_api(context_text)
        elif self.provider == "local" and self.local_pipeline:
            return self._tag_via_local_pipeline(context_text)
        else:
            return self._tag_via_heuristics(context_text)

    def _get_prompt(self, context_text):
        return (
            "Analyze the following 30-second conversational transcript snippet. "
            "Identify the main category/topic of discussion (e.g. Technology, Cooking, Automotive, Finance, Travel, Health, General) "
            "and the tone of the conversation (e.g. Informative, Casual, Professional, Enthusiastic).\n"
            "Based on the content, suggest 2-3 specific, targeted products or services that would make natural ads to insert immediately after this conversation.\n\n"
            f"Transcript Snippet:\n\"\"{context_text}\"\"\n\n"
            "You MUST respond ONLY with a valid JSON object in the following format (no conversational filler, no markdown block wrappers):\n"
            "{\n"
            '  "category": "Category Name",\n'
            '  "tone": "Tone Description",\n'
            '  "ad_suggestions": ["Ad Suggestion 1", "Ad Suggestion 2"]\n'
            "}"
        )

    def _tag_via_gemini(self, context_text):
        """Queries Google Gemini API for structured contextual tagging."""
        print("[LLM] Querying Google Gemini API for tagging (Direct REST)...")
        try:
            import requests
            
            # We use the stable gemini-2.5-flash-lite model on the v1beta endpoint
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={self.gemini_api_key}"
            
            # structured output schema
            payload = {
                "contents": [
                    {
                        "parts": [{"text": self._get_prompt(context_text)}]
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": {
                        "type": "OBJECT",
                        "properties": {
                            "category": {"type": "STRING"},
                            "tone": {"type": "STRING"},
                            "ad_suggestions": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"}
                            }
                        },
                        "required": ["category", "tone", "ad_suggestions"]
                    },
                    "temperature": 0.1
                }
            }
            
            headers = {"Content-Type": "application/json"}
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code != 200:
                raise RuntimeError(f"Google API returned status code {response.status_code}: {response.text}")
                
            response_data = response.json()
            raw_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(raw_text)
            
            return {
                "category": data.get("category", "General"),
                "tone": data.get("tone", "Informative"),
                "ad_suggestions": data.get("ad_suggestions", ["General Ad"])
            }
        except Exception as e:
            print(f"[LLM] Gemini tagging query failed: {e}. Falling back to heuristics.")
            return self._tag_via_heuristics(context_text)

    def _tag_via_hf_api(self, context_text):
        """Calls Hugging Face's serverless Inference API."""
        print("[LLM] Querying Hugging Face Inference API...")
        try:
            from huggingface_hub import InferenceClient
            client = InferenceClient(model="Qwen/Qwen2.5-7B-Instruct", token=self.hf_token)
            
            prompt = self._get_prompt(context_text)
            messages = [{"role": "user", "content": prompt}]
            
            response = client.chat_completion(
                messages=messages,
                max_tokens=256,
                temperature=0.1
            )
            raw_content = response.choices[0].message.content
            return self._parse_json_response(raw_content)
        except Exception as e:
            print(f"[LLM] HF API query failed: {e}. Falling back to heuristics.")
            return self._tag_via_heuristics(context_text)

    def _tag_via_local_pipeline(self, context_text):
        """Invokes the locally loaded Hugging Face pipeline."""
        print("[LLM] Running local model inference...")
        try:
            prompt = self._get_prompt(context_text)
            
            # Format using a simple instruction template
            formatted_prompt = f"<|im_start|>system\nYou are a precise metadata classifier. You output only raw JSON.<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
            
            outputs = self.local_pipeline(
                formatted_prompt,
                max_new_tokens=256,
                temperature=0.1,
                do_sample=False,
                return_full_text=False
            )
            raw_content = outputs[0]["generated_text"]
            return self._parse_json_response(raw_content)
        except Exception as e:
            print(f"[LLM] Local model inference failed: {e}. Falling back to heuristics.")
            return self._tag_via_heuristics(context_text)

    def _tag_via_heuristics(self, context_text):
        """
        Fast, zero-dependency keyword classifier.
        Provides a fallback if no LLM service is configured.
        """
        text_lower = context_text.lower()
        
        # Define categories and keyword weights
        categories = {
            "Technology": {
                "keywords": ["kubernetes", "serverless", "database", "scalability", "cloud", "postgresql", "python", "developer", "api", "code", "architecture", "microservices", "vms", "containers", "json", "jason", "javascript", "data", "format", "notation"],
                "ads": [
                    "CloudVibe Hosting - High Performance Serverless Deployments",
                    "QueryCraft DB - AI-powered Database Indexing & Scale",
                    "PyShield - Automated Security Auditing for Python Apps"
                ],
                "tone": "Informative & Professional"
            },
            "Cooking / Culinary": {
                "keywords": ["bake", "baking", "sourdough", "fermentation", "flour", "dough", "oven", "starter", "gluten", "recipe", "yeast", "mixing", "chef", "cook"],
                "ads": [
                    "RiseMaster Dutch Oven - Retain Heat for the Perfect Sourdough Crust",
                    "Baker's Choice Premium Organic Artisan Flour",
                    "DoughPro Stand Mixer - 10-Speed Heavy Duty Dough Hook"
                ],
                "tone": "Warm & Instructional"
            },
            "Automotive": {
                "keywords": ["cylinder", "valves", "gasket", "torque", "motor", "rpm", "wrench", "car", "engine", "restoration", "intake", "exhaust", "springs", "straightedge", "feeler"],
                "ads": [
                    "TorqueArmor Precision Socket & Click-Torque Wrench Set",
                    "GasketSeal Pro - High-Temperature Engine Sealant",
                    "RevMax Performance Valve Springs & Engine Components"
                ],
                "tone": "Hands-on & Explanatory"
            },
            "Finance": {
                "keywords": ["money", "stocks", "investment", "portfolio", "crypto", "bitcoin", "savings", "dividends", "tax", "trade", "market"],
                "ads": [
                    "WealthPath Capital - Intelligent Robo-Advisory Portfolio",
                    "CoinVault Ledger - Offline Hardware Security for Crypto Assets"
                ],
                "tone": "Analytical & Advisory"
            }
        }
        
        # Calculate scores
        scores = {}
        for cat, data in categories.items():
            score = 0
            for kw in data["keywords"]:
                # Count occurrences of the keyword
                score += text_lower.count(kw)
            scores[cat] = score
            
        # Find highest-scoring category
        best_cat = "General / Lifestyle"
        best_ads = [
            "Everyday Essentials - Quality Goods for Your Daily Routine",
            "Universal Stream - Premium Entertainment for the Whole Family"
        ]
        best_tone = "Conversational & Casual"
        
        max_score = 0
        for cat, score in scores.items():
            if score > max_score:
                max_score = score
                best_cat = cat
                best_ads = categories[cat]["ads"]
                best_tone = categories[cat]["tone"]
                
        return {
            "category": best_cat,
            "tone": best_tone,
            "ad_suggestions": best_ads
        }

    def _parse_json_response(self, text):
        """Cleans and extracts JSON content from model output."""
        try:
            # Strip markdown block wrappers if present (e.g. ```json ... ```)
            clean_text = text.strip()
            if clean_text.startswith("```"):
                # Find the first newline and remove up to that, then strip the ending ```
                clean_text = re.sub(r'^```(?:json)?\n', '', clean_text)
                clean_text = re.sub(r'\n```$', '', clean_text)
                clean_text = clean_text.strip()
                
            # If there's leading/trailing filler text outside of curl brackets, extract the JSON block
            match = re.search(r'\{.*\}', clean_text, re.DOTALL)
            if match:
                clean_text = match.group(0)
                
            data = json.loads(clean_text)
            
            # Ensure correct keys are present
            return {
                "category": data.get("category", "General"),
                "tone": data.get("tone", "Informative"),
                "ad_suggestions": data.get("ad_suggestions", ["General Product Ad"])
            }
        except Exception as parse_err:
            print(f"[LLM] JSON Parsing error: {parse_err}. Raw output was:\n{text}")
            # Fall back to heuristic classification rather than crashing
            return self._tag_via_heuristics(text)
