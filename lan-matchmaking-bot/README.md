# LAN Matchmaking Bot

Multi-game tournament management system for LAN parties.

## Features

- ✅ Support for 6 different games simultaneously (2 active at once)
- ✅ Skill-based matchmaking with team balancing
- ✅ Automatic queue management
- ✅ Per-game statistics and leaderboards
- ✅ Real-time channel updates
- ✅ Points tracking and verification
- ✅ Match history
- ✅ Player priority queue system

## Supported Games

1. 👽 Halo: CE - Team Slayer (3v3)
2. 🎖️ CoD Black Ops 3 - TDM (3v3)
3. 🚩 Halo: CE - Capture the Flag (3v3)
4. 🥊 Mortal Kombat 1 (1v1)
5. 💣 CoD 4: MW - Search and Destroy (3v3)
6. 🚗 Rocket League (3v3)

## Setup

1. Install dependencies:
```bash
   pip install -r requirements.txt
```

2. Configure `.env`:
```
   DISCORD_TOKEN=your_bot_token
   MONGODB_URI=your_mongodb_connection
   GUILD_ID=your_server_id
   ADMIN_ROLE_NAME=Admin
```

3. Run the bot:
```bash
   python bot.py
```

## Admin Workflow

1. `/enablegames` - Enable 2 games (e.g., Halo and CoD)
2. Players use `/register` and `/setskill`
3. Players use `/online` to join queues
4. Bot automatically creates matches
5. `/startmatch` - Start matches when ready
6. `/endmatch` - End matches after gameplay
7. Players use `/submitpoints`
8. `/verifypoints` - Finalize and update leaderboard

## Player Workflow

1. `/register` - One-time registration
2. `/setskill` - Set skill levels for games
3. `/online` - Join queue(s) for available games
4. Wait for match notification
5. Play your match!
6. `/submitpoints` - Submit your score
7. Check leaderboards in game channels

## Bot Commands

### Owner Commands (prefix: !)
- `!sync` - Sync slash commands
- `!status` - Check bot status
- `!setupgame <game_id>` - Manually setup game channels
- `!resetgame <game_id>` - Reset all game data
- `!help` - Show help

### Player Commands (prefix: /)
See `/help` in Discord

### Admin Commands (prefix: /)
See `/help` in Discord (requires Admin role)

## Architecture
```
Bot
├── Player Management
│   ├── Registration
│   ├── Skill Levels (per game)
│   ├── Queue Status (multi-game)
│   └── Statistics (per game)
├── Matchmaking
│   ├── Skill-based balancing
│   ├── Queue priority
│   ├── Team diversity
│   └── Multi-game support
├── Match Management
│   ├── Pending matches
│   ├── Active matches
│   ├── Points submission
│   └── Verification
└── Channels
    ├── Per-game categories
    ├── Queue displays
    ├── Leaderboards
    ├── Match history
    └── Team voice/text channels
```

## Database Schema

### Collections
- `players` - User profiles and queue status
- `game_stats` - Per-game statistics
- `matches` - Match history and current matches
- `settings` - System configuration

## Support

For issues or questions, contact the bot developer.
```

### Create `.gitignore` (if not already created):
```
# Virtual Environment
venv/
env/
ENV/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python

# Environment Variables
.env
.env.local

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Logs
*.log

# Database
*.db
*.sqlite