#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chinese word-guessing game (Semantle-style).

A secret word is chosen. You guess words; the game reports how semantically
close your guess is (cosine similarity + closeness rank vs. the whole vocab).
"""

import argparse
import random
import sys
import time

import numpy as np
from gensim.models import KeyedVectors

from config import DEFAULT_VECTORS_PATH, DEFAULT_LIMIT
from engine import temperature_indicator
from words import CANDIDATE_WORDS

try:
    from opencc import OpenCC
    _t2s = OpenCC("t2s")
    def to_simplified(text: str) -> str:
        return _t2s.convert(text)
except ImportError:
    def to_simplified(text: str) -> str:
        return text


def parse_args():
    p = argparse.ArgumentParser(description="中文猜词游戏 — Chinese Word Guessing Game")
    p.add_argument(
        "--vectors",
        default=DEFAULT_VECTORS_PATH,
        help="Path to the word2vec-format vectors file.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Max number of vectors to load (file is freq-sorted; default 1M).",
    )
    p.add_argument("--answer", default=None, help="Set the secret word manually.")
    p.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
    return p.parse_args()


def load_vectors(path: str, limit: int):
    import os
    if not os.path.isfile(path):
        print(f"错误: 找不到向量文件 '{path}'")
        print("请先运行: bash download_vectors.sh")
        print("或使用 --vectors 指定正确路径。")
        sys.exit(1)

    cache_path = path + f".limit{limit}.kv"
    if os.path.isfile(cache_path):
        print(f"正在加载缓存 (Loading cache: {cache_path}) ...")
        t0 = time.time()
        kv = KeyedVectors.load(cache_path)
        elapsed = time.time() - t0
        print(f"已加载 {len(kv)} 个词, 维度 {kv.vector_size}, 耗时 {elapsed:.1f}s")
        return kv

    print(f"正在加载词向量 (Loading vectors from {path}) ...")
    print("  首次加载较慢，之后将使用缓存。")
    t0 = time.time()
    kv = KeyedVectors.load_word2vec_format(
        path, binary=False, limit=limit, unicode_errors="ignore"
    )
    elapsed = time.time() - t0
    print(f"已加载 {len(kv)} 个词, 维度 {kv.vector_size}, 耗时 {elapsed:.1f}s")

    print(f"正在保存缓存 (Saving cache for fast reload) ...")
    kv.save(cache_path)
    print(f"缓存已保存: {cache_path}")
    return kv


def precompute_ranks(kv: KeyedVectors, secret: str):
    print("正在计算相似度排名 (Precomputing ranks) ...")
    t0 = time.time()
    secret_vec = kv.get_vector(secret, norm=True)
    all_norms = kv.get_normed_vectors()
    similarities = all_norms @ secret_vec
    ranked_indices = np.argsort(-similarities)
    rank_map = {}
    for rank, idx in enumerate(ranked_indices):
        rank_map[kv.index_to_key[idx]] = (rank, float(similarities[idx]))
    elapsed = time.time() - t0
    print(f"排名计算完成, 耗时 {elapsed:.1f}s")
    return rank_map


def print_guess_result(word: str, similarity: float, rank: int, total: int, guess_num: int):
    pct = similarity * 100
    percentile = (1 - rank / total) * 100
    temp = temperature_indicator(rank)
    print(f"  #{guess_num:<4} {word:<8}  相似度: {pct:6.2f}%  "
          f"排名: 第{rank}近 / 共{total}词 (超过{percentile:.1f}%的词)  {temp}")


def print_history(history: list):
    if not history:
        return
    print("\n  ---- 猜测历史 (按相似度排序) ----")
    sorted_h = sorted(history, key=lambda x: -x[1])
    for i, (word, sim, rank, num) in enumerate(sorted_h[:15]):
        pct = sim * 100
        temp = temperature_indicator(rank)
        print(f"  {i+1:>3}. #{num:<4} {word:<8} {pct:6.2f}%  第{rank}近  {temp}")
    if len(history) > 15:
        print(f"  ... 还有 {len(history) - 15} 条记录")
    print()


def play_round(kv: KeyedVectors, secret: str):
    """Play one round of the guessing game. Returns when round ends."""
    rank_map = precompute_ranks(kv, secret)
    total = len(rank_map)

    print()
    print("  " + "-" * 40)
    print(f"  词表大小: {total} 词")
    print(f"  答案已设定。开始猜吧！")
    print()
    print("  输入猜测的词，或使用命令:")
    print("    :hint  - 显示一个提示 (接近答案的词)")
    print("    :top   - 显示当前最接近的猜测")
    print("    :give  - 放弃 (显示答案)")
    print("    :quit  - 返回主菜单")
    print("  " + "-" * 40)
    print()

    history = []
    guessed_words = set()
    guess_count = 0

    while True:
        try:
            raw = input("猜一个词> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not raw:
            continue

        if raw == ":quit":
            print(f"  答案是: {secret}")
            return

        if raw == ":give":
            print(f"\n  🎯 答案是: {secret}")
            print(f"  你一共猜了 {guess_count} 次。")
            return

        if raw == ":hint":
            hint_rank = max(1, min(len(history) * 2 + 10, 50))
            for word, (r, _) in rank_map.items():
                if r == hint_rank and word != secret and word not in guessed_words:
                    print(f"  💡 提示: 第{hint_rank}接近答案的词是 「{word}」")
                    break
            else:
                print("  💡 试试猜一些常见名词吧！")
            continue

        if raw == ":top":
            print_history(history)
            continue

        word = to_simplified(raw)

        if word not in kv:
            print(f"  ⚠️  「{raw}」不在词表中，换个更常见的词试试。")
            continue

        if word in guessed_words:
            r, sim = rank_map[word]
            print(f"  ⚠️  你已经猜过「{word}」了 (相似度 {sim*100:.2f}%, 第{r}近)")
            continue

        guess_count += 1
        guessed_words.add(word)
        rank, similarity = rank_map[word]

        print_guess_result(word, similarity, rank, total, guess_count)
        history.append((word, similarity, rank, guess_count))

        if word == secret:
            print()
            print("  🎉🎉🎉 恭喜！你猜对了！")
            print(f"  答案: {secret}")
            print(f"  总共猜了 {guess_count} 次")
            print()
            return


def show_menu():
    print()
    print("=" * 60)
    print("  🎯 中文猜词游戏 (Chinese Word Guessing Game)")
    print("=" * 60)
    print("  [1] 随机猜词 (Random word)")
    print("  [2] 自定义猜词 (Custom word)")
    print("  [3] 退出 (Exit)")
    print("=" * 60)


def main_menu(kv: KeyedVectors, valid_candidates: list):
    """Main menu loop. Blocks on input() when idle — no CPU usage."""
    while True:
        show_menu()
        try:
            choice = input("\n请选择> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            return

        if choice == "1":
            secret = random.choice(valid_candidates)
            play_round(kv, secret)

        elif choice == "2":
            try:
                raw = input("请输入答案词> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                continue
            if not raw:
                continue
            word = to_simplified(raw)
            if word not in kv:
                print(f"  ⚠️  「{raw}」不在词表中，请换一个词。")
                continue
            play_round(kv, word)

        elif choice == "3":
            print("  再见！")
            return

        else:
            print("  请输入 1、2 或 3。")


def main():
    args = parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    kv = load_vectors(args.vectors, args.limit)

    valid_candidates = [w for w in CANDIDATE_WORDS if w in kv]
    if not valid_candidates:
        print("错误: 候选词列表中没有词在词表里。请检查向量文件。")
        sys.exit(1)

    # If --answer is given, play one round directly then go to menu.
    if args.answer:
        secret = to_simplified(args.answer.strip())
        if secret not in kv:
            print(f"错误: 答案 '{secret}' 不在词表中。请换一个词。")
            sys.exit(1)
        play_round(kv, secret)

    main_menu(kv, valid_candidates)


if __name__ == "__main__":
    main()
