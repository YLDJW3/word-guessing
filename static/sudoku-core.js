// -*- sudoku core: generation, solving, grading, hints -*-
// Runs in the browser (window.SudokuCore) and Node (module.exports) — no DOM, no deps.
// Cells are indexed 0..80; value 0 = empty. A "grid"/"values" is an 81-length int array.

(function () {
  "use strict";

  // --- Units & peers (precomputed) ---
  const ROWS = [], COLS = [], BOXES = [];
  for (let r = 0; r < 9; r++) { ROWS[r] = []; for (let c = 0; c < 9; c++) ROWS[r].push(r * 9 + c); }
  for (let c = 0; c < 9; c++) { COLS[c] = []; for (let r = 0; r < 9; r++) COLS[c].push(r * 9 + c); }
  for (let b = 0; b < 9; b++) {
    BOXES[b] = [];
    const br = 3 * Math.floor(b / 3), bc = 3 * (b % 3);
    for (let dr = 0; dr < 3; dr++) for (let dc = 0; dc < 3; dc++) BOXES[b].push((br + dr) * 9 + (bc + dc));
  }
  const UNITS = [...ROWS, ...COLS, ...BOXES];
  const rc = (i) => [Math.floor(i / 9), i % 9];
  const boxOf = (i) => 3 * Math.floor(Math.floor(i / 9) / 3) + Math.floor((i % 9) / 3);

  const PEERS = [];
  for (let i = 0; i < 81; i++) {
    const [r, c] = rc(i), s = new Set();
    ROWS[r].forEach(j => s.add(j));
    COLS[c].forEach(j => s.add(j));
    BOXES[boxOf(i)].forEach(j => s.add(j));
    s.delete(i);
    PEERS[i] = [...s];
  }

  // --- Small helpers ---
  function shuffle(a) {
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }
  const setEq = (a, b) => a.size === b.size && [...a].every(x => b.has(x));
  const sameCells = (a, b) => a.length === b.length && a.every(x => b.includes(x));
  const canPlace = (g, i, d) => !PEERS[i].some(p => g[p] === d);

  const UNIT_NAME = (u) => u < 9 ? `第 ${u + 1} 行` : u < 18 ? `第 ${u - 9 + 1} 列` : `第 ${u - 18 + 1} 宫`;
  const RCLABEL = (i) => { const [r, c] = rc(i); return `R${r + 1}C${c + 1}`; };
  const PEERSET = PEERS.map(p => new Set(p));
  const isPeer = (i, j) => PEERSET[i].has(j);
  const commonPeers = (i, j) => PEERS[i].filter(p => PEERSET[j].has(p));
  const TECH_NAME = {
    pointing: "区块排除", claiming: "区块排除",
    naked_pair: "显性数对", hidden_pair: "隐性数对", x_wing: "X-Wing",
    xy_wing: "XY-Wing", swordfish: "Swordfish", xyz_wing: "XYZ-Wing",
  };

  // --- Full-solution generator (randomized backtracking) ---
  function fillSolution(g) {
    const i = g.indexOf(0);
    if (i === -1) return true;
    for (const d of shuffle([1, 2, 3, 4, 5, 6, 7, 8, 9])) {
      if (canPlace(g, i, d)) { g[i] = d; if (fillSolution(g)) return true; g[i] = 0; }
    }
    return false;
  }
  function generateSolution() { const g = new Array(81).fill(0); fillSolution(g); return g; }

  // --- Uniqueness: count solutions up to `limit` (MRV backtracking) ---
  function countSolutions(grid, limit = 2) {
    const g = grid.slice();
    let count = 0;
    (function bt() {
      if (count >= limit) return;
      let bi = -1, bc = null;
      for (let i = 0; i < 81; i++) if (g[i] === 0) {
        const cs = [];
        for (let d = 1; d <= 9; d++) if (canPlace(g, i, d)) cs.push(d);
        if (cs.length === 0) return;              // dead end
        if (bi === -1 || cs.length < bc.length) { bi = i; bc = cs; if (cs.length === 1) break; }
      }
      if (bi === -1) { count++; return; }         // full grid
      for (const d of bc) { g[bi] = d; bt(); g[bi] = 0; if (count >= limit) return; }
    })();
    return count;
  }

  // --- Dig holes while keeping a unique solution ---
  function dig(solution, targetGivens) {
    const puzzle = solution.slice();
    let givens = 81;
    for (const i of shuffle([...Array(81).keys()])) {
      if (givens <= targetGivens) break;
      const saved = puzzle[i];
      puzzle[i] = 0;
      if (countSolutions(puzzle, 2) !== 1) puzzle[i] = saved; else givens--;
    }
    return puzzle;
  }

  // --- Candidate model for human techniques ---
  function computeCands(values) {
    const cand = new Array(81).fill(null);
    for (let i = 0; i < 81; i++) {
      if (values[i] !== 0) continue;
      const s = new Set([1, 2, 3, 4, 5, 6, 7, 8, 9]);
      for (const p of PEERS[i]) s.delete(values[p]);
      cand[i] = s;
    }
    return cand;
  }
  function place(state, i, d) {
    state.values[i] = d; state.cand[i] = null;
    for (const p of PEERS[i]) if (state.cand[p]) state.cand[p].delete(d);
  }
  function applyStep(state, step) {
    if (step.kind === "place") place(state, step.cell, step.digit);
    else for (const rm of step.removals) if (state.cand[rm.cell]) state.cand[rm.cell].delete(rm.digit);
  }

  // --- Techniques: each returns a step {kind, ...} or null ---
  function nakedSingle(state) {
    for (let i = 0; i < 81; i++) if (state.values[i] === 0 && state.cand[i].size === 1) {
      const d = [...state.cand[i]][0], [r, c] = rc(i);
      return { kind: "place", cell: i, digit: d, rank: 1, technique: "naked_single",
        reason: `R${r + 1}C${c + 1} 只能填 ${d} —— 同行、同列、同宫已占用其他 8 个数字（唯一候选）。` };
    }
    return null;
  }
  function hiddenSingle(state) {
    for (let u = 0; u < 27; u++) {
      const unit = UNITS[u];
      for (let d = 1; d <= 9; d++) {
        if (unit.some(i => state.values[i] === d)) continue;
        const cells = unit.filter(i => state.values[i] === 0 && state.cand[i].has(d));
        if (cells.length === 1) {
          const [r, c] = rc(cells[0]);
          return { kind: "place", cell: cells[0], digit: d, rank: 2, technique: "hidden_single",
            reason: `R${r + 1}C${c + 1} 填 ${d} —— 在${UNIT_NAME(u)}中只有这一格能放 ${d}（隐性唯一）。` };
        }
      }
    }
    return null;
  }
  function lockedCandidates(state) {
    // Pointing: a digit confined to one line within a box eliminates it elsewhere on that line.
    for (let b = 0; b < 9; b++) for (let d = 1; d <= 9; d++) {
      const cells = BOXES[b].filter(i => state.values[i] === 0 && state.cand[i] && state.cand[i].has(d));
      if (cells.length < 2) continue;
      const rows = new Set(cells.map(i => Math.floor(i / 9))), cols = new Set(cells.map(i => i % 9));
      if (rows.size === 1) {
        const r = [...rows][0];
        const removals = ROWS[r].filter(i => boxOf(i) !== b && state.values[i] === 0 && state.cand[i] && state.cand[i].has(d)).map(i => ({ cell: i, digit: d }));
        if (removals.length) return { kind: "eliminate", removals, rank: 3, technique: "pointing" };
      }
      if (cols.size === 1) {
        const c = [...cols][0];
        const removals = COLS[c].filter(i => boxOf(i) !== b && state.values[i] === 0 && state.cand[i] && state.cand[i].has(d)).map(i => ({ cell: i, digit: d }));
        if (removals.length) return { kind: "eliminate", removals, rank: 3, technique: "pointing" };
      }
    }
    // Claiming: a digit confined to one box within a line eliminates it elsewhere in that box.
    for (let u = 0; u < 18; u++) for (let d = 1; d <= 9; d++) {
      const unit = UNITS[u];
      const cells = unit.filter(i => state.values[i] === 0 && state.cand[i] && state.cand[i].has(d));
      if (cells.length < 2) continue;
      const boxes = new Set(cells.map(boxOf));
      if (boxes.size === 1) {
        const b = [...boxes][0];
        const removals = BOXES[b].filter(i => !unit.includes(i) && state.values[i] === 0 && state.cand[i] && state.cand[i].has(d)).map(i => ({ cell: i, digit: d }));
        if (removals.length) return { kind: "eliminate", removals, rank: 3, technique: "claiming" };
      }
    }
    return null;
  }
  function nakedPair(state) {
    for (const unit of UNITS) {
      const empties = unit.filter(i => state.values[i] === 0 && state.cand[i]);
      for (let a = 0; a < empties.length; a++) for (let b = a + 1; b < empties.length; b++) {
        const ca = state.cand[empties[a]], cb = state.cand[empties[b]];
        if (ca.size === 2 && cb.size === 2 && setEq(ca, cb)) {
          const [d1, d2] = [...ca], removals = [];
          for (const i of empties) {
            if (i === empties[a] || i === empties[b]) continue;
            if (state.cand[i].has(d1)) removals.push({ cell: i, digit: d1 });
            if (state.cand[i].has(d2)) removals.push({ cell: i, digit: d2 });
          }
          if (removals.length) return { kind: "eliminate", removals, rank: 4, technique: "naked_pair" };
        }
      }
    }
    return null;
  }
  function hiddenPair(state) {
    for (const unit of UNITS) {
      const pos = {};
      for (let d = 1; d <= 9; d++) pos[d] = unit.filter(i => state.values[i] === 0 && state.cand[i] && state.cand[i].has(d));
      const digits = []; for (let d = 1; d <= 9; d++) if (pos[d].length === 2) digits.push(d);
      for (let a = 0; a < digits.length; a++) for (let b = a + 1; b < digits.length; b++) {
        const d1 = digits[a], d2 = digits[b];
        if (sameCells(pos[d1], pos[d2])) {
          const removals = [];
          for (const i of pos[d1]) for (const d of state.cand[i]) if (d !== d1 && d !== d2) removals.push({ cell: i, digit: d });
          if (removals.length) return { kind: "eliminate", removals, rank: 5, technique: "hidden_pair" };
        }
      }
    }
    return null;
  }
  function xWing(state) {
    for (let d = 1; d <= 9; d++) {
      // rows sharing the same two columns for digit d
      const rowPos = [];
      for (let r = 0; r < 9; r++) rowPos[r] = ROWS[r].filter(i => state.values[i] === 0 && state.cand[i] && state.cand[i].has(d)).map(i => i % 9);
      for (let r1 = 0; r1 < 9; r1++) for (let r2 = r1 + 1; r2 < 9; r2++) {
        if (rowPos[r1].length === 2 && sameCells(rowPos[r1], rowPos[r2])) {
          const [c1, c2] = rowPos[r1], removals = [];
          for (let r = 0; r < 9; r++) if (r !== r1 && r !== r2) for (const c of [c1, c2]) {
            const i = r * 9 + c;
            if (state.values[i] === 0 && state.cand[i] && state.cand[i].has(d)) removals.push({ cell: i, digit: d });
          }
          if (removals.length) return { kind: "eliminate", removals, rank: 6, technique: "x_wing" };
        }
      }
      // columns sharing the same two rows
      const colPos = [];
      for (let c = 0; c < 9; c++) colPos[c] = COLS[c].filter(i => state.values[i] === 0 && state.cand[i] && state.cand[i].has(d)).map(i => Math.floor(i / 9));
      for (let c1 = 0; c1 < 9; c1++) for (let c2 = c1 + 1; c2 < 9; c2++) {
        if (colPos[c1].length === 2 && sameCells(colPos[c1], colPos[c2])) {
          const [r1, r2] = colPos[c1], removals = [];
          for (let c = 0; c < 9; c++) if (c !== c1 && c !== c2) for (const r of [r1, r2]) {
            const i = r * 9 + c;
            if (state.values[i] === 0 && state.cand[i] && state.cand[i].has(d)) removals.push({ cell: i, digit: d });
          }
          if (removals.length) return { kind: "eliminate", removals, rank: 6, technique: "x_wing" };
        }
      }
    }
    return null;
  }

  // XY-Wing: pivot with candidates {X,Y}; two pincers {X,Z} and {Y,Z}, each a peer of the
  // pivot. Any cell seeing both pincers can't be Z.
  function xyWing(state) {
    const bivalue = [];
    for (let i = 0; i < 81; i++) if (state.values[i] === 0 && state.cand[i] && state.cand[i].size === 2) bivalue.push(i);
    for (const pivot of bivalue) {
      const [X, Y] = [...state.cand[pivot]];
      const pincers = bivalue.filter(j => j !== pivot && isPeer(pivot, j));
      for (let a = 0; a < pincers.length; a++) for (let b = 0; b < pincers.length; b++) {
        if (a === b) continue;
        const ca = state.cand[pincers[a]], cb = state.cand[pincers[b]];
        // pincer A = {X, Z}, pincer B = {Y, Z}
        if (!ca.has(X) || ca.has(Y)) continue;
        if (!cb.has(Y) || cb.has(X)) continue;
        const Za = [...ca].find(d => d !== X), Zb = [...cb].find(d => d !== Y);
        if (Za == null || Za !== Zb) continue;
        const Z = Za;
        const removals = [];
        for (const cell of commonPeers(pincers[a], pincers[b])) {
          if (cell === pivot) continue;
          if (state.values[cell] === 0 && state.cand[cell] && state.cand[cell].has(Z)) removals.push({ cell, digit: Z });
        }
        if (removals.length) return { kind: "eliminate", removals, rank: 7, technique: "xy_wing",
          note: `枢轴 ${RCLABEL(pivot)}{${X},${Y}} 与两翼 ${RCLABEL(pincers[a])}、${RCLABEL(pincers[b])} 构成 XY-Wing，排除 ${Z}` };
      }
    }
    return null;
  }

  // Swordfish: 3 rows where digit d sits in the same ≤3 columns (or transposed).
  function swordfish(state) {
    const scan = (lineCells, crossIndex) => {
      for (let d = 1; d <= 9; d++) {
        const pos = [];
        for (let l = 0; l < 9; l++) pos[l] = lineCells(l).filter(i => state.values[i] === 0 && state.cand[i] && state.cand[i].has(d)).map(crossIndex);
        const lines = [];
        for (let l = 0; l < 9; l++) if (pos[l].length >= 2 && pos[l].length <= 3) lines.push(l);
        for (let a = 0; a < lines.length; a++) for (let b = a + 1; b < lines.length; b++) for (let c = b + 1; c < lines.length; c++) {
          const cols = new Set([...pos[lines[a]], ...pos[lines[b]], ...pos[lines[c]]]);
          if (cols.size !== 3) continue;
          const lineSet = new Set([lines[a], lines[b], lines[c]]);
          const removals = [];
          for (const cross of cols) for (let l = 0; l < 9; l++) {
            if (lineSet.has(l)) continue;
            const i = lineCells(l)[cross];
            if (state.values[i] === 0 && state.cand[i] && state.cand[i].has(d)) removals.push({ cell: i, digit: d });
          }
          if (removals.length) return { kind: "eliminate", removals, rank: 8, technique: "swordfish",
            note: `数字 ${d} 在三条线上构成 Swordfish` };
        }
      }
      return null;
    };
    return scan(r => ROWS[r], i => i % 9) || scan(c => COLS[c], i => Math.floor(i / 9));
  }

  // XYZ-Wing: pivot {X,Y,Z} with two bivalue pincers {X,Z} and {Y,Z}, both peers of the
  // pivot. A cell seeing the pivot and both pincers can't be Z.
  function xyzWing(state) {
    for (let pivot = 0; pivot < 81; pivot++) {
      if (state.values[pivot] !== 0 || !state.cand[pivot] || state.cand[pivot].size !== 3) continue;
      const trip = [...state.cand[pivot]];
      const pincers = [];
      for (const j of PEERS[pivot]) if (state.values[j] === 0 && state.cand[j] && state.cand[j].size === 2 && [...state.cand[j]].every(d => trip.includes(d))) pincers.push(j);
      for (let a = 0; a < pincers.length; a++) for (let b = a + 1; b < pincers.length; b++) {
        const union = new Set([...state.cand[pincers[a]], ...state.cand[pincers[b]]]);
        if (union.size !== 3) continue;                         // together cover X,Y,Z
        const Z = [...state.cand[pincers[a]]].find(d => state.cand[pincers[b]].has(d));
        if (Z == null) continue;                                 // shared digit = Z
        const removals = [];
        for (const cell of PEERS[pivot]) {
          if (cell === pincers[a] || cell === pincers[b]) continue;
          if (!isPeer(cell, pincers[a]) || !isPeer(cell, pincers[b])) continue;
          if (state.values[cell] === 0 && state.cand[cell] && state.cand[cell].has(Z)) removals.push({ cell, digit: Z });
        }
        if (removals.length) return { kind: "eliminate", removals, rank: 7, technique: "xyz_wing",
          note: `枢轴 ${RCLABEL(pivot)} 与两翼 ${RCLABEL(pincers[a])}、${RCLABEL(pincers[b])} 构成 XYZ-Wing，排除 ${Z}` };
      }
    }
    return null;
  }


  const PLACERS = [nakedSingle, hiddenSingle];
  const ELIMERS = [lockedCandidates, nakedPair, hiddenPair, xWing, xyWing, xyzWing, swordfish];
  // Technique ladder tagged with rank, hardest-last.
  const LADDER = [
    { fn: nakedSingle, rank: 1 },
    { fn: hiddenSingle, rank: 2 },
    { fn: lockedCandidates, rank: 3 },
    { fn: nakedPair, rank: 4 },
    { fn: hiddenPair, rank: 5 },
    { fn: xWing, rank: 6 },
    { fn: xyWing, rank: 7 },
    { fn: xyzWing, rank: 7 },
    { fn: swordfish, rank: 8 },
  ];

  // --- Logical solver (for grading): returns {solved, maxRank}. maxRank caps techniques. ---
  function solveLogically(values, maxRank = 8) {
    const state = { values: values.slice(), cand: computeCands(values) };
    let used = 0;
    for (let guard = 0; guard < 2000; guard++) {
      if (state.values.every(v => v !== 0)) return { solved: true, maxRank: used };
      let step = null;
      for (const t of LADDER) { if (t.rank > maxRank) break; step = t.fn(state); if (step) break; }
      if (!step) return { solved: false, maxRank: used };
      used = Math.max(used, step.rank);
      applyStep(state, step);
    }
    return { solved: false, maxRank: used };
  }

  function gradeToBand(maxRank, solved) {
    if (!solved) return "master";
    if (maxRank <= 2) return "intro";
    if (maxRank <= 4) return "middle";
    if (maxRank === 5) return "hard";
    if (maxRank === 6) return "expert";
    return "master";
  }

  // --- Dig holes while the puzzle stays solvable within `ceil` techniques ---
  // Full logical solvability implies a unique solution, so no separate uniqueness pass needed.
  // Stops once `minGivens` is reached so easier levels keep more clues.
  function dig(solution, ceil, minGivens) {
    const puzzle = solution.slice();
    let givens = 81;
    for (const i of shuffle([...Array(81).keys()])) {
      if (givens <= minGivens) break;
      const saved = puzzle[i];
      puzzle[i] = 0;
      if (!solveLogically(puzzle, ceil).solved) puzzle[i] = saved; else givens--;
    }
    return puzzle;
  }

  // --- Difficulty = technique ceiling + a givens floor (fewer clues → harder feel). ---
  // `minRank` (master) forces the puzzle to actually require an advanced technique.
  const SETTINGS = {
    intro:  { ceil: 2, floor: 42 },
    middle: { ceil: 4, floor: 34 },
    hard:   { ceil: 5, floor: 30 },
    expert: { ceil: 6, floor: 26 },
    master: { ceil: 8, floor: 24, minRank: 7 },
  };
  function generatePuzzle(difficulty) {
    const cfg = SETTINGS[difficulty] || SETTINGS.middle;
    const { ceil, floor, minRank = 0 } = cfg;
    const CAP = minRank ? 60 : 1;
    let best = null;
    for (let attempt = 0; attempt < CAP; attempt++) {
      const solution = generateSolution();
      const puzzle = dig(solution, ceil, floor);
      const g = solveLogically(puzzle, ceil);
      const result = { puzzle, solution, difficulty, band: difficulty, grade: g.maxRank,
        givens: puzzle.filter(v => v !== 0).length };
      if (!best || result.grade > best.grade) best = result;
      if (g.maxRank >= minRank) return result;
    }
    return best; // hardest found within the attempt cap
  }

  // --- Hint: reveal one correct placement + the human reason ---
  // Uses the stored `solution` only for an error guard and a last-resort fallback; the
  // explanation itself comes from logic on the current board.
  function getHint(values, solution) {
    for (let i = 0; i < 81; i++) if (values[i] !== 0 && solution && values[i] !== solution[i]) {
      const [r, c] = rc(i);
      return { type: "error", cell: i, message: `R${r + 1}C${c + 1} 的 ${values[i]} 与本局唯一解冲突，请先修正后再提示。` };
    }
    if (values.every(v => v !== 0)) return { type: "done", message: "已经完成啦！" };

    const state = { values: values.slice(), cand: computeCands(values) };
    let elimNote = null;
    for (let guard = 0; guard < 300; guard++) {
      let placed = null;
      for (const t of PLACERS) { placed = t(state); if (placed) break; }
      if (placed) {
        const [r, c] = rc(placed.cell);
        let reason = placed.reason;
        if (elimNote) reason = `先用「${elimNote}」排除部分候选，随后 ` + reason;
        return { type: "place", cell: placed.cell, row: r + 1, col: c + 1, digit: placed.digit,
          technique: placed.technique, reason };
      }
      let elim = null;
      for (const t of ELIMERS) { elim = t(state); if (elim) break; }
      if (elim) { applyStep(state, elim); elimNote = elim.note || TECH_NAME[elim.technique] || elim.technique; continue; }
      break; // stuck for our technique set
    }
    // Fallback: the ladder can't progress — give the digit from the unique solution.
    if (solution) {
      const i = state.values.indexOf(0), [r, c] = rc(i);
      return { type: "place", cell: i, row: r + 1, col: c + 1, digit: solution[i], technique: "solution",
        reason: `R${r + 1}C${c + 1} 依据本局唯一解应填 ${solution[i]}（此步需要更高级技巧）。` };
    }
    return { type: "stuck", message: "暂时找不到确定的下一步。" };
  }

  const SudokuCore = {
    generatePuzzle, getHint, solveLogically, countSolutions, computeCands,
    UNITS, PEERS, ROWS, COLS, BOXES, rc,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = SudokuCore;
  if (typeof window !== "undefined") window.SudokuCore = SudokuCore;
})();
