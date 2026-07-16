# -*- coding: utf-8 -*-
"""Central configuration for the word-guessing game.

All tunable values live here so the CLI (game.py), the server (server.py), and the
shared engine (engine.py) draw from one place.
"""

# --- Vectors / loading ---
DEFAULT_VECTORS_PATH = "data/sgns.merge.word"
DEFAULT_LIMIT = 1_000_000  # max vectors to load (file is frequency-sorted)

# --- Server ---
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000

# --- Stats ---
STATS_DB_PATH = "data/stats.db"  # SQLite file for persistent game statistics

# --- Rooms / players ---
ROOM_ID_LENGTH = 4
MAX_NAME_LENGTH = 20

# --- Hints ---
HINT_INTERVAL = 100    # one hint earned per this many guesses
HINT_CAP_DELTA = 0.05  # hint word similarity must be <= best + this (cosine points)
MIN_HINT_RANK = 100    # never reveal a word ranked closer than this to the answer

# --- Temperature thresholds: ordered (max_rank, emoji); fallback used beyond the last ---
TEMPERATURE_LEVELS = [
    (10, "🔥🔥🔥"),
    (100, "🔥🔥"),
    (1000, "🔥"),
    (5000, "♨️"),
    (10000, "🌤️"),
    (50000, "🌥️"),
]
TEMPERATURE_FALLBACK = "❄️"
