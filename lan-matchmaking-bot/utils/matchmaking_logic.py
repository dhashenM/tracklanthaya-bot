from itertools import combinations
import config


def calculate_team_balance(players, team1_indices):
    """
    Calculate skill imbalance between two teams

    Args:
        players: List of player dicts with 'skill_level'
        team1_indices: Tuple of indices for team 1

    Returns:
        (team1_players, team2_players, imbalance)
    """
    team1 = [players[i] for i in team1_indices]
    team2 = [players[i] for i, p in enumerate(players) if i not in team1_indices]

    team1_skill = sum(p['skill_level'] for p in team1)
    team2_skill = sum(p['skill_level'] for p in team2)

    imbalance = abs(team1_skill - team2_skill)

    return team1, team2, imbalance


def find_balanced_teams(players, used_combinations=None):
    """
    Find the most balanced team split

    Args:
        players: List of player dicts (must be 6+ players)
        used_combinations: Set of frozensets to avoid repeated team combinations

    Returns:
        (team1, team2, imbalance) or None if no valid split found
    """
    if len(players) < config.MATCH_SIZE:
        return None

    if used_combinations is None:
        used_combinations = set()

    # Get all possible team combinations
    team_size = config.TEAM_SIZE
    all_combinations = list(combinations(range(len(players)), team_size))

    # Calculate imbalance for each combination
    results = []
    for team1_indices in all_combinations:
        team1, team2, imbalance = calculate_team_balance(players, team1_indices)

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
        return find_balanced_teams(players, set())

    # Sort by imbalance (best balance first)
    results.sort(key=lambda x: x[2])

    # Return best balance
    if results:
        team1, team2, imbalance, combo_id = results[0]
        return team1, team2, imbalance, combo_id

    return None


def create_match_from_queue(online_players, used_combinations=None):
    """
    Create a match from the queue of online players

    Args:
        online_players: List of online players sorted by priority
        used_combinations: Set of recently used team combinations

    Returns:
        dict with match info or None
    """
    if len(online_players) < config.MATCH_SIZE:
        return None

    # Try with minimum players first (6)
    for queue_size in range(config.MATCH_SIZE,
                            min(len(online_players) + 1,
                                config.MATCH_SIZE + config.MAX_QUEUE_EXPANSION + 1)):

        candidate_players = online_players[:queue_size]
        result = find_balanced_teams(candidate_players, used_combinations)

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