import random
import asyncio
import math

# -----------------------------------------
# PARCHI
# -----------------------------------------

PARCHI_VALUES = {
    "Virat Kohli": 5000,
    "MS Dhoni": 4500,
    "Rohit Sharma": 4000,
    "KL Rahul": 3500
}


def create_deck():
    deck = []

    for player in PARCHI_VALUES:
        for _ in range(4):
            deck.append(player)

    random.shuffle(deck)

    return deck


def deal_cards(players):
    """
    players = list of user IDs

    Returns:
        {
            user_id: [card, card, card, card]
        }
    """

    deck = create_deck()

    hands = {}

    for index, user_id in enumerate(players):
        start = index * 4
        end = start + 4

        hands[user_id] = deck[start:end]

    return hands


def has_four_same(cards):
    if len(cards) != 4:
        return None

    if cards[0] == cards[1] == cards[2] == cards[3]:
        return cards[0]

    return None


def check_winner(cards):
    winner = has_four_same(cards)

    if winner:
        return {
            "player": winner,
            "amount": PARCHI_VALUES[winner]
        }

    return None


# -----------------------------------------
# CARD DISPLAY
# -----------------------------------------

def format_cards(cards):
    result = []

    for index, card in enumerate(cards, start=1):
        result.append(f"{index}. {card}")

    return "\n".join(result)


# -----------------------------------------
# FLY / ROCKET
# -----------------------------------------

MIN_MULTIPLIER = 1.1
MAX_MULTIPLIER = 100.0


def generate_crash_point():
    """
    Generates a crash point between 1.1x and 100x.

    The distribution makes small crashes more common
    while still allowing large multipliers.
    """

    value = 1.0 / random.random()

    value = max(MIN_MULTIPLIER, value)

    return min(round(value, 2), MAX_MULTIPLIER)


def multiplier_at_time(seconds):
    """
    Slowly increases multiplier.

    Starts at 1.1x and gradually increases.
    """

    multiplier = 1.1 + (seconds * 0.08)

    # Slight acceleration as time passes.
    if seconds > 10:
        multiplier += ((seconds - 10) ** 1.15) * 0.025

    multiplier = min(multiplier, MAX_MULTIPLIER)

    return round(multiplier, 2)


def calculate_payout(bet, multiplier):
    return math.floor(bet * multiplier)


async def fly_multiplier_generator():
    """
    Yields:
        elapsed_seconds, multiplier

    until 100x.
    """

    elapsed = 0

    while True:
        multiplier = multiplier_at_time(elapsed)

        yield elapsed, multiplier

        if multiplier >= MAX_MULTIPLIER:
            break

        await asyncio.sleep(1)

        elapsed += 1
