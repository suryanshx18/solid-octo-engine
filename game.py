import random

from database import (
    get_game_players,
    update_game,
    connect
)


ROLES = [
    "Survivor",
    "Survivor",
    "Survivor",
    "Saboteur",
    "Trickster",
    "Chaos Agent"
]


def assign_roles(game_id):
    players = get_game_players(game_id)

    roles = ROLES.copy()

    while len(roles) < len(players):
        roles.append("Survivor")

    random.shuffle(roles)

    conn = connect()
    cur = conn.cursor()

    for player, role in zip(players, roles):
        mission = None

        if role == "Saboteur":
            mission = "Make the players lose at least one AI round."

        elif role == "Trickster":
            mission = "Use your special ability when available."

        elif role == "Chaos Agent":
            mission = "Cause chaos and finish among the top players."

        else:
            mission = "Survive and finish with the highest score."

        cur.execute("""
            UPDATE game_players
            SET role = ?, secret_mission = ?
            WHERE game_id = ? AND user_id = ?
        """, (
            role,
            mission,
            game_id,
            player["user_id"]
        ))

    conn.commit()
    conn.close()


def start_game_engine(game_id):
    assign_roles(game_id)

    update_game(
        game_id,
        status="active",
        round_number=1
    )


def calculate_ai_power():
    return random.randint(60, 150)


def resolve_action(action):
    if action == "attack":
        return random.randint(20, 50)

    if action == "defend":
        return random.randint(10, 30)

    if action == "gamble":
        if random.random() < 0.5:
            return random.randint(40, 100)
        return -random.randint(10, 50)

    if action == "sabotage":
        return -random.randint(10, 40)

    return 0


def random_event():
    events = [
        (
            "🎲 DOUBLE CHAOS",
            "All positive action rewards are doubled this round."
        ),
        (
            "🤖 AI OVERDRIVE",
            "The AI becomes stronger this round."
        ),
        (
            "💰 LUCKY ROUND",
            "Players have increased gambling rewards."
        ),
        (
            "🃏 TRUST NOBODY",
            "A secret betrayal bonus has appeared."
        ),
        (
            "⚡ CHAOS SURGE",
            "Everyone gets a random score modifier."
        )
    ]

    return random.choice(events)
