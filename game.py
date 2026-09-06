import random


PARCHI_VALUES = {
    "Virat Kohli": 5000,
    "MS Dhoni": 4500,
    "Rohit Sharma": 4000,
    "KL Rahul": 3500
}


def create_deck():
    deck = []

    for name in PARCHI_VALUES:
        for _ in range(4):
            deck.append(name)

    random.shuffle(deck)

    return deck


def deal_cards(player_ids):
    deck = create_deck()

    hands = {}

    for index, user_id in enumerate(player_ids):
        start = index * 4
        hands[user_id] = deck[start:start + 4]

    return hands


def check_winner(cards):
    if len(cards) != 4:
        return None

    if cards[0] == cards[1] == cards[2] == cards[3]:
        name = cards[0]

        return {
            "player": name,
            "amount": PARCHI_VALUES[name]
        }

    return None


def arcade_multiplier(seconds):
    multiplier = 1.10 + (seconds * 0.08)

    if seconds > 10:
        multiplier += (
            ((seconds - 10) ** 1.15) * 0.025
        )

    return round(
        min(multiplier, 100.0),
        2
    )
