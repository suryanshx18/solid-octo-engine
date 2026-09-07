"""
game3.py
--------
Three complete multiplayer games:

1. Ludo (classic 4-tokens-per-player implementation on a shared 52-cell loop
   plus a private 6-cell home stretch per player)
2. Power Rangers (original turn-based battle mini-game, no franchise content)
3. Business Tycoon (original property-trading game, not a Monopoly clone)

Same contract as game1.py (see its module docstring).
All coins/money in these games are virtual and have no real-world value.

LUDO NOTE: each player gets 4 tokens on a classic 52-cell shared loop with a
private 6-cell home stretch. Entry points are spaced every 13 cells (0, 13,
26, 39) and safe cells are the 4 entry points plus 4 star cells (8, 21, 34,
47), matching the traditional layout. The one simplification versus a
physical board is that there is no "blockade" rule (two of a player's own
tokens stacked on one cell do not block opponents from passing) - everything
else (six-to-start, extra roll on six, three-sixes forfeit, capturing on
non-safe cells, choosing which token to move, all-4-home to win) is real,
validated, server-authoritative gameplay.
"""

from __future__ import annotations

import asyncio
import random
from typing import Callable, Dict, List, Optional, Tuple

from aiogram import Bot
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db

FinishCallback = Callable[[int], None]


def _safe_name(name: str) -> str:
    return name if name else "Player"


# ==========================================================================
# 1) LUDO (classic 4-token implementation)
# ==========================================================================

class LudoGame:
    PREFIX = "ludo"
    NAME = "Ludo"
    EMOJI = "🎲"
    MIN_PLAYERS = 2
    MAX_PLAYERS = 4
    TOKENS_PER_PLAYER = 4
    TURN_SECONDS = 30

    MAIN_TRACK_LEN = 52          # total cells on the shared loop
    STEPS_ON_MAIN = 51           # local indices 0..50 are travelled on the shared loop
    LAST_MAIN_LOCAL = STEPS_ON_MAIN - 1   # 50 - last local index still on the shared loop
    HOME_STRETCH_LEN = 6         # local indices 51..56 are the private home stretch
    FINISH_LOCAL = STEPS_ON_MAIN + HOME_STRETCH_LEN - 1  # 56 = token is home/finished

    SAFE_CELLS = {0, 8, 13, 21, 26, 34, 39, 47}
    START_OFFSETS = [0, 13, 26, 39]

    WIN_REWARD = 400
    PARTICIPATION_REWARD = 40
    CAPTURE_BONUS = 30

    RULES_TEXT = (
        "🎲 <b>LUDO - RULES</b>\n\n"
        "2-4 players, 4 tokens each, classic rules.\n"
        "• Roll a 6 to bring a token out of your yard.\n"
        "• Roll again if you roll a 6 (max 3 in a row, or your turn is forfeited).\n"
        "• If more than one of your tokens can move, you'll be asked which one.\n"
        "• Land exactly on an opponent's token (on a non-safe cell) to send it back to their yard!\n"
        "• Star cells (safe cells) protect tokens from capture.\n"
        "• Each token travels the shared loop, then its own private home stretch.\n"
        "• Get all 4 tokens home to win!"
    )

    def __init__(self, bot: Bot, chat_id: int, creator_id: int, on_finish: FinishCallback):
        self.bot = bot
        self.chat_id = chat_id
        self.creator_id = creator_id
        self.on_finish = on_finish
        self.status = "lobby"
        self.players: Dict[int, str] = {}
        self.lobby_message_id: Optional[int] = None
        self._tasks: List[asyncio.Task] = []

        # user_id -> list of 4 local positions.
        # -1 = in yard, 0..LAST_MAIN_LOCAL = on shared loop,
        # LAST_MAIN_LOCAL+1..FINISH_LOCAL-1 = private home stretch, FINISH_LOCAL = home/finished
        self.tokens: Dict[int, List[int]] = {}
        self.start_offset: Dict[int, int] = {}
        self.turn_order: List[int] = []
        self.turn_index = 0
        self.consecutive_sixes = 0
        self.board_message_id: Optional[int] = None
        self.tokens_emoji = ["🔴", "🔵", "🟢", "🟡"]
        self.emoji_of: Dict[int, str] = {}

        # state for the "choose which token to move" step
        self._pending_roll: Optional[int] = None
        self._pending_player: Optional[int] = None

    # ---------------------------------------------------------------- lobby

    def lobby_text(self) -> str:
        lines = [f"{self.EMOJI} <b>GAME LOBBY - {self.NAME}</b>\n",
                  f"👥 Players: {len(self.players)}/{self.MAX_PLAYERS} (min {self.MIN_PLAYERS})\n"]
        for i, name in enumerate(self.players.values(), 1):
            lines.append(f"{i}. {name}")
        if not self.players:
            lines.append("(no one yet)")
        lines.append("\nPress JOIN to enter!")
        return "\n".join(lines)

    def lobby_keyboard(self):
        b = InlineKeyboardBuilder()
        b.button(text="🎮 JOIN", callback_data=f"{self.PREFIX}:join")
        b.button(text="🚀 START", callback_data=f"{self.PREFIX}:start")
        b.button(text="❌ CANCEL", callback_data=f"{self.PREFIX}:cancel")
        b.adjust(2, 1)
        return b.as_markup()

    async def add_player(self, user_id: int, name: str) -> Tuple[bool, str]:
        if self.status != "lobby":
            return False, "❌ This game has already started."
        if user_id in self.players:
            return False, "You already joined!"
        if len(self.players) >= self.MAX_PLAYERS:
            return False, "❌ Lobby is full."
        self.players[user_id] = _safe_name(name)
        return True, f"✅ {_safe_name(name)} joined ({len(self.players)}/{self.MAX_PLAYERS})"

    async def try_start(self, requester_id: int) -> Tuple[bool, str]:
        if self.status != "lobby":
            return False, "❌ Game already started."
        if len(self.players) < self.MIN_PLAYERS:
            return False, f"❌ Need at least {self.MIN_PLAYERS} players (have {len(self.players)})."
        await self._begin()
        return True, "🚀 Game starting!"

    async def send_lobby(self) -> None:
        msg = await self.bot.send_message(self.chat_id, self.lobby_text(), reply_markup=self.lobby_keyboard())
        self.lobby_message_id = msg.message_id

    async def _refresh_lobby(self) -> None:
        if self.lobby_message_id:
            try:
                await self.bot.edit_message_text(
                    self.lobby_text(), self.chat_id, self.lobby_message_id,
                    reply_markup=self.lobby_keyboard()
                )
            except Exception:
                pass

    # -------------------------------------------------------------- setup

    async def _begin(self) -> None:
        self.status = "running"
        self.turn_order = list(self.players.keys())
        random.shuffle(self.turn_order)
        for i, uid in enumerate(self.turn_order):
            self.emoji_of[uid] = self.tokens_emoji[i % len(self.tokens_emoji)]
            self.start_offset[uid] = self.START_OFFSETS[i % len(self.START_OFFSETS)]
            self.tokens[uid] = [-1] * self.TOKENS_PER_PLAYER
        self.turn_index = 0
        self.consecutive_sixes = 0
        self._pending_roll = None
        self._pending_player = None

        msg = await self.bot.send_message(self.chat_id, self._render(), reply_markup=self._roll_keyboard())
        self.board_message_id = msg.message_id
        self._tasks.append(asyncio.create_task(self._turn_timer()))

    def _current(self) -> int:
        return self.turn_order[self.turn_index % len(self.turn_order)]

    def _global_cell(self, uid: int, local: int) -> int:
        """Only meaningful while local is on the shared loop (0..LAST_MAIN_LOCAL)."""
        return (self.start_offset[uid] + local) % self.MAIN_TRACK_LEN

    def _token_status_text(self, uid: int, local: int) -> str:
        if local == -1:
            return "yard"
        if local == self.FINISH_LOCAL:
            return "HOME 🏁"
        if local > self.LAST_MAIN_LOCAL:
            step = local - self.LAST_MAIN_LOCAL  # 1..HOME_STRETCH_LEN-1
            return f"home stretch ({step}/{self.HOME_STRETCH_LEN - 1})"
        return f"cell {self._global_cell(uid, local)}"

    # ------------------------------------------------------------- render

    def _render(self) -> str:
        lines = [f"{self.EMOJI} <b>Ludo</b>\n"]
        for uid in self.turn_order:
            token_strs = [
                f"T{i + 1}:{self._token_status_text(uid, local)}"
                for i, local in enumerate(self.tokens[uid])
            ]
            finished = sum(1 for l in self.tokens[uid] if l == self.FINISH_LOCAL)
            lines.append(f"{self.emoji_of[uid]} {self.players[uid]} ({finished}/4 home): " + ", ".join(token_strs))
        lines.append(f"\n👉 Turn: {self.emoji_of[self._current()]} {self.players[self._current()]}")
        return "\n".join(lines)

    def _roll_keyboard(self):
        b = InlineKeyboardBuilder()
        b.button(text="🎲 Roll Dice", callback_data=f"{self.PREFIX}:roll")
        return b.as_markup()

    def _movable_tokens(self, uid: int, roll: int) -> List[int]:
        movable = []
        for i, local in enumerate(self.tokens[uid]):
            if local == -1:
                if roll == 6:
                    movable.append(i)
            elif local == self.FINISH_LOCAL:
                continue
            else:
                if local + roll <= self.FINISH_LOCAL:
                    movable.append(i)
        return movable

    def _token_choice_keyboard(self, uid: int, movable: List[int]):
        b = InlineKeyboardBuilder()
        for i in movable:
            local = self.tokens[uid][i]
            label = f"{self.emoji_of[uid]} T{i + 1} ({self._token_status_text(uid, local)})"
            b.button(text=label, callback_data=f"{self.PREFIX}:token:{i}")
        b.adjust(1)
        return b.as_markup()

    async def _refresh_board(self, keyboard=None) -> None:
        if self.board_message_id:
            try:
                await self.bot.edit_message_text(
                    self._render(), self.chat_id, self.board_message_id,
                    reply_markup=keyboard or self._roll_keyboard()
                )
            except Exception:
                pass

    async def _turn_timer(self) -> None:
        try:
            while self.status == "running":
                await asyncio.sleep(self.TURN_SECONDS)
                if self.status != "running":
                    break
                await self.bot.send_message(self.chat_id, "⏱ Turn timed out, moving to next player.")
                self._pending_roll = None
                self._pending_player = None
                self._advance_turn()
                await self._refresh_board()
        except asyncio.CancelledError:
            pass

    def _advance_turn(self) -> None:
        self.consecutive_sixes = 0
        self.turn_index += 1

    # ------------------------------------------------------------ actions

    async def handle_callback(self, callback: CallbackQuery) -> None:
        data = callback.data or ""
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""

        if action == "join":
            ok, msg = await self.add_player(callback.from_user.id, callback.from_user.first_name)
            await callback.answer(msg, show_alert=not ok)
            if ok:
                await self._refresh_lobby()
        elif action == "cancel":
            if callback.from_user.id != self.creator_id:
                await callback.answer("Only the creator can cancel.", show_alert=True)
                return
            await callback.answer("Cancelled.")
            await self.force_end("Cancelled by creator.")
        elif action == "start":
            ok, msg = await self.try_start(callback.from_user.id)
            await callback.answer(msg, show_alert=not ok)
        elif action == "roll":
            await self._handle_roll(callback)
        elif action == "token":
            await self._handle_token_choice(callback, int(parts[2]))

    async def _handle_roll(self, callback: CallbackQuery) -> None:
        if self.status != "running":
            await callback.answer("Game not running.", show_alert=True)
            return
        current = self._current()
        if callback.from_user.id != current:
            await callback.answer("❌ It's not your turn!", show_alert=True)
            return
        if self._pending_roll is not None:
            await callback.answer("Choose a token to move first.", show_alert=True)
            return

        roll = random.randint(1, 6)
        await callback.answer(f"🎲 You rolled a {roll}!")
        await self.bot.send_message(self.chat_id, f"🎲 {self.players[current]} rolled a <b>{roll}</b>.")

        movable = self._movable_tokens(current, roll)
        if not movable:
            await self.bot.send_message(self.chat_id, "❌ No valid moves with this roll.")
            await self._after_roll_resolved(current, roll)
            return

        if len(movable) == 1:
            await self._move_token(current, movable[0], roll)
            await self._after_roll_resolved(current, roll)
            return

        # multiple tokens can legally move - ask the player to pick one
        self._pending_roll = roll
        self._pending_player = current
        await self._refresh_board(keyboard=self._token_choice_keyboard(current, movable))

    async def _handle_token_choice(self, callback: CallbackQuery, token_idx: int) -> None:
        current = self._current()
        if callback.from_user.id != current:
            await callback.answer("❌ It's not your turn!", show_alert=True)
            return
        if self._pending_roll is None or self._pending_player != current:
            await callback.answer("No pending roll.", show_alert=True)
            return

        roll = self._pending_roll
        self._pending_roll = None
        self._pending_player = None
        await callback.answer()

        await self._move_token(current, token_idx, roll)
        await self._after_roll_resolved(current, roll)

    async def _move_token(self, uid: int, token_idx: int, roll: int) -> None:
        old_local = self.tokens[uid][token_idx]

        if old_local == -1:
            new_local = 0
            self.tokens[uid][token_idx] = new_local
            await self.bot.send_message(
                self.chat_id,
                f"{self.emoji_of[uid]} {self.players[uid]}'s token T{token_idx + 1} leaves the yard!"
            )
        else:
            new_local = old_local + roll
            self.tokens[uid][token_idx] = new_local
            await self.bot.send_message(
                self.chat_id,
                f"{self.emoji_of[uid]} {self.players[uid]}'s token T{token_idx + 1} moves to "
                f"{self._token_status_text(uid, new_local)}."
            )

        if new_local == self.FINISH_LOCAL:
            await self.bot.send_message(
                self.chat_id, f"🏁 {self.players[uid]}'s token T{token_idx + 1} made it home!"
            )
            return

        # capturing only happens on the shared loop, never in a private home stretch
        if new_local <= self.LAST_MAIN_LOCAL:
            global_cell = self._global_cell(uid, new_local)
            if global_cell not in self.SAFE_CELLS:
                for other in self.turn_order:
                    if other == uid:
                        continue
                    for j, other_local in enumerate(self.tokens[other]):
                        if other_local == -1 or other_local == self.FINISH_LOCAL:
                            continue
                        if other_local <= self.LAST_MAIN_LOCAL and self._global_cell(other, other_local) == global_cell:
                            self.tokens[other][j] = -1
                            db.add_coins(uid, self.CAPTURE_BONUS)
                            await self.bot.send_message(
                                self.chat_id,
                                f"💥 {self.players[uid]} captured {self.players[other]}'s token T{j + 1}! "
                                f"Sent back to yard."
                            )

    async def _after_roll_resolved(self, uid: int, roll: int) -> None:
        if all(l == self.FINISH_LOCAL for l in self.tokens[uid]):
            await self._finish(uid)
            return

        if roll == 6:
            self.consecutive_sixes += 1
            if self.consecutive_sixes >= 3:
                await self.bot.send_message(self.chat_id, "❌ Three 6's in a row - turn forfeited!")
                self._advance_turn()
        else:
            self._advance_turn()

        await self._refresh_board()

    async def _finish(self, winner_id: int) -> None:
        for t in self._tasks:
            t.cancel()
        lines = [f"{self.EMOJI} <b>GAME OVER - Ludo</b>\n",
                 f"🏆 Winner: <b>{self.players[winner_id]}</b> {self.emoji_of[winner_id]} (all 4 tokens home!)\n",
                 "💰 <b>Rewards:</b>"]
        for uid in self.players:
            amt = self.WIN_REWARD if uid == winner_id else self.PARTICIPATION_REWARD
            new_bal = db.add_coins(uid, amt)
            lines.append(f"• {self.players[uid]}: +{amt} coins (balance: {new_bal})")
            db.update_stats(uid, won=(uid == winner_id))
        db.record_game_result(self.chat_id, self.NAME, winner_id, list(self.players.keys()))
        await self.bot.send_message(self.chat_id, "\n".join(lines))
        self.status = "ended"
        self.on_finish(self.chat_id)

    async def force_end(self, reason: str) -> None:
        for t in self._tasks:
            t.cancel()
        self.status = "ended"
        try:
            await self.bot.send_message(self.chat_id, f"🛑 <b>GAME ENDED</b>\n\n{reason}")
        except Exception:
            pass
        self.on_finish(self.chat_id)


# ==========================================================================
# 2) POWER RANGERS (original battle mini-game - no franchise content)
# ==========================================================================

class PowerRangersGame:
    PREFIX = "rangers"
    NAME = "Power Rangers"
    EMOJI = "⚡"
    MIN_PLAYERS = 2
    MAX_PLAYERS = 6
    TURN_SECONDS = 30
    MAX_ROUNDS = 20
    START_HP = 100
    START_ENERGY = 100
    ENERGY_REGEN = 10

    WIN_REWARD = 350
    PARTICIPATION_REWARD = 40

    ABILITIES = {
        "strike": {"name": "Power Strike", "cost": 20, "cooldown": 0, "dmg": (20, 30)},
        "shield": {"name": "Shield", "cost": 15, "cooldown": 2, "dmg": None},
        "boost": {"name": "Team Boost", "cost": 25, "cooldown": 3, "heal": 15},
        "blast": {"name": "Energy Blast", "cost": 30, "cooldown": 2, "dmg": (15, 25)},
    }

    RULES_TEXT = (
        "⚡ <b>POWER RANGERS - RULES</b> (original mini-game)\n\n"
        "2-6 players battle in free-for-all combat with 100 HP and 100 Energy each.\n\n"
        "Abilities:\n"
        "• 💥 Power Strike (20 energy): 20-30 damage to a target.\n"
        "• 🛡 Shield (15 energy, cooldown 2): halves the next hit you take.\n"
        "• 💚 Team Boost (25 energy, cooldown 3): heal 15 HP.\n"
        "• 🌀 Energy Blast (30 energy, cooldown 2): 15-25 damage, ignores Shield.\n\n"
        "Energy regenerates +10 each of your turns. Last Ranger standing wins!"
    )

    def __init__(self, bot: Bot, chat_id: int, creator_id: int, on_finish: FinishCallback):
        self.bot = bot
        self.chat_id = chat_id
        self.creator_id = creator_id
        self.on_finish = on_finish
        self.status = "lobby"
        self.players: Dict[int, str] = {}
        self.lobby_message_id: Optional[int] = None
        self._tasks: List[asyncio.Task] = []

        self.hp: Dict[int, int] = {}
        self.energy: Dict[int, int] = {}
        self.shielded: Dict[int, bool] = {}
        self.cooldowns: Dict[int, Dict[str, int]] = {}
        self.turn_order: List[int] = []
        self.turn_index = 0
        self.round_num = 0
        self.board_message_id: Optional[int] = None
        self._pending_action: Optional[str] = None  # awaiting target selection

    def lobby_text(self) -> str:
        lines = [f"{self.EMOJI} <b>GAME LOBBY - {self.NAME}</b>\n",
                  f"👥 Players: {len(self.players)}/{self.MAX_PLAYERS} (min {self.MIN_PLAYERS})\n"]
        for i, name in enumerate(self.players.values(), 1):
            lines.append(f"{i}. {name}")
        if not self.players:
            lines.append("(no one yet)")
        lines.append("\nPress JOIN to enter!")
        return "\n".join(lines)

    def lobby_keyboard(self):
        b = InlineKeyboardBuilder()
        b.button(text="🎮 JOIN", callback_data=f"{self.PREFIX}:join")
        b.button(text="🚀 START", callback_data=f"{self.PREFIX}:start")
        b.button(text="❌ CANCEL", callback_data=f"{self.PREFIX}:cancel")
        b.adjust(2, 1)
        return b.as_markup()

    async def add_player(self, user_id: int, name: str) -> Tuple[bool, str]:
        if self.status != "lobby":
            return False, "❌ This game has already started."
        if user_id in self.players:
            return False, "You already joined!"
        if len(self.players) >= self.MAX_PLAYERS:
            return False, "❌ Lobby is full."
        self.players[user_id] = _safe_name(name)
        return True, f"✅ {_safe_name(name)} joined ({len(self.players)}/{self.MAX_PLAYERS})"

    async def try_start(self, requester_id: int) -> Tuple[bool, str]:
        if self.status != "lobby":
            return False, "❌ Game already started."
        if len(self.players) < self.MIN_PLAYERS:
            return False, f"❌ Need at least {self.MIN_PLAYERS} players (have {len(self.players)})."
        await self._begin()
        return True, "🚀 Game starting!"

    async def send_lobby(self) -> None:
        msg = await self.bot.send_message(self.chat_id, self.lobby_text(), reply_markup=self.lobby_keyboard())
        self.lobby_message_id = msg.message_id

    async def _refresh_lobby(self) -> None:
        if self.lobby_message_id:
            try:
                await self.bot.edit_message_text(
                    self.lobby_text(), self.chat_id, self.lobby_message_id,
                    reply_markup=self.lobby_keyboard()
                )
            except Exception:
                pass

    async def _begin(self) -> None:
        self.status = "running"
        self.turn_order = list(self.players.keys())
        random.shuffle(self.turn_order)
        self.hp = {uid: self.START_HP for uid in self.turn_order}
        self.energy = {uid: self.START_ENERGY for uid in self.turn_order}
        self.shielded = {uid: False for uid in self.turn_order}
        self.cooldowns = {uid: {k: 0 for k in self.ABILITIES} for uid in self.turn_order}
        self.turn_index = 0
        self.round_num = 1

        msg = await self.bot.send_message(self.chat_id, self._render(), reply_markup=self._ability_keyboard())
        self.board_message_id = msg.message_id
        self._tasks.append(asyncio.create_task(self._turn_timer()))

    def _alive(self) -> List[int]:
        return [uid for uid in self.turn_order if self.hp[uid] > 0]

    def _current(self) -> int:
        alive = self._alive()
        idx = self.turn_index % len(alive)
        return alive[idx]

    def _render(self) -> str:
        lines = [f"{self.EMOJI} <b>Power Rangers Battle</b> (Round {self.round_num}/{self.MAX_ROUNDS})\n"]
        for uid in self.turn_order:
            status = "💀 KO" if self.hp[uid] <= 0 else f"❤️{self.hp[uid]} ⚡{self.energy[uid]}"
            shield = " 🛡" if self.shielded.get(uid) else ""
            lines.append(f"• {self.players[uid]}: {status}{shield}")
        if self._alive():
            lines.append(f"\n👉 Turn: {self.players[self._current()]}")
        return "\n".join(lines)

    def _ability_keyboard(self):
        b = InlineKeyboardBuilder()
        current = self._current()
        for key, ab in self.ABILITIES.items():
            cd = self.cooldowns[current][key]
            enough_energy = self.energy[current] >= ab["cost"]
            label = f"{ab['name']} ({ab['cost']}⚡)"
            if cd > 0:
                label += f" [CD {cd}]"
            b.button(text=label, callback_data=f"{self.PREFIX}:ability:{key}")
        b.adjust(2)
        return b.as_markup()

    def _target_keyboard(self, action: str):
        b = InlineKeyboardBuilder()
        current = self._current()
        for uid in self._alive():
            if uid != current:
                b.button(text=self.players[uid], callback_data=f"{self.PREFIX}:target:{action}:{uid}")
        b.adjust(2)
        return b.as_markup()

    async def _refresh_board(self, keyboard=None) -> None:
        if self.board_message_id:
            try:
                await self.bot.edit_message_text(
                    self._render(), self.chat_id, self.board_message_id,
                    reply_markup=keyboard or self._ability_keyboard()
                )
            except Exception:
                pass

    async def _turn_timer(self) -> None:
        try:
            while self.status == "running":
                await asyncio.sleep(self.TURN_SECONDS)
                if self.status != "running":
                    break
                await self.bot.send_message(self.chat_id, "⏱ Turn timed out, skipping.")
                self._next_turn()
                await self._refresh_board()
        except asyncio.CancelledError:
            pass

    def _next_turn(self) -> None:
        current = self._current()
        for k in self.cooldowns[current]:
            if self.cooldowns[current][k] > 0:
                self.cooldowns[current][k] -= 1
        self.energy[current] = min(self.START_ENERGY, self.energy[current] + self.ENERGY_REGEN)
        self._pending_action = None
        self.turn_index += 1
        if self.turn_index % max(1, len(self._alive())) == 0:
            self.round_num += 1

    async def handle_callback(self, callback: CallbackQuery) -> None:
        data = callback.data or ""
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""

        if action == "join":
            ok, msg = await self.add_player(callback.from_user.id, callback.from_user.first_name)
            await callback.answer(msg, show_alert=not ok)
            if ok:
                await self._refresh_lobby()
        elif action == "cancel":
            if callback.from_user.id != self.creator_id:
                await callback.answer("Only the creator can cancel.", show_alert=True)
                return
            await callback.answer("Cancelled.")
            await self.force_end("Cancelled by creator.")
        elif action == "start":
            ok, msg = await self.try_start(callback.from_user.id)
            await callback.answer(msg, show_alert=not ok)
        elif action == "ability":
            await self._handle_ability(callback, parts[2])
        elif action == "target":
            await self._handle_target(callback, parts[2], int(parts[3]))

    async def _handle_ability(self, callback: CallbackQuery, key: str) -> None:
        if self.status != "running":
            await callback.answer("Game not running.", show_alert=True)
            return
        current = self._current()
        if callback.from_user.id != current:
            await callback.answer("❌ It's not your turn!", show_alert=True)
            return
        ab = self.ABILITIES[key]
        if self.cooldowns[current][key] > 0:
            await callback.answer("That ability is on cooldown.", show_alert=True)
            return
        if self.energy[current] < ab["cost"]:
            await callback.answer("Not enough energy.", show_alert=True)
            return

        if key in ("strike", "blast"):
            await callback.answer("Choose a target.")
            await self._refresh_board(keyboard=self._target_keyboard(key))
            return

        # self-targeted abilities
        self.energy[current] -= ab["cost"]
        if key == "shield":
            self.shielded[current] = True
            self.cooldowns[current][key] = ab["cooldown"]
            await self.bot.send_message(self.chat_id, f"🛡 {self.players[current]} raises a Shield!")
        elif key == "boost":
            heal = ab["heal"]
            self.hp[current] = min(self.START_HP, self.hp[current] + heal)
            self.cooldowns[current][key] = ab["cooldown"]
            await self.bot.send_message(self.chat_id, f"💚 {self.players[current]} uses Team Boost, heals {heal} HP!")

        await callback.answer()
        self._next_turn()
        if not await self._check_win():
            await self._refresh_board()

    async def _handle_target(self, callback: CallbackQuery, key: str, target_id: int) -> None:
        current = self._current()
        if callback.from_user.id != current:
            await callback.answer("❌ It's not your turn!", show_alert=True)
            return
        ab = self.ABILITIES[key]
        if self.hp.get(target_id, 0) <= 0:
            await callback.answer("That target is already down.", show_alert=True)
            return
        self.energy[current] -= ab["cost"]
        self.cooldowns[current][key] = ab["cooldown"]
        dmg = random.randint(*ab["dmg"])

        ignores_shield = key == "blast"
        if self.shielded.get(target_id) and not ignores_shield:
            dmg = dmg // 2
            self.shielded[target_id] = False
            shield_note = " (shield absorbed half the damage!)"
        else:
            shield_note = ""

        self.hp[target_id] = max(0, self.hp[target_id] - dmg)
        await callback.answer(f"Hit for {dmg}!")
        await self.bot.send_message(
            self.chat_id,
            f"{'💥' if key=='strike' else '🌀'} {self.players[current]} uses {ab['name']} on "
            f"{self.players[target_id]} for {dmg} damage!{shield_note}"
        )
        if self.hp[target_id] <= 0:
            await self.bot.send_message(self.chat_id, f"💀 {self.players[target_id]} has been knocked out!")

        self._next_turn()
        if not await self._check_win():
            await self._refresh_board()

    async def _check_win(self) -> bool:
        alive = self._alive()
        if len(alive) <= 1 or self.round_num > self.MAX_ROUNDS:
            winner = alive[0] if len(alive) == 1 else max(self.hp, key=lambda u: self.hp[u])
            await self._finish(winner)
            return True
        return False

    async def _finish(self, winner_id: int) -> None:
        for t in self._tasks:
            t.cancel()
        lines = [f"{self.EMOJI} <b>BATTLE OVER!</b>\n", f"🏆 Winner: <b>{self.players[winner_id]}</b>\n",
                 "💰 <b>Rewards:</b>"]
        for uid in self.players:
            amt = self.WIN_REWARD if uid == winner_id else self.PARTICIPATION_REWARD
            new_bal = db.add_coins(uid, amt)
            lines.append(f"• {self.players[uid]}: +{amt} coins (balance: {new_bal})")
            db.update_stats(uid, won=(uid == winner_id))
        db.record_game_result(self.chat_id, self.NAME, winner_id, list(self.players.keys()))
        await self.bot.send_message(self.chat_id, "\n".join(lines))
        self.status = "ended"
        self.on_finish(self.chat_id)

    async def force_end(self, reason: str) -> None:
        for t in self._tasks:
            t.cancel()
        self.status = "ended"
        try:
            await self.bot.send_message(self.chat_id, f"🛑 <b>GAME ENDED</b>\n\n{reason}")
        except Exception:
            pass
        self.on_finish(self.chat_id)


# ==========================================================================
# 3) BUSINESS TYCOON (original property game - not a Monopoly clone)
# ==========================================================================

BOARD: List[Dict] = [
    {"type": "start", "name": "🏁 Start Plaza"},
    {"type": "property", "name": "Sunrise Bakery", "price": 100},
    {"type": "property", "name": "Cyber Cafe", "price": 120},
    {"type": "event", "name": "📰 Business Event"},
    {"type": "property", "name": "Green Valley Farm", "price": 140},
    {"type": "property", "name": "Tech Hub Offices", "price": 160},
    {"type": "tax", "name": "🧾 Maintenance Tax", "amount": 50},
    {"type": "property", "name": "Ocean View Villas", "price": 180},
    {"type": "property", "name": "Downtown Mall", "price": 200},
    {"type": "event", "name": "📰 Business Event"},
    {"type": "property", "name": "Skyline Tower", "price": 220},
    {"type": "property", "name": "Gold Mine Co.", "price": 240},
    {"type": "property", "name": "Silver Screen Studio", "price": 260},
    {"type": "event", "name": "📰 Business Event"},
    {"type": "property", "name": "Grand Hotel", "price": 280},
    {"type": "property", "name": "Space Port Ventures", "price": 300},
    {"type": "tax", "name": "🧾 Maintenance Tax", "amount": 80},
    {"type": "property", "name": "Diamond Plaza", "price": 320},
    {"type": "property", "name": "Royal Palace Resort", "price": 340},
    {"type": "event", "name": "📰 Business Event"},
]

EVENTS = [
    ("🚀 Your startup went viral! Investors pour in money.", 150),
    ("📉 Market downturn hits your businesses.", -100),
    ("🎉 A charity gala boosts your public image and sales.", 80),
    ("🔥 A minor fire damages one of your properties.", -60),
    ("💼 You closed a great business deal!", 120),
    ("🌧 Bad weather slows business this week.", -40),
]


class BusinessTycoonGame:
    PREFIX = "biz"
    NAME = "Business Tycoon"
    EMOJI = "🏦"
    MIN_PLAYERS = 2
    MAX_PLAYERS = 4
    STARTING_MONEY = 1500
    PASS_START_BONUS = 200
    MAX_ROUNDS = 15
    TURN_SECONDS = 30
    DECISION_SECONDS = 20

    WIN_REWARD = 400
    PARTICIPATION_REWARD = 40

    RULES_TEXT = (
        "🏦 <b>BUSINESS TYCOON - RULES</b> (original property game)\n\n"
        "2-4 players start with 1500 virtual game-money (session-only, separate from "
        "your persistent coin balance).\n\n"
        "Roll the dice to move around the board:\n"
        "• Land on an unowned property → buy it or skip.\n"
        "• Land on someone else's property → pay rent.\n"
        "• Land on a Business Event tile → random gain or loss.\n"
        "• Pass Start → collect a bonus.\n"
        "• Run out of money → you go bankrupt and are out.\n\n"
        f"Game ends after {MAX_ROUNDS} full rounds or when only one player remains. "
        "Highest net worth (money + property values) wins!"
    )

    def __init__(self, bot: Bot, chat_id: int, creator_id: int, on_finish: FinishCallback):
        self.bot = bot
        self.chat_id = chat_id
        self.creator_id = creator_id
        self.on_finish = on_finish
        self.status = "lobby"
        self.players: Dict[int, str] = {}
        self.lobby_message_id: Optional[int] = None
        self._tasks: List[asyncio.Task] = []

        self.money: Dict[int, int] = {}
        self.position: Dict[int, int] = {}
        self.owned: Dict[int, Optional[int]] = {i: None for i in range(len(BOARD))}  # tile_idx -> owner
        self.bankrupt: Dict[int, bool] = {}
        self.turn_order: List[int] = []
        self.turn_index = 0
        self.round_num = 1
        self.board_message_id: Optional[int] = None
        self._awaiting_buy_tile: Optional[int] = None

    def lobby_text(self) -> str:
        lines = [f"{self.EMOJI} <b>GAME LOBBY - {self.NAME}</b>\n",
                  f"👥 Players: {len(self.players)}/{self.MAX_PLAYERS} (min {self.MIN_PLAYERS})\n"]
        for i, name in enumerate(self.players.values(), 1):
            lines.append(f"{i}. {name}")
        if not self.players:
            lines.append("(no one yet)")
        lines.append("\nPress JOIN to enter!")
        return "\n".join(lines)

    def lobby_keyboard(self):
        b = InlineKeyboardBuilder()
        b.button(text="🎮 JOIN", callback_data=f"{self.PREFIX}:join")
        b.button(text="🚀 START", callback_data=f"{self.PREFIX}:start")
        b.button(text="❌ CANCEL", callback_data=f"{self.PREFIX}:cancel")
        b.adjust(2, 1)
        return b.as_markup()

    async def add_player(self, user_id: int, name: str) -> Tuple[bool, str]:
        if self.status != "lobby":
            return False, "❌ This game has already started."
        if user_id in self.players:
            return False, "You already joined!"
        if len(self.players) >= self.MAX_PLAYERS:
            return False, "❌ Lobby is full."
        self.players[user_id] = _safe_name(name)
        return True, f"✅ {_safe_name(name)} joined ({len(self.players)}/{self.MAX_PLAYERS})"

    async def try_start(self, requester_id: int) -> Tuple[bool, str]:
        if self.status != "lobby":
            return False, "❌ Game already started."
        if len(self.players) < self.MIN_PLAYERS:
            return False, f"❌ Need at least {self.MIN_PLAYERS} players (have {len(self.players)})."
        await self._begin()
        return True, "🚀 Game starting!"

    async def send_lobby(self) -> None:
        msg = await self.bot.send_message(self.chat_id, self.lobby_text(), reply_markup=self.lobby_keyboard())
        self.lobby_message_id = msg.message_id

    async def _refresh_lobby(self) -> None:
        if self.lobby_message_id:
            try:
                await self.bot.edit_message_text(
                    self.lobby_text(), self.chat_id, self.lobby_message_id,
                    reply_markup=self.lobby_keyboard()
                )
            except Exception:
                pass

    async def _begin(self) -> None:
        self.status = "running"
        self.turn_order = list(self.players.keys())
        random.shuffle(self.turn_order)
        self.money = {uid: self.STARTING_MONEY for uid in self.turn_order}
        self.position = {uid: 0 for uid in self.turn_order}
        self.bankrupt = {uid: False for uid in self.turn_order}
        self.turn_index = 0
        self.round_num = 1

        msg = await self.bot.send_message(self.chat_id, self._render(), reply_markup=self._roll_keyboard())
        self.board_message_id = msg.message_id
        self._tasks.append(asyncio.create_task(self._turn_timer()))

    def _active(self) -> List[int]:
        return [uid for uid in self.turn_order if not self.bankrupt[uid]]

    def _current(self) -> int:
        active = self._active()
        return active[self.turn_index % len(active)]

    def _render(self) -> str:
        lines = [f"{self.EMOJI} <b>Business Tycoon</b> (Round {self.round_num}/{self.MAX_ROUNDS})\n"]
        for uid in self.turn_order:
            if self.bankrupt[uid]:
                lines.append(f"• {self.players[uid]}: 💀 Bankrupt")
            else:
                tile = BOARD[self.position[uid]]["name"]
                lines.append(f"• {self.players[uid]}: 💵{self.money[uid]} @ {tile}")
        if self._active():
            lines.append(f"\n👉 Turn: {self.players[self._current()]}")
        return "\n".join(lines)

    def _roll_keyboard(self):
        b = InlineKeyboardBuilder()
        b.button(text="🎲 Roll Dice", callback_data=f"{self.PREFIX}:roll")
        return b.as_markup()

    def _buy_keyboard(self, tile_idx: int):
        b = InlineKeyboardBuilder()
        b.button(text="💰 Buy", callback_data=f"{self.PREFIX}:buy:{tile_idx}")
        b.button(text="⏭ Skip", callback_data=f"{self.PREFIX}:skip:{tile_idx}")
        return b.as_markup()

    async def _refresh_board(self, keyboard=None) -> None:
        if self.board_message_id:
            try:
                await self.bot.edit_message_text(
                    self._render(), self.chat_id, self.board_message_id,
                    reply_markup=keyboard or self._roll_keyboard()
                )
            except Exception:
                pass

    async def _turn_timer(self) -> None:
        try:
            while self.status == "running":
                await asyncio.sleep(self.TURN_SECONDS)
                if self.status != "running":
                    break
                await self.bot.send_message(self.chat_id, "⏱ Turn timed out, moving to next player.")
                self._next_turn()
                if not await self._check_end():
                    await self._refresh_board()
        except asyncio.CancelledError:
            pass

    def _next_turn(self) -> None:
        active = self._active()
        if not active:
            return
        self.turn_index += 1
        if self.turn_index % max(1, len(active)) == 0:
            self.round_num += 1

    async def handle_callback(self, callback: CallbackQuery) -> None:
        data = callback.data or ""
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""

        if action == "join":
            ok, msg = await self.add_player(callback.from_user.id, callback.from_user.first_name)
            await callback.answer(msg, show_alert=not ok)
            if ok:
                await self._refresh_lobby()
        elif action == "cancel":
            if callback.from_user.id != self.creator_id:
                await callback.answer("Only the creator can cancel.", show_alert=True)
                return
            await callback.answer("Cancelled.")
            await self.force_end("Cancelled by creator.")
        elif action == "start":
            ok, msg = await self.try_start(callback.from_user.id)
            await callback.answer(msg, show_alert=not ok)
        elif action == "roll":
            await self._handle_roll(callback)
        elif action == "buy":
            await self._handle_buy_decision(callback, int(parts[2]), buy=True)
        elif action == "skip":
            await self._handle_buy_decision(callback, int(parts[2]), buy=False)

    async def _handle_roll(self, callback: CallbackQuery) -> None:
        if self.status != "running":
            await callback.answer("Game not running.", show_alert=True)
            return
        current = self._current()
        if callback.from_user.id != current:
            await callback.answer("❌ It's not your turn!", show_alert=True)
            return

        roll = random.randint(1, 6)
        await callback.answer(f"🎲 Rolled a {roll}!")
        old_pos = self.position[current]
        new_pos = (old_pos + roll) % len(BOARD)
        passed_start = new_pos < old_pos or (old_pos + roll) >= len(BOARD)
        self.position[current] = new_pos

        msg_lines = [f"🎲 {self.players[current]} rolled {roll} and landed on <b>{BOARD[new_pos]['name']}</b>."]
        if passed_start and new_pos != 0:
            self.money[current] += self.PASS_START_BONUS
            msg_lines.append(f"🏁 Passed Start! +{self.PASS_START_BONUS}")

        tile = BOARD[new_pos]
        keyboard = None
        if tile["type"] == "start":
            self.money[current] += self.PASS_START_BONUS
            msg_lines.append(f"🏁 Landed on Start! +{self.PASS_START_BONUS}")
        elif tile["type"] == "tax":
            self.money[current] -= tile["amount"]
            msg_lines.append(f"🧾 Paid {tile['amount']} in maintenance tax.")
        elif tile["type"] == "event":
            text, delta = random.choice(EVENTS)
            self.money[current] += delta
            sign = "+" if delta >= 0 else ""
            msg_lines.append(f"{text} ({sign}{delta})")
        elif tile["type"] == "property":
            owner = self.owned[new_pos]
            if owner is None:
                if self.money[current] >= tile["price"]:
                    msg_lines.append(f"🏷 Unowned! Price: {tile['price']}. Buy it?")
                    keyboard = self._buy_keyboard(new_pos)
                else:
                    msg_lines.append("🏷 Unowned, but you can't afford it.")
            elif owner == current:
                msg_lines.append("🏠 You already own this property.")
            else:
                rent = max(10, tile["price"] // 7)
                self.money[current] -= rent
                self.money[owner] += rent
                msg_lines.append(f"💸 Paid {rent} rent to {self.players[owner]}.")

        await self.bot.send_message(self.chat_id, "\n".join(msg_lines))

        if self.money[current] < 0:
            await self._go_bankrupt(current)
            if await self._check_end():
                return
            self._next_turn()
            await self._refresh_board()
            return

        if keyboard is None:
            self._next_turn()
        await self._refresh_board(keyboard=keyboard)

    async def _handle_buy_decision(self, callback: CallbackQuery, tile_idx: int, buy: bool) -> None:
        current = self._current()
        if callback.from_user.id != current:
            await callback.answer("❌ Not your decision!", show_alert=True)
            return
        if buy:
            price = BOARD[tile_idx]["price"]
            if self.money[current] < price:
                await callback.answer("Not enough money.", show_alert=True)
                return
            self.money[current] -= price
            self.owned[tile_idx] = current
            await callback.answer("Purchased!")
            await self.bot.send_message(self.chat_id, f"✅ {self.players[current]} bought {BOARD[tile_idx]['name']}!")
        else:
            await callback.answer("Skipped.")

        self._next_turn()
        if not await self._check_end():
            await self._refresh_board()

    async def _go_bankrupt(self, uid: int) -> None:
        self.bankrupt[uid] = True
        for tile_idx, owner in self.owned.items():
            if owner == uid:
                self.owned[tile_idx] = None
        await self.bot.send_message(self.chat_id, f"💀 {self.players[uid]} has gone bankrupt and is out of the game!")

    async def _check_end(self) -> bool:
        active = self._active()
        if len(active) <= 1 or self.round_num > self.MAX_ROUNDS:
            await self._finish()
            return True
        return False

    def _net_worth(self, uid: int) -> int:
        worth = self.money[uid]
        for tile_idx, owner in self.owned.items():
            if owner == uid:
                worth += BOARD[tile_idx]["price"]
        return worth

    async def _finish(self) -> None:
        for t in self._tasks:
            t.cancel()
        active = self._active()
        if len(active) == 1:
            winner = active[0]
        else:
            winner = max(self.turn_order, key=lambda u: self._net_worth(u) if not self.bankrupt[u] else -1)

        lines = [f"{self.EMOJI} <b>GAME OVER - Business Tycoon</b>\n", "📊 Final net worth:"]
        for uid in self.turn_order:
            worth = self._net_worth(uid) if not self.bankrupt[uid] else 0
            lines.append(f"• {self.players[uid]}: {'💀 Bankrupt' if self.bankrupt[uid] else worth}")
        lines.append(f"\n🏆 Winner: <b>{self.players[winner]}</b>\n")

        lines.append("💰 <b>Rewards:</b>")
        for uid in self.players:
            amt = self.WIN_REWARD if uid == winner else self.PARTICIPATION_REWARD
            new_bal = db.add_coins(uid, amt)
            lines.append(f"• {self.players[uid]}: +{amt} coins (balance: {new_bal})")
            db.update_stats(uid, won=(uid == winner))
        db.record_game_result(self.chat_id, self.NAME, winner, list(self.players.keys()))

        await self.bot.send_message(self.chat_id, "\n".join(lines))
        self.status = "ended"
        self.on_finish(self.chat_id)

    async def force_end(self, reason: str) -> None:
        for t in self._tasks:
            t.cancel()
        self.status = "ended"
        try:
            await self.bot.send_message(self.chat_id, f"🛑 <b>GAME ENDED</b>\n\n{reason}")
        except Exception:
            pass
        self.on_finish(self.chat_id)
