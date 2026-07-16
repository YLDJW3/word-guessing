# -*- coding: utf-8 -*-
"""Persistent game statistics via SQLite.

Records one row per finished game plus a row per participant, and exposes
per-player aggregates (games played, wins) and a recent-games feed.

Uses a connection per call — simple and safe for this game's low write volume.
"""

import sqlite3

_DB_PATH = "data/stats.db"


def _connect():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str) -> None:
    """Create the stats tables if they don't exist. Sets the module DB path."""
    global _DB_PATH
    _DB_PATH = path
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT,
                mode TEXT,
                answer TEXT,
                host TEXT,
                winner TEXT,
                winner_guesses INTEGER,
                total_guesses INTEGER,
                num_players INTEGER,
                started_at REAL,
                finished_at REAL
            );
            CREATE TABLE IF NOT EXISTS game_players (
                game_id INTEGER,
                player TEXT,
                guesses INTEGER,
                is_winner INTEGER
            );
            """
        )


def record_game(*, room_id: str, mode: str, answer: str, host: str, winner: str,
                player_guesses: dict[str, int], started_at: float,
                finished_at: float) -> None:
    """Insert one finished game and its per-player rows in a single transaction.

    player_guesses maps each participant's name to how many guesses they made.
    """
    total_guesses = sum(player_guesses.values())
    winner_guesses = player_guesses.get(winner, 0)
    num_players = len(player_guesses)

    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO games (room_id, mode, answer, host, winner,
                   winner_guesses, total_guesses, num_players, started_at, finished_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (room_id, mode, answer, host, winner, winner_guesses, total_guesses,
             num_players, started_at, finished_at),
        )
        game_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO game_players (game_id, player, guesses, is_winner) VALUES (?, ?, ?, ?)",
            [(game_id, p, g, 1 if p == winner else 0) for p, g in player_guesses.items()],
        )


def get_player_stats() -> list[dict]:
    """Per-player aggregates: games played and wins, most wins first."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT player, COUNT(*) AS played, SUM(is_winner) AS wins
               FROM game_players
               GROUP BY player COLLATE NOCASE
               ORDER BY wins DESC, played DESC"""
        ).fetchall()
    return [{"player": r["player"], "played": r["played"], "wins": r["wins"]} for r in rows]


def get_recent_games(limit: int = 50) -> list[dict]:
    """Recent finished games (newest first), each with its participant list."""
    with _connect() as conn:
        games = conn.execute(
            "SELECT * FROM games ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for g in games:
            players = conn.execute(
                "SELECT player FROM game_players WHERE game_id = ? ORDER BY is_winner DESC",
                (g["id"],),
            ).fetchall()
            row = dict(g)
            row["players"] = [p["player"] for p in players]
            result.append(row)
    return result
