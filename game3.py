"""
game3.py
--------
Three complete multiplayer games:

1. Ludo - 4 tokens per player on a simplified shared track
2. Power Rangers - original turn-based battle mini-game
3. Business Tycoon - original property-trading game

All coins/money in these games are virtual and have no real-world value.

LUDO NOTE:
This version uses FOUR TOKENS PER PLAYER. Each player can bring all 4 tokens
out of the yard, move them independently, capture opponents, and must get all
4 tokens to the finish to win. The board is a Telegram-friendly simplified
52-cell shared loop plus a private home stretch for each player.
"""

from __future__ import annotations

import asyncio
import random
import math
import os
import tempfile
import struct
import zlib
from typing import Callable, Dict, List, Optional, Tuple

from aiogram import Bot
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db

FinishCallback = Callable[[int], None]


def _safe_name(name: str) -> str:
    return name if name else "Player"


# ==========================================================================
# 1) LUDO - FOUR TOKENS PER PLAYER
# ==========================================================================


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + kind + data +
            struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def _write_png(path: str, width: int, height: int, pixels: bytearray) -> None:
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * stride:(y + 1) * stride])
    png = (b"\x89PNG\r\n\x1a\n" +
           _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
           _png_chunk(b"IDAT", zlib.compress(bytes(raw), 6)) +
           _png_chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def _set_px(pixels: bytearray, width: int, height: int, x: int, y: int,
            rgb: Tuple[int, int, int]) -> None:
    if 0 <= x < width and 0 <= y < height:
        i = (y * width + x) * 3
        pixels[i:i + 3] = bytes(rgb)


def _fill_circle(pixels: bytearray, width: int, height: int,
                 cx: int, cy: int, r: int,
                 rgb: Tuple[int, int, int]) -> None:
    r2 = r * r
    for y in range(max(0, cy - r), min(height, cy + r + 1)):
        dy = y - cy
        for x in range(max(0, cx - r), min(width, cx + r + 1)):
            dx = x - cx
            if dx * dx + dy * dy <= r2:
                _set_px(pixels, width, height, x, y, rgb)


class LudoGame:
    PREFIX = "ludo"
    NAME = "Ludo"
    EMOJI = "🎲"

    MIN_PLAYERS = 2
    MAX_PLAYERS = 4

    # IMPORTANT: every player has FOUR independently movable tokens.
    TOKENS_PER_PLAYER = 4

    TURN_SECONDS = 30

    MAIN_TRACK_LEN = 52
    STEPS_ON_MAIN = 51
    LAST_MAIN_LOCAL = STEPS_ON_MAIN - 1

    HOME_STRETCH_LEN = 6
    FINISH_LOCAL = STEPS_ON_MAIN + HOME_STRETCH_LEN - 1

    SAFE_CELLS = {0, 8, 13, 21, 26, 34, 39, 47}
    START_OFFSETS = [0, 13, 26, 39]

    WIN_REWARD = 400
    PARTICIPATION_REWARD = 40
    CAPTURE_BONUS = 30

    RULES_TEXT = (
        "🎲 <b>LUDO - RULES</b>\n\n"
        "2-4 players, 4 tokens each.\n"
        "• Roll a 6 to bring a token out of your yard.\n"
        "• Roll again if you roll a 6.\n"
        "• Three 6s in a row forfeits the turn.\n"
        "• If multiple tokens can move, choose which token to move.\n"
        "• Land exactly on an opponent's token on a non-safe cell to capture it.\n"
        "• Safe cells protect tokens from capture.\n"
        "• Each of your 4 tokens moves around the shared loop and then your "
        "private home stretch.\n"
        "• Get ALL 4 tokens home to win!"
    )

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        creator_id: int,
        on_finish: FinishCallback,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.creator_id = creator_id
        self.on_finish = on_finish

        self.status = "lobby"
        self.players: Dict[int, str] = {}
        self.lobby_message_id: Optional[int] = None
        self._tasks: List[asyncio.Task] = []

        # uid -> [token1, token2, token3, token4]
        # -1 = yard
        # 0..LAST_MAIN_LOCAL = shared track
        # LAST_MAIN_LOCAL+1..FINISH_LOCAL = home stretch
        # FINISH_LOCAL = home
        self.tokens: Dict[int, List[int]] = {}

        self.start_offset: Dict[int, int] = {}
        self.turn_order: List[int] = []
        self.turn_index = 0
        self.consecutive_sixes = 0

        self.board_message_id: Optional[int] = None

        self.tokens_emoji = ["🔴", "🔵", "🟢", "🟡"]
        self.emoji_of: Dict[int, str] = {}

        self._pending_roll: Optional[int] = None
        self._pending_player: Optional[int] = None

    def lobby_text(self) -> str:
        lines = [
            f"{self.EMOJI} <b>GAME LOBBY - {self.NAME}</b>\n",
            f"👥 Players: {len(self.players)}/{self.MAX_PLAYERS} "
            f"(min {self.MIN_PLAYERS})\n",
        ]

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
        return (
            True,
            f"✅ {_safe_name(name)} joined "
            f"({len(self.players)}/{self.MAX_PLAYERS})",
        )

    async def try_start(self, requester_id: int) -> Tuple[bool, str]:
        if self.status != "lobby":
            return False, "❌ Game already started."

        if len(self.players) < self.MIN_PLAYERS:
            return (
                False,
                f"❌ Need at least {self.MIN_PLAYERS} players "
                f"(have {len(self.players)}).",
            )

        await self._begin()
        return True, "🚀 Game starting!"

    async def send_lobby(self) -> None:
        msg = await self.bot.send_message(
            self.chat_id,
            self.lobby_text(),
            reply_markup=self.lobby_keyboard(),
        )
        self.lobby_message_id = msg.message_id

    async def _refresh_lobby(self) -> None:
        if self.lobby_message_id:
            try:
                await self.bot.edit_message_text(
                    self.lobby_text(),
                    self.chat_id,
                    self.lobby_message_id,
                    reply_markup=self.lobby_keyboard(),
                )
            except Exception:
                pass

    async def _begin(self) -> None:
        self.status = "running"

        self.turn_order = list(self.players.keys())
        random.shuffle(self.turn_order)

        # FOUR TOKENS FOR EVERY PLAYER.
        for i, uid in enumerate(self.turn_order):
            self.emoji_of[uid] = self.tokens_emoji[
                i % len(self.tokens_emoji)
            ]
            self.start_offset[uid] = self.START_OFFSETS[
                i % len(self.START_OFFSETS)
            ]

            # Explicitly create exactly four token positions.
            self.tokens[uid] = [-1 for _ in range(self.TOKENS_PER_PLAYER)]

        self.turn_index = 0
        self.consecutive_sixes = 0
        self._pending_roll = None
        self._pending_player = None

        msg = await self.bot.send_message(
            self.chat_id,
            self._render(),
            reply_markup=self._roll_keyboard(),
        )
        self.board_message_id = msg.message_id
        await self._send_ludo_board_image(
            f"🎲 Ludo board — {self.players[self._current()]}'s turn. Token positions are shown."
        )
        await self.bot.send_message(
            self.chat_id,
            f"🎯 {self.players[self._current()]}, it's your turn! 🎲"
        )

        self._tasks.append(asyncio.create_task(self._turn_timer()))

    def _current(self) -> int:
        return self.turn_order[self.turn_index % len(self.turn_order)]

    def _global_cell(self, uid: int, local: int) -> int:
        return (self.start_offset[uid] + local) % self.MAIN_TRACK_LEN

    def _token_status_text(self, uid: int, local: int) -> str:
        if local == -1:
            return "yard"

        if local == self.FINISH_LOCAL:
            return "HOME 🏁"

        if local > self.LAST_MAIN_LOCAL:
            step = local - self.LAST_MAIN_LOCAL
            return f"home stretch ({step}/{self.HOME_STRETCH_LEN - 1})"

        return f"cell {self._global_cell(uid, local)}"

    def _render(self) -> str:
        lines = [f"{self.EMOJI} <b>Ludo</b> - 4 Tokens Each\n"]

        for uid in self.turn_order:
            token_strs = [
                f"T{i + 1}:{self._token_status_text(uid, local)}"
                for i, local in enumerate(self.tokens[uid])
            ]

            finished = sum(
                1
                for local in self.tokens[uid]
                if local == self.FINISH_LOCAL
            )

            lines.append(
                f"{self.emoji_of[uid]} {self.players[uid]} "
                f"({finished}/4 home): "
                + ", ".join(token_strs)
            )

        if self.turn_order:
            current = self._current()
            lines.append(
                f"\n👉 Turn: {self.emoji_of[current]} "
                f"{self.players[current]}"
            )

        return "\n".join(lines)

    def _roll_keyboard(self):
        b = InlineKeyboardBuilder()
        b.button(
            text="🎲 Roll Dice",
            callback_data=f"{self.PREFIX}:roll",
        )
        return b.as_markup()

    def _movable_tokens(self, uid: int, roll: int) -> List[int]:
        movable: List[int] = []

        for i, local in enumerate(self.tokens[uid]):
            # Token in yard: only a 6 can bring it onto the start cell.
            if local == -1:
                if roll == 6:
                    movable.append(i)
                continue

            # Finished tokens cannot move.
            if local == self.FINISH_LOCAL:
                continue

            # Exact landing is required; no overshooting home.
            if local + roll <= self.FINISH_LOCAL:
                movable.append(i)

        return movable

    def _token_choice_keyboard(
        self,
        uid: int,
        movable: List[int],
    ):
        b = InlineKeyboardBuilder()

        for i in movable:
            local = self.tokens[uid][i]
            label = (
                f"{self.emoji_of[uid]} "
                f"T{i + 1} ({self._token_status_text(uid, local)})"
            )

            b.button(
                text=label,
                callback_data=f"{self.PREFIX}:token:{i}",
            )

        b.adjust(1)
        return b.as_markup()

    def _token_color(self, uid: int) -> Tuple[int, int, int]:
        return {
            "🔴": (220, 55, 55),
            "🔵": (55, 105, 220),
            "🟢": (55, 175, 85),
            "🟡": (235, 190, 45),
        }.get(self.emoji_of.get(uid, ""), (120, 120, 120))

    def _make_ludo_board_image(self) -> str:
        """Create a lightweight PNG showing all four-token positions."""
        width, height = 900, 900
        bg = (245, 247, 250)
        pixels = bytearray(bytes(bg) * (width * height))
        cx, cy, radius = 450, 430, 300

        track = []
        for cell in range(self.MAIN_TRACK_LEN):
            angle = -math.pi / 2 + 2 * math.pi * cell / self.MAIN_TRACK_LEN
            track.append((round(cx + radius * math.cos(angle)),
                          round(cy + radius * math.sin(angle))))

        _fill_circle(pixels, width, height, cx, cy, radius + 42, (225, 229, 235))
        _fill_circle(pixels, width, height, cx, cy, radius + 32, bg)
        for cell, (x, y) in enumerate(track):
            _fill_circle(pixels, width, height, x, y, 18,
                         (255, 231, 160) if cell in self.SAFE_CELLS else (255, 255, 255))
            _fill_circle(pixels, width, height, x, y, 11, (190, 195, 205))

        _fill_circle(pixels, width, height, cx, cy, 72, (235, 238, 244))
        _fill_circle(pixels, width, height, cx, cy, 50, (255, 255, 255))

        yards = [(145, 180), (755, 180), (755, 680), (145, 680)]
        for idx, uid in enumerate(self.turn_order[:4]):
            ux, uy = yards[idx]
            col = self._token_color(uid)
            pale = tuple(min(255, int(c + (255 - c) * 0.72)) for c in col)
            _fill_circle(pixels, width, height, ux, uy, 70, pale)
            slots = [(ux - 27, uy - 27), (ux + 27, uy - 27),
                     (ux - 27, uy + 27), (ux + 27, uy + 27)]
            for j, (sx, sy) in enumerate(slots):
                if self.tokens.get(uid, [-1] * 4)[j] == -1:
                    _fill_circle(pixels, width, height, sx, sy, 16, (245, 245, 248))
                    _fill_circle(pixels, width, height, sx, sy, 11, col)

        occupied: Dict[Tuple[int, int], int] = {}
        offsets = [(0, 0), (-11, -11), (11, -11), (-11, 11), (11, 11)]
        for uid in self.turn_order:
            col = self._token_color(uid)
            for local in self.tokens.get(uid, []):
                if local == -1:
                    continue
                if local == self.FINISH_LOCAL:
                    bx, by = cx, cy
                elif local <= self.LAST_MAIN_LOCAL:
                    bx, by = track[self._global_cell(uid, local)]
                else:
                    step = local - self.LAST_MAIN_LOCAL
                    angle = -math.pi / 2 + 2 * math.pi * self.start_offset[uid] / self.MAIN_TRACK_LEN
                    dist = radius - 55 - step * 32
                    bx, by = round(cx + dist * math.cos(angle)), round(cy + dist * math.sin(angle))
                count = occupied.get((bx, by), 0)
                occupied[(bx, by)] = count + 1
                ox, oy = offsets[min(count, len(offsets) - 1)]
                _fill_circle(pixels, width, height, bx + ox, by + oy, 14, (35, 35, 40))
                _fill_circle(pixels, width, height, bx + ox, by + oy, 10, col)

        # Ring around the current player's yard.
        if self.turn_order:
            current = self._current()
            idx = self.turn_order.index(current)
            ux, uy = yards[idx]
            col = self._token_color(current)
            _fill_circle(pixels, width, height, ux, uy, 76, col)
            pale = tuple(min(255, int(c + (255 - c) * 0.72)) for c in col)
            _fill_circle(pixels, width, height, ux, uy, 70, pale)

        fd, path = tempfile.mkstemp(prefix="ludo_", suffix=".png")
        os.close(fd)
        _write_png(path, width, height, pixels)
        return path

    async def _send_ludo_board_image(self, caption: str) -> None:
        path = self._make_ludo_board_image()
        try:
            await self.bot.send_photo(self.chat_id, FSInputFile(path), caption=caption)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    async def _refresh_board(self, keyboard=None) -> None:
        if self.board_message_id:
            try:
                await self.bot.edit_message_text(
                    self._render(),
                    self.chat_id,
                    self.board_message_id,
                    reply_markup=keyboard or self._roll_keyboard(),
                )
            except Exception:
                pass

    async def _turn_timer(self) -> None:
        try:
            while self.status == "running":
                await asyncio.sleep(self.TURN_SECONDS)

                if self.status != "running":
                    break

                await self.bot.send_message(
                    self.chat_id,
                    "⏱ Turn timed out, moving to next player.",
                )

                self._pending_roll = None
                self._pending_player = None
                self._advance_turn()
                await self._refresh_board()
                if self.status == "running":
                    await self._send_ludo_board_image(
                        f"🎲 Turn changed — {self.players[self._current()]}'s token positions."
                    )
                    await self.bot.send_message(
                        self.chat_id,
                        f"🎯 {self.players[self._current()]}, it's your turn! 🎲"
                    )

        except asyncio.CancelledError:
            pass

    def _advance_turn(self) -> None:
        self.consecutive_sixes = 0
        self._pending_roll = None
        self._pending_player = None
        self.turn_index += 1

    async def handle_callback(self, callback: CallbackQuery) -> None:
        data = callback.data or ""
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""

        if action == "join":
            ok, msg = await self.add_player(
                callback.from_user.id,
                callback.from_user.first_name,
            )
            await callback.answer(msg, show_alert=not ok)

            if ok:
                await self._refresh_lobby()

        elif action == "cancel":
            if callback.from_user.id != self.creator_id:
                await callback.answer(
                    "Only the creator can cancel.",
                    show_alert=True,
                )
                return

            await callback.answer("Cancelled.")
            await self.force_end("Cancelled by creator.")

        elif action == "start":
            ok, msg = await self.try_start(callback.from_user.id)
            await callback.answer(msg, show_alert=not ok)

        elif action == "roll":
            await self._handle_roll(callback)

        elif action == "token" and len(parts) > 2:
            try:
                token_idx = int(parts[2])
            except ValueError:
                await callback.answer(
                    "Invalid token.",
                    show_alert=True,
                )
                return

            await self._handle_token_choice(callback, token_idx)

    async def _handle_roll(self, callback: CallbackQuery) -> None:
        if self.status != "running":
            await callback.answer(
                "Game not running.",
                show_alert=True,
            )
            return

        current = self._current()

        if callback.from_user.id != current:
            await callback.answer(
                "❌ It's not your turn!",
                show_alert=True,
            )
            return

        if self._pending_roll is not None:
            await callback.answer(
                "Choose a token to move first.",
                show_alert=True,
            )
            return

        roll = random.randint(1, 6)

        await callback.answer(f"🎲 You rolled a {roll}!")

        await self.bot.send_message(
            self.chat_id,
            f"🎲 {self.players[current]} rolled a <b>{roll}</b>.",
        )

        movable = self._movable_tokens(current, roll)

        if not movable:
            await self.bot.send_message(
                self.chat_id,
                "❌ No valid token moves with this roll.",
            )
            await self._after_roll_resolved(current, roll)
            return

        # Exactly one legal token -> move immediately.
        if len(movable) == 1:
            await self._move_token(current, movable[0], roll)
            await self._after_roll_resolved(current, roll)
            return

        # Multiple legal tokens -> player MUST choose one of their four tokens.
        self._pending_roll = roll
        self._pending_player = current

        await self._refresh_board(
            keyboard=self._token_choice_keyboard(current, movable)
        )

    async def _handle_token_choice(
        self,
        callback: CallbackQuery,
        token_idx: int,
    ) -> None:
        if self.status != "running":
            await callback.answer(
                "Game not running.",
                show_alert=True,
            )
            return

        current = self._current()

        if callback.from_user.id != current:
            await callback.answer(
                "❌ It's not your turn!",
                show_alert=True,
            )
            return

        if self._pending_roll is None or self._pending_player != current:
            await callback.answer(
                "No pending token choice.",
                show_alert=True,
            )
            return

        if not 0 <= token_idx < self.TOKENS_PER_PLAYER:
            await callback.answer(
                "Invalid token.",
                show_alert=True,
            )
            return

        roll = self._pending_roll

        movable = self._movable_tokens(current, roll)

        if token_idx not in movable:
            await callback.answer(
                "That token cannot move with this roll.",
                show_alert=True,
            )
            return

        self._pending_roll = None
        self._pending_player = None

        await callback.answer()

        await self._move_token(current, token_idx, roll)
        await self._after_roll_resolved(current, roll)

    async def _move_token(
        self,
        uid: int,
        token_idx: int,
        roll: int,
    ) -> None:
        old_local = self.tokens[uid][token_idx]

        # Bringing a token out of the yard with a 6.
        if old_local == -1:
            new_local = 0
            self.tokens[uid][token_idx] = new_local

            await self.bot.send_message(
                self.chat_id,
                f"{self.emoji_of[uid]} "
                f"{self.players[uid]}'s token T{token_idx + 1} "
                f"leaves the yard and enters cell "
                f"{self._global_cell(uid, new_local)}!",
            )

        else:
            new_local = old_local + roll
            self.tokens[uid][token_idx] = new_local

            await self.bot.send_message(
                self.chat_id,
                f"{self.emoji_of[uid]} "
                f"{self.players[uid]}'s token T{token_idx + 1} "
                f"moves to "
                f"{self._token_status_text(uid, new_local)}.",
            )

        # Token reached the finish.
        if new_local == self.FINISH_LOCAL:
            await self.bot.send_message(
                self.chat_id,
                f"🏁 {self.players[uid]}'s token "
                f"T{token_idx + 1} made it home!",
            )
            return

        # Capture only occurs on the shared main track.
        if new_local <= self.LAST_MAIN_LOCAL:
            global_cell = self._global_cell(uid, new_local)

            if global_cell not in self.SAFE_CELLS:
                for other in self.turn_order:
                    if other == uid:
                        continue

                    for j, other_local in enumerate(self.tokens[other]):
                        if other_local in (-1, self.FINISH_LOCAL):
                            continue

                        if other_local <= self.LAST_MAIN_LOCAL:
                            other_global = self._global_cell(
                                other,
                                other_local,
                            )

                            if other_global == global_cell:
                                self.tokens[other][j] = -1

                                db.add_coins(
                                    uid,
                                    self.CAPTURE_BONUS,
                                )

                                await self.bot.send_message(
                                    self.chat_id,
                                    f"💥 {self.players[uid]} captured "
                                    f"{self.players[other]}'s token "
                                    f"T{j + 1}! Sent back to yard.",
                                )

    async def _after_roll_resolved(
        self,
        uid: int,
        roll: int,
    ) -> None:
        # WIN CONDITION: all four tokens are home.
        if all(
            local == self.FINISH_LOCAL
            for local in self.tokens[uid]
        ):
            # Show the final board image too, so the winning token positions
            # are visible before the game-over message.
            await self._send_ludo_board_image(
                f"🏁 Final Ludo board — {self.players[uid]} has all 4 tokens home!"
            )
            await self._finish(uid)
            return

        if roll == 6:
            self.consecutive_sixes += 1

            if self.consecutive_sixes >= 3:
                await self.bot.send_message(
                    self.chat_id,
                    "❌ Three 6's in a row - turn forfeited!",
                )
                self._advance_turn()
            else:
                # Keep the same player for the extra roll.
                self._pending_roll = None
                self._pending_player = None
        else:
            self._advance_turn()

        await self._refresh_board()
        if self.status == "running":
            await self._send_ludo_board_image(
                f"🎲 Turn complete — {self.players[self._current()]}'s token positions."
            )
            await self.bot.send_message(
                self.chat_id,
                f"🎯 {self.players[self._current()]}, it's your turn! 🎲"
            )

    async def _finish(self, winner_id: int) -> None:
        for task in self._tasks:
            task.cancel()

        lines = [
            f"{self.EMOJI} <b>GAME OVER - Ludo</b>\n",
            f"🏆 Winner: <b>{self.players[winner_id]}</b> "
            f"{self.emoji_of[winner_id]} "
            f"(all 4 tokens home!)\n",
            "💰 <b>Rewards:</b>",
        ]

        for uid in self.players:
            amount = (
                self.WIN_REWARD
                if uid == winner_id
                else self.PARTICIPATION_REWARD
            )

            new_balance = db.add_coins(uid, amount)

            lines.append(
                f"• {self.players[uid]}: +{amount} coins "
                f"(balance: {new_balance})"
            )

            db.update_stats(
                uid,
                won=(uid == winner_id),
            )

        db.record_game_result(
            self.chat_id,
            self.NAME,
            winner_id,
            list(self.players.keys()),
        )

        await self.bot.send_message(
            self.chat_id,
            "\n".join(lines),
        )

        self.status = "ended"
        self.on_finish(self.chat_id)

    async def force_end(self, reason: str) -> None:
        for task in self._tasks:
            task.cancel()

        self.status = "ended"

        try:
            await self.bot.send_message(
                self.chat_id,
                f"🛑 <b>GAME ENDED</b>\n\n{reason}",
            )
        except Exception:
            pass

        self.on_finish(self.chat_id)


# ==========================================================================
# 2) POWER RANGERS - ORIGINAL BATTLE MINI-GAME
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
        "strike": {
            "name": "Power Strike",
            "cost": 20,
            "cooldown": 0,
            "dmg": (20, 30),
        },
        "shield": {
            "name": "Shield",
            "cost": 15,
            "cooldown": 2,
            "dmg": None,
        },
        "boost": {
            "name": "Team Boost",
            "cost": 25,
            "cooldown": 3,
            "heal": 15,
        },
        "blast": {
            "name": "Energy Blast",
            "cost": 30,
            "cooldown": 2,
            "dmg": (15, 25),
        },
    }

    RULES_TEXT = (
        "⚡ <b>POWER RANGERS - RULES</b> (original mini-game)\n\n"
        "2-6 players battle in free-for-all combat with 100 HP and "
        "100 Energy each.\n\n"
        "Abilities:\n"
        "• 💥 Power Strike (20 energy): 20-30 damage to a target.\n"
        "• 🛡 Shield (15 energy, cooldown 2): halves the next hit you take.\n"
        "• 💚 Team Boost (25 energy, cooldown 3): heal 15 HP.\n"
        "• 🌀 Energy Blast (30 energy, cooldown 2): 15-25 damage, "
        "ignores Shield.\n\n"
        "Energy regenerates +10 each of your turns. Last Ranger standing wins!"
    )

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        creator_id: int,
        on_finish: FinishCallback,
    ):
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
        self._pending_action: Optional[str] = None

    def lobby_text(self) -> str:
        lines = [
            f"{self.EMOJI} <b>GAME LOBBY - {self.NAME}</b>\n",
            f"👥 Players: {len(self.players)}/{self.MAX_PLAYERS} "
            f"(min {self.MIN_PLAYERS})\n",
        ]

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
            return False, "❌ Lobby is full!"

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
        msg = await self.bot.send_message(
            self.chat_id,
            self.lobby_text(),
            reply_markup=self.lobby_keyboard(),
        )
        self.lobby_message_id = msg.message_id

    async def _refresh_lobby(self) -> None:
        if self.lobby_message_id:
            try:
                await self.bot.edit_message_text(
                    self.lobby_text(),
                    self.chat_id,
                    self.lobby_message_id,
                    reply_markup=self.lobby_keyboard(),
                )
            except Exception:
                pass

    async def _begin(self) -> None:
        self.status = "running"
        self.turn_order = list(self.players.keys())
        random.shuffle(self.turn_order)

        self.hp = {
            uid: self.START_HP
            for uid in self.turn_order
        }
        self.energy = {
            uid: self.START_ENERGY
            for uid in self.turn_order
        }
        self.shielded = {
            uid: False
            for uid in self.turn_order
        }
        self.cooldowns = {
            uid: {key: 0 for key in self.ABILITIES}
            for uid in self.turn_order
        }

        self.turn_index = 0
        self.round_num = 1

        msg = await self.bot.send_message(
            self.chat_id,
            self._render(),
            reply_markup=self._ability_keyboard(),
        )
        self.board_message_id = msg.message_id

        self._tasks.append(asyncio.create_task(self._turn_timer()))

    def _alive(self) -> List[int]:
        return [
            uid
            for uid in self.turn_order
            if self.hp[uid] > 0
        ]

    def _current(self) -> int:
        alive = self._alive()
        idx = self.turn_index % len(alive)
        return alive[idx]

    def _render(self) -> str:
        lines = [
            f"{self.EMOJI} <b>Power Rangers Battle</b> "
            f"(Round {self.round_num}/{self.MAX_ROUNDS})\n"
        ]

        for uid in self.turn_order:
            status = (
                "💀 KO"
                if self.hp[uid] <= 0
                else f"❤️{self.hp[uid]} ⚡{self.energy[uid]}"
            )

            shield = " 🛡" if self.shielded.get(uid) else ""

            lines.append(
                f"• {self.players[uid]}: {status}{shield}"
            )

        if self._alive():
            lines.append(
                f"\n👉 Turn: {self.players[self._current()]}"
            )

        return "\n".join(lines)

    def _ability_keyboard(self):
        b = InlineKeyboardBuilder()
        current = self._current()

        for key, ab in self.ABILITIES.items():
            cd = self.cooldowns[current][key]
            label = f"{ab['name']} ({ab['cost']}⚡)"

            if cd > 0:
                label += f" [CD {cd}]"

            b.button(
                text=label,
                callback_data=f"{self.PREFIX}:ability:{key}",
            )

        b.adjust(2)
        return b.as_markup()

    def _target_keyboard(self, action: str):
        b = InlineKeyboardBuilder()
        current = self._current()

        for uid in self._alive():
            if uid != current:
                b.button(
                    text=self.players[uid],
                    callback_data=f"{self.PREFIX}:target:{action}:{uid}",
                )

        b.adjust(2)
        return b.as_markup()

    async def _refresh_board(self, keyboard=None) -> None:
        if self.board_message_id:
            try:
                await self.bot.edit_message_text(
                    self._render(),
                    self.chat_id,
                    self.board_message_id,
                    reply_markup=keyboard or self._ability_keyboard(),
                )
            except Exception:
                pass

    async def _turn_timer(self) -> None:
        try:
            while self.status == "running":
                await asyncio.sleep(self.TURN_SECONDS)

                if self.status != "running":
                    break

                await self.bot.send_message(
                    self.chat_id,
                    "⏱ Turn timed out, skipping.",
                )

                self._next_turn()
                await self._refresh_board()
                if self.status == "running" and self._alive():
                    await self.bot.send_message(
                        self.chat_id,
                        f"🎯 {self.players[self._current()]}, it's your turn! ⚔️"
                    )

        except asyncio.CancelledError:
            pass

    def _next_turn(self) -> None:
        current = self._current()

        for key in self.cooldowns[current]:
            if self.cooldowns[current][key] > 0:
                self.cooldowns[current][key] -= 1

        self.energy[current] = min(
            self.START_ENERGY,
            self.energy[current] + self.ENERGY_REGEN,
        )

        self._pending_action = None
        self.turn_index += 1

        if self.turn_index % max(1, len(self._alive())) == 0:
            self.round_num += 1

    async def handle_callback(self, callback: CallbackQuery) -> None:
        data = callback.data or ""
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""

        if action == "join":
            ok, msg = await self.add_player(
                callback.from_user.id,
                callback.from_user.first_name,
            )
            await callback.answer(msg, show_alert=not ok)

            if ok:
                await self._refresh_lobby()

        elif action == "cancel":
            if callback.from_user.id != self.creator_id:
                await callback.answer(
                    "Only the creator can cancel.",
                    show_alert=True,
                )
                return

            await callback.answer("Cancelled.")
            await self.force_end("Cancelled by creator.")

        elif action == "start":
            ok, msg = await self.try_start(callback.from_user.id)
            await callback.answer(msg, show_alert=not ok)

        elif action == "ability":
            if len(parts) > 2:
                await self._handle_ability(callback, parts[2])

        elif action == "target":
            if len(parts) > 3:
                try:
                    target_id = int(parts[3])
                except ValueError:
                    await callback.answer("Invalid target.", show_alert=True)
                    return

                await self._handle_target(
                    callback,
                    parts[2],
                    target_id,
                )

    async def _handle_ability(
        self,
        callback: CallbackQuery,
        key: str,
    ) -> None:
        if self.status != "running":
            await callback.answer(
                "Game not running.",
                show_alert=True,
            )
            return

        if key not in self.ABILITIES:
            await callback.answer(
                "Invalid ability.",
                show_alert=True,
            )
            return

        current = self._current()

        if callback.from_user.id != current:
            await callback.answer(
                "❌ It's not your turn!",
                show_alert=True,
            )
            return

        ab = self.ABILITIES[key]

        if self.cooldowns[current][key] > 0:
            await callback.answer(
                "That ability is on cooldown.",
                show_alert=True,
            )
            return

        if self.energy[current] < ab["cost"]:
            await callback.answer(
                "Not enough energy.",
                show_alert=True,
            )
            return

        if key in ("strike", "blast"):
            await callback.answer("Choose a target.")
            await self._refresh_board(
                keyboard=self._target_keyboard(key)
            )
            return

        self.energy[current] -= ab["cost"]

        if key == "shield":
            self.shielded[current] = True
            self.cooldowns[current][key] = ab["cooldown"]

            await self.bot.send_message(
                self.chat_id,
                f"🛡 {self.players[current]} raises a Shield!",
            )

        elif key == "boost":
            heal = ab["heal"]

            self.hp[current] = min(
                self.START_HP,
                self.hp[current] + heal,
            )

            self.cooldowns[current][key] = ab["cooldown"]

            await self.bot.send_message(
                self.chat_id,
                f"💚 {self.players[current]} uses Team Boost, "
                f"heals {heal} HP!",
            )

        await callback.answer()

        self._next_turn()

        if not await self._check_win():
            await self._refresh_board()

    async def _handle_target(
        self,
        callback: CallbackQuery,
        key: str,
        target_id: int,
    ) -> None:
        if self.status != "running":
            await callback.answer(
                "Game not running.",
                show_alert=True,
            )
            return

        if key not in self.ABILITIES:
            await callback.answer(
                "Invalid ability.",
                show_alert=True,
            )
            return

        current = self._current()

        if callback.from_user.id != current:
            await callback.answer(
                "❌ It's not your turn!",
                show_alert=True,
            )
            return

        if target_id == current:
            await callback.answer(
                "You cannot target yourself.",
                show_alert=True,
            )
            return

        ab = self.ABILITIES[key]

        if self.hp.get(target_id, 0) <= 0:
            await callback.answer(
                "That target is already down.",
                show_alert=True,
            )
            return

        if self.energy[current] < ab["cost"]:
            await callback.answer(
                "Not enough energy.",
                show_alert=True,
            )
            return

        self.energy[current] -= ab["cost"]
        self.cooldowns[current][key] = ab["cooldown"]

        dmg = random.randint(*ab["dmg"])

        ignores_shield = key == "blast"

        if self.shielded.get(target_id) and not ignores_shield:
            dmg //= 2
            self.shielded[target_id] = False
            shield_note = " (shield absorbed half the damage!)"
        else:
            shield_note = ""

        self.hp[target_id] = max(
            0,
            self.hp[target_id] - dmg,
        )

        await callback.answer(f"Hit for {dmg}!")

        await self.bot.send_message(
            self.chat_id,
            f"{'💥' if key == 'strike' else '🌀'} "
            f"{self.players[current]} uses {ab['name']} on "
            f"{self.players[target_id]} for {dmg} damage!"
            f"{shield_note}",
        )

        if self.hp[target_id] <= 0:
            await self.bot.send_message(
                self.chat_id,
                f"💀 {self.players[target_id]} has been knocked out!",
            )

        self._next_turn()

        if not await self._check_win():
            await self._refresh_board()
            await self.bot.send_message(
                self.chat_id,
                f"🎯 {self.players[self._current()]}, it's your turn! ⚔️"
            )

    async def _check_win(self) -> bool:
        alive = self._alive()

        if len(alive) <= 1 or self.round_num > self.MAX_ROUNDS:
            winner = (
                alive[0]
                if len(alive) == 1
                else max(self.hp, key=lambda uid: self.hp[uid])
            )

            await self._finish(winner)
            return True

        return False

    async def _finish(self, winner_id: int) -> None:
        for task in self._tasks:
            task.cancel()

        lines = [
            f"{self.EMOJI} <b>BATTLE OVER!</b>\n",
            f"🏆 Winner: <b>{self.players[winner_id]}</b>\n",
            "💰 <b>Rewards:</b>",
        ]

        for uid in self.players:
            amount = (
                self.WIN_REWARD
                if uid == winner_id
                else self.PARTICIPATION_REWARD
            )

            new_balance = db.add_coins(uid, amount)

            lines.append(
                f"• {self.players[uid]}: +{amount} coins "
                f"(balance: {new_balance})"
            )

            db.update_stats(
                uid,
                won=(uid == winner_id),
            )

        db.record_game_result(
            self.chat_id,
            self.NAME,
            winner_id,
            list(self.players.keys()),
        )

        await self.bot.send_message(
            self.chat_id,
            "\n".join(lines),
        )

        self.status = "ended"
        self.on_finish(self.chat_id)

    async def force_end(self, reason: str) -> None:
        for task in self._tasks:
            task.cancel()

        self.status = "ended"

        try:
            await self.bot.send_message(
                self.chat_id,
                f"🛑 <b>GAME ENDED</b>\n\n{reason}",
            )
        except Exception:
            pass

        self.on_finish(self.chat_id)


# ==========================================================================
# 3) BUSINESS TYCOON
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
        "2-4 players start with 1500 virtual game-money (session-only, "
        "separate from your persistent coin balance).\n\n"
        "Roll the dice to move around the board:\n"
        "• Land on an unowned property → buy it or skip.\n"
        "• Land on someone else's property → pay rent.\n"
        "• Land on a Business Event tile → random gain or loss.\n"
        "• Pass Start → collect a bonus.\n"
        "• Run out of money → you go bankrupt and are out.\n\n"
        f"Game ends after {MAX_ROUNDS} full rounds or when only one player "
        "remains. Highest net worth (money + property values) wins!"
    )

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        creator_id: int,
        on_finish: FinishCallback,
    ):
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

        self.owned: Dict[int, Optional[int]] = {
            i: None for i in range(len(BOARD))
        }

        self.bankrupt: Dict[int, bool] = {}

        self.turn_order: List[int] = []
        self.turn_index = 0
        self.round_num = 1

        self.board_message_id: Optional[int] = None
        self._awaiting_buy_tile: Optional[int] = None

    def lobby_text(self) -> str:
        lines = [
            f"{self.EMOJI} <b>GAME LOBBY - {self.NAME}</b>\n",
            f"👥 Players: {len(self.players)}/{self.MAX_PLAYERS} "
            f"(min {self.MIN_PLAYERS})\n",
        ]

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
        msg = await self.bot.send_message(
            self.chat_id,
            self.lobby_text(),
            reply_markup=self.lobby_keyboard(),
        )
        self.lobby_message_id = msg.message_id

    async def _refresh_lobby(self) -> None:
        if self.lobby_message_id:
            try:
                await self.bot.edit_message_text(
                    self.lobby_text(),
                    self.chat_id,
                    self.lobby_message_id,
                    reply_markup=self.lobby_keyboard(),
                )
            except Exception:
                pass

    async def _begin(self) -> None:
        self.status = "running"
        self.turn_order = list(self.players.keys())
        random.shuffle(self.turn_order)

        self.money = {
            uid: self.STARTING_MONEY
            for uid in self.turn_order
        }
        self.position = {
            uid: 0
            for uid in self.turn_order
        }
        self.bankrupt = {
            uid: False
            for uid in self.turn_order
        }

        self.turn_index = 0
        self.round_num = 1

        msg = await self.bot.send_message(
            self.chat_id,
            self._render(),
            reply_markup=self._roll_keyboard(),
        )
        self.board_message_id = msg.message_id

        self._tasks.append(asyncio.create_task(self._turn_timer()))

    def _active(self) -> List[int]:
        return [
            uid
            for uid in self.turn_order
            if not self.bankrupt[uid]
        ]

    def _current(self) -> int:
        active = self._active()
        return active[self.turn_index % len(active)]

    def _render(self) -> str:
        lines = [
            f"{self.EMOJI} <b>Business Tycoon</b> "
            f"(Round {self.round_num}/{self.MAX_ROUNDS})\n"
        ]

        for uid in self.turn_order:
            if self.bankrupt[uid]:
                lines.append(
                    f"• {self.players[uid]}: 💀 Bankrupt"
                )
            else:
                tile = BOARD[self.position[uid]]["name"]
                lines.append(
                    f"• {self.players[uid]}: "
                    f"💵{self.money[uid]} @ {tile}"
                )

        if self._active():
            lines.append(
                f"\n👉 Turn: {self.players[self._current()]}"
            )

        return "\n".join(lines)

    def _roll_keyboard(self):
        b = InlineKeyboardBuilder()
        b.button(
            text="🎲 Roll Dice",
            callback_data=f"{self.PREFIX}:roll",
        )
        return b.as_markup()

    def _buy_keyboard(self, tile_idx: int):
        b = InlineKeyboardBuilder()
        b.button(
            text="💰 Buy",
            callback_data=f"{self.PREFIX}:buy:{tile_idx}",
        )
        b.button(
            text="⏭ Skip",
            callback_data=f"{self.PREFIX}:skip:{tile_idx}",
        )
        return b.as_markup()

    async def _refresh_board(self, keyboard=None) -> None:
        if self.board_message_id:
            try:
                await self.bot.edit_message_text(
                    self._render(),
                    self.chat_id,
                    self.board_message_id,
                    reply_markup=keyboard or self._roll_keyboard(),
                )
            except Exception:
                pass

    async def _turn_timer(self) -> None:
        try:
            while self.status == "running":
                await asyncio.sleep(self.TURN_SECONDS)

                if self.status != "running":
                    break

                await self.bot.send_message(
                    self.chat_id,
                    "⏱ Turn timed out, moving to next player.",
                )

                self._next_turn()

                if not await self._check_end():
                    await self._refresh_board()
                    await self.bot.send_message(
                        self.chat_id,
                        f"🎯 {self.players[self._current()]}, it's your turn! 💼"
                    )

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
            ok, msg = await self.add_player(
                callback.from_user.id,
                callback.from_user.first_name,
            )
            await callback.answer(msg, show_alert=not ok)

            if ok:
                await self._refresh_lobby()

        elif action == "cancel":
            if callback.from_user.id != self.creator_id:
                await callback.answer(
                    "Only the creator can cancel.",
                    show_alert=True,
                )
                return

            await callback.answer("Cancelled.")
            await self.force_end("Cancelled by creator.")

        elif action == "start":
            ok, msg = await self.try_start(callback.from_user.id)
            await callback.answer(msg, show_alert=not ok)

        elif action == "roll":
            await self._handle_roll(callback)

        elif action == "buy" and len(parts) > 2:
            try:
                tile_idx = int(parts[2])
            except ValueError:
                await callback.answer("Invalid property.", show_alert=True)
                return

            await self._handle_buy_decision(
                callback,
                tile_idx,
                buy=True,
            )

        elif action == "skip" and len(parts) > 2:
            try:
                tile_idx = int(parts[2])
            except ValueError:
                await callback.answer("Invalid property.", show_alert=True)
                return

            await self._handle_buy_decision(
                callback,
                tile_idx,
                buy=False,
            )

    async def _handle_roll(self, callback: CallbackQuery) -> None:
        if self.status != "running":
            await callback.answer(
                "Game not running.",
                show_alert=True,
            )
            return

        current = self._current()

        if callback.from_user.id != current:
            await callback.answer(
                "❌ It's not your turn!",
                show_alert=True,
            )
            return

        roll = random.randint(1, 6)

        await callback.answer(f"🎲 Rolled a {roll}!")

        old_pos = self.position[current]
        new_pos = (old_pos + roll) % len(BOARD)

        passed_start = (
            new_pos < old_pos
            or (old_pos + roll) >= len(BOARD)
        )

        self.position[current] = new_pos

        msg_lines = [
            f"🎲 {self.players[current]} rolled {roll} "
            f"and landed on <b>{BOARD[new_pos]['name']}</b>."
        ]

        if passed_start and new_pos != 0:
            self.money[current] += self.PASS_START_BONUS
            msg_lines.append(
                f"🏁 Passed Start! +{self.PASS_START_BONUS}"
            )

        tile = BOARD[new_pos]
        keyboard = None

        if tile["type"] == "start":
            self.money[current] += self.PASS_START_BONUS
            msg_lines.append(
                f"🏁 Landed on Start! +{self.PASS_START_BONUS}"
            )

        elif tile["type"] == "tax":
            self.money[current] -= tile["amount"]
            msg_lines.append(
                f"🧾 Paid {tile['amount']} in maintenance tax."
            )

        elif tile["type"] == "event":
            text, delta = random.choice(EVENTS)
            self.money[current] += delta
            sign = "+" if delta >= 0 else ""
            msg_lines.append(
                f"{text} ({sign}{delta})"
            )

        elif tile["type"] == "property":
            owner = self.owned[new_pos]

            if owner is None:
                if self.money[current] >= tile["price"]:
                    msg_lines.append(
                        f"🏷 Unowned! Price: {tile['price']}. Buy it?"
                    )
                    keyboard = self._buy_keyboard(new_pos)
                else:
                    msg_lines.append(
                        "🏷 Unowned, but you can't afford it."
                    )

            elif owner == current:
                msg_lines.append(
                    "🏠 You already own this property."
                )

            else:
                rent = max(10, tile["price"] // 7)
                self.money[current] -= rent
                self.money[owner] += rent

                msg_lines.append(
                    f"💸 Paid {rent} rent to "
                    f"{self.players[owner]}."
                )

        await self.bot.send_message(
            self.chat_id,
            "\n".join(msg_lines),
        )

        if self.money[current] < 0:
            await self._go_bankrupt(current)

            if await self._check_end():
                return

            self._next_turn()
            await self._refresh_board()
            if self.status == "running":
                await self.bot.send_message(
                    self.chat_id,
                    f"🎯 {self.players[self._current()]}, it's your turn! 💼"
                )
            return

        if keyboard is None:
            self._next_turn()

        await self._refresh_board(keyboard=keyboard)
        if keyboard is None and self.status == "running":
            await self.bot.send_message(
                self.chat_id,
                f"🎯 {self.players[self._current()]}, it's your turn! 💼"
            )

    async def _handle_buy_decision(
        self,
        callback: CallbackQuery,
        tile_idx: int,
        buy: bool,
    ) -> None:
        if self.status != "running":
            await callback.answer(
                "Game not running.",
                show_alert=True,
            )
            return

        if tile_idx not in range(len(BOARD)):
            await callback.answer(
                "Invalid property.",
                show_alert=True,
            )
            return

        current = self._current()

        if callback.from_user.id != current:
            await callback.answer(
                "❌ Not your decision!",
                show_alert=True,
            )
            return

        if BOARD[tile_idx]["type"] != "property":
            await callback.answer(
                "That is not a property.",
                show_alert=True,
            )
            return

        # Prevent stale buy buttons from purchasing a different property.
        if self.position[current] != tile_idx:
            await callback.answer(
                "This purchase option has expired.",
                show_alert=True,
            )
            return

        if self.owned[tile_idx] is not None:
            await callback.answer(
                "That property is already owned.",
                show_alert=True,
            )
            return

        if buy:
            price = BOARD[tile_idx]["price"]

            if self.money[current] < price:
                await callback.answer(
                    "Not enough money.",
                    show_alert=True,
                )
                return

            self.money[current] -= price
            self.owned[tile_idx] = current

            await callback.answer("Purchased!")

            await self.bot.send_message(
                self.chat_id,
                f"✅ {self.players[current]} bought "
                f"{BOARD[tile_idx]['name']}!",
            )

        else:
            await callback.answer("Skipped.")

        self._next_turn()

        if not await self._check_end():
            await self._refresh_board()
            await self.bot.send_message(
                self.chat_id,
                f"🎯 {self.players[self._current()]}, it's your turn! 💼"
            )

    async def _go_bankrupt(self, uid: int) -> None:
        self.bankrupt[uid] = True

        for tile_idx, owner in self.owned.items():
            if owner == uid:
                self.owned[tile_idx] = None

        await self.bot.send_message(
            self.chat_id,
            f"💀 {self.players[uid]} has gone bankrupt "
            f"and is out of the game!",
        )

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
        for task in self._tasks:
            task.cancel()

        active = self._active()

        if len(active) == 1:
            winner = active[0]
        else:
            winner = max(
                self.turn_order,
                key=lambda uid:
                    self._net_worth(uid)
                    if not self.bankrupt[uid]
                    else -1,
            )

        lines = [
            f"{self.EMOJI} <b>GAME OVER - Business Tycoon</b>\n",
            "📊 Final net worth:",
        ]

        for uid in self.turn_order:
            worth = (
                self._net_worth(uid)
                if not self.bankrupt[uid]
                else 0
            )

            lines.append(
                f"• {self.players[uid]}: "
                f"{'💀 Bankrupt' if self.bankrupt[uid] else worth}"
            )

        lines.append(
            f"\n🏆 Winner: <b>{self.players[winner]}</b>\n"
        )
        lines.append("💰 <b>Rewards:</b>")

        for uid in self.players:
            amount = (
                self.WIN_REWARD
                if uid == winner
                else self.PARTICIPATION_REWARD
            )

            new_balance = db.add_coins(uid, amount)

            lines.append(
                f"• {self.players[uid]}: +{amount} coins "
                f"(balance: {new_balance})"
            )

            db.update_stats(
                uid,
                won=(uid == winner),
            )

        db.record_game_result(
            self.chat_id,
            self.NAME,
            winner,
            list(self.players.keys()),
        )

        await self.bot.send_message(
            self.chat_id,
            "\n".join(lines),
        )

        self.status = "ended"
        self.on_finish(self.chat_id)

    async def force_end(self, reason: str) -> None:
        for task in self._tasks:
            task.cancel()

        self.status = "ended"

        try:
            await self.bot.send_message(
                self.chat_id,
                f"🛑 <b>GAME ENDED</b>\n\n{reason}",
            )
        except Exception:
            pass

        self.on_finish(self.chat_id)
