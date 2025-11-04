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

# Channel Configuration
MATCH_CATEGORY_NAME = "Active Matches"
TEAM1_CHANNEL_NAME = "🔴 Team 1"
TEAM2_CHANNEL_NAME = "🔵 Team 2"