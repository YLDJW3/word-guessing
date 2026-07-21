# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Semantle-style Chinese word-guessing game. A secret word is chosen; players guess words and
get back how *semantically* close each guess is, scored by cosine similarity over pre-trained
word2vec embeddings. Ships as a single-player CLI **and** a multiplayer WebSocket web server.
A standalone client-side Sudoku game is bundled as a bonus.

## Commands

```bash
# Environment (Python 3.10+, 3.13 recommended — gensim doesn't build on 3.14)
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
bash download_vectors.sh          # ~1.5GB embeddings from Google Drive → data/

# Run the web server (makefile uses `uv run`)
make server                        # = uv run server.py --allow-names-file allowlist.txt
python server.py --limit 500000 --port 8000 --admin-token mysecret
make tunnel                        # expose via cloudflared

# Run the single-player CLI
python game.py --answer 苹果 --limit 200000
```

There is **no test suite, linter, or build step** — this is a small script-based project.
Verify changes by running the server/CLI directly. First vector load parses the text file
(~30–90s) and writes a `.kv` binary cache; subsequent loads are ~1–2s. Pass `--limit` low to
speed up iteration.

## Architecture

Two entry points share one pure-computation core:

- **`engine.py`** — `GameEngine` wraps a gensim `KeyedVectors`. All scoring logic lives here:
  `compute_rank_map(secret)` builds `{word: (rank, similarity)}` for the *entire* vocab in one
  vectorized pass (this is the expensive per-round step), and `score_guess`, `get_hint`,
  `get_capped_hint`, `validate_word` (traditional→simplified via optional opencc) operate on
  that map. Neither entry point reimplements scoring — change it here.
- **`config.py`** — every tunable (vector path/limit, ports, hint interval/cap/rank-buffer,
  temperature emoji thresholds, room/chat limits, reveal count). CLI, server, and engine all
  import from here. Prefer adding a constant here over hardcoding.
- **`game.py`** — single-player CLI. Owns its own vector loading and REPL (`:hint`, `:top`,
  `:give`, `:quit`); draws candidate secrets from `words.py` intersected with loaded vocab.
- **`server.py`** — FastAPI + WebSocket multiplayer. See below.
- **`stats.py`** — SQLite persistence (`data/stats.db`). `record_game` is called on game-won;
  `get_player_stats` / `get_recent_games` back the admin page.
- **`words.py`** — curated ~200 common Chinese words as the random-secret pool.

### Server (`server.py`) — key facts

- **All room state is in-memory** in the module-level `rooms: dict[str, Room]` and
  `active_names: set`. Restarting the server loses every game. There is no DB-backed room state;
  only finished games persist (via `stats.py`).
- The **`Room` dataclass** (line ~53) is the single source of truth per game: holds the secret,
  the precomputed `rank_map`, mode, host, connected `players` (name→WebSocket), per-player and
  shared guess lists, chat, and hint milestone counters. `MAX_ROOMS` rooms are kept as
  rejoinable history; `evict_old_rooms` drops the oldest *empty* room on overflow.
- **WebSocket protocol** (`/ws`): a single loop dispatches on the incoming JSON `type` field —
  `set_name`, `create_room`, `join_room`, `guess`, `hint`, `chat`, `leave_room`. The server
  pushes messages with a `type` too (`name_set`, `room_joined`, `scoreboard`, `guess_result`,
  `game_won`, `reveal`, `chat`, `hint_status`, `error`, …). When editing message handling,
  keep server `type` strings in sync with the JS in `static/index.html`.
- **Two game modes** drive branching throughout: `competitive` (per-player guess lists, a
  scoreboard that deliberately hides opponents' actual words) vs `cooperative` (one
  `shared_guesses` feed everyone sees). Hints follow the same split — per-player milestone in
  competitive, one shared `coop_hint_used_milestone` in cooperative.
- A **custom competitive host is a spectator/quizmaster** (`is_spectator`): they set the word,
  so they watch instead of guessing. Guard new player-action code against this case.
- **Hints are earned and capped** — one per `HINT_INTERVAL` guesses, revealed word's similarity
  ≤ best + `HINT_CAP_DELTA`, never among the top `MIN_HINT_RANK` closest. Logic split between
  the accounting helpers (lines ~150–200) and `engine.get_capped_hint`.
- **Admin routes** (`/admin`, `/api/stats/*`) are gated by a `key` query param checked against
  `--admin-token` (random if unset, printed at startup). Returns 403 otherwise.

### Routing / frontend

- `/` → `static/home.html` (game picker), `/word` → `static/index.html` (word game),
  `/sudoku` → `static/sudoku.html`, `/{name}` → word game pre-filled with that nickname.
- Frontends are **vanilla HTML/JS, no build**. Edit the `static/*.html` files directly.
- Sudoku is fully client-side: `static/sudoku-core.js` (generator/solver/hint, runs in browser
  *and* Node) + `static/sudoku.html` (UI). No server involvement. Spec in `spec/sudoku.md`.

## Notes

- The `data/` directory (vectors, `.kv` caches, `stats.db`) is gitignored and multi-GB.
- Any word2vec-format file works as a drop-in via `--vectors <path>`.
