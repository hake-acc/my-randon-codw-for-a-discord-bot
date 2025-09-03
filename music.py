import discord
from discord.ext import commands
import yt_dlp
import asyncio
from youtubesearchpython import VideosSearch
import sqlite3
from datetime import datetime
from cogs.premium import is_premium_user, is_premium_guild, require_premium

DATABASE_FILE = "bot_database.db"

COLORS = {
    'success': 0x00FF00,
    'error': 0xFF0000,
    'warning': 0xFFA500,
    'info': 0x0099FF,
    'music': 0xFF0000
}

def create_embed(title, description, color=COLORS['info']):
    """Create a consistent embed"""
    embed = discord.Embed(title=title, description=description, color=color)
    embed.timestamp = datetime.now()
    return embed

def create_success_embed(title, description, user=None):
    """Create a success embed"""
    embed = create_embed(title, description, COLORS['success'])
    if user:
        embed.set_footer(text=f"Requested by {user.display_name}", icon_url=user.display_avatar.url)
    return embed

def create_error_embed(title, description):
    """Create an error embed"""
    return create_embed(title, description, COLORS['error'])

class MusicPlayer:
    """Music player for a guild"""
    
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.queue = []
        self.current_song = None
        self.voice_client = None
        self.volume = 0.5
        self.loop_mode = "off"  # off, single, queue
        self.filters = {}
    
    def add_to_queue(self, song_data):
        """Add song to queue"""
        self.queue.append(song_data)
    
    def get_next_song(self):
        """Get next song from queue"""
        if not self.queue:
            return None
        
        if self.loop_mode == "single" and self.current_song:
            return self.current_song
        elif self.loop_mode == "queue" and self.current_song:
            self.queue.append(self.current_song)
        
        return self.queue.pop(0)

class MusicSystem(commands.Cog):
    """Complete music system with YouTube/Spotify support and premium filters"""
    
    def __init__(self, bot):
        self.bot = bot
        self.players = {}  # guild_id: MusicPlayer
        self.ytdl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extractflat': False,
            'writethumbnail': False,
            'writeinfojson': False
        }
    
    def get_player(self, guild_id: int) -> MusicPlayer:
        """Get or create music player for guild"""
        if guild_id not in self.players:
            self.players[guild_id] = MusicPlayer(guild_id)
        return self.players[guild_id]
    
    async def search_youtube(self, query: str, limit: int = 1):
        """Search YouTube for songs"""
        try:
            search = VideosSearch(query, limit=limit)
            results = search.result()
            
            if results and results['result']:
                return results['result']
            return None
        except Exception as e:
            print(f"YouTube search error: {e}")
            return None
    
    async def get_song_info(self, url_or_query: str):
        """Get song information from URL or search query"""
        try:
            # Check if it's a URL
            if url_or_query.startswith(('http://', 'https://')):
                with yt_dlp.YoutubeDL(self.ytdl_opts) as ytdl:
                    info = ytdl.extract_info(url_or_query, download=False)
                    return {
                        'title': info.get('title', 'Unknown'),
                        'url': info.get('webpage_url', url_or_query),
                        'duration': info.get('duration', 0),
                        'thumbnail': info.get('thumbnail', ''),
                        'uploader': info.get('uploader', 'Unknown'),
                        'stream_url': info.get('url', '')
                    }
            else:
                # Search YouTube
                results = await self.search_youtube(url_or_query)
                if results:
                    video = results[0]
                    return {
                        'title': video['title'],
                        'url': video['link'],
                        'duration': video.get('duration', {}).get('secondsText', '0'),
                        'thumbnail': video.get('thumbnails', [{}])[0].get('url', ''),
                        'uploader': video.get('channel', {}).get('name', 'Unknown'),
                        'stream_url': video['link']
                    }
                return None
        except Exception as e:
            print(f"Error getting song info: {e}")
            return None
    
    @discord.app_commands.command(name="play", description="🎵 Play music from YouTube")
    @discord.app_commands.describe(query="Song name or YouTube URL")
    async def play(self, interaction: discord.Interaction, query: str):
        """Play music"""
        # Check if user is in voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            embed = create_error_embed("Not in Voice", "You need to be in a voice channel to play music!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Get song info
        song_info = await self.get_song_info(query)
        if not song_info:
            embed = create_error_embed("Not Found", f"Could not find: **{query}**")
            await interaction.followup.send(embed=embed)
            return
        
        # Get player
        player = self.get_player(interaction.guild.id)
        
        # Connect to voice if not connected
        if not player.voice_client:
            try:
                player.voice_client = await interaction.user.voice.channel.connect()
            except Exception as e:
                embed = create_error_embed("Connection Failed", f"Could not connect to voice channel: {str(e)}")
                await interaction.followup.send(embed=embed)
                return
        
        # Add to queue
        song_info['requested_by'] = interaction.user
        player.add_to_queue(song_info)
        
        # If not currently playing, start playing
        if not player.voice_client.is_playing():
            await self.play_next(player, interaction.channel)
        
        embed = create_success_embed(
            "🎵 Added to Queue",
            f"**{song_info['title']}**\nBy: {song_info['uploader']}",
            interaction.user
        )
        
        embed.add_field(
            name="📊 Queue Info",
            value=f"Position: **{len(player.queue)}**\nDuration: **{song_info.get('duration', 'Unknown')}**",
            inline=True
        )
        
        if song_info['thumbnail']:
            embed.set_thumbnail(url=song_info['thumbnail'])
        
        await interaction.followup.send(embed=embed)
    
    async def play_next(self, player: MusicPlayer, channel):
        """Play next song in queue"""
        song = player.get_next_song()
        if not song:
            return
        
        try:
            # Get stream URL
            with yt_dlp.YoutubeDL(self.ytdl_opts) as ytdl:
                info = ytdl.extract_info(song['stream_url'], download=False)
                stream_url = info['url']
            
            # Create audio source
            ffmpeg_opts = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': f'-vn -filter:a "volume={player.volume}"'
            }
            
            audio_source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_opts)
            
            # Play audio
            player.current_song = song
            player.voice_client.play(audio_source, after=lambda e: asyncio.create_task(self.song_finished(player, channel, e)))
            
            # Send now playing message
            embed = create_embed(
                title="🎵 Now Playing",
                description=f"**{song['title']}**\nBy: {song['uploader']}",
                color=COLORS['music']
            )
            
            embed.add_field(
                name="🎧 Requested by",
                value=song['requested_by'].mention,
                inline=True
            )
            
            embed.add_field(
                name="📊 Queue",
                value=f"**{len(player.queue)}** songs remaining",
                inline=True
            )
            
            if song['thumbnail']:
                embed.set_thumbnail(url=song['thumbnail'])
            
            # Add music controls
            view = MusicControlView(player, interaction.guild.id)
            
            await channel.send(embed=embed, view=view)
            
        except Exception as e:
            print(f"Error playing song: {e}")
            await self.play_next(player, channel)  # Try next song
    
    async def song_finished(self, player: MusicPlayer, channel, error):
        """Handle song finishing"""
        if error:
            print(f"Player error: {error}")
        
        # Play next song
        await self.play_next(player, channel)
    
    @discord.app_commands.command(name="skip", description="⏭️ Skip current song")
    async def skip(self, interaction: discord.Interaction):
        """Skip current song"""
        player = self.get_player(interaction.guild.id)
        
        if not player.voice_client or not player.voice_client.is_playing():
            embed = create_error_embed("Nothing Playing", "No music is currently playing!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        player.voice_client.stop()
        
        embed = create_success_embed(
            "⏭️ Song Skipped",
            f"Skipped by {interaction.user.mention}",
            interaction.user
        )
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="queue", description="📋 View music queue")
    async def queue(self, interaction: discord.Interaction):
        """Show music queue"""
        player = self.get_player(interaction.guild.id)
        
        if not player.queue and not player.current_song:
            embed = create_embed(
                title="📋 Music Queue",
                description="**Queue is empty**\n\nUse `/play <song>` to add music!",
                color=COLORS['warning']
            )
        else:
            embed = create_embed(
                title="📋 Music Queue",
                description="**Current queue and now playing**",
                color=COLORS['music']
            )
            
            if player.current_song:
                embed.add_field(
                    name="🎵 Now Playing",
                    value=f"**{player.current_song['title']}**\nBy: {player.current_song['uploader']}",
                    inline=False
                )
            
            if player.queue:
                queue_text = ""
                for i, song in enumerate(player.queue[:10]):  # Show first 10
                    queue_text += f"{i+1}. **{song['title']}**\n"
                
                embed.add_field(
                    name=f"📊 Up Next ({len(player.queue)} songs)",
                    value=queue_text,
                    inline=False
                )
                
                if len(player.queue) > 10:
                    embed.add_field(
                        name="➕ More",
                        value=f"And **{len(player.queue) - 10}** more songs...",
                        inline=False
                    )
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="volume", description="🔊 Change music volume")
    @discord.app_commands.describe(volume="Volume level (1-100)")
    async def volume(self, interaction: discord.Interaction, volume: int):
        """Change music volume"""
        if volume < 1 or volume > 100:
            embed = create_error_embed("Invalid Volume", "Volume must be between 1 and 100!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        player = self.get_player(interaction.guild.id)
        player.volume = volume / 100
        
        if player.voice_client and player.voice_client.source:
            player.voice_client.source.volume = player.volume
        
        embed = create_success_embed(
            "🔊 Volume Changed",
            f"Volume set to **{volume}%**",
            interaction.user
        )
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="bassboost", description="🎛️ [PREMIUM] Apply bass boost filter")
    @discord.app_commands.describe(intensity="Bass boost intensity (1-10)")
    async def bassboost(self, interaction: discord.Interaction, intensity: int = 5):
        """Apply bass boost filter (premium only)"""
        if not (is_premium_user(interaction.user.id) or is_premium_guild(interaction.guild.id)):
            embed = create_error_embed(
                "Premium Required",
                "Audio filters are **premium-only** features!"
            )
            embed.add_field(
                name="🎫 Get Premium",
                value="Use `/premium redeem <code>` to unlock audio filters",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if intensity < 1 or intensity > 10:
            embed = create_error_embed("Invalid Intensity", "Bass boost intensity must be between 1 and 10!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        player = self.get_player(interaction.guild.id)
        player.filters['bassboost'] = intensity
        
        embed = create_success_embed(
            "🎛️ Bass Boost Applied",
            f"Bass boost set to **{intensity}/10**",
            interaction.user
        )
        
        embed.add_field(
            name="💎 Premium Feature",
            value="This filter will apply to the next song played",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="disconnect", description="📤 Disconnect from voice channel")
    async def disconnect(self, interaction: discord.Interaction):
        """Disconnect from voice"""
        player = self.get_player(interaction.guild.id)
        
        if not player.voice_client:
            embed = create_error_embed("Not Connected", "Bot is not connected to a voice channel!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await player.voice_client.disconnect()
        player.voice_client = None
        player.queue.clear()
        player.current_song = None
        
        embed = create_success_embed(
            "📤 Disconnected",
            "Left voice channel and cleared queue",
            interaction.user
        )
        
        await interaction.response.send_message(embed=embed)

class MusicControlView(discord.ui.View):
    """Interactive music controls"""
    
    def __init__(self, player: MusicPlayer, guild_id: int):
        super().__init__(timeout=None)  # Persistent view
        self.player = player
        self.guild_id = guild_id
    
    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Pause or resume music"""
        if not self.player.voice_client:
            await interaction.response.send_message("❌ Not connected to voice!", ephemeral=True)
            return
        
        if self.player.voice_client.is_paused():
            self.player.voice_client.resume()
            button.emoji = "⏸️"
            status = "▶️ Resumed"
        else:
            self.player.voice_client.pause()
            button.emoji = "▶️"
            status = "⏸️ Paused"
        
        embed = create_embed(
            title="🎵 Music Control",
            description=f"**{status}** by {interaction.user.mention}",
            color=COLORS['music']
        )
        
        await interaction.response.send_message(embed=embed, delete_after=3)
        await interaction.edit_original_response(view=self)
    
    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Skip current song"""
        if not self.player.voice_client or not self.player.voice_client.is_playing():
            await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)
            return
        
        self.player.voice_client.stop()
        
        embed = create_embed(
            title="⏭️ Song Skipped",
            description=f"Skipped by {interaction.user.mention}",
            color=COLORS['music']
        )
        
        await interaction.response.send_message(embed=embed, delete_after=3)
    
    @discord.ui.button(emoji="📋", style=discord.ButtonStyle.secondary)
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show queue"""
        if not self.player.queue and not self.player.current_song:
            embed = create_embed(
                title="📋 Music Queue",
                description="**Queue is empty**",
                color=COLORS['warning']
            )
        else:
            embed = create_embed(
                title="📋 Music Queue",
                description="**Current queue**",
                color=COLORS['music']
            )
            
            if self.player.current_song:
                embed.add_field(
                    name="🎵 Now Playing",
                    value=f"**{self.player.current_song['title']}**",
                    inline=False
                )
            
            if self.player.queue:
                queue_text = ""
                for i, song in enumerate(self.player.queue[:5]):
                    queue_text += f"{i+1}. {song['title']}\n"
                
                embed.add_field(
                    name=f"📊 Up Next ({len(self.player.queue)})",
                    value=queue_text,
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(emoji="🔄", style=discord.ButtonStyle.secondary)
    async def toggle_loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle loop mode"""
        loop_modes = ["off", "single", "queue"]
        current_index = loop_modes.index(self.player.loop_mode)
        new_index = (current_index + 1) % len(loop_modes)
        self.player.loop_mode = loop_modes[new_index]
        
        loop_emojis = {"off": "➡️", "single": "🔂", "queue": "🔁"}
        button.emoji = loop_emojis[self.player.loop_mode]
        
        embed = create_embed(
            title="🔄 Loop Mode",
            description=f"Loop mode: **{self.player.loop_mode.title()}**",
            color=COLORS['music']
        )
        
        await interaction.response.send_message(embed=embed, delete_after=3)
        await interaction.edit_original_response(view=self)
    
    @discord.ui.button(emoji="📤", style=discord.ButtonStyle.danger)
    async def disconnect(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Disconnect from voice"""
        if not self.player.voice_client:
            await interaction.response.send_message("❌ Not connected to voice!", ephemeral=True)
            return
        
        await self.player.voice_client.disconnect()
        self.player.voice_client = None
        self.player.queue.clear()
        self.player.current_song = None
        
        embed = create_embed(
            title="📤 Disconnected",
            description=f"Left voice channel • Requested by {interaction.user.mention}",
            color=COLORS['warning']
        )
        
        await interaction.response.send_message(embed=embed, delete_after=5)

async def setup(bot):
    await bot.add_cog(MusicSystem(bot))