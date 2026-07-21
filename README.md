# Semantle (Chinese Word Guessing Game)

A Semantle-style word-guessing game for Chinese. A secret word is chosen, and
players guess words — after each guess the game reports how *semantically* close
the guess is, powered by cosine similarity over word embeddings.

Supports both **single-player CLI** and **multiplayer web** (friends connect via browser).

Vectors: [Chinese-Word-Vectors](https://github.com/Embedding/Chinese-Word-Vectors)
(Mixed-large corpus, 300-dim, word2vec format).

## Setup

```bash
# 1. Create a virtual environment and install deps
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Download word vectors (~1.5GB from Google Drive)
bash download_vectors.sh
# If the script can't download automatically, it prints manual instructions.
```

## Single-player CLI

```bash
# Main menu (random / custom word)
python game.py

# Set a specific answer directly
python game.py --answer 苹果

# Limit vocab to speed up loading
python game.py --limit 200000
```

### In-game commands (CLI)

| Command | Effect |
|---------|--------|
| `:hint` | Reveal a word that's close to the answer |
| `:top`  | Show your best guesses so far (sorted by similarity) |
| `:give` | Give up and reveal the answer |
| `:quit` | Return to main menu |

(The web server has its own earned/capped hint system — see [Hints](#hints) below.)

## Multiplayer Web Server

Start the server:

```bash
python server.py
# or with custom options:
python server.py --vectors data/sgns.merge.word --limit 500000 --port 8000
```

Then open `http://<your-ip>:8000` in a browser — it opens the word game (Semantle) by
default, with a top nav bar to switch between 🎯 Semantle and 🧩 数独 (Sudoku at `/sudoku`).
Share the URL with friends to play together. (A per-player nickname deep-link like `/alice`
still enters the word game directly with that name.)

### Restrict who can join (name allowlist)

By default anyone with the URL can pick a nickname and play. To limit entry to a fixed
set of names, pass an allowlist (case-insensitive). Only listed nicknames are accepted:

```bash
# Inline, comma-separated
python server.py --allow-names alice,bob,charlie

# Or from a file (one nickname per line)
python server.py --allow-names-file friends.txt
```

### Admin stats page

Finished games are recorded to a SQLite database (`data/stats.db` by default; override
with `--stats-db`). Stats are **admin-only**, served at a separate address gated by a
secret token — players can't see them.

```bash
# Provide your own token (stable URL you can bookmark)
python server.py --admin-token mysecret

# Or omit it — a random token is generated and printed at startup:
#   Admin stats page: http://0.0.0.0:8000/admin?key=<token>
```

Open `http://<your-ip>:8000/admin?key=<token>` to view:
- **Player leaderboard** — games played, wins, win rate.
- **Recent games** — answer, mode, winner + guesses taken, participants, time.

The `/admin` page and the `/api/stats/*` endpoints both require the correct `key`
(returns 403 otherwise). Note the token appears in the URL, so it may show up in
server/proxy logs — fine for a friend group.

### Game modes

| Mode | Description |
|------|-------------|
| **Competitive (竞争)** | Each player guesses independently. First to find the word wins. A live scoreboard shows each player's best similarity (the word itself is hidden so it can't be copied). |
| **Cooperative (合作)** | Shared guess feed — all players see everyone's guesses and work together. |

### How to play (web)

1. Open the page, enter a nickname.
2. **Create a room** — choose competitive or cooperative mode, optionally set a custom secret word (or leave blank for random).
3. Share the 4-character room code with friends.
4. Friends **join the room** by entering the code.
5. Everyone guesses — results update in real time via WebSocket. The guess table is
   sorted by similarity (closest on top), with your latest guess pinned as a marked row.
6. When someone guesses correctly, everyone sees who won, then can return to the lobby.

### Hints

Hints are **earned and bounded** so they help without spoiling:

- **Earned:** one hint per 100 guesses. Cooperative counts the room's total guesses;
  competitive counts each player's own. Hints don't stack (one held at a time).
- **Capped:** the revealed word's similarity is at most **+5 percentage points** above
  your current closest guess — a nudge forward, not a giveaway.
- **Rank buffer:** a hint never reveals a word among the **100 closest** to the answer.
  Once your best guess reaches the top 100, hints turn off automatically.

The 💡 button shows a countdown to the next hint and enables when one is available.
In cooperative mode a hint is broadcast to everyone; in competitive it's private.

These values (hint interval, cap, rank buffer, temperature thresholds, defaults) are all
tunable in `config.py`.

### Deployment

For a small group of friends:

```bash
# Direct (LAN or port-forwarded)
python server.py --host 0.0.0.0 --port 8000

# Via tunnel (internet, no port forwarding needed)
# e.g. ngrok, cloudflared:
cloudflared tunnel --url http://localhost:8000
```

## Sudoku (bonus single-player game)

A standalone 9×9 Sudoku is served at **`/sudoku`** (reachable from the entry page and the
word-game lobby; links back to 🏠 首页 / 🎯 猜词). It's fully client-side — no server state.

- **Difficulty:** 入门 / 中级 / 困难 / 专家 / 大师 (intro/middle/hard/expert/master), graded by the
  hardest human technique required (singles → pointing/pairs → hidden pairs → X-Wing →
  XY-Wing/XYZ-Wing/Swordfish) plus a givens floor. **Master** puzzles are filtered to actually
  require one of the advanced techniques.
- **Hint (💡):** fills one logically-deducible digit and explains *why* in plain language
  (naming the cell, digit, technique, and unit). Guards against a contradictory board.
- **Check (🔍):** flags wrong entries on demand. Also has pencil notes (✏️), erase, timer,
  keyboard support, and `localStorage` autosave so a refresh resumes the puzzle.
- Every generated puzzle has a unique solution. Logic lives in `static/sudoku-core.js`
  (browser + Node), UI in `static/sudoku.html`.

## How it works

1. Loads pre-trained word vectors (word2vec text format) once at startup.
2. First load parses the text file (~30-90s); subsequent loads use a cached
   binary format (~1-2s).
3. For each game round, precomputes cosine similarity of the secret vs. every
   word in the vocab.
4. Each guess shows:
   - **Similarity %** — cosine similarity × 100.
   - **Rank** — how close compared to all other words ("第 N 近 / 共 M 词").
   - **Temperature** — emoji indicator (🔥 = very close, ❄️ = far away).

## Requirements

- Python 3.10+ (3.13 recommended; gensim doesn't compile on 3.14 yet)
- ~1.5GB disk for the vectors file
- ~1GB RAM with default `--limit 1000000`

## Embedding source

[Chinese-Word-Vectors](https://github.com/Embedding/Chinese-Word-Vectors) — Mixed-large
corpus (Baidu Baike + Wikipedia + news + Weibo), 300-dim, ~350K words, word2vec text format.

Any word2vec-format file works as a drop-in replacement via `--vectors <path>`.

Traditional Chinese input (e.g. 「愛」) is automatically converted to simplified
(「爱」) if `opencc-python-reimplemented` is installed.

## Project structure

```
game.py              # Single-player CLI
server.py            # Multiplayer web server (FastAPI + WebSocket)
engine.py            # Shared game logic (validate, rank, score)
stats.py             # SQLite persistence for game statistics
config.py            # Central config (defaults, hint tuning, thresholds)
words.py             # Curated candidate secret words (~200)
static/index.html    # Word game frontend (default, served at / and /{name})
static/admin.html    # Admin stats page (token-gated)
static/sudoku.html   # Sudoku game UI (served at /sudoku)
static/sudoku-core.js# Sudoku generator/solver/hint logic (browser + Node)
download_vectors.sh  # Download vectors from Google Drive
requirements.txt     # Python dependencies
```

The Sudoku design spec lives in `spec/sudoku.md`.
