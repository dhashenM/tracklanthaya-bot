from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import config


class Database:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        """Connect to MongoDB"""
        self.client = AsyncIOMotorClient(config.MONGODB_URI)
        self.db = self.client['lan_matchmaking']
        print("✅ Connected to MongoDB")

    async def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            print("❌ Disconnected from MongoDB")

    # Player/Member Methods
    async def create_player(self, user_id: int, username: str):
        """Create a new player profile"""
        player = {
            'user_id': user_id,
            'username': username,
            'skill_levels': {game_id: 5 for game_id in config.GAMES.keys()},  # Separate skill for each game
            'queue_status': {},  # {game_id: 'online'/'offline'}
            'created_at': datetime.utcnow(),
            'current_match_game': None  # Which game they're currently playing (if any)
        }
        await self.db.players.update_one(
            {'user_id': user_id},
            {'$set': player},
            upsert=True
        )
        return player

    async def get_player(self, user_id: int):
        """Get player by user ID"""
        return await self.db.players.find_one({'user_id': user_id})

    async def update_player(self, user_id: int, update_data: dict):
        """Update player data"""
        await self.db.players.update_one(
            {'user_id': user_id},
            {'$set': update_data}
        )

    async def get_all_players(self):
        """Get all players"""
        cursor = self.db.players.find()
        return await cursor.to_list(length=None)

    async def get_online_players(self, game_id: str):
        """Get all online players for a specific game who aren't in a match"""
        cursor = self.db.players.find({
            f'queue_status.{game_id}': 'online',
            'current_match_game': None  # Not currently in any match
        }).sort(f'queue_priority.{game_id}', -1)
        return await cursor.to_list(length=None)

    async def get_leaderboard(self, game_id: str, limit=10):
        """Get top players by points for specific game"""
        cursor = self.db.game_stats.find({'game_id': game_id}).sort('points', -1).limit(limit)
        stats = await cursor.to_list(length=limit)

        # Enrich with player usernames
        result = []
        for stat in stats:
            player = await self.get_player(stat['user_id'])
            if player:
                stat['username'] = player['username']
                result.append(stat)
        return result

    # Game Stats Methods
    async def get_game_stats(self, user_id: int, game_id: str):
        """Get player stats for specific game"""
        stats = await self.db.game_stats.find_one({
            'user_id': user_id,
            'game_id': game_id
        })

        if not stats:
            # Create default stats
            stats = {
                'user_id': user_id,
                'game_id': game_id,
                'points': 0,
                'matches_played': 0,
                'wins': 0,
                'losses': 0,
                'queue_priority': 0
            }
            await self.db.game_stats.insert_one(stats)

        return stats

    async def update_game_stats(self, user_id: int, game_id: str, update_data: dict):
        """Update player stats for specific game"""
        await self.db.game_stats.update_one(
            {'user_id': user_id, 'game_id': game_id},
            {'$set': update_data},
            upsert=True
        )

    # Match Methods
    async def create_match(self, game_id: str, match_data: dict):
        """Create a new match for specific game"""
        match_data['game_id'] = game_id
        match_data['created_at'] = datetime.utcnow()
        match_data['status'] = 'pending'  # pending, active, completed, cancelled
        result = await self.db.matches.insert_one(match_data)
        match_data['_id'] = result.inserted_id
        return match_data

    async def get_match(self, match_id):
        """Get match by ID"""
        from bson import ObjectId
        return await self.db.matches.find_one({'_id': ObjectId(match_id)})

    async def update_match(self, match_id, update_data: dict):
        """Update match data"""
        from bson import ObjectId
        await self.db.matches.update_one(
            {'_id': ObjectId(match_id)},
            {'$set': update_data}
        )

    async def get_active_match(self, game_id: str):
        """Get currently active match for specific game"""
        return await self.db.matches.find_one({
            'game_id': game_id,
            'status': 'active'
        })

    async def get_pending_match(self, game_id: str):
        """Get pending (upcoming) match for specific game"""
        return await self.db.matches.find_one({
            'game_id': game_id,
            'status': 'pending'
        })

    async def get_match_history(self, game_id: str, limit=10):
        """Get completed matches for specific game"""
        cursor = self.db.matches.find({
            'game_id': game_id,
            'status': 'completed'
        }).sort('created_at', -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_player_active_match(self, user_id: int):
        """Get the active match a player is currently in (any game)"""
        return await self.db.matches.find_one({
            'status': 'active',
            '$or': [
                {'team1.user_id': user_id},
                {'team2.user_id': user_id}
            ]
        })

    # System Settings
    async def get_system_setting(self, key: str):
        """Get system setting"""
        setting = await self.db.settings.find_one({'key': key})
        return setting['value'] if setting else None

    async def set_system_setting(self, key: str, value):
        """Set system setting"""
        await self.db.settings.update_one(
            {'key': key},
            {'$set': {'key': key, 'value': value}},
            upsert=True
        )

    async def get_enabled_games(self):
        """Get list of currently enabled games"""
        setting = await self.get_system_setting('enabled_games')
        return setting if setting else []

    async def set_enabled_games(self, game_ids: list):
        """Set which games are enabled"""
        await self.set_system_setting('enabled_games', game_ids)


# Global database instance
db = Database()