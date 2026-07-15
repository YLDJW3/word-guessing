# 中文猜词游戏 (Chinese Word Guessing Game)

A Semantle-style CLI game: a secret Chinese word is chosen, and you guess words.
After each guess the game tells you how *semantically* close your guess is to the
answer — powered by cosine similarity over Chinese word embeddings.

Vectors: [Chinese-Word-Vectors](https://github.com/Embedding/Chinese-Word-Vectors)
(Mixed-large corpus, 300-dim, word2vec format).

## Setup

```bash
# 1. Create a virtual environment and install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Download word vectors (~1.5GB from Google Drive)
bash download_vectors.sh
# If the script can't download automatically, it prints manual instructions.
```

## Play

```bash
# Random secret word
python game.py

# Set a specific answer (for testing / sharing with friends)
python game.py --answer 苹果

# Limit vocab to speed up loading (first N most-frequent words)
python game.py --limit 200000
```

### In-game commands

| Command | Effect |
|---------|--------|
| `:hint` | Reveal a word that's close to the answer |
| `:top`  | Show your best guesses so far (sorted by similarity) |
| `:give` | Give up and reveal the answer |
| `:quit` | Exit the game |

## How it works

1. Loads pre-trained word vectors (Tencent AI Lab, word2vec text format).
2. Picks a secret word from a curated candidates list (`words.py`).
3. Precomputes cosine similarity of the secret vs. every word in the vocab.
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
