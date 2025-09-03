import discord
from discord.ext import commands
import sqlite3
import asyncio
from datetime import datetime
import psutil
import platform

DATABASE_FILE = "bot_database.db"

COLORS = {
    'success': 0x00FF00,
    'error': 0xFF0000,
    'warning': 0xFFA500,
    'info': 0x0099FF,
    'utility': 0x36393F
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

class UtilityCommands(commands.Cog):
    """Utility and information commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.now()
    
    @discord.app_commands.command(name="ping", description="🏓 Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        """Check bot ping"""
        embed = create_embed(
            title="🏓 Pong!",
            description=f"**Latency:** {round(self.bot.latency * 1000)}ms",
            color=COLORS['success']
        )
        
        embed.add_field(
            name="📊 Connection Quality",
            value="🟢 Excellent" if self.bot.latency < 0.1 else "🟡 Good" if self.bot.latency < 0.2 else "🔴 Poor",
            inline=True
        )
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="uptime", description="⏰ Check bot uptime")
    async def uptime(self, interaction: discord.Interaction):
        """Check bot uptime"""
        uptime_delta = datetime.now() - self.start_time
        days = uptime_delta.days
        hours, remainder = divmod(uptime_delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        embed = create_embed(
            title="⏰ Bot Uptime",
            description=f"**{days}d {hours}h {minutes}m {seconds}s**",
            color=COLORS['info']
        )
        
        embed.add_field(
            name="📅 Started",
            value=f"<t:{int(self.start_time.timestamp())}:F>",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="botinfo", description="🤖 Get bot information")
    async def botinfo(self, interaction: discord.Interaction):
        """Get bot information"""
        embed = create_embed(
            title="🤖 Bot Information",
            description="**Ultimate All-in-One Discord Bot**",
            color=COLORS['utility']
        )
        
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        
        embed.add_field(
            name="📊 Statistics",
            value=f"**Servers:** {len(self.bot.guilds):,}\n**Users:** {len(self.bot.users):,}\n**Commands:** {len(self.bot.tree.get_commands())}",
            inline=True
        )
        
        embed.add_field(
            name="💻 System",
            value=f"**Python:** {platform.python_version()}\n**Discord.py:** {discord.__version__}\n**Platform:** {platform.system()}",
            inline=True
        )
        
        uptime_delta = datetime.now() - self.start_time
        days = uptime_delta.days
        hours, remainder = divmod(uptime_delta.seconds, 3600)
        minutes = remainder // 60
        
        embed.add_field(
            name="⏰ Uptime",
            value=f"**{days}d {hours}h {minutes}m**",
            inline=True
        )
        
        # Get system resources
        try:
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            
            embed.add_field(
                name="🖥️ Resources",
                value=f"**CPU:** {cpu_percent}%\n**Memory:** {memory.percent}%\n**Available:** {memory.available // (1024**3)}GB",
                inline=False
            )
        except:
            pass
        
        embed.add_field(
            name="✨ Features",
            value="• Premium System\n• Economy & Leveling\n• Music & Giveaways\n• Advanced Moderation\n• Interactive Setup",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="translate", description="🌐 Translate text")
    @discord.app_commands.describe(
        text="Text to translate",
        target_language="Target language code (e.g., es, fr, de)"
    )
    async def translate(self, interaction: discord.Interaction, text: str, target_language: str = "en"):
        """Translate text (simplified version)"""
        # This is a simplified translation - in production you'd use Google Translate API
        embed = create_embed(
            title="🌐 Translation",
            description=f"**Original:** {text}\n**Target Language:** {target_language.upper()}",
            color=COLORS['info']
        )
        
        embed.add_field(
            name="ℹ️ Note",
            value="Translation service requires external API integration",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="help", description="❓ Get help and command information")
    @discord.app_commands.describe(category="Specific category to view")
    @discord.app_commands.choices(category=[
        discord.app_commands.Choice(name="🚀 Setup & Config", value="setup"),
        discord.app_commands.Choice(name="🛡️ Moderation", value="moderation"),
        discord.app_commands.Choice(name="💰 Economy", value="economy"),
        discord.app_commands.Choice(name="📊 Leveling", value="leveling"),
        discord.app_commands.Choice(name="🎵 Music", value="music"),
        discord.app_commands.Choice(name="🎉 Giveaways", value="giveaways"),
        discord.app_commands.Choice(name="🎭 Fun", value="fun"),
        discord.app_commands.Choice(name="💎 Premium", value="premium")
    ])
    async def help(self, interaction: discord.Interaction, category: discord.app_commands.Choice[str] = None):
        """Show help information"""
        
        if not category:
            # Main help embed
            embed = create_embed(
                title="❓ Bot Help Center",
                description="**Ultimate All-in-One Discord Bot**\n\nSelect a category below to view commands",
                color=COLORS['utility']
            )
            
            embed.add_field(
                name="🚀 Setup & Configuration",
                value="`/setup` `/welcomesetup` `/ticket_setup` `/create_template`",
                inline=True
            )
            
            embed.add_field(
                name="🛡️ Moderation",
                value="`/ban` `/kick` `/timeout` `/warn` `/purge` `/automod_setup`",
                inline=True
            )
            
            embed.add_field(
                name="💰 Economy",
                value="`/balance` `/daily` `/weekly` `/work` `/gamble` `/shop`",
                inline=True
            )
            
            embed.add_field(
                name="📊 Leveling",
                value="`/rank` `/leaderboard` `/level_admin`",
                inline=True
            )
            
            embed.add_field(
                name="🎵 Music",
                value="`/play` `/skip` `/queue` `/volume` `/bassboost` `/disconnect`",
                inline=True
            )
            
            embed.add_field(
                name="🎉 Giveaways",
                value="`/giveaway` - Create, manage, and end giveaways",
                inline=True
            )
            
            embed.add_field(
                name="🎭 Fun & Utility",
                value="`/8ball` `/dice` `/meme` `/joke` `/poll` `/remind` `/userinfo`",
                inline=True
            )
            
            embed.add_field(
                name="💎 Premium",
                value="`/premium` `/premium_admin` - Manage premium features",
                inline=True
            )
            
            embed.add_field(
                name="🔗 Quick Links",
                value="Use `/help <category>` for detailed command information",
                inline=False
            )
            
        else:
            # Category-specific help
            if category.value == "setup":
                embed = create_embed(
                    title="🚀 Setup & Configuration Commands",
                    description="**Interactive server setup and configuration**",
                    color=COLORS['info']
                )
                
                embed.add_field(
                    name="/setup",
                    value="Interactive server rebuild with live preview",
                    inline=False
                )
                
                embed.add_field(
                    name="/welcomesetup",
                    value="Configure welcome messages with interactive panels",
                    inline=False
                )
                
                embed.add_field(
                    name="/ticket_setup",
                    value="Setup ticket system with category and role selection",
                    inline=False
                )
                
                embed.add_field(
                    name="/create_template",
                    value="Create custom server templates with step-by-step builder",
                    inline=False
                )
            
            elif category.value == "moderation":
                embed = create_embed(
                    title="🛡️ Moderation Commands",
                    description="**Advanced moderation and AutoMod features**",
                    color=COLORS['error']
                )
                
                embed.add_field(
                    name="Basic Moderation",
                    value="`/ban` `/kick` `/timeout` `/warn` `/purge`",
                    inline=False
                )
                
                embed.add_field(
                    name="Channel Management",
                    value="`/lock` `/unlock` `/slowmode`",
                    inline=False
                )
                
                embed.add_field(
                    name="AutoMod",
                    value="`/automod_setup` - Configure automated moderation",
                    inline=False
                )
            
            # Add other categories as needed...
            
        embed.set_footer(text="All setup commands use interactive embed interfaces")
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(UtilityCommands(bot))