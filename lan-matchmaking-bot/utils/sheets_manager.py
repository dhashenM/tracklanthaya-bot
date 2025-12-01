import gspread
from google.oauth2.service_account import Credentials
import config
from utils.database import db
from utils.channel_manager import get_channel_manager
import asyncio
import re


class SheetsManager:
    """Manages Google Sheets integration for all games"""

    def __init__(self, bot):
        self.bot = bot
        self.client = None
        self.last_known_hash = None
        self.is_running = False

    def connect(self):
        """Connect to Google Sheets API"""
        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]

            creds = Credentials.from_service_account_file(
                'service_account.json',
                scopes=scopes
            )

            self.client = gspread.authorize(creds)
            print("✅ Connected to Google Sheets API")
            return True
        except FileNotFoundError:
            print("⚠️ service_account.json not found. Google Sheets integration disabled.")
            return False
        except Exception as e:
            print(f"⚠️ Failed to connect to Google Sheets: {e}")
            return False

    def parse_column_name(self, raw_name):
        """Parse column name to extract game and type"""
        # Examples: "Halo: TS_Score", "BO3_Matches", "Total_Score"
        raw_name = raw_name.strip()

        if '_' not in raw_name:
            return None, None

        parts = raw_name.split('_')
        game_part = '_'.join(parts[:-1])  # Everything before last underscore
        type_part = parts[-1].lower()  # score or matches

        return game_part, type_part

    async def get_master_sheet_data(self):
        """Fetch all player data from master sheet"""
        if not self.client:
            return None

        try:
            sheet = self.client.open_by_key(config.MASTER_SHEET_ID)
            worksheet = sheet.get_worksheet(0)  # First sheet

            # Get all values
            all_data = worksheet.get_all_values()

            if not all_data or len(all_data) < 3:
                print("⚠️ Sheet doesn't have enough rows")
                return None

            # The sheet has 3 header rows:
            # Row 1: General headers
            # Row 2: Game names
            # Row 3: Score/Matches labels

            # We'll use row 2 and 3 to construct column identifiers
            row2 = all_data[1]  # Game names
            row3 = all_data[2]  # Score/Matches

            # Build column mapping
            column_map = {}

            for i, (game_name, stat_type) in enumerate(zip(row2, row3)):
                game_name = game_name.strip()
                stat_type = stat_type.strip().lower()

                if not game_name or not stat_type:
                    continue

                # Create identifier
                if stat_type in ['score', 'matches']:
                    column_map[i] = {
                        'game': game_name,
                        'type': stat_type
                    }

            # Find required columns
            name_col = None
            discord_id_col = None

            for i, header in enumerate(all_data[0]):
                header_lower = header.strip().lower()
                if 'name' in header_lower and name_col is None:
                    name_col = i
                elif 'discord' in header_lower:
                    discord_id_col = i

            if name_col is None:
                print("⚠️ Could not find 'Name' column")
                return None

            # Parse data rows (start from row 4, index 3)
            players_data = []

            for row in all_data[3:]:
                if not row or len(row) <= max(name_col, discord_id_col or 0):
                    continue

                name = row[name_col].strip() if name_col < len(row) else ""
                discord_id = row[discord_id_col].strip() if discord_id_col and discord_id_col < len(row) else ""

                if not name:
                    continue

                player_data = {
                    'name': name,
                    'discord_id': discord_id,
                    'games': {}
                }

                # Extract game stats
                for col_idx, col_info in column_map.items():
                    if col_idx >= len(row):
                        continue

                    value = row[col_idx].strip()
                    game_name = col_info['game']
                    stat_type = col_info['type']

                    # Initialize game entry
                    if game_name not in player_data['games']:
                        player_data['games'][game_name] = {}

                    # Parse value
                    try:
                        if stat_type == 'score':
                            player_data['games'][game_name]['score'] = float(value) if value else 0.0
                        elif stat_type == 'matches':
                            player_data['games'][game_name]['matches'] = int(float(value)) if value else 0
                    except ValueError:
                        pass

                players_data.append(player_data)

            return players_data

        except Exception as e:
            print(f"⚠️ Error reading master sheet: {e}")
            import traceback
            traceback.print_exc()
            return None

    def map_sheet_game_to_game_id(self, sheet_game_name):
        """Map sheet game name to internal game ID"""
        # Create mapping
        for game_id, game_info in config.GAMES.items():
            if game_info['short_name'] == sheet_game_name:
                return game_id
        return None

    async def sync_all_stats(self, guild):
        """Sync all player stats from sheet to database"""
        data = await self.get_master_sheet_data()

        if not data:
            return False

        # Check for changes
        data_hash = str(sorted([str(d) for d in data]))

        if data_hash == self.last_known_hash:
            return False  # No changes

        self.last_known_hash = data_hash

        print(f"📊 Syncing stats from Google Sheets...")

        updated_players = set()
        updated_games = set()

        for player_data in data:
            name = player_data['name']
            discord_id = player_data['discord_id']

            # Find player - prefer by Discord ID, fallback to username
            player = None

            if discord_id:
                # Try to find by Discord ID first
                all_players = await db.get_all_players()
                for p in all_players:
                    if str(p['user_id']) == discord_id or p['username'] == discord_id:
                        player = p
                        break

            if not player:
                # Try by username
                all_players = await db.get_all_players()
                for p in all_players:
                    if p['username'].lower() == name.lower():
                        player = p
                        break

            if not player:
                print(f"⚠️ Player '{name}' (Discord ID: {discord_id or 'N/A'}) not found. Skipping.")
                continue

            # Update stats for each game
            for sheet_game_name, game_stats in player_data['games'].items():
                game_id = self.map_sheet_game_to_game_id(sheet_game_name)

                if not game_id:
                    continue

                score = game_stats.get('score', 0)
                matches = game_stats.get('matches', 0)

                # Get current stats
                current_stats = await db.get_game_stats(player['user_id'], game_id)

                # Update with sheet data
                await db.update_game_stats(player['user_id'], game_id, {
                    'points': score,
                    'matches_played': matches,
                    # Preserve other fields
                    'wins': current_stats.get('wins', 0),
                    'losses': current_stats.get('losses', 0),
                    'queue_priority': current_stats.get('queue_priority', 0)
                })

                updated_players.add(player['username'])
                updated_games.add(game_id)

        print(f"✅ Updated {len(updated_players)} players across {len(updated_games)} games")

        # Update leaderboard channels for affected games
        if guild and updated_games:
            cm = get_channel_manager(self.bot)
            for game_id in updated_games:
                await cm.update_leaderboard(guild, game_id)

            # Update total leaderboard
            await cm.update_total_leaderboard(guild)

        return True

    async def start_sync_loop(self):
        """Start the background sync loop"""
        if not config.GOOGLE_SHEETS_ENABLED:
            print("ℹ️ Google Sheets sync disabled in config")
            return

        if not self.connect():
            print("ℹ️ Google Sheets sync disabled - connection failed")
            return

        self.is_running = True
        print(f"🔄 Starting Google Sheets sync loop (every {config.SHEET_CHECK_INTERVAL}s)")

        while self.is_running:
            try:
                # Get guild
                guild = None
                for g in self.bot.guilds:
                    guild = g
                    break

                if guild:
                    await self.sync_all_stats(guild)

                await asyncio.sleep(config.SHEET_CHECK_INTERVAL)

            except Exception as e:
                print(f"⚠️ Error in sheets sync loop: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(config.SHEET_CHECK_INTERVAL)

    def stop_sync_loop(self):
        """Stop the background sync loop"""
        self.is_running = False
        print("⏹️ Stopped Google Sheets sync loop")


# Global instance
sheets_manager = None


def get_sheets_manager(bot):
    """Get or create sheets manager instance"""
    global sheets_manager
    if sheets_manager is None:
        sheets_manager = SheetsManager(bot)
    return sheets_manager