import discord
from discord.ui import Button, View
from utils.database import db
from utils.channel_manager import get_channel_manager
import config


class OnlineButton(Button):
    """Button to go online for a specific game"""

    def __init__(self, game_id: str):
        game_info = config.GAMES[game_id]
        super().__init__(
            style=discord.ButtonStyle.success,
            label=f"Go Online for {game_info['short_name']}",
            emoji=game_info['emoji'],
            custom_id=f"online_{game_id}"
        )
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        player = await db.get_player(interaction.user.id)

        if not player:
            await interaction.response.send_message(
                "❌ You need to register first! Use `/register`",
                ephemeral=True
            )
            return

        # Check if matchmaking is enabled
        enabled_games = await db.get_enabled_games()
        if self.game_id not in enabled_games:
            await interaction.response.send_message(
                "❌ This game is not currently enabled!",
                ephemeral=True
            )
            return

        # Check skill level
        skill_levels = player.get('skill_levels', {})
        if self.game_id not in skill_levels or skill_levels.get(self.game_id) == 5:
            await interaction.response.send_message(
                f"⚠️ Please set your skill level first for {config.GAMES[self.game_id]['name']}!\n\n"
                f"Use `/setskill` to set your skill level (1-10).",
                ephemeral=True
            )
            return

        # Check if in a match
        if player.get('current_match_game'):
            game_info = config.GAMES[player['current_match_game']]
            await interaction.response.send_message(
                f"❌ You're currently in an active {game_info['name']} match!",
                ephemeral=True
            )
            return

        # Check current status
        queue_status = player.get('queue_status', {})
        current_status = queue_status.get(self.game_id, 'offline')

        if current_status == 'online':
            await interaction.response.send_message(
                "⚠️ You're already online for this game!",
                ephemeral=True
            )
            return

        # Set online
        queue_status[self.game_id] = 'online'
        await db.update_player(interaction.user.id, {'queue_status': queue_status})

        game_info = config.GAMES[self.game_id]
        await interaction.response.send_message(
            f"✅ You are now online for **{game_info['name']}**!",
            ephemeral=True
        )

        # Update queue channel
        from utils.channel_manager import get_channel_manager
        cm = get_channel_manager(interaction.client)
        await cm.update_queue(interaction.guild, self.game_id)

        # Trigger matchmaking
        matchmaking_cog = interaction.client.get_cog('MatchmakingCommands')
        if matchmaking_cog:
            await matchmaking_cog.check_and_create_match(interaction.guild, self.game_id)


class OfflineButton(Button):
    """Button to go offline for a specific game"""

    def __init__(self, game_id: str):
        game_info = config.GAMES[game_id]
        super().__init__(
            style=discord.ButtonStyle.danger,
            label=f"Go Offline for {game_info['short_name']}",
            emoji="⚪",
            custom_id=f"offline_{game_id}"
        )
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        player = await db.get_player(interaction.user.id)

        if not player:
            await interaction.response.send_message(
                "❌ You need to register first! Use `/register`",
                ephemeral=True
            )
            return

        queue_status = player.get('queue_status', {})
        current_status = queue_status.get(self.game_id, 'offline')

        if current_status == 'offline':
            await interaction.response.send_message(
                "⚠️ You're already offline for this game!",
                ephemeral=True
            )
            return

        # Set offline
        queue_status[self.game_id] = 'offline'
        await db.update_player(interaction.user.id, {'queue_status': queue_status})

        game_info = config.GAMES[self.game_id]
        await interaction.response.send_message(
            f"✅ You are now offline for **{game_info['name']}**.",
            ephemeral=True
        )

        # Update queue channel
        from utils.channel_manager import get_channel_manager
        cm = get_channel_manager(interaction.client)
        await cm.update_queue(interaction.guild, self.game_id)


class GameQueueView(View):
    """Persistent view with online/offline buttons for a game"""

    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.add_item(OnlineButton(game_id))
        self.add_item(OfflineButton(game_id))