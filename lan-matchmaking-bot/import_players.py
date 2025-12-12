import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv('MONGODB_URI')

# IMPORTANT: These usernames must EXACTLY match their Discord usernames
# Check their Discord profiles to get the exact spelling
players_data = {
    ("Fettucine#3547",4,8,4,2,5,7),
    ("manualcs",6,3,8,6,3,5),
    ("sadeshmagic",6,2,8,3,6,2),
    ("h311_k",6,4,7,4,7,5),
    ("odeusys",6,5,6,5,9,5),
    ("lemikey",4,1,6,3,7,5),
    ("zae2k",8,2,8,5,9,6),
    ("coolmentork",3,2,4,8,5,1),
    ("cjherath89",4,2,4,3,3,1),
    ("Gaz#9958",2,2,1,1,2,1),
    ("zihar",5,2,2,1,4,1),
    ("dooli69",3,5,5,2,6,2),
    ("gurami.",8,3,8,2,8,6),
    ("chunkygg",7,4,4,6,6,4),
    ("soul_ex",8,6,7,7,10,3),
    ("maalu_paan",1,1,4,2,5,1),
    ("ThievingKnave#9600",10,2,2,2,4,7),
    ("4dibb",4,4,4,4,4,4),
    ("miaboar",7,4,4,4,4,5),
    ("falcon_253_",4,3,9,3,9,3),
    ("tubeknight" ,7,3,3,3,10,9),
    ("sushi1756",5,1,5,1,5,1),
    ("sacrosanct1423",5,5,5,5,5,5),
    ("jackb0247",4,6,6,6,4,6),
    #("sacrosanct1423", 1, 8, 4, 9, 5, 7),  # If their Discord name is "fettucine" (lowercase), use that
}

game_order = ['nfs_mw', 'cod_bo3', 'halo_slayer', 'mk1', 'cod_mw', 'rocket_league']


async def import_players():
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client['lan_matchmaking']

    print("🔄 Starting import...")
    print("⚠️  Make sure usernames exactly match Discord usernames!")
    print("")

    created = 0
    updated = 0

    for player_data in players_data:
        username = player_data[0].strip()
        skills = player_data[1:]

        # Create skill levels dict
        skill_levels = {}
        for game_id, skill in zip(game_order, skills):
            skill_levels[game_id] = int(skill)

        # Check if already exists
        existing = await db.players.find_one({'username': username})

        if existing:
            # Update existing
            await db.players.update_one(
                {'username': username},
                {'$set': {'skill_levels': skill_levels}}
            )
            print(f"🔄 Updated: {username}")
            updated += 1
        else:
            # Create temp player document
            # Using username hash as temporary user_id
            temp_user_id = abs(hash(username)) % (10 ** 10)

            player_doc = {
                'user_id': temp_user_id,
                'username': username,
                'skill_levels': skill_levels,
                'queue_status': {},
                'created_at': datetime.utcnow(),
                'current_match_game': None,
                'temp_account': True
            }

            await db.players.insert_one(player_doc)
            print(f"✅ Created: {username}")
            created += 1

    print(f"\n{'=' * 50}")
    print(f"✅ Import complete!")
    print(f"   Created: {created}")
    print(f"   Updated: {updated}")
    print(f"{'=' * 50}")
    print(f"\n📝 Next steps:")
    print(f"   1. Invite players to Discord server")
    print(f"   2. They run /register")
    print(f"   3. Skills will auto-link!")

    client.close()


if __name__ == "__main__":
    asyncio.run(import_players())