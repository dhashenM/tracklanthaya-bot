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
MASTER_SHEET_ID = os.getenv('MASTER_SHEET_ID', '')  # Your main sheet ID
SHEET_CHECK_INTERVAL = 30  # Check every 30 seconds

# Matchmaking Configuration
TEAM_SIZE = 3
MATCH_SIZE = TEAM_SIZE * 2
SKILL_IMBALANCE_THRESHOLD = 3
MAX_QUEUE_EXPANSION = 4
POINTS_ENTRY_TIMEOUT = 600

# Game Definitions - Column mapping for Google Sheets
GAMES = {
    'halo_slayer': {
        'name': 'Halo: CE - Team Slayer',
        'short_name': 'Halo: TS',
        'emoji': '👽',
        'team_size': 3,
        'category_name': '👽 Halo: Team Slayer',
        'sheet_score_col': 'Halo: TS_Score',  # Column header in sheet
        'sheet_matches_col': 'Halo: TS_Matches'
    },
    'cod_bo3': {
        'name': 'CoD Black Ops 3 - TDM',
        'short_name': 'BO3',
        'emoji': '🎖️',
        'team_size': 3,
        'category_name': '🎖️ CoD: Black Ops 3',
        'sheet_score_col': 'BO3_Score',
        'sheet_matches_col': 'BO3_Matches'
    },
    'halo_ctf': {
        'name': 'Halo: CE - Capture the Flag',
        'short_name': 'Halo: CTF',
        'emoji': '🚩',
        'team_size': 3,
        'category_name': '🚩 Halo: CTF',
        'sheet_score_col': 'Halo: CTF_Score',
        'sheet_matches_col': 'Halo: CTF_Matches'
    },
    'mk1': {
        'name': 'Mortal Kombat 11',
        'short_name': 'MK11',
        'emoji': '🥊',
        'team_size': 1,
        'category_name': '🥊 Mortal Kombat 11',
        'sheet_score_col': 'MK11_Score',
        'sheet_matches_col': 'MK11_Matches'
    },
    'cod_mw': {
        'name': 'CoD 4: MW - Search and Destroy',
        'short_name': 'MW',
        'emoji': '💣',
        'team_size': 3,
        'category_name': '💣 CoD: Modern Warfare',
        'sheet_score_col': 'MW_Score',
        'sheet_matches_col': 'MW_Matches'
    },
    'rocket_league': {
        'name': 'Rocket League',
        'short_name': 'RL',
        'emoji': '🚗',
        'team_size': 3,
        'category_name': '🚗 Rocket League',
        'sheet_score_col': 'RL_Score',
        'sheet_matches_col': 'RL_Matches'
    }
}

# Total leaderboard category
TOTAL_LEADERBOARD_CATEGORY = "🏆 Overall Leaderboard"
TOTAL_LEADERBOARD_CHANNEL = "🏆│total-leaderboard"

# Channel Configuration
TEAM1_CHANNEL_NAME = "🔴 Team 1"
TEAM2_CHANNEL_NAME = "🔵 Team 2"
QUEUE_CHANNEL_NAME = "queue"
LEADERBOARD_CHANNEL_NAME = "leaderboard"
MATCH_HISTORY_CHANNEL_NAME = "match-history"
UPCOMING_MATCHES_CHANNEL_NAME = "upcoming-matches"
GENERAL_CHANNEL_NAME = "general"