import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
MONGODB_URI = os.getenv('MONGODB_URI')
GUILD_ID = int(os.getenv('GUILD_ID'))
ADMIN_ROLE_NAME = os.getenv('ADMIN_ROLE_NAME', 'Admin')

# Google Sheets Configuration
GOOGLE_SHEETS_ENABLED = os.getenv('GOOGLE_SHEETS_ENABLED', 'True').lower() == 'true'
ROCKET_LEAGUE_SHEET_ID = os.getenv('ROCKET_LEAGUE_SHEET_ID', '')  # Add to .env
SHEET_CHECK_INTERVAL = 30  # Check every 30 seconds

# Matchmaking Configuration
TEAM_SIZE = 3
MATCH_SIZE = TEAM_SIZE * 2
SKILL_IMBALANCE_THRESHOLD = 3
MAX_QUEUE_EXPANSION = 4
POINTS_ENTRY_TIMEOUT = 600  # Keep for other games

# Game Definitions with stat types
GAMES = {
    'halo_slayer': {
        'name': 'Halo: CE - Team Slayer',
        'short_name': 'Halo Slayer',
        'emoji': '👽',
        'team_size': 3,
        'category_name': '👽 Halo: Team Slayer',
        'stat_types': ['points'],  # Traditional points system
        'uses_sheets': False
    },
    'cod_bo3': {
        'name': 'CoD Black Ops 3 - TDM',
        'short_name': 'CoD BO3',
        'emoji': '🎖️',
        'team_size': 3,
        'category_name': '🎖️ CoD: Black Ops 3',
        'stat_types': ['points'],
        'uses_sheets': False
    },
    'halo_ctf': {
        'name': 'Halo: CE - Capture the Flag',
        'short_name': 'Halo CTF',
        'emoji': '🚩',
        'team_size': 3,
        'category_name': '🚩 Halo: CTF',
        'stat_types': ['points'],
        'uses_sheets': False
    },
    'mk1': {
        'name': 'Mortal Kombat 1',
        'short_name': 'MK1',
        'emoji': '🥊',
        'team_size': 1,
        'category_name': '🥊 Mortal Kombat 1',
        'stat_types': ['points'],
        'uses_sheets': False
    },
    'cod_mw': {
        'name': 'CoD 4: MW - Search and Destroy',
        'short_name': 'CoD MW',
        'emoji': '💣',
        'team_size': 3,
        'category_name': '💣 CoD: Modern Warfare',
        'stat_types': ['points'],
        'uses_sheets': False
    },
    'rocket_league': {
        'name': 'Rocket League',
        'short_name': 'Rocket League',
        'emoji': '🚗',
        'team_size': 3,
        'category_name': '🚗 Rocket League',
        'stat_types': ['goals', 'assists', 'saves', 'shots'],  # Custom stats
        'uses_sheets': True  # Uses Google Sheets
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