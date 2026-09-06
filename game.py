import random

import database


ROLE_INFO = {
    "Mafia": (
        "Eliminate the Citizens without getting voted out.",
        "Mafia"
    ),

    "Detective": (
        "Investigate players and identify the Mafia.",
        "Citizen"
    ),

    "Doctor": (
        "Protect one player each night.",
        "Citizen"
    ),

    "Citizen": (
        "Find and eliminate the Mafia through discussion and voting.",
        "Citizen"
    )
}


def create_roles(player_count):

    roles = []

    mafia_count = max(
        1,
        player_count // 4
    )

    roles.extend(
        ["Mafia"] * mafia_count
    )

    if player_count >= 5:
        roles.append("Detective")

    if player_count >= 6:
        roles.append("Doctor")

    while len(roles) < player_count:
        roles.append("Citizen")

    random.shuffle(roles)

    return roles


def assign_roles(game_id):

    players = database.get_game_players(game_id)

    roles = create_roles(
        len(players)
    )

    for player, role in zip(players, roles):

        mission, _ = ROLE_INFO[role]

        database.assign_player_role(
            game_id,
            player["user_id"],
            role,
            mission
        )


def start_game(game_id):

    assign_roles(game_id)

    database.update_game(
        game_id,
        status="active",
        phase="night",
        round=1
    )


def get_winner(game_id):

    players = database.get_game_players(
        game_id,
        alive_only=True
    )

    mafia = [
        p for p in players
        if p["role"] == "Mafia"
    ]

    citizens = [
        p for p in players
        if p["role"] != "Mafia"
    ]

    if len(mafia) == 0:
        return "citizens", citizens

    if len(mafia) >= len(citizens):
        return "mafia", mafia

    return None, []


def resolve_night(game_id):

    current_game = database.get_game(
        game_id
    )

    mafia_target = current_game["night_target"]
    doctor_target = current_game["doctor_target"]

    killed = None

    if (
        mafia_target
        and mafia_target != doctor_target
    ):

        target = database.get_player(
            game_id,
            mafia_target
        )

        if target and target["alive"]:

            database.kill_player(
                game_id,
                mafia_target
            )

            killed = target

    database.clear_night_actions(
        game_id
    )

    return killed


def count_votes(game_id):

    votes = database.get_votes(
        game_id,
        "day"
    )

    counts = {}

    for vote in votes:

        target = vote["target_id"]

        counts[target] = (
            counts.get(target, 0) + 1
        )

    if not counts:
        return None, 0

    highest = max(
        counts.values()
    )

    leaders = [
        user_id
        for user_id, count in counts.items()
        if count == highest
    ]

    if len(leaders) != 1:
        return None, highest

    return leaders[0], highest


def resolve_day(game_id):

    target_id, votes = count_votes(
        game_id
    )

    if target_id is None:
        return None, votes

    target = database.get_player(
        game_id,
        target_id
    )

    if not target or not target["alive"]:
        return None, votes

    database.kill_player(
        game_id,
        target_id
    )

    return target, votes
