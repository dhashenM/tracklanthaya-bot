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
            'skill_level': 5,  # Default skill level
            'status': 'offline',  # offline or online
            'points': 0,
            'matches_played': 0,
            'wins': 0,
            'losses': 0,
            'created_at': datetime.utcnow(),
            'queue_priority': 0  # For tracking queue skips
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

    async def get_online_players(self):
        """Get all online players"""
        cursor = self.db.players.find({'status': 'online'}).sort('queue_priority', -1)
        return await cursor.to_list(length=None)

    async def get_leaderboard(self, limit=10):
        """Get top players by points"""
        cursor = self.db.players.find().sort('points', -1).limit(limit)
        return await cursor.to_list(length=limit)

    # Match Methods
    async def create_match(self, match_data: dict):
        """Create a new match"""
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

    async def get_active_match(self):
        """Get currently active match"""
        return await self.db.matches.find_one({'status': 'active'})

    async def get_pending_match(self):
        """Get pending (upcoming) match"""
        return await self.db.matches.find_one({'status': 'pending'})

    async def get_match_history(self, limit=10):
        """Get completed matches"""
        cursor = self.db.matches.find({'status': 'completed'}).sort('created_at', -1).limit(limit)
        return await cursor.to_list(length=limit)

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


# Global database instance
db = Database()