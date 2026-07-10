import re

class BoundaryAnalyzer:
    def __init__(self, min_gap_seconds=1.5, target_context_seconds=30.0):
        """
        Initializes the BoundaryAnalyzer.
        min_gap_seconds: The minimum silence gap (in seconds) between speech segments to consider as a break.
        target_context_seconds: The duration of the preceding transcript to capture for LLM context.
        """
        self.min_gap_seconds = min_gap_seconds
        self.target_context_seconds = target_context_seconds

    def find_ad_breaks(self, segments, top_n=3):
        """
        Analyzes the list of transcription segments and finds natural conversational breaks.
        Calculates a score for each gap based on:
        - Gap length: longer gaps are higher scoring (up to a reasonable limit).
        - Sentence boundary: if the segment before the gap ends with a period, question mark, or exclamation point.
        
        Returns:
            List of dicts representing the top_n ad breaks: [
                {
                    "break_id": int,
                    "timestamp": float,       # Global timeline seconds
                    "timestamp_str": str,   # HH:MM:SS format
                    "gap_duration": float,
                    "preceding_context": str, # Stitched text from preceding 30 seconds
                    "score": float
                },
                ...
            ]
        """
        if len(segments) < 2:
            print("[Analyzer] Not enough transcription segments to find gaps.")
            return []

        candidates = []
        
        for i in range(len(segments) - 1):
            current_seg = segments[i]
            next_seg = segments[i+1]
            
            # Gap is the silence between the end of current segment and start of next segment
            gap_duration = next_seg["start"] - current_seg["end"]
            
            if gap_duration >= self.min_gap_seconds:
                # Score calculation
                score = gap_duration
                
                # Check for linguistic punctuation cues at the end of the current segment
                text_clean = current_seg["text"].strip()
                ends_sentence = text_clean and text_clean[-1] in ('.', '?', '!')
                
                if ends_sentence:
                    score += 3.0  # Heavy weight for completed sentences
                else:
                    # Check if it ends with a comma (moderate pause)
                    ends_clause = text_clean and text_clean[-1] in (',', ';', ':')
                    if ends_clause:
                        score += 1.0
                
                # Calculate the exact timestamp (midpoint of the silence gap)
                break_timestamp = current_seg["end"] + (gap_duration / 2.0)
                
                candidates.append({
                    "segment_idx": i,
                    "timestamp": break_timestamp,
                    "gap_duration": gap_duration,
                    "ends_sentence": ends_sentence,
                    "score": score
                })
                
        # Sort candidates by score in descending order
        candidates.sort(key=lambda x: x["score"], reverse=True)
        top_candidates = candidates[:top_n]
        
        # Sort top candidates chronologically for output consistency
        top_candidates.sort(key=lambda x: x["timestamp"])
        
        results = []
        for idx, cand in enumerate(top_candidates):
            seg_idx = cand["segment_idx"]
            break_time = cand["timestamp"]
            
            # Extract context (preceding 30 seconds of text)
            context_text = self._extract_preceding_context(segments, seg_idx, break_time)
            
            results.append({
                "break_id": idx + 1,
                "timestamp": break_time,
                "timestamp_str": self._format_timestamp(break_time),
                "gap_duration": cand["gap_duration"],
                "preceding_context": context_text,
                "score": cand["score"]
            })
            
        print(f"[Analyzer] Found {len(results)} optimal ad break positions.")
        return results

    def _extract_preceding_context(self, segments, ending_segment_idx, break_time):
        """
        Gathers segments backwards starting from ending_segment_idx until the 
        cumulative time matches target_context_seconds (e.g., 30s).
        Returns the stitched clean text transcript.
        """
        context_segments = []
        cumulative_time = 0.0
        
        # Start scanning backwards from the segment immediately before the break
        idx = ending_segment_idx
        while idx >= 0:
            seg = segments[idx]
            seg_duration = seg["end"] - seg["start"]
            
            # Add segment
            context_segments.append(seg)
            cumulative_time += seg_duration
            
            # Break if we have accumulated enough text context duration
            # or if the first segment is more than 35 seconds prior to the break time
            if cumulative_time >= self.target_context_seconds or (break_time - seg["start"]) >= (self.target_context_seconds + 5.0):
                break
                
            idx -= 1
            
        # Sort chronologically (since we collected them backwards)
        context_segments.reverse()
        
        # Stitch texts
        stitched_text = " ".join([seg["text"] for seg in context_segments])
        
        # Clean up double spaces or raw characters
        stitched_text = re.sub(r'\s+', ' ', stitched_text).strip()
        return stitched_text

    def _format_timestamp(self, seconds):
        """Converts float seconds into HH:MM:SS format."""
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
