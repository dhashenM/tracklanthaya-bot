import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
MONGODB_URI = os.getenv('MONGODB_URI')
GUILD_ID = int(os.getenv('GUILD_ID'))
ADMIN_ROLE_NAME = os.getenv('ADMIN_ROLE_NAME', 'Admin')

# Matchmaking Configuration
TEAM_SIZE = 3  # 3v3 matches
MATCH_SIZE = TEAM_SIZE * 2  # 6 players total
SKILL_IMBALANCE_THRESHOLD = 3  # Maximum allowed skill difference between teams
MAX_QUEUE_EXPANSION = 4  # Expand queue up to 10 players (6+4)
POINTS_ENTRY_TIMEOUT = 600  # 10 minutes in seconds

# Game Definitions
GAMES = {
    'halo_slayer': {
        'name': 'Halo: CE - Team Slayer',
        'short_name': 'Halo Slayer',
        'emoji': '👽',
        'team_size': 3,  # 3v3
        'category_name': '👽 Halo: Team Slayer'
    },
    'cod_bo3': {
        'name': 'CoD Black Ops 3 - TDM',
        'short_name': 'CoD BO3',
        'emoji': '🎖️',
        'team_size': 3,  # 3v3
        'category_name': '🎖️ CoD: Black Ops 3'
    },
    'halo_ctf': {
        'name': 'Halo: CE - Capture the Flag',
        'short_name': 'Halo CTF',
        'emoji': '🚩',
        'team_size': 3,  # 3v3
        'category_name': '🚩 Halo: CTF'
    },
    'mk1': {
        'name': 'Mortal Kombat 1',
        'short_name': 'MK1',
        'emoji': '🥊',
        'team_size': 1,  # 1v1
        'category_name': '🥊 Mortal Kombat 1'
    },
    'cod_mw': {
        'name': 'CoD 4: MW - Search and Destroy',
        'short_name': 'CoD MW',
        'emoji': '💣',
        'team_size': 3,  # 3v3
        'category_name': '💣 CoD: Modern Warfare'
    },
    'rocket_league': {
        'name': 'Rocket League',
        'short_name': 'Rocket League',
        'emoji': '🚗',
        'team_size': 3,  # 3v3
        'category_name': '🚗 Rocket League'
    }
}

# Channel Configuration
TEAM1_CHANNEL_NAME = "🔴 Team 1"
TEAM2_CHANNEL_NAME = "🔵 Team 2"
QUEUE_CHANNEL_NAME = "queue"
LEADERBOARD_CHANNEL_NAME = "leaderboard"
MATCH_HISTORY_CHANNEL_NAME = "match-history"
UPCOMING_MATCHES_CHANNEL_NAME = "upcoming-matches"
GENERAL_CHANNEL_NAME = "general"