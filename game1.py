"""
game1.py
========
Games implemented here:
  1. Raja Mantri  - hidden role deduction game (Raja / Mantri / Chor / Sipahi)
  2. Impostor     - social deduction game with discussion + voting
  3. 4 Card Match - memory pair-matching mini game

Also defines BaseGame, the shared lobby/join/start/cancel scaffolding that
game2.py and game3.py reuse, and GAME_INFO metadata consumed by bot.py's
/games menu and /help.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional

from aiogram import Bot
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import database as db

logger = logging.getLogger("games_bot.game1")


def display_name(user_id: int, players: dict) -> str:
    return players.get(user_id, f"Player {user_id}")


def safe_reply_markup(buttons: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==========================================================================
# BaseGame - shared lobby scaffolding for every game
# ==========================================================================


class BaseGame:
    """
    Common lobby/join/start/cleanup logic shared by all games.
    Concrete games override `on_start()`, `handle_callback()`, and optionally
    `handle_message()` for text-driven games like Antakshari.
    """

    key: str = "base"
    display_name_: str = "Game"
    emoji: str = "🎮"

    def __init__(self, bot: Bot, chat_id: int, host_id: int, host_name: str, manager: "GameManager" = None):
        self.bot = bot
        self.chat_id = chat_id
        self.host_id = host_id
        self.manager = manager
        self.on_finish = None
        self.players: dict[int, str] = {host_id: host_name}
        self.status = "lobby"  # lobby -> running -> ended
        self.lobby_message_id: Optional[int] = None
        self.board_message_id: Optional[int] = None
        self._tasks: list[asyncio.Task] = []
        self.min_players, self.max_players = db.GAME_LIMITS.get(self.key, (2, 8))

    # -- lobby -------------------------------------------------------------

    def lobby_text(self) -> str:
        lines = [f"{self.emoji} GAME LOBBY", "", f"{self.emoji} {self.display_name_}", ""]
        lines.append(f"👥 Players: {len(self.players)}/{self.max_players}")
        for i, (uid, name) in enumerate(self.players.items(), start=1):
            lines.append(f"{i}. {name}")
        lines.append("")
        lines.append(f"Minimum players to start: {self.min_players}")
        lines.append("Press JOIN to enter!")
        return "\n".join(lines)

    def lobby_keyboard(self) -> InlineKeyboardMarkup:
        return safe_reply_markup(
            [
                [
                    InlineKeyboardButton(text="🎮 JOIN", callback_data=f"{self.key}:join"),
                    InlineKeyboardButton(text="🚀 START", callback_data=f"{self.key}:start"),
                ],
                [InlineKeyboardButton(text="❌ CANCEL", callback_data=f"{self.key}:cancel")],
            ]
        )

    async def send_lobby(self, message: Message = None) -> None:
        if message is not None:
            sent = await message.answer(self.lobby_text(), reply_markup=self.lobby_keyboard())
        else:
            sent = await self.bot.send_message(self.chat_id, self.lobby_text(), reply_markup=self.lobby_keyboard())
        self.lobby_message_id = sent.message_id

    async def _refresh_lobby(self) -> None:
        if self.lobby_message_id is None:
            return
        try:
            await self.bot.edit_message_text(
                self.lobby_text(),
                chat_id=self.chat_id,
                message_id=self.lobby_message_id,
                reply_markup=self.lobby_keyboard(),
            )
        except Exception as exc:  # message not modified, deleted, etc.
            logger.debug("refresh_lobby: %s", exc)

    refresh_lobby = _refresh_lobby

    async def add_player(self, user_id: int, name: str) -> str:
        if self.status != "lobby":
            return False, "❌ Game has already started."
        if user_id in self.players:
            return False, "You already joined!"
        if len(self.players) >= self.max_players:
            return False, "❌ Lobby is full."
        self.players[user_id] = name
        await self._refresh_lobby()
        return True, f"✅ {name} joined ({len(self.players)}/{self.max_players})"

    async def try_start(self, requester_id: int) -> tuple[bool, str]:
        if requester_id != self.host_id:
            return False, "❌ Only the lobby creator can start the game."
        result = await self.begin()
        messages = {
            "ok": "🚀 Game starting!",
            "already_running": "❌ Game already started.",
            "not_enough": f"❌ Need at least {self.min_players} players.",
        }
        return result == "ok", messages.get(result, "❌ Could not start game.")

    def can_start(self) -> bool:
        return len(self.players) >= self.min_players

    async def begin(self) -> str:
        if self.status != "lobby":
            return "already_running"
        if not self.can_start():
            return "not_enough"
        self.status = "running"
        self.cancel_tasks()
        await self.on_start()
        return "ok"

    # -- lifecycle -----------------------------------------------------

    def track(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        return task

    def cancel_tasks(self) -> None:
        for t in self._tasks:
            if not t.done():
                t.cancel()
        self._tasks.clear()

    async def cleanup(self) -> None:
        self.cancel_tasks()
        self.status = "ended"
        if self.manager is not None:
            try:
                self.manager.remove(self.chat_id)
            except Exception:
                pass
        if self.on_finish is not None:
            try:
                self.on_finish(self.chat_id)
            except Exception:
                pass

    async def force_end(self, reason_text: str) -> None:
        try:
            await self.bot.send_message(self.chat_id, f"🛑 GAME ENDED\n\n{reason_text}")
        except Exception as exc:
            logger.warning("force_end notify failed: %s", exc)
        await self.cleanup()

    async def award(self, user_id: int, amount: int, won: bool) -> None:
        if amount > 0:
            db.add_coins(user_id, amount)
        db.record_game_stat(user_id, won)

    # -- overridable hooks ------------------------------------------------

    async def on_start(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    async def handle_callback(self, callback: CallbackQuery, parts: list[str]) -> None:  # pragma: no cover
        raise NotImplementedError

    async def handle_message(self, message: Message) -> None:
        """Optional: only games that read free-text (e.g. Antakshari) use this."""
        return None


class GameManager:
    """Keeps track of the single active game per chat_id."""

    def __init__(self):
        self.active: dict[int, BaseGame] = {}

    def get(self, chat_id: int) -> Optional[BaseGame]:
        return self.active.get(chat_id)

    def has_active(self, chat_id: int) -> bool:
        return chat_id in self.active

    def register(self, game: BaseGame) -> None:
        self.active[game.chat_id] = game

    def remove(self, chat_id: int) -> None:
        self.active.pop(chat_id, None)


# ==========================================================================
# 1. RAJA MANTRI
# ==========================================================================

RAJA_ROLES = ["👑 Raja", "🧠 Mantri", "🥷 Chor", "💂 Sipahi"]
RAJA_POINTS = {"👑 Raja": 1000, "🧠 Mantri": 800, "💂 Sipahi": 500, "🥷 Chor": 0}
RAJA_CHOR_ESCAPE_BONUS = 500


class RajaMantriGame(BaseGame):
    key = "raja"
    display_name_ = "Raja Mantri"
    emoji = "👑"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.roles: dict[int, str] = {}
        self.sipahi_id: Optional[int] = None
        self.chor_id: Optional[int] = None

    async def on_start(self) -> None:
        user_ids = list(self.players.keys())
        roles = RAJA_ROLES[:]
        random.shuffle(roles)
        self.roles = dict(zip(user_ids, roles))
        for uid, role in self.roles.items():
            if role == "💂 Sipahi":
                self.sipahi_id = uid
            elif role == "🥷 Chor":
                self.chor_id = uid

        text = (
            "👑 RAJA MANTRI - Roles have been secretly assigned!\n\n"
            "Each player: tap the button below to privately view your role "
            "(only you will see it).\n\n"
            f"💂 Sipahi is: {display_name(self.sipahi_id, self.players)} (kept secret from others, "
            "but the Sipahi themself will now try to catch the Chor)."
        )
        kb = safe_reply_markup(
            [[InlineKeyboardButton(text="🎭 Reveal My Role", callback_data="raja:reveal")]]
        )
        sent = await self.bot.send_message(self.chat_id, text, reply_markup=kb)
        self.board_message_id = sent.message_id
        self.track(self._guess_timeout())

    async def _guess_timeout(self) -> None:
        try:
            await asyncio.sleep(db.TURN_TIMEOUT + 20)
            if self.status == "running":
                await self.bot.send_message(
                    self.chat_id, "⏰ Sipahi took too long to guess. Chor escapes by default!"
                )
                await self._resolve(correct=False)
        except asyncio.CancelledError:
            pass

    async def handle_callback(self, callback: CallbackQuery, parts: list[str]) -> None:
        action = parts[0] if parts else ""
        uid = callback.from_user.id

        if action == "reveal":
            if uid not in self.roles:
                await callback.answer("You're not in this game.", show_alert=True)
                return
            role = self.roles[uid]
            extra = ""
            if role == "💂 Sipahi":
                buttons = [
                    [InlineKeyboardButton(text=name, callback_data=f"raja:guess:{pid}")]
                    for pid, name in self.players.items()
                    if pid != uid
                ]
                try:
                    await self.bot.send_message(
                        uid, "💂 You are the SIPAHI. Who do you think is the Chor?",
                        reply_markup=safe_reply_markup(buttons),
                    )
                    extra = " (Check your DM to make your guess, or use the buttons below if shown.)"
                except Exception:
                    extra = " (Enable DMs with the bot, or ask the host to relay guesses.)"
                # Also allow guessing directly in-group via alert instructions
                await callback.answer(f"Your role: {role}\nPoints: {RAJA_POINTS[role]}{extra}", show_alert=True)
                await self.bot.send_message(
                    self.chat_id,
                    "💂 The Sipahi has been notified privately and must now guess the Chor.\n"
                    "Sipahi, use the buttons below:",
                    reply_markup=safe_reply_markup(
                        [
                            [InlineKeyboardButton(text=name, callback_data=f"raja:guess:{pid}")]
                            for pid, name in self.players.items()
                            if pid != uid
                        ]
                    ),
                )
            else:
                await callback.answer(f"Your role: {role}\nPoints: {RAJA_POINTS[role]}", show_alert=True)
            return

        if action == "guess":
            if uid != self.sipahi_id:
                await callback.answer("Only the Sipahi can guess!", show_alert=True)
                return
            if self.status != "running":
                return
            guessed_id = int(parts[1])
            correct = guessed_id == self.chor_id
            await callback.answer("Guess locked in!")
            await self._resolve(correct)
            return

    async def _resolve(self, correct: bool) -> None:
        if self.status != "running":
            return
        self.status = "resolving"
        self.cancel_tasks()

        lines = ["👑 RAJA MANTRI - RESULTS", ""]
        scores: dict[int, int] = {}
        for uid, role in self.roles.items():
            scores[uid] = RAJA_POINTS[role]

        if correct:
            lines.append(f"✅ Sipahi correctly caught the Chor!")
        else:
            lines.append(f"❌ Sipahi guessed wrong! The Chor escapes and steals points!")
            scores[self.chor_id] = RAJA_POINTS["💂 Sipahi"] + RAJA_CHOR_ESCAPE_BONUS
            scores[self.sipahi_id] = 0

        for uid, role in self.roles.items():
            name = display_name(uid, self.players)
            pts = scores[uid]
            lines.append(f"{role} - {name}: {pts} pts")

        winner_id = max(scores, key=lambda k: scores[k])
        lines.append("")
        lines.append(f"🏆 Winner: {display_name(winner_id, self.players)}!")

        for uid in self.players:
            coins = max(scores[uid] // 2, db.REWARDS["participation"])
            won = uid == winner_id
            await self.award(uid, coins, won)
            lines.append(f"💰 {display_name(uid, self.players)} earned {coins} coins")

        db.record_game_result(self.chat_id, self.key, winner_id, list(self.players.keys()))
        await self.bot.send_message(self.chat_id, "\n".join(lines))
        await self.cleanup()


# ==========================================================================
# 2. IMPOSTOR
# ==========================================================================

IMPOSTOR_WORDS = {
    "Fruits": ["Apple", "Banana", "Mango", "Grapes", "Papaya"],
    "Animals": ["Tiger", "Elephant", "Dolphin", "Eagle", "Panda"],
    "Movies": ["Inception", "Titanic", "Avatar", "Gladiator", "Interstellar"],
    "Countries": ["India", "Japan", "Brazil", "Canada", "Egypt"],
    "Sports": ["Cricket", "Football", "Tennis", "Badminton", "Chess"],
}


class ImpostorGame(BaseGame):
    key = "impostor"
    display_name_ = "Impostor"
    emoji = "🕵️"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.impostor_id: Optional[int] = None
        self.category = ""
        self.word = ""
        self.phase = "roles"  # roles -> discussion -> voting -> done
        self.votes: dict[int, int] = {}  # voter_id -> target_id

    async def on_start(self) -> None:
        self.category, words = random.choice(list(IMPOSTOR_WORDS.items()))
        self.word = random.choice(words)
        self.impostor_id = random.choice(list(self.players.keys()))

        kb = safe_reply_markup([[InlineKeyboardButton(text="🎭 Reveal My Info", callback_data="impostor:reveal")]])
        await self.bot.send_message(
            self.chat_id,
            "🕵️ IMPOSTOR - Roles assigned!\n\nTap below to privately see your secret info.",
            reply_markup=kb,
        )
        self.phase = "discussion"
        self.track(self._discussion_phase())

    async def _discussion_phase(self) -> None:
        try:
            await self.bot.send_message(
                self.chat_id,
                f"💬 Discuss for {db.DISCUSSION_TIMEOUT} seconds! Figure out who the impostor is.",
            )
            await asyncio.sleep(db.DISCUSSION_TIMEOUT)
            await self._start_voting()
        except asyncio.CancelledError:
            pass

    async def _start_voting(self) -> None:
        self.phase = "voting"
        self.votes.clear()
        buttons = [
            [InlineKeyboardButton(text=f"🗳️ {name}", callback_data=f"impostor:vote:{pid}")]
            for pid, name in self.players.items()
        ]
        sent = await self.bot.send_message(
            self.chat_id,
            f"🗳️ VOTING TIME! You have {db.VOTE_TIMEOUT} seconds to vote for who you think is the impostor.",
            reply_markup=safe_reply_markup(buttons),
        )
        self.board_message_id = sent.message_id
        self.track(self._voting_timeout())

    async def _voting_timeout(self) -> None:
        try:
            await asyncio.sleep(db.VOTE_TIMEOUT)
            await self._resolve_votes()
        except asyncio.CancelledError:
            pass

    async def handle_callback(self, callback: CallbackQuery, parts: list[str]) -> None:
        action = parts[0] if parts else ""
        uid = callback.from_user.id

        if action == "reveal":
            if uid not in self.players:
                await callback.answer("You're not in this game.", show_alert=True)
                return
            if uid == self.impostor_id:
                text = f"🕵️ You are the IMPOSTOR!\nCategory hint: {self.category}\n(You don't know the exact word - blend in!)"
            else:
                text = f"✅ You are a CREWMATE.\nCategory: {self.category}\nSecret word: {self.word}"
            await callback.answer(text, show_alert=True)
            return

        if action == "vote":
            if self.phase != "voting":
                await callback.answer("Voting isn't open right now.", show_alert=True)
                return
            if uid not in self.players:
                await callback.answer("You're not in this game.", show_alert=True)
                return
            target_id = int(parts[1])
            if target_id not in self.players:
                await callback.answer("Invalid target.", show_alert=True)
                return
            self.votes[uid] = target_id
            await callback.answer(f"Vote recorded for {display_name(target_id, self.players)}!")
            if len(self.votes) >= len(self.players):
                self.cancel_tasks()
                await self._resolve_votes()
            return

    async def _resolve_votes(self) -> None:
        if self.phase != "voting":
            return
        self.phase = "done"
        self.cancel_tasks()

        tally: dict[int, int] = {pid: 0 for pid in self.players}
        for target in self.votes.values():
            tally[target] = tally.get(target, 0) + 1

        if not any(tally.values()):
            await self.bot.send_message(self.chat_id, "🤷 No votes were cast. Round ends with no elimination.")
            eliminated = None
        else:
            max_votes = max(tally.values())
            top = [pid for pid, v in tally.items() if v == max_votes]
            eliminated = random.choice(top) if len(top) > 1 else top[0]

        lines = ["🕵️ IMPOSTOR - RESULTS", ""]
        for pid, count in sorted(tally.items(), key=lambda x: -x[1]):
            lines.append(f"{display_name(pid, self.players)}: {count} vote(s)")
        lines.append("")
        lines.append(f"🎭 The impostor was: {display_name(self.impostor_id, self.players)}")

        crew_won = eliminated == self.impostor_id
        if eliminated is not None:
            lines.append(
                f"👢 Eliminated: {display_name(eliminated, self.players)} - "
                + ("Correct! Crew wins! 🎉" if crew_won else "Wrong guess! Impostor wins! 😈")
            )
        else:
            crew_won = False
            lines.append("😈 No one was eliminated - the impostor wins by default!")

        for uid in self.players:
            if uid == self.impostor_id:
                won = not crew_won
                coins = 400 if won else db.REWARDS["participation"]
            else:
                won = crew_won
                coins = db.REWARDS["first"] if won else db.REWARDS["participation"]
            await self.award(uid, coins, won)
            lines.append(f"💰 {display_name(uid, self.players)} earned {coins} coins")

        winner_id = self.impostor_id if not crew_won else eliminated
        db.record_game_result(self.chat_id, self.key, winner_id, list(self.players.keys()))
        await self.bot.send_message(self.chat_id, "\n".join(lines))
        await self.cleanup()


# ==========================================================================
# 3. 4 CARD MATCH  (memory pair-matching game)
# ==========================================================================

CARD_SYMBOLS = ["🍎", "🍌", "🍇", "🍒"]  # 4 symbols -> 4 pairs -> 8 cards


class FourCardMatchGame(BaseGame):
    key = "4card"
    display_name_ = "4 Card Match"
    emoji = "🃏"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.board: list[str] = []
        self.revealed: list[bool] = []
        self.matched: list[bool] = []
        self.turn_order: list[int] = []
        self.turn_index = 0
        self.first_pick: Optional[int] = None
        self.scores: dict[int, int] = {}

    async def on_start(self) -> None:
        deck = CARD_SYMBOLS * 2
        random.shuffle(deck)
        self.board = deck
        self.revealed = [False] * 8
        self.matched = [False] * 8
        self.turn_order = list(self.players.keys())
        random.shuffle(self.turn_order)
        self.scores = {uid: 0 for uid in self.players}
        await self._send_board(new=True)

    def _cell_text(self, i: int) -> str:
        if self.matched[i]:
            return self.board[i]
        if self.revealed[i]:
            return self.board[i]
        return "❓"

    def _keyboard(self) -> InlineKeyboardMarkup:
        rows = []
        for r in range(2):
            row = []
            for c in range(4):
                i = r * 4 + c
                row.append(
                    InlineKeyboardButton(text=self._cell_text(i), callback_data=f"4card:pick:{i}")
                )
            rows.append(row)
        return safe_reply_markup(rows)

    def _status_text(self) -> str:
        current = self.turn_order[self.turn_index]
        lines = ["🃏 4 CARD MATCH", ""]
        for uid in self.players:
            lines.append(f"{display_name(uid, self.players)}: {self.scores[uid]} pair(s)")
        lines.append("")
        lines.append(f"🎯 Turn: {display_name(current, self.players)}")
        return "\n".join(lines)

    async def _send_board(self, new: bool) -> None:
        text = self._status_text()
        kb = self._keyboard()
        if new or self.board_message_id is None:
            sent = await self.bot.send_message(self.chat_id, text, reply_markup=kb)
            self.board_message_id = sent.message_id
        else:
            try:
                await self.bot.edit_message_text(
                    text, chat_id=self.chat_id, message_id=self.board_message_id, reply_markup=kb
                )
            except Exception as exc:
                logger.debug("4card board edit failed: %s", exc)

    async def handle_callback(self, callback: CallbackQuery, parts: list[str]) -> None:
        action = parts[0] if parts else ""
        uid = callback.from_user.id
        if action != "pick":
            return

        current_player = self.turn_order[self.turn_index]
        if uid != current_player:
            await callback.answer("It's not your turn!", show_alert=True)
            return

        idx = int(parts[1])
        if self.matched[idx] or self.revealed[idx] or idx == self.first_pick:
            await callback.answer("Invalid card.", show_alert=True)
            return

        self.revealed[idx] = True

        if self.first_pick is None:
            self.first_pick = idx
            await callback.answer(f"Card {idx+1}: {self.board[idx]}")
            await self._send_board(new=False)
            return

        # second pick
        first = self.first_pick
        self.first_pick = None
        await callback.answer(f"Card {idx+1}: {self.board[idx]}")

        if self.board[first] == self.board[idx]:
            self.matched[first] = True
            self.matched[idx] = True
            self.scores[uid] += 1
            await self._send_board(new=False)
            if all(self.matched):
                await self._finish()
                return
            # matching player goes again
            await self.bot.send_message(
                self.chat_id,
                f"🎯 {display_name(uid, self.players)}, you matched! It's your turn again! 🃏"
            )
        else:
            await self._send_board(new=False)
            await asyncio.sleep(1.2)
            self.revealed[first] = False
            self.revealed[idx] = False
            self.turn_index = (self.turn_index + 1) % len(self.turn_order)
            await self._send_board(new=False)
            next_uid = self.turn_order[self.turn_index]
            await self.bot.send_message(
                self.chat_id,
                f"🎯 {display_name(next_uid, self.players)}, it's your turn! 🃏"
            )

    async def _finish(self) -> None:
        top_score = max(self.scores.values())
        winners = [uid for uid, s in self.scores.items() if s == top_score]
        lines = ["🃏 4 CARD MATCH - FINISHED!", ""]
        for uid, s in self.scores.items():
            lines.append(f"{display_name(uid, self.players)}: {s} pair(s)")
        lines.append("")
        if len(winners) == 1:
            lines.append(f"🏆 Winner: {display_name(winners[0], self.players)}!")
        else:
            names = ", ".join(display_name(w, self.players) for w in winners)
            lines.append(f"🏆 It's a tie between: {names}!")

        for uid in self.players:
            won = uid in winners
            coins = db.REWARDS["first"] // len(winners) if won else db.REWARDS["participation"]
            await self.award(uid, coins, won)
            lines.append(f"💰 {display_name(uid, self.players)} earned {coins} coins")

        db.record_game_result(self.chat_id, self.key, winners[0] if len(winners) == 1 else None, list(self.players.keys()))
        await self.bot.send_message(self.chat_id, "\n".join(lines))
        await self.cleanup()


# ==========================================================================
# Metadata used by bot.py (/games menu, /help)
# ==========================================================================

GAME_INFO_G1 = {
    "raja": {"cls": RajaMantriGame, "title": "👑 Raja Mantri", "cmds": ["/raja", "/raja_join", "/raja_start", "/raja_rules"]},
    "impostor": {"cls": ImpostorGame, "title": "🕵️ Impostor", "cmds": ["/impostor", "/impostor_join", "/impostor_start", "/impostor_vote", "/impostor_rules"]},
    "4card": {"cls": FourCardMatchGame, "title": "🃏 4 Card Match", "cmds": ["/4card", "/4card_join", "/4card_start", "/4card_rules"]},
}

RULES_TEXT_G1 = {
    "raja": (
        "👑 RAJA MANTRI RULES\n\n"
        "Exactly 4 players. Roles (Raja, Mantri, Chor, Sipahi) are assigned secretly.\n"
        "The Sipahi must guess who the Chor is. Guess correctly and Sipahi scores big; "
        "guess wrong and the Chor escapes with bonus points!\n"
        "Highest score wins coins."
    ),
    "impostor": (
        "🕵️ IMPOSTOR RULES\n\n"
        "4+ players. One random impostor doesn't know the secret word, only the category.\n"
        "Discuss, then vote out who you think the impostor is.\n"
        "Crew wins if they eliminate the impostor; otherwise the impostor wins."
    ),
    "4card": (
        "🃏 4 CARD MATCH RULES\n\n"
        "2-4 players. 4 pairs of cards are hidden on an 8-card board.\n"
        "Take turns flipping two cards. Match them and go again, score a point!\n"
        "Most pairs when the board clears wins."
    ),
}
