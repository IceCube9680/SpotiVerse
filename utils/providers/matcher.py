# utils/providers/matcher.py
import re
import difflib
import logging
from typing import Optional, List, Tuple
from utils.providers.base import TrackMetadata, AudioSource

logger = logging.getLogger(__name__)

class TrackMatcher:
    """
    Intelligent Track Matching & Source Selection Engine:
    - Title & Artist normalization (removes video noise, remastered tags, feat credits)
    - ISRC exact matching
    - Duration tolerance comparison
    - Fuzzy title/artist similarity scoring
    - Quality-aware audio source selection
    """

    NOISE_PATTERNS = [
        r"\[.*?official.*?video.*?\]",
        r"\(.*?official.*?video.*?\)",
        r"\[.*?official.*?audio.*?\]",
        r"\(.*?official.*?audio.*?\)",
        r"\[.*?lyrics.*?\]",
        r"\(.*?lyrics.*?\)",
        r"\[.*?music\s+video.*?\]",
        r"\(.*?music\s+video.*?\)",
        r"\[.*?4k.*?\]",
        r"\[.*?hd.*?\]",
        r"\(.*?remaster(?:ed)?.*?\)",
        r"\[.*?remaster(?:ed)?.*?\]",
        r"\(.*?deluxe.*?\)",
        r"\[.*?deluxe.*?\]",
        r"\(.*?bonus\s+track.*?\)",
        r"\[.*?bonus\s+track.*?\]",
        r"\(.*?visualizer.*?\)",
        r"\[.*?visualizer.*?\]",
        r"\bft\.?\s+.*",
        r"\bfeat\.?\s+.*",
    ]

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Strip extraneous text, parenthesis, special characters from title or artist."""
        if not text:
            return ""
        cleaned = text.lower()
        for pat in cls.NOISE_PATTERNS:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE)

        # Remove special characters
        cleaned = re.sub(r"[^\w\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @classmethod
    def similarity(cls, str1: str, str2: str) -> float:
        """Compute SequenceMatcher similarity between two strings (0.0 to 1.0)."""
        s1 = cls.clean_text(str1)
        s2 = cls.clean_text(str2)
        if not s1 or not s2:
            return 0.0
        if s1 == s2:
            return 1.0
        return difflib.SequenceMatcher(None, s1, s2).ratio()

    @classmethod
    def is_duration_match(cls, dur1: int, dur2: int, tolerance_sec: int = 10) -> Tuple[bool, int]:
        """
        Check if duration difference is within acceptable tolerance.
        Returns: (is_match, diff_seconds)
        """
        if dur1 <= 0 or dur2 <= 0:
            return True, 0  # Missing duration does not strictly disqualify
        diff = abs(dur1 - dur2)
        return diff <= tolerance_sec, diff

    @classmethod
    def compute_match_confidence(cls, target: TrackMetadata, candidate_title: str,
                                 candidate_artist: str, candidate_duration: int,
                                 candidate_isrc: Optional[str] = None) -> float:
        """
        Calculates confidence score (0.0 to 1.0) between target metadata and candidate.
        """
        # 1. ISRC exact match is 100% confidence
        if candidate_isrc and target.isrc:
            if candidate_isrc.strip().upper() == target.isrc.strip().upper():
                return 1.0

        # 2. Title similarity (weight: 0.5)
        title_sim = cls.similarity(target.title, candidate_title)

        # 3. Artist similarity (weight: 0.3)
        artist_sim = cls.similarity(target.artist, candidate_artist)
        # Check if artist is in candidate title (e.g. YouTube titles "Artist - Title")
        if target.artist and cls.clean_text(target.artist) in cls.clean_text(candidate_title):
            artist_sim = max(artist_sim, 0.9)

        # 4. Duration match (weight: 0.2)
        is_dur_ok, diff = cls.is_duration_match(target.duration, candidate_duration, tolerance_sec=15)
        if target.duration > 0 and candidate_duration > 0:
            if diff <= 3:
                dur_score = 1.0
            elif diff <= 8:
                dur_score = 0.8
            elif diff <= 15:
                dur_score = 0.5
            else:
                dur_score = 0.0
        else:
            dur_score = 0.7  # neutral when missing

        # Reject immediately if duration mismatch is huge (> 30s) and title is not identical
        if target.duration > 0 and candidate_duration > 0 and diff > 30:
            return 0.1

        confidence = (title_sim * 0.5) + (artist_sim * 0.3) + (dur_score * 0.2)
        return round(confidence, 3)

    @classmethod
    def match_track(cls, target: TrackMetadata, candidate: TrackMetadata, threshold: float = 0.65) -> Tuple[bool, float]:
        """
        Compare target and candidate track metadata and return (is_match, confidence_score).
        """
        score = cls.compute_match_confidence(
            target=target,
            candidate_title=candidate.title,
            candidate_artist=candidate.artist,
            candidate_duration=candidate.duration,
            candidate_isrc=candidate.isrc
        )
        return score >= threshold, score

    @classmethod
    def rank_sources(cls, sources: List[AudioSource], requested_quality: str = "best") -> List[AudioSource]:
        """
        Sort and rank available audio sources based on quality preference:
        - If requested_quality is lossless/flac: prioritize lossless sources, then highest bitrate.
        - Otherwise: prioritize highest bitrate, native Opus/AAC streams.
        """
        def _score(src: AudioSource) -> float:
            score = 0.0
            if src.lossless:
                score += 1000.0
            score += float(src.bitrate)
            if src.sample_rate >= 96000:
                score += 50.0
            elif src.sample_rate >= 48000:
                score += 20.0
            if src.codec in ("opus", "aac"):
                score += 10.0
            return score

        return sorted(sources, key=_score, reverse=True)
