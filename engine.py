# -*- coding: utf-8 -*-
"""Game engine: pure-computation logic for the word-guessing game.

Used by both the CLI (game.py) and the web server (server.py).
"""

import time

import numpy as np
from gensim.models import KeyedVectors

from config import TEMPERATURE_LEVELS, TEMPERATURE_FALLBACK

try:
    from opencc import OpenCC
    _t2s = OpenCC("t2s")
    def to_simplified(text: str) -> str:
        return _t2s.convert(text)
except ImportError:
    def to_simplified(text: str) -> str:
        return text


def temperature_indicator(rank: int) -> str:
    for max_rank, emoji in TEMPERATURE_LEVELS:
        if rank <= max_rank:
            return emoji
    return TEMPERATURE_FALLBACK


class GameEngine:
    def __init__(self, kv: KeyedVectors):
        self.kv = kv
        self.total = len(kv)

    def validate_word(self, raw: str) -> str | None:
        """Normalize (traditional→simplified) and check if in vocab.
        Returns the normalized word, or None if not in vocabulary."""
        word = to_simplified(raw.strip())
        if word in self.kv:
            return word
        return None

    def compute_rank_map(self, secret: str) -> dict[str, tuple[int, float]]:
        """Precompute cosine similarity ranks for a secret word.
        Returns {word: (rank, similarity)} for all words in vocab."""
        secret_vec = self.kv.get_vector(secret, norm=True)
        all_norms = self.kv.get_normed_vectors()
        similarities = all_norms @ secret_vec
        ranked_indices = np.argsort(-similarities)
        rank_map = {}
        for rank, idx in enumerate(ranked_indices):
            rank_map[self.kv.index_to_key[idx]] = (rank, float(similarities[idx]))
        return rank_map

    def score_guess(self, word: str, rank_map: dict) -> dict:
        """Score a validated word against a precomputed rank map.
        Returns a dict with all display fields."""
        rank, similarity = rank_map[word]
        pct = similarity * 100
        percentile = (1 - rank / self.total) * 100
        return {
            "word": word,
            "similarity": round(pct, 2),
            "rank": rank,
            "percentile": round(percentile, 1),
            "temperature": temperature_indicator(rank),
            "is_answer": rank == 0,
        }

    def get_hint(self, rank_map: dict, target_rank: int, secret: str, exclude: set) -> str | None:
        """Find a word at approximately target_rank, excluding secret and already-guessed words."""
        for word, (r, _) in rank_map.items():
            if r == target_rank and word != secret and word not in exclude:
                return word
        return None

    def get_capped_hint(self, rank_map: dict, best_cos: float, cap_delta: float,
                        secret: str, exclude: set, min_rank: int = 0) -> str | None:
        """Return the highest-similarity word w with best_cos < sim(w) <= best_cos + cap_delta,
        excluding the secret and already-guessed words. None if no word qualifies.
        best_cos and cap_delta are in cosine units (0-1); cap_delta=0.10 = +10 percentage points.
        min_rank: words ranked closer to the answer than this (rank < min_rank) are off-limits,
        so a hint never spoils by revealing one of the very closest words."""
        cap = best_cos + cap_delta
        best_word = None
        best_word_sim = -1.0
        for word, (r, sim) in rank_map.items():
            if word == secret or word in exclude or r < min_rank:
                continue
            if best_cos < sim <= cap and sim > best_word_sim:
                best_word_sim = sim
                best_word = word
        return best_word
