import gspread
from google.oauth2.service_account import Credentials
import config
from utils.database import db
from utils.channel_manager import get_channel_manager
import asyncio


class SheetsManager:
    """Manages Google Sheets integration"""

    def __init__(self, bot):
        self.bot = bot
        self.client = None
        self.last_known_data = {}  # Track changes
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

    async def get_rocket_league_data(self):
        """Fetch Rocket League data from Google Sheet"""
        if not self.client:
            return None

        try:
            sheet = self.client.open_by_key(config.ROCKET_LEAGUE_SHEET_ID)
            worksheet = sheet.get_worksheet(0)  # First sheet

            # Get all values
            data = worksheet.get_all_values()

            if not data or len(data) < 2:
                return None

            # Parse header
            headers = [h.strip().lower() for h in data[0]]

            # Expected headers
            if 'username' not in headers:
                print("⚠️ Sheet must have 'Username' column")
                return None

            # Parse rows
            parsed_data = []
            for row in data[1:]:  # Skip header
                if not row or not row[0].strip():  # Skip empty rows
                    continue

                row_data = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        value = row[i].strip()
                        # Convert numbers
                        if header in ['goals', 'assists', 'saves', 'shots']:
                            try:
                                row_data[header] = int(value) if value else 0
                            except ValueError:
                                row_data[header] = 0
                        else:
                            row_data[header] = value

                if row_data.get('username'):
                    parsed_data.append(row_data)

            return parsed_data

        except Exception as e:
            print(f"⚠️ Error reading Rocket League sheet: {e}")
            return None

    async def sync_rocket_league_stats(self, guild):
        """Sync Rocket League stats from sheet to database"""
        data = await self.get_rocket_league_data()

        if not data:
            return False

        # Convert to hashable format for change detection
        data_hash = str(sorted([str(d) for d in data]))

        # Check if data changed
        if data_hash == self.last_known_data.get('rocket_league'):
            return False  # No changes

        self.last_known_data['rocket_league'] = data_hash

        print(f"📊 Syncing Rocket League stats from Google Sheets...")

        updated_count = 0

        for player_data in data:
            username = player_data['username']

            # Find player by username (case-insensitive)
            players = await db.get_all_players()
            player = None
            for p in players:
                if p['username'].lower() == username.lower():
                    player = p
                    break

            if not player:
                print(f"⚠️ Player '{username}' not found in database. Skipping.")
                continue

            # Update stats
            stats = await db.get_game_stats(player['user_id'], 'rocket_league')

            # Calculate total points (you can adjust the formula)
            total_points = (
                    player_data.get('goals', 0) * 10 +  # 10 points per goal
                    player_data.get('assists', 0) * 5 +  # 5 points per assist
                    player_data.get('saves', 0) * 3 +  # 3 points per save
                    player_data.get('shots', 0) * 1  # 1 point per shot
            )

            # Store detailed stats
            await db.update_game_stats(player['user_id'], 'rocket_league', {
                'points': total_points,
                'goals': player_data.get('goals', 0),
                'assists': player_data.get('assists', 0),
                'saves': player_data.get('saves', 0),
                'shots': player_data.get('shots', 0),
                # Keep match counts if they exist
                'matches_played': stats.get('matches_played', 0),
                'wins': stats.get('wins', 0),
                'losses': stats.get('losses', 0),
                'queue_priority': stats.get('queue_priority', 0)
            })

            updated_count += 1

        print(f"✅ Updated {updated_count} Rocket League player stats")

        # Update leaderboard channel
        if guild and updated_count > 0:
            cm = get_channel_manager(self.bot)
            await cm.update_leaderboard(guild, 'rocket_league')

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
                    await self.sync_rocket_league_stats(guild)

                await asyncio.sleep(config.SHEET_CHECK_INTERVAL)

            except Exception as e:
                print(f"⚠️ Error in sheets sync loop: {e}")
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