# Spec: Single-Player 9×9 Sudoku

## 1. Summary

Add a standalone single-player 9×9 Sudoku game to the project. Players pick a difficulty
(**intro / middle / hard / expert**), fill the grid, and can press a **Hint** button that
fills in one new digit *and explains the human-logic reason* for it. It's fully client-side
(no game state on the server) and served as its own page, consistent with the existing
vanilla-HTML/JS/CSS, no-build-step style and dark theme.

This game is independent of the word-guessing game — it shares only the web server and
visual style, not the room/WebSocket machinery.

## 2. Goals / Non-goals

**Goals**
- Playable 9×9 Sudoku with a clean, **mobile-friendly** UI (on-screen number pad).
- Four difficulty levels with meaningfully different challenge.
- Every generated puzzle has a **unique solution**.
- A **Hint** that reveals one correct digit with a plain-language reason (which technique
  and why), not just "the answer is 5".
- Pencil/candidate notes, erase, and win detection.

**Non-goals (v1)**
- Multiplayer, accounts, leaderboards, or server-side persistence.
- Puzzle import/export, custom puzzles, or daily challenges (possible later).
- Techniques beyond what's needed to grade/solve expert (no fish beyond X-Wing in v1).

## 3. Placement & architecture

- **Client-side only.** All logic (generation, solving, grading, hints) runs in the browser.
- **Served by the existing FastAPI app** as a new page:
  - Add `static/sudoku.html` (self-contained: HTML + CSS + JS, like `index.html`).
  - Add a route `GET /sudoku` in `server.py` returning that file (declared alongside the
    other explicit routes, **before** the `/{name}` catch-all so it isn't swallowed).
  - Optional: a small link from the word-game lobby ("🧩 数独") and vice-versa. Kept optional
    to avoid coupling; decide during implementation.
- The file can also be opened directly (`file://`) for offline play since there's no backend
  dependency.

### File layout
```
spec/sudoku.md          # this document
static/sudoku.html      # NEW — the whole game (markup + styles + script)
server.py               # + GET /sudoku route
```
If the script grows large, split into `static/sudoku/{index.html,sudoku.js,sudoku.css}` and
serve the folder; v1 assumes a single file for simplicity.

## 4. Core components (client JS)

### 4.1 Board model
- `grid`: 81 cells. Each cell holds `{value: 0..9, given: bool, notes: Set<1..9>}` (0 = empty).
- Helpers: `rowCells(r)`, `colCells(c)`, `boxCells(b)`, `peers(i)` (the 20 cells sharing a
  row/col/box), and `candidates(i)` = digits not used by any peer.
- Immutable "solution" grid kept for validation and as the source of truth for hints.

### 4.2 Generator
1. **Full solution:** fill an empty grid via randomized backtracking (shuffle candidate order)
   to get a complete valid solution.
2. **Dig holes:** remove cells one at a time (in random order); after each removal, run the
   uniqueness check — if the puzzle still has exactly one solution, keep it removed, else
   restore. Continue until the target givens / difficulty grade is reached.
3. **Grade & accept:** run the logical solver (4.4) on the dug puzzle; accept only if its
   grade matches the requested difficulty band (regenerate otherwise, with an attempt cap).

### 4.3 Uniqueness / brute solver
- Backtracking solver with an early-exit "count up to 2 solutions" mode. A puzzle is valid
  iff exactly one solution exists. Used only during generation.

### 4.4 Logical (human) solver — grading + hints
Applies human techniques in increasing order of difficulty; each pass returns the **first**
deduction found (a cell → digit) plus metadata, or "no technique applies".

Technique ladder (v1):
1. **Naked Single** — a cell has exactly one candidate.
2. **Hidden Single** — a digit has exactly one possible cell within a row, column, or box.
3. **Locked Candidates / Pointing** — a digit confined to one box-line eliminates elsewhere
   (used for candidate elimination; may not directly place a digit but unlocks later steps).
4. **Naked Pair / Hidden Pair** — elimination technique.
5. **X-Wing** — advanced elimination (expert only).

The solver loop: repeatedly apply techniques 1→N; placements fill cells, eliminations prune
candidates; record the **hardest** technique used. **Grade = hardest technique required to
solve the puzzle to completion.**

### 4.5 Hint engine
- On **Hint**: run the logical solver on the *current* board state (respecting user entries),
  find the simplest next **placement** (a digit that can be logically placed now), and:
  - fill that cell (mark it as hint-filled/highlighted),
  - show a **reason** string in a hint panel.
- If the only progress is an elimination (no placement yet), the hint explains the
  elimination and, if needed, keeps applying until it can name a placement — v1 always
  resolves to a concrete "place digit D at RxCy" with the governing reason.
- Guard: if the user's board has an error/contradiction, the hint panel says so instead of
  giving a bogus digit (compare against the stored solution; the first user cell that
  conflicts is flagged).

#### Hint reason format (examples)
- Naked single: `R3C5 只能填 7 —— 该格其余 1–9 都已被同行/列/宫占用（唯一候选）。`
- Hidden single (box): `R1C2 填 4 —— 在第 1 宫里只有这一格能放 4（宫内隐性唯一）。`
- Hidden single (row): `R6C9 填 2 —— 第 6 行中只有这一格能放 2。`
- Pointing (elimination leading to a single): explains the box-line lock, then the resulting
  placement.

Each reason names: the cell (RxCy), the digit, the technique, and the unit (row/col/box).

### 4.6 Difficulty settings

Grade primarily by **hardest required technique** (robust), with givens count as a secondary
target for feel:

| Level | 中文 | Hardest technique needed | Approx. givens |
|-------|------|--------------------------|----------------|
| intro | 入门 | Naked/Hidden Singles only | 40–48 |
| middle | 中级 | + Pointing / Naked Pair | 32–38 |
| hard | 困难 | + Hidden Pair / advanced eliminations | 28–32 |
| expert | 专家 | + X-Wing | 24–28 |

Generation regenerates until the grade matches; an attempt cap (e.g. 200) prevents hangs,
falling back to the closest grade found.

## 5. UI / UX (mobile-first)

- **9×9 grid** with bold 3×3 box borders; givens in a distinct weight/color from user entries;
  hint-filled cells briefly highlighted.
- **Selection model:** tap a cell to select; tap a number-pad key to place (or add a note in
  notes mode). Highlight the selected cell, its peers, and all cells with the same digit.
- **Number pad** (1–9) below the grid + **Erase**, **Notes toggle (笔记)**, **Hint (提示)**,
  **New Game (新游戏)** with a difficulty selector.
- **Hint panel:** a text area under the board showing the latest hint's reason.
- **Status:** timer (mm:ss), and optional mistake counter (compare entries to solution).
- **Win state:** on completion, a banner ("🎉 完成！用时 mm:ss").
- Reuse the existing dark palette and button styles for visual consistency.
- Keyboard support on desktop (1–9 to place, arrows to move, Backspace to erase, `n` notes,
  `h` hint) — with the IME-safe pattern already used elsewhere.

## 6. State & persistence

- In-memory game state.
- **`localStorage` autosave (v1):** persist the current puzzle, user progress + notes,
  difficulty, and elapsed time, so a refresh or phone-lock resumes the game (matches the
  word game's refresh-friendliness). Saved on each move/tick; cleared on win or New Game.
- No server state.

## 7. Implementation phases

1. **Grid + rendering + input** — static board, selection, number pad, notes, erase, win check.
2. **Generator + uniqueness solver** — produce unique puzzles; hard-code difficulty by givens
   first to unblock UI.
3. **Logical solver + technique ladder** — grade puzzles; wire real difficulty bands.
4. **Hint engine + reasons** — simplest-next-placement with explanations; error guard.
5. **Polish** — timer, highlights, win banner, mobile tuning, optional localStorage resume,
   optional cross-link with the word game; `GET /sudoku` route + README note.

## 8. Verification

- **Generator/solver (unit, headless JS or a small Node script):**
  - Every generated puzzle has exactly one solution (uniqueness solver returns 1).
  - Grades land in the requested band across many samples per difficulty.
  - Logical solver fully solves intro/middle/hard/expert samples using ≤ the band's technique.
- **Hint:**
  - On a solvable state, returns a correct placement matching the stored solution, with a
    reason string naming cell/digit/technique/unit.
  - On a user-error board, reports the conflict instead of a digit.
- **UI (manual, incl. mobile viewport):** place/erase/notes, difficulty switch generates a new
  puzzle, hint fills + explains, win banner on completion, keyboard shortcuts on desktop.
- **Route:** `GET /sudoku` serves the page; `/{name}` still resolves names; other routes intact.

## 9. Decisions & open questions

- **Decided (defaults):** client-side only; single self-contained `static/sudoku.html`; grade
  by hardest technique; hint always resolves to a concrete placement + reason; difficulty
  labels intro/middle/hard/expert (入门/中级/困难/专家).
- **Decided (confirmed with user):**
  1. **Cross-link both games** — Sudoku at `/sudoku`, plus a 🧩 数独 link on the word-game
     lobby and a 🎯 link back from Sudoku, so players can move between them.
  2. **localStorage resume in v1** — autosave current puzzle, progress, difficulty, and timer
     so a refresh / phone-lock resumes the game (this becomes part of phase 1/5, not deferred).
  3. **Manual 检查 (Check) button** — wrong cells are flagged only when the player presses
     Check (forgiving; no auto-highlight as you type). The Hint contradiction guard still
     applies independently.
