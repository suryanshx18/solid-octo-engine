import random

PARCHI_VALUES = {
    "Virat Kohli": 5000,
    "MS Dhoni": 4500,
    "Rohit Sharma": 4000,
    "KL Rahul": 3500
}


def create_deck():
    deck = []

    for player_name in PARCHI_VALUES:
        for _ in range(4):
            deck.append(player_name)

    random.shuffle(deck)
    return deck


def deal_cards(player_ids):
    deck = create_deck()

    hands = {}

    for index, user_id in enumerate(player_ids):
        start = index * 4
        end = start + 4

        hands[user_id] = deck[start:end]

    return hands


def check_winner(cards):
    if len(cards) != 4:
        return None

    if cards[0] == cards[1] == cards[2] == cards[3]:
        player_name = cards[0]

        return {
            "player": player_name,
            "amount": PARCHI_VALUES[player_name]
        }

    return None


def format_cards(cards):
    if not cards:
        return "No cards"

    return "\n".join(
        f"{index}. {card}"
        for index, card in enumerate(cards, start=1)
    )


# Free arcade Fly multiplier.
# No coins are staked.

def arcade_multiplier(seconds):
    multiplier = 1.1 + (seconds * 0.08)

    if seconds > 10:
        multiplier += ((seconds - 10) ** 1.15) * 0.025

    return round(min(multiplier, 100.0), 2)
