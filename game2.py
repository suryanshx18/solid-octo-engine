"""
game2.py
========
Games implemented here:
  1. Antakshari    - word-chain game validated on the last letter/sound
  2. Cards         - High Card mode + a non-gambling Blackjack practice mode
  3. Make The Box  - dots-and-boxes grid strategy game
"""

from __future__ import annotations

import asyncio
import logging
import random
import string
from typing import Optional

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database as db
from game1 import BaseGame, display_name, safe_reply_markup

logger = logging.getLogger("games_bot.game2")


# ==========================================================================
# 1. ANTAKSHARI
# ==========================================================================

VOWELS_HINT = "Any real word is accepted as long as it starts with the required letter."


class AntakshariGame(BaseGame):
    key = "antakshari"
    display_name_ = "Antakshari"
    emoji = "🎵"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.turn_order: list[int] = []
        self.turn_index = 0
        self.alive: set[int] = set()
        self.used_words: set[str] = set()
        self.required_letter: str = ""
        self.scores: dict[int, int] = {}
        self.turn_token = 0

    async def on_start(self) -> None:
        self.turn_order = list(self.players.keys())
        random.shuffle(self.turn_order)
        self.alive = set(self.turn_order)
        self.scores = {uid: 0 for uid in self.players}
        self.required_letter = random.choice(string.ascii_uppercase)
        await self.bot.send_message(
            self.chat_id,
            f"🎵 ANTAKSHARI STARTED!\n\n{VOWELS_HINT}\n"
            f"No repeating a word already used this game.\n"
            f"You have {db.TURN_TIMEOUT}s per turn or you're eliminated!",
        )
        await self._announce_turn()

    def _current(self) -> int:
        return self.turn_order[self.turn_index]

    async def _announce_turn(self) -> None:
        current = self._current()
        await self.bot.send_message(
            self.chat_id,
            f"🎯 {display_name(current, self.players)}'s turn!\n"
            f"Send a word starting with letter '{self.required_letter}'.",
        )
        self.turn_token += 1
        self.track(self._turn_timeout(self.turn_token))

    async def _turn_timeout(self, token: int) -> None:
        try:
            await asyncio.sleep(db.TURN_TIMEOUT)
            if self.status == "running" and self.turn_token == token:
                current = self._current()
                await self.bot.send_message(
                    self.chat_id, f"⏰ {display_name(current, self.players)} ran out of time and is eliminated!"
                )
                await self._eliminate(current)
        except asyncio.CancelledError:
            pass

    async def _eliminate(self, user_id: int) -> None:
        self.alive.discard(user_id)
        if len(self.alive) <= 1:
            await self._finish()
            return
        self._advance_turn()
        await self._announce_turn()

    def _advance_turn(self) -> None:
        n = len(self.turn_order)
        for _ in range(n):
            self.turn_index = (self.turn_index + 1) % n
            if self.turn_order[self.turn_index] in self.alive:
                return

    async def handle_message(self, message: Message) -> None:
        if self.status != "running":
            return
        if message.from_user.id != self._current():
            return
        word = (message.text or "").strip()
        if not word or not word[0].isalpha():
            return
        first_letter = word[0].upper()
        norm = word.lower()

        if first_letter != self.required_letter:
            await message.reply(f"❌ Word must start with '{self.required_letter}'. Try again!")
            return
        if norm in self.used_words:
            await message.reply("❌ That word was already used. Try another!")
            return

        self.used_words.add(norm)
        self.scores[message.from_user.id] = self.scores.get(message.from_user.id, 0) + 1
        self.required_letter = word[-1].upper() if word[-1].isalpha() else self.required_letter
        await message.reply(f"✅ Nice! Next letter: '{self.required_letter}'")
        self._advance_turn()
        await self._announce_turn()

    async def handle_callback(self, callback: CallbackQuery, parts: list[str]) -> None:
        return  # antakshari is fully message-driven

    async def _finish(self) -> None:
        self.status = "ended"
        self.cancel_tasks()
        winner_id = next(iter(self.alive), None)
        lines = ["🎵 ANTAKSHARI - FINISHED!", ""]
        for uid in self.players:
            lines.append(f"{display_name(uid, self.players)}: {self.scores.get(uid, 0)} word(s)")
        lines.append("")
        if winner_id:
            lines.append(f"🏆 Winner: {display_name(winner_id, self.players)}!")
        for uid in self.players:
            won = uid == winner_id
            coins = db.REWARDS["first"] if won else max(db.REWARDS["participation"], self.scores.get(uid, 0) * 20)
            await self.award(uid, coins, won)
            lines.append(f"💰 {display_name(uid, self.players)} earned {coins} coins")
        db.record_game_result(self.chat_id, self.key, winner_id, list(self.players.keys()))
        await self.bot.send_message(self.chat_id, "\n".join(lines))
        await self.cleanup()


# ==========================================================================
# 2. CARDS  (High Card mode + Blackjack practice mode)
# ==========================================================================

SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
RANK_VALUE = {r: i for i, r in enumerate(RANKS, start=2)}
BJ_VALUE = {**{str(n): n for n in range(2, 11)}, "J": 10, "Q": 10, "K": 10, "A": 11}


def fresh_deck() -> list[tuple[str, str]]:
    deck = [(r, s) for r in RANKS for s in SUITS]
    random.shuffle(deck)
    return deck


def card_str(card: tuple[str, str]) -> str:
    return f"{card[0]}{card[1]}"


def bj_hand_value(hand: list[tuple[str, str]]) -> int:
    total = sum(BJ_VALUE[c[0]] for c in hand)
    aces = sum(1 for c in hand if c[0] == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


class CardsGame(BaseGame):
    key = "cards"
    display_name_ = "Cards"
    emoji = "🃏"

    def __init__(self, *a, mode: str = "highcard", **kw):
        super().__init__(*a, **kw)
        self.mode = mode if mode in ("highcard", "blackjack") else "highcard"
        self.deck: list[tuple[str, str]] = []
        # blackjack state
        self.order: list[int] = []
        self.idx = 0
        self.hands: dict[int, list[tuple[str, str]]] = {}
        self.dealer_hand: list[tuple[str, str]] = []
        self.results: dict[int, str] = {}

    async def on_start(self) -> None:
        self.deck = fresh_deck()
        if self.mode == "highcard":
            await self._play_high_card()
        else:
            await self._start_blackjack()

    # -- High Card ----------------------------------------------------

    async def _play_high_card(self) -> None:
        draws = {uid: self.deck.pop() for uid in self.players}
        lines = ["🃏 CARDS - High Card", ""]
        for uid, card in draws.items():
            lines.append(f"{display_name(uid, self.players)} drew {card_str(card)}")

        best = max(RANK_VALUE[c[0]] for c in draws.values())
        winners = [uid for uid, c in draws.items() if RANK_VALUE[c[0]] == best]
        while len(winners) > 1 and self.deck:
            lines.append("\n🔁 Tie! Redraw for: " + ", ".join(display_name(w, self.players) for w in winners))
            draws = {uid: self.deck.pop() for uid in winners}
            for uid, card in draws.items():
                lines.append(f"{display_name(uid, self.players)} drew {card_str(card)}")
            best = max(RANK_VALUE[c[0]] for c in draws.values())
            winners = [uid for uid, c in draws.items() if RANK_VALUE[c[0]] == best]

        winner_id = winners[0]
        lines.append("")
        lines.append(f"🏆 Winner: {display_name(winner_id, self.players)}!")
        for uid in self.players:
            won = uid == winner_id
            coins = db.REWARDS["first"] if won else db.REWARDS["participation"]
            await self.award(uid, coins, won)
            lines.append(f"💰 {display_name(uid, self.players)} earned {coins} coins")

        db.record_game_result(self.chat_id, self.key, winner_id, list(self.players.keys()))
        await self.bot.send_message(self.chat_id, "\n".join(lines))
        await self.cleanup()

    # -- Blackjack practice (sequential, one player at a time, no real bets) --

    async def _start_blackjack(self) -> None:
        self.order = list(self.players.keys())
        self.idx = 0
        await self.bot.send_message(
            self.chat_id, "🃏 CARDS - Blackjack Practice Mode (no real bets, virtual reward only)."
        )
        await self._blackjack_next_player()

    async def _blackjack_next_player(self) -> None:
        if self.idx >= len(self.order):
            await self._finish_blackjack()
            return
        uid = self.order[self.idx]
        self.hands[uid] = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]
        await self._send_blackjack_state(uid)

    async def _send_blackjack_state(self, uid: int) -> None:
        hand = self.hands[uid]
        text = (
            f"🃏 {display_name(uid, self.players)}'s turn (Blackjack Practice)\n\n"
            f"Your hand: {' '.join(card_str(c) for c in hand)} = {bj_hand_value(hand)}\n"
            f"Dealer shows: {card_str(self.dealer_hand[0])}\n\n"
            "Hit or Stand?"
        )
        kb = safe_reply_markup(
            [[InlineKeyboardButton(text="➕ Hit", callback_data="cards:hit"),
              InlineKeyboardButton(text="✋ Stand", callback_data="cards:stand")]]
        )
        sent = await self.bot.send_message(self.chat_id, text, reply_markup=kb)
        self.board_message_id = sent.message_id

    async def handle_callback(self, callback: CallbackQuery, parts: list[str]) -> None:
        if self.mode != "blackjack":
            return
        uid = callback.from_user.id
        if self.idx >= len(self.order) or uid != self.order[self.idx]:
            await callback.answer("It's not your turn!", show_alert=True)
            return
        action = parts[0]
        hand = self.hands[uid]

        if action == "hit":
            if not self.deck:
                await callback.answer("Deck empty!", show_alert=True)
                return
            hand.append(self.deck.pop())
            await callback.answer(f"Drew {card_str(hand[-1])}")
            if bj_hand_value(hand) > 21:
                self.results[uid] = "bust"
                await self.bot.send_message(self.chat_id, f"💥 {display_name(uid, self.players)} busts with {bj_hand_value(hand)}!")
                self.idx += 1
                await self._blackjack_next_player()
            else:
                await self._send_blackjack_state(uid)
            return

        if action == "stand":
            await callback.answer("You stand.")
            while bj_hand_value(self.dealer_hand) < 17 and self.deck:
                self.dealer_hand.append(self.deck.pop())
            player_val = bj_hand_value(hand)
            dealer_val = bj_hand_value(self.dealer_hand)
            if dealer_val > 21 or player_val > dealer_val:
                self.results[uid] = "win"
                outcome = "🎉 You win!"
            elif player_val == dealer_val:
                self.results[uid] = "push"
                outcome = "🤝 Push (tie)."
            else:
                self.results[uid] = "lose"
                outcome = "😢 Dealer wins."
            await self.bot.send_message(
                self.chat_id,
                f"{display_name(uid, self.players)}: {player_val} vs Dealer: {dealer_val}\n{outcome}",
            )
            self.idx += 1
            await self._blackjack_next_player()
            return

    async def _finish_blackjack(self) -> None:
        lines = ["🃏 BLACKJACK PRACTICE - RESULTS", ""]
        winner_id = None
        for uid in self.players:
            result = self.results.get(uid, "bust")
            won = result == "win"
            if won and winner_id is None:
                winner_id = uid
            coins = {"win": 300, "push": 100, "lose": db.REWARDS["participation"], "bust": db.REWARDS["participation"]}[result]
            await self.award(uid, coins, won)
            lines.append(f"{display_name(uid, self.players)}: {result} (+{coins} coins)")
        db.record_game_result(self.chat_id, self.key, winner_id, list(self.players.keys()))
        await self.bot.send_message(self.chat_id, "\n".join(lines))
        await self.cleanup()


# ==========================================================================
# 3. MAKE THE BOX  (dots and boxes)
# ==========================================================================

BOX_GRID_SIZE = 3  # 3x3 boxes -> 4x4 dots


class Edge:
    __slots__ = ("id", "kind", "r", "c", "owner")

    def __init__(self, id_: int, kind: str, r: int, c: int):
        self.id = id_
        self.kind = kind  # 'h' or 'v'
        self.r = r
        self.c = c
        self.owner: Optional[int] = None


class MakeTheBoxGame(BaseGame):
    key = "box"
    display_name_ = "Make The Box"
    emoji = "📦"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.n = BOX_GRID_SIZE
        self.edges: list[Edge] = []
        self.h_index: dict[tuple[int, int], Edge] = {}
        self.v_index: dict[tuple[int, int], Edge] = {}
        self.box_owner: dict[tuple[int, int], int] = {}
        self.turn_order: list[int] = []
        self.turn_index = 0
        self.scores: dict[int, int] = {}

    async def on_start(self) -> None:
        n = self.n
        eid = 0
        for r in range(n + 1):
            for c in range(n):
                e = Edge(eid, "h", r, c)
                self.edges.append(e)
                self.h_index[(r, c)] = e
                eid += 1
        for r in range(n):
            for c in range(n + 1):
                e = Edge(eid, "v", r, c)
                self.edges.append(e)
                self.v_index[(r, c)] = e
                eid += 1

        self.turn_order = list(self.players.keys())
        random.shuffle(self.turn_order)
        self.scores = {uid: 0 for uid in self.players}
        await self._send_board(new=True)

    def _grid_text(self) -> str:
        n = self.n
        lines = []
        for r in range(n + 1):
            row = "•"
            for c in range(n):
                edge = self.h_index[(r, c)]
                row += "───" if edge.owner is not None else "   "
                row += "•"
            lines.append(row)
            if r < n:
                row2 = ""
                for c in range(n + 1):
                    vedge = self.v_index[(r, c)]
                    row2 += "│" if vedge.owner is not None else " "
                    if c < n:
                        owner = self.box_owner.get((r, c))
                        mark = "?"
                        if owner is not None:
                            initial = self.players.get(owner, "?")[:1].upper()
                            mark = initial
                        else:
                            mark = " "
                        row2 += f" {mark} "
                lines.append(row2)
        return "```\n" + "\n".join(lines) + "\n```"

    def _keyboard(self) -> InlineKeyboardMarkup:
        buttons = []
        row = []
        for e in self.edges:
            if e.owner is not None:
                continue
            label = f"{'—' if e.kind=='h' else '|'}{e.id}"
            row.append(InlineKeyboardButton(text=label, callback_data=f"box:edge:{e.id}"))
            if len(row) == 5:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        return safe_reply_markup(buttons)

    def _status(self) -> str:
        current = self.turn_order[self.turn_index]
        lines = ["📦 MAKE THE BOX", "", self._grid_text(), ""]
        for uid in self.players:
            lines.append(f"{display_name(uid, self.players)}: {self.scores[uid]} box(es)")
        lines.append("")
        lines.append(f"🎯 Turn: {display_name(current, self.players)} - pick an edge below")
        return "\n".join(lines)

    async def _send_board(self, new: bool) -> None:
        text = self._status()
        kb = self._keyboard()
        if new or self.board_message_id is None:
            sent = await self.bot.send_message(self.chat_id, text, reply_markup=kb, parse_mode="Markdown")
            self.board_message_id = sent.message_id
        else:
            try:
                await self.bot.edit_message_text(
                    text, chat_id=self.chat_id, message_id=self.board_message_id,
                    reply_markup=kb, parse_mode="Markdown",
                )
            except Exception as exc:
                logger.debug("box board edit failed: %s", exc)

    def _check_box_completed(self, r: int, c: int) -> bool:
        try:
            top = self.h_index[(r, c)]
            bottom = self.h_index[(r + 1, c)]
            left = self.v_index[(r, c)]
            right = self.v_index[(r, c + 1)]
        except KeyError:
            return False
        return all(e.owner is not None for e in (top, bottom, left, right))

    async def handle_callback(self, callback: CallbackQuery, parts: list[str]) -> None:
        if parts[0] != "edge":
            return
        uid = callback.from_user.id
        current = self.turn_order[self.turn_index]
        if uid != current:
            await callback.answer("It's not your turn!", show_alert=True)
            return
        edge_id = int(parts[1])
        edge = self.edges[edge_id]
        if edge.owner is not None:
            await callback.answer("Already claimed.", show_alert=True)
            return

        edge.owner = uid
        await callback.answer("Edge claimed!")

        completed_any = False
        n = self.n
        for r in range(n):
            for c in range(n):
                if (r, c) in self.box_owner:
                    continue
                if self._check_box_completed(r, c):
                    self.box_owner[(r, c)] = uid
                    self.scores[uid] += 1
                    completed_any = True

        remaining = [e for e in self.edges if e.owner is None]
        if not remaining:
            await self._finish()
            return

        if not completed_any:
            self.turn_index = (self.turn_index + 1) % len(self.turn_order)
        await self._send_board(new=False)
        current_name = display_name(self.turn_order[self.turn_index], self.players)
        await self.bot.send_message(
            self.chat_id,
            f"🎯 {current_name}, it's your turn! Pick an edge. 📦"
        )

    async def _finish(self) -> None:
        top = max(self.scores.values())
        winners = [uid for uid, s in self.scores.items() if s == top]
        lines = ["📦 MAKE THE BOX - FINISHED!", "", self._grid_text(), ""]
        for uid, s in self.scores.items():
            lines.append(f"{display_name(uid, self.players)}: {s} box(es)")
        lines.append("")
        if len(winners) == 1:
            lines.append(f"🏆 Winner: {display_name(winners[0], self.players)}!")
        else:
            lines.append("🏆 It's a tie between: " + ", ".join(display_name(w, self.players) for w in winners))

        for uid in self.players:
            won = uid in winners
            coins = db.REWARDS["first"] // len(winners) if won else db.REWARDS["participation"]
            await self.award(uid, coins, won)
            lines.append(f"💰 {display_name(uid, self.players)} earned {coins} coins")

        db.record_game_result(self.chat_id, self.key, winners[0] if len(winners) == 1 else None, list(self.players.keys()))
        await self.bot.send_message(self.chat_id, "\n".join(lines), parse_mode="Markdown")
        await self.cleanup()


GAME_INFO_G2 = {
    "antakshari": {"cls": AntakshariGame, "title": "🎵 Antakshari", "cmds": ["/antakshari", "/anti_join", "/anti_start", "/anti_rules"]},
    "cards": {"cls": CardsGame, "title": "🃏 Cards", "cmds": ["/cards", "/card_join", "/card_start", "/card_rules"]},
    "box": {"cls": MakeTheBoxGame, "title": "📦 Make The Box", "cmds": ["/box", "/box_join", "/box_start", "/box_rules"]},
}

RULES_TEXT_G2 = {
    "antakshari": (
        "🎵 ANTAKSHARI RULES\n\n"
        "Take turns sending a word starting with the required letter (the last letter of the "
        "previous word). No repeats. Miss the timer and you're eliminated. Last one standing wins!"
    ),
    "cards": (
        "🃏 CARDS RULES\n\n"
        "High Card mode: everyone draws one card, highest rank wins (ties redraw).\n"
        "Blackjack Practice mode: play solo hands against the dealer with Hit/Stand - "
        "virtual reward only, no real bets."
    ),
    "box": (
        "📦 MAKE THE BOX RULES\n\n"
        "Take turns claiming edges on the grid. Complete a box's 4th edge to claim it and go again. "
        "Most boxes when the grid is full wins."
    ),
}
