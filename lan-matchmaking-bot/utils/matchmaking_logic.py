from itertools import combinations
import config


def calculate_team_balance(players, team1_indices, team_size):
    """
    Calculate skill imbalance between two teams
    """
    team1 = [players[i] for i in team1_indices]
    team2 = [players[i] for i, p in enumerate(players) if i not in team1_indices][:team_size]

    team1_skill = sum(p['skill_level'] for p in team1)
    team2_skill = sum(p['skill_level'] for p in team2)

    imbalance = abs(team1_skill - team2_skill)

    return team1, team2, imbalance


def find_balanced_teams(players, game_id, team_size, used_combinations=None):
    """
    Find the most balanced team split for a specific game
    """
    match_size = team_size * 2

    if len(players) < match_size:
        return None

    if used_combinations is None:
        used_combinations = set()

    # Enrich players with their skill level for this game
    enriched_players = []
    for player in players:
        player_copy = player.copy()
        player_copy['skill_level'] = player['skill_levels'].get(game_id, 5)
        enriched_players.append(player_copy)

    # Get all possible team combinations
    all_combinations = list(combinations(range(len(enriched_players)), team_size))

    # Calculate imbalance for each combination
    results = []
    for team1_indices in all_combinations:
        team1, team2, imbalance = calculate_team_balance(enriched_players, team1_indices, team_size)

        # Create a unique identifier for this team combination
        team1_ids = frozenset(p['user_id'] for p in team1)
        team2_ids = frozenset(p['user_id'] for p in team2)
        combo_id = frozenset([team1_ids, team2_ids])

        # Skip if this combination was recently used
        if combo_id in used_combinations:
            continue

        results.append((team1, team2, imbalance, combo_id))

    if not results:
        # If all combinations were used, clear the history and try again
        return find_balanced_teams(players, game_id, team_size, set())

    # Sort by imbalance (best balance first)
    results.sort(key=lambda x: x[2])

    # Return best balance
    if results:
        team1, team2, imbalance, combo_id = results[0]
        return team1, team2, imbalance, combo_id

    return None


def find_1v1_match(players, game_id):
    """
    Find best 1v1 match based on similar skill levels
    """
    if len(players) < 2:
        return None

    # Enrich with skill levels
    enriched_players = []
    for player in players:
        player_copy = player.copy()
        player_copy['skill_level'] = player['skill_levels'].get(game_id, 5)
        enriched_players.append(player_copy)

    # Sort by skill level
    enriched_players.sort(key=lambda p: p['skill_level'])

    # Find two closest skill levels
    best_pair = None
    best_diff = float('inf')

    for i in range(len(enriched_players) - 1):
        for j in range(i + 1, len(enriched_players)):
            diff = abs(enriched_players[i]['skill_level'] - enriched_players[j]['skill_level'])
            if diff < best_diff:
                best_diff = diff
                best_pair = (enriched_players[i], enriched_players[j])

    if best_pair:
        player1, player2 = best_pair
        return {
            'team1': [player1],  # Player 1
            'team2': [player2],  # Player 2
            'imbalance': best_diff,
            'combo_id': frozenset([frozenset([player1['user_id']]), frozenset([player2['user_id']])]),
            'leftover_players': [p for p in enriched_players if
                                 p['user_id'] not in [player1['user_id'], player2['user_id']]]
        }

    return None


def find_ffa_match(players, game_id, player_count):
    """
    Find players for free-for-all match (no teams, no skill balancing needed)
    """
    if len(players) < player_count:
        return None

    # Simply take first N players (prioritized by queue order)
    selected_players = players[:player_count]
    leftover_players = players[player_count:]

    # Enrich with skill levels
    for player in selected_players:
        player['skill_level'] = player['skill_levels'].get(game_id, 5)

    return {
        'players': selected_players,  # All players in one group
        'team1': selected_players,  # Store as team1 for compatibility
        'team2': [],  # No team2 in FFA
        'imbalance': 0,  # No balancing in FFA
        'combo_id': frozenset([frozenset([p['user_id'] for p in selected_players])]),
        'leftover_players': leftover_players
    }


def create_match_from_queue(online_players, game_id, used_combinations=None):
    """
    Create a match from the queue of online players for a specific game
    Handles team-based, 1v1, and FFA games
    """
    game_info = config.GAMES[game_id]
    match_type = game_info.get('match_type', 'team')  # 'team', '1v1', or 'ffa'

    # Handle different match types
    if match_type == '1v1':
        return find_1v1_match(online_players, game_id)

    elif match_type == 'ffa':
        player_count = game_info['team_size']  # For FFA, team_size is total players
        return find_ffa_match(online_players, game_id, player_count)

    else:  # Standard team-based game
        team_size = game_info['team_size']
        match_size = team_size * 2

        if len(online_players) < match_size:
            return None

        # Try with minimum players first
        max_queue_size = min(len(online_players), match_size + config.MAX_QUEUE_EXPANSION)

        for queue_size in range(match_size, max_queue_size + 1):
            candidate_players = online_players[:queue_size]
            result = find_balanced_teams(candidate_players, game_id, team_size, used_combinations)

            if result:
                team1, team2, imbalance, combo_id = result

                # Check if imbalance is acceptable
                if imbalance <= config.SKILL_IMBALANCE_THRESHOLD or queue_size == len(online_players):
                    # Determine which players were left out
                    matched_ids = set(p['user_id'] for p in team1 + team2)
                    leftover_players = [p for p in candidate_players if p['user_id'] not in matched_ids]

                    return {
                        'team1': team1,
                        'team2': team2,
                        'imbalance': imbalance,
                        'combo_id': combo_id,
                        'leftover_players': leftover_players
                    }

        return None