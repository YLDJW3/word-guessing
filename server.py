#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multiplayer Chinese word-guessing game — FastAPI + WebSocket server."""

import argparse
import os
import random
import secrets
import string
import sys
import time
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

import stats
from config import (
    DEFAULT_VECTORS_PATH, DEFAULT_LIMIT, DEFAULT_HOST, DEFAULT_PORT,
    ROOM_ID_LENGTH, MAX_NAME_LENGTH, MAX_ROOMS,
    HINT_INTERVAL, HINT_CAP_DELTA, MIN_HINT_RANK,
    STATS_DB_PATH, REVEAL_TOP_N,
    CHAT_HISTORY, MAX_CHAT_LEN,
)
from engine import GameEngine, to_simplified
from words import CANDIDATE_WORDS

# ---------------------------------------------------------------------------
# Globals (initialized at startup)
# ---------------------------------------------------------------------------
engine: GameEngine = None  # type: ignore
valid_candidates: list[str] = []

# Optional nickname allowlist (lowercased). Empty set = anyone may enter.
allowed_names: set[str] = set()

# Secret token gating the admin stats page/API. Set at startup.
admin_token: str = ""


def check_admin(key: str) -> bool:
    return bool(admin_token) and secrets.compare_digest(key, admin_token)

# Hint tuning (HINT_INTERVAL, HINT_CAP_DELTA, MIN_HINT_RANK) is imported from config.
# They remain module globals here so tests can still override e.g. server.HINT_INTERVAL.

# ---------------------------------------------------------------------------
# Room model
# ---------------------------------------------------------------------------

@dataclass
class Room:
    room_id: str
    secret: str
    rank_map: dict
    mode: str  # "competitive" or "cooperative"
    host: str
    custom: bool = False  # True when the host set the secret (custom-word room)
    players: dict[str, WebSocket] = field(default_factory=dict)
    player_guesses: dict[str, list] = field(default_factory=dict)
    shared_guesses: list = field(default_factory=list)
    winner: str | None = None
    created_at: float = field(default_factory=time.time)
    chat: list = field(default_factory=list)  # recent chat messages {player, text, ts}
    # Hint tracking. Milestone = how many HINT_INTERVAL blocks have been consumed.
    hint_used_milestone: dict[str, int] = field(default_factory=dict)  # competitive, per player
    coop_hint_used_milestone: int = 0  # cooperative, shared

rooms: dict[str, Room] = {}

# Active player nicknames across all connections (case-insensitive uniqueness).
active_names: set[str] = set()


def generate_room_id() -> str:
    while True:
        rid = "".join(random.choices(string.ascii_uppercase + string.digits, k=ROOM_ID_LENGTH))
        if rid not in rooms:
            return rid


def evict_old_rooms() -> None:
    """Keep at most MAX_ROOMS rooms as rejoinable history. Evict the oldest rooms with no
    connected players first (dict is insertion-ordered); never kick an active room, so a
    transient overflow is possible if all rooms are occupied."""
    while len(rooms) > MAX_ROOMS:
        victim = next((rid for rid, room in rooms.items() if not room.players), None)
        if victim is None:
            break
        rooms.pop(victim, None)


async def broadcast(room: Room, message: dict, exclude: str | None = None):
    """Send a JSON message to all players in a room."""
    disconnected = []
    for name, ws in room.players.items():
        if name == exclude:
            continue
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(name)
    for name in disconnected:
        del room.players[name]


def build_scoreboard(room: Room) -> list[dict]:
    """Competitive standings: each player's best rank/similarity and guess count.
    The actual word is deliberately omitted (would leak opponents' guesses)."""
    scoreboard = []
    for pname, guesses in room.player_guesses.items():
        if guesses:
            best = min(guesses, key=lambda g: g["rank"])
            scoreboard.append({
                "name": pname,
                "best_rank": best["rank"],
                "best_similarity": best["similarity"],
                "guess_count": len(guesses),
            })
    scoreboard.sort(key=lambda s: s["best_rank"])
    return scoreboard


def is_spectator(room: Room, name: str) -> bool:
    """The host of a custom competitive room is a quizmaster: they set the word, so they
    watch (see everyone's guesses) instead of playing."""
    return room.custom and room.mode == "competitive" and name == room.host


def all_guesses(room: Room) -> list[dict]:
    """Every guess made in the room (each carries a `player` field)."""
    if room.mode == "cooperative":
        return list(room.shared_guesses)
    return [g for gs in room.player_guesses.values() for g in gs]


def build_reveal(room: Room) -> dict:
    """Post-game reveal: the closest words to the answer + everyone's guess paths."""
    top = sorted(
        ((w, r, s) for w, (r, s) in room.rank_map.items() if 1 <= r <= REVEAL_TOP_N),
        key=lambda x: x[1],
    )
    top_words = [{"word": w, "rank": r, "similarity": round(s * 100, 2)} for w, r, s in top]
    return {"top_words": top_words, "guesses": all_guesses(room)}


# ---------------------------------------------------------------------------
# Hint accounting
# ---------------------------------------------------------------------------

def guess_count_for(room: Room, player: str) -> int:
    if room.mode == "cooperative":
        return len(room.shared_guesses)
    return len(room.player_guesses.get(player, []))


def per_player_guess_counts(room: Room) -> dict[str, int]:
    """Guesses made by each participant (everyone who joined the room)."""
    counts = {}
    for player in room.player_guesses.keys():
        if room.mode == "cooperative":
            counts[player] = sum(1 for g in room.shared_guesses if g["player"] == player)
        else:
            counts[player] = len(room.player_guesses[player])
    return counts


def used_milestone(room: Room, player: str) -> int:
    if room.mode == "cooperative":
        return room.coop_hint_used_milestone
    return room.hint_used_milestone.get(player, 0)


def hint_available(room: Room, player: str) -> bool:
    return guess_count_for(room, player) // HINT_INTERVAL > used_milestone(room, player)


def guesses_to_next_hint(room: Room, player: str) -> int:
    if hint_available(room, player):
        return 0
    count = guess_count_for(room, player)
    return (used_milestone(room, player) + 1) * HINT_INTERVAL - count


def hint_status_msg(room: Room, player: str) -> dict:
    return {
        "type": "hint_status",
        "available": hint_available(room, player),
        "next_in": guesses_to_next_hint(room, player),
    }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="中文猜词游戏")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def html(name: str) -> FileResponse:
    # no-cache: browsers must revalidate, so HTML edits show up without a manual cache clear.
    return FileResponse(os.path.join(STATIC_DIR, name), headers={"Cache-Control": "no-cache"})


@app.get("/")
async def index():
    return html("index.html")


@app.get("/word")
async def word_game():
    return html("index.html")


@app.get("/sudoku")
async def sudoku():
    return html("sudoku.html")


@app.get("/api/rooms")
async def list_rooms():
    # Recent rooms as rejoinable history — newest first, including empty and finished.
    result = []
    for rid, room in rooms.items():
        result.append({
            "room_id": rid,
            "mode": room.mode,
            "player_count": len(room.players),
            "host": room.host,
            "finished": room.winner is not None,
        })
    result.reverse()
    return result


@app.get("/admin")
async def admin_page(key: str = ""):
    if not check_admin(key):
        raise HTTPException(status_code=403, detail="Forbidden")
    return html("admin.html")


@app.get("/api/stats/players")
async def stats_players():
    # Public: player win/loss leaderboard (no answers revealed).
    return stats.get_player_stats()


@app.get("/api/stats/games")
async def stats_games(key: str = "", limit: int = 50):
    if not check_admin(key):
        raise HTTPException(status_code=403, detail="Forbidden")
    return stats.get_recent_games(limit)


# Mount static files (CSS, JS if any) after explicit routes
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# Catch-all deep link: /{name} serves the SPA, which reads the nickname from the path.
# Declared last so explicit routes (/, /admin, /api/*) and /static win first. A path param
# without a :path converter matches only a single segment, so /api/stats/* etc. never hit it.
@app.get("/{name}")
async def named_entry(name: str):
    return html("index.html")


# ---------------------------------------------------------------------------
# WebSocket game endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    player_name: str | None = None
    current_room: Room | None = None

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "set_name":
                requested = data.get("name", "").strip()[:MAX_NAME_LENGTH]
                reclaim = data.get("reclaim", False)  # reconnect: same person taking name back
                if not requested:
                    await ws.send_json({"type": "error", "message": "请输入昵称"})
                    continue
                # Enforce the allowlist if one is configured (applies to reclaim too).
                if allowed_names and requested.lower() not in allowed_names:
                    await ws.send_json({"type": "error", "message": f"昵称「{requested}」不在允许名单中"})
                    continue
                # Reject if the name is in use by another connection — unless this is a
                # reconnect reclaiming its own name.
                if not reclaim and requested.lower() in active_names and requested != player_name:
                    await ws.send_json({"type": "error", "message": f"昵称「{requested}」已被占用，请换一个"})
                    continue
                # Release the previous name if this connection is renaming.
                if player_name:
                    active_names.discard(player_name.lower())
                player_name = requested
                active_names.add(player_name.lower())
                await ws.send_json({"type": "name_set", "name": player_name})

            elif msg_type == "create_room":
                if not player_name:
                    await ws.send_json({"type": "error", "message": "请先设置昵称"})
                    continue

                mode = data.get("mode", "competitive")
                if mode not in ("competitive", "cooperative"):
                    mode = "competitive"

                custom_word = data.get("secret", "").strip()
                if custom_word:
                    word = engine.validate_word(custom_word)
                    if word is None:
                        await ws.send_json({"type": "error", "message": f"「{custom_word}」不在词表中"})
                        continue
                    secret = word
                else:
                    secret = random.choice(valid_candidates)

                room_id = generate_room_id()
                rank_map = engine.compute_rank_map(secret)
                room = Room(
                    room_id=room_id,
                    secret=secret,
                    rank_map=rank_map,
                    mode=mode,
                    host=player_name,
                    custom=bool(custom_word),
                )
                room.players[player_name] = ws
                spectator = is_spectator(room, player_name)
                if not spectator:
                    room.player_guesses[player_name] = []
                rooms[room_id] = room
                evict_old_rooms()  # keep the room history bounded
                current_room = room

                payload = {
                    "type": "room_joined",
                    "room_id": room_id,
                    "mode": mode,
                    "players": list(room.players.keys()),
                    "total_words": engine.total,
                    "is_host": True,
                    "custom": room.custom,
                    "spectator": spectator,
                    "chat": room.chat,
                }
                if spectator:
                    payload["answer"] = room.secret  # host set it, so reveal to them
                await ws.send_json(payload)
                await ws.send_json(hint_status_msg(room, player_name))

            elif msg_type == "join_room":
                if not player_name:
                    await ws.send_json({"type": "error", "message": "请先设置昵称"})
                    continue

                room_id = data.get("room_id", "").strip().upper()
                if room_id not in rooms:
                    await ws.send_json({"type": "error", "message": f"房间 {room_id} 不存在"})
                    continue

                room = rooms[room_id]
                # Finished rooms are rejoinable (read-only result); empty unfinished rooms
                # are rejoinable to continue. Register / take over the socket either way.
                room.players[player_name] = ws
                spectator = is_spectator(room, player_name)
                # setdefault preserves the player's guess history across a reconnect; the
                # spectator host is never enrolled as a guesser.
                if not spectator:
                    room.player_guesses.setdefault(player_name, [])
                current_room = room

                if room.winner is not None or room.mode == "cooperative" or spectator:
                    # Finished (reveal), coop, and the quizmaster all see every guess.
                    history = all_guesses(room)
                else:
                    history = room.player_guesses.get(player_name, [])
                payload = {
                    "type": "room_joined",
                    "room_id": room_id,
                    "mode": room.mode,
                    "players": list(room.players.keys()),
                    "total_words": engine.total,
                    "is_host": player_name == room.host,
                    "history": history,
                    "finished": room.winner is not None,
                    "custom": room.custom,
                    "spectator": spectator,
                    "chat": room.chat,
                }
                if room.winner is not None or spectator:
                    payload["answer"] = room.secret
                if room.winner is not None:
                    payload["winner"] = room.winner
                    payload["winner_guesses"] = guess_count_for(room, room.winner)
                    payload["top_words"] = build_reveal(room)["top_words"]
                await ws.send_json(payload)

                await ws.send_json(hint_status_msg(room, player_name))

                # Standings for a (re)joining competitive player — live or final.
                if room.mode == "competitive":
                    await ws.send_json({"type": "scoreboard", "scoreboard": build_scoreboard(room)})

                await broadcast(room, {
                    "type": "player_joined",
                    "name": player_name,
                    "players": list(room.players.keys()),
                }, exclude=player_name)

            elif msg_type == "guess":
                if not current_room or not player_name:
                    await ws.send_json({"type": "error", "message": "你不在任何房间中"})
                    continue

                room = current_room
                if room.winner:
                    await ws.send_json({"type": "error", "message": "游戏已结束"})
                    continue

                if is_spectator(room, player_name):
                    await ws.send_json({"type": "error", "message": "你是出题者，无法猜词"})
                    continue

                raw = data.get("word", "").strip()
                if not raw:
                    continue

                word = engine.validate_word(raw)
                if word is None:
                    await ws.send_json({"type": "not_in_vocab", "word": raw})
                    continue

                # Check duplicate
                if room.mode == "competitive":
                    already = any(g["word"] == word for g in room.player_guesses[player_name])
                else:
                    already = any(g["word"] == word for g in room.shared_guesses)

                if already:
                    rank, sim = room.rank_map[word]
                    await ws.send_json({
                        "type": "already_guessed",
                        "word": word,
                        "similarity": round(sim * 100, 2),
                        "rank": rank,
                    })
                    continue

                result = engine.score_guess(word, room.rank_map)
                result["player"] = player_name
                result["type"] = "guess_result"

                if room.mode == "cooperative":
                    room.shared_guesses.append(result)
                    await broadcast(room, result)
                    # Shared counter — refresh hint status for everyone.
                    await broadcast(room, hint_status_msg(room, player_name))
                else:
                    room.player_guesses[player_name].append(result)
                    await ws.send_json(result)
                    await ws.send_json(hint_status_msg(room, player_name))
                    await broadcast(room, {"type": "scoreboard", "scoreboard": build_scoreboard(room)})
                    # Custom room: the quizmaster host watches every player's guesses.
                    if room.custom and room.host != player_name:
                        host_ws = room.players.get(room.host)
                        if host_ws is not None:
                            try:
                                await host_ws.send_json(result)
                            except Exception:
                                pass

                # Check win
                if result["is_answer"]:
                    room.winner = player_name
                    await broadcast(room, {
                        "type": "game_won",
                        "winner": player_name,
                        "word": word,
                        "guesses": guess_count_for(room, player_name),
                    })
                    # Post-game reveal: everyone's guesses + the closest words to the answer.
                    await broadcast(room, {"type": "reveal", "answer": room.secret, **build_reveal(room)})
                    # Persist the finished game (runs once — later guesses short-circuit).
                    try:
                        stats.record_game(
                            room_id=room.room_id,
                            mode=room.mode,
                            answer=room.secret,
                            host=room.host,
                            winner=player_name,
                            player_guesses=per_player_guess_counts(room),
                            started_at=room.created_at,
                            finished_at=time.time(),
                        )
                    except Exception as e:
                        print(f"Failed to record game stats: {e}")

            elif msg_type == "hint":
                if not current_room or not player_name:
                    continue
                room = current_room
                if room.winner:
                    continue

                if not hint_available(room, player_name):
                    n = guesses_to_next_hint(room, player_name)
                    await ws.send_json({
                        "type": "hint_unavailable",
                        "message": f"还需 {n} 次猜测才能获得提示",
                    })
                    continue

                # Relevant guess set (shared vs the player's own).
                if room.mode == "cooperative":
                    guesses = room.shared_guesses
                else:
                    guesses = room.player_guesses.get(player_name, [])

                exclude = {g["word"] for g in guesses}
                best_cos = max(room.rank_map[g["word"]][1] for g in guesses)
                best_rank = min(room.rank_map[g["word"]][0] for g in guesses)

                # Too close: within the rank buffer, any hint would spoil. Don't consume.
                if best_rank <= MIN_HINT_RANK:
                    await ws.send_json({
                        "type": "hint_unavailable",
                        "message": f"你已进入前{MIN_HINT_RANK}名，提示已关闭",
                    })
                    continue

                hint_word = engine.get_capped_hint(
                    room.rank_map, best_cos, HINT_CAP_DELTA, room.secret, exclude,
                    min_rank=MIN_HINT_RANK,
                )

                if hint_word is None:
                    # No suitable word in the band — do not consume the hint.
                    await ws.send_json({
                        "type": "hint_unavailable",
                        "message": "附近暂无合适提示词",
                    })
                    continue

                # Consume the hint for the current milestone.
                milestone = guess_count_for(room, player_name) // HINT_INTERVAL
                if room.mode == "cooperative":
                    room.coop_hint_used_milestone = milestone
                else:
                    room.hint_used_milestone[player_name] = milestone

                hint = engine.score_guess(hint_word, room.rank_map)
                hint["type"] = "hint"
                hint["requested_by"] = player_name

                if room.mode == "cooperative":
                    await broadcast(room, hint)
                    await broadcast(room, hint_status_msg(room, player_name))
                else:
                    await ws.send_json(hint)
                    await ws.send_json(hint_status_msg(room, player_name))

            elif msg_type == "chat":
                if not current_room or not player_name:
                    continue
                text = data.get("text", "").strip()[:MAX_CHAT_LEN]
                if not text:
                    continue
                room = current_room
                message = {"type": "chat", "player": player_name, "text": text, "ts": time.time()}
                room.chat.append(message)
                del room.chat[:-CHAT_HISTORY]  # keep only the most recent
                await broadcast(room, message)

            elif msg_type == "leave_room":
                if current_room and player_name:
                    room = current_room
                    room.players.pop(player_name, None)
                    # Room is kept as rejoinable history (evicted only when over capacity).
                    await broadcast(room, {
                        "type": "player_left",
                        "name": player_name,
                        "players": list(room.players.keys()),
                    })
                    current_room = None
                await ws.send_json({"type": "left_room"})

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # Network drop (e.g. phone lock) or tab close: remove the player but keep the room
        # as history so they (or others) can rejoin it later.
        if current_room and player_name:
            current_room.players.pop(player_name, None)
            await broadcast(current_room, {
                "type": "player_left",
                "name": player_name,
                "players": list(current_room.players.keys()),
            })
        if player_name:
            active_names.discard(player_name.lower())


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def load_engine(vectors_path: str, limit: int) -> GameEngine:
    from gensim.models import KeyedVectors

    cache_path = vectors_path + f".limit{limit}.kv"
    if os.path.isfile(cache_path):
        print(f"Loading cache: {cache_path} ...")
        t0 = time.time()
        kv = KeyedVectors.load(cache_path)
        print(f"Loaded {len(kv)} words, dim={kv.vector_size}, {time.time()-t0:.1f}s")
        return GameEngine(kv)

    if not os.path.isfile(vectors_path):
        print(f"Error: vectors file not found: {vectors_path}")
        print("Run: bash download_vectors.sh")
        sys.exit(1)

    print(f"Loading vectors: {vectors_path} (first load is slow) ...")
    t0 = time.time()
    kv = KeyedVectors.load_word2vec_format(
        vectors_path, binary=False, limit=limit, unicode_errors="ignore"
    )
    print(f"Loaded {len(kv)} words, dim={kv.vector_size}, {time.time()-t0:.1f}s")

    print("Saving cache ...")
    kv.save(cache_path)
    return GameEngine(kv)


def main():
    parser = argparse.ArgumentParser(description="Word Guess Server")
    parser.add_argument("--vectors", default=DEFAULT_VECTORS_PATH)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--allow-names", default="",
                        help="Comma-separated nickname allowlist. If set, only these names may enter.")
    parser.add_argument("--allow-names-file", default="",
                        help="Path to a file with one allowed nickname per line.")
    parser.add_argument("--stats-db", default=STATS_DB_PATH,
                        help="Path to the SQLite stats database.")
    parser.add_argument("--admin-token", default="",
                        help="Secret token for the admin stats page. Auto-generated if omitted.")
    args = parser.parse_args()

    global engine, valid_candidates, allowed_names, admin_token

    names = [n.strip() for n in args.allow_names.split(",") if n.strip()]
    if args.allow_names_file:
        with open(args.allow_names_file, encoding="utf-8") as f:
            names += [line.strip() for line in f if line.strip()]
    allowed_names = {n.lower() for n in names}

    admin_token = args.admin_token or secrets.token_urlsafe(16)

    stats.init_db(args.stats_db)

    engine = load_engine(args.vectors, args.limit)
    valid_candidates = [w for w in CANDIDATE_WORDS if engine.validate_word(w)]

    if not valid_candidates:
        print("Error: no candidate words found in vocabulary")
        sys.exit(1)

    print(f"\nStarting server at http://{args.host}:{args.port}")
    print(f"Candidates: {len(valid_candidates)} words ready")
    if allowed_names:
        print(f"Name allowlist active: {len(allowed_names)} names permitted")
    else:
        print("Name allowlist: disabled (anyone may enter)")
    print(f"Admin stats page: http://{args.host}:{args.port}/admin?key={admin_token}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
