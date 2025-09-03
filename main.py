import discord
from discord.ext import commands, tasks
import time
import asyncio
import aiohttp
import json
import random
import datetime
from typing import Optional, List
import logging
import base64
import hashlib
import platform
import math
import os
import pickle
import traceback
import io
import sqlite3
import config

# Setup logging
logging.basicConfig(level=logging.INFO)

# Database helper functions
def get_db_connection():
    """Get database connection"""
    return sqlite3.connect('bot_database.db')

def init_db():
    """Initialize database if it doesn't exist"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create guild_settings table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            welcome_enabled INTEGER DEFAULT 0,
            welcome_channel_id INTEGER,
            welcome_message TEXT,
            welcome_embed_title TEXT,
            welcome_embed_description TEXT,
            welcome_embed_color INTEGER,
            welcome_dm_enabled INTEGER DEFAULT 0,
            goodbye_enabled INTEGER DEFAULT 0,
            goodbye_channel_id INTEGER,
            goodbye_message TEXT,
            goodbye_embed_title TEXT,
            goodbye_embed_description TEXT,
            goodbye_embed_color INTEGER,
            autorole_enabled INTEGER DEFAULT 0,
            custom_prefix TEXT DEFAULT '!',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auto_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            role_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS afk_users (
            user_id INTEGER PRIMARY KEY,
            guild_id INTEGER,
            reason TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            channel_id INTEGER,
            message TEXT,
            remind_time TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS custom_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_name TEXT UNIQUE,
            description TEXT,
            created_by INTEGER,
            roles_data TEXT,
            channels_data TEXT,
            settings_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

# Bot Configuration
TOKEN = config.token
BOT_OWNER_ID = 1209807688435892285

# Dynamic prefix function
def get_prefix(bot, message):
    """Get custom prefix for guild or default"""
    if not message.guild:
        return "!"  # Default for DMs
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT custom_prefix FROM guild_settings WHERE guild_id = ?', (message.guild.id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return result[0]
        else:
            return "!"  # Default prefix
    except:
        return "!"  # Fallback

# Bot Setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=get_prefix, intents=intents)

@bot.event
async def on_ready():
    print(f"⚙️ Utility Core Ready! Logged in as {bot.user}")
    print(f"🆔 Bot ID: {bot.user.id}")
    print(f"🏢 Servers: {len(bot.guilds)}")
    print(f"👥 Users: {sum(guild.member_count for guild in bot.guilds)}")

    try:
        # Sync slash commands
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

    # Set bot status
    try:
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(bot.guilds)} servers | /help for commands"
            )
        )
        print("🔄 Status changed to normal activity")
    except Exception as e:
        print(f"⚠️ Could not set status: {e}")

    # Start auto-meme system
    if not auto_meme_poster.is_running():
        auto_meme_poster.start()
        print("🎭 Auto-meme system started")
    else:
        print("🎭 Auto-meme system already running")

# Anti-nuke event handlers with enhanced detection
@bot.event
async def on_guild_channel_delete(channel):
    """Handle channel deletion for anti-nuke protection"""
    if not hasattr(channel, 'guild') or not channel.guild:
        return
    
    try:
        async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
            if entry.target.id == channel.id:
                if await increment_user_action(channel.guild.id, entry.user.id, 'channel_delete', channel.guild):
                    await trigger_anti_nuke(channel.guild, entry.user, 'Mass Channel Deletion')
                break
    except:
        pass

@bot.event
async def on_guild_channel_create(channel):
    """Handle channel creation for anti-nuke protection"""
    if not hasattr(channel, 'guild') or not channel.guild:
        return
        
    try:
        async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.channel_create, limit=1):
            if entry.target.id == channel.id:
                if await increment_user_action(channel.guild.id, entry.user.id, 'channel_create', channel.guild):
                    await trigger_anti_nuke(channel.guild, entry.user, 'Mass Channel Creation')
                break
    except:
        pass

@bot.event
async def on_guild_role_delete(role):
    """Handle role deletion for anti-nuke protection"""
    try:
        async for entry in role.guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=1):
            if entry.target.id == role.id:
                if await increment_user_action(role.guild.id, entry.user.id, 'role_delete', role.guild):
                    await trigger_anti_nuke(role.guild, entry.user, 'Mass Role Deletion')
                break
    except:
        pass

@bot.event
async def on_guild_role_create(role):
    """Handle role creation for anti-nuke protection"""
    try:
        async for entry in role.guild.audit_logs(action=discord.AuditLogAction.role_create, limit=1):
            if entry.target.id == role.id:
                if await increment_user_action(role.guild.id, entry.user.id, 'role_create', role.guild):
                    await trigger_anti_nuke(role.guild, entry.user, 'Mass Role Creation')
                break
    except:
        pass

@bot.event
async def on_member_ban(guild, user):
    """Handle member bans for anti-nuke protection"""
    try:
        async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=1):
            if entry.target.id == user.id:
                if await increment_user_action(guild.id, entry.user.id, 'member_ban', guild):
                    await trigger_anti_nuke(guild, entry.user, 'Mass Banning')
                break
    except:
        pass

@bot.event
async def on_member_kick(guild, user):
    """Handle member kicks for anti-nuke protection"""
    try:
        async for entry in guild.audit_logs(action=discord.AuditLogAction.kick, limit=1):
            if entry.target.id == user.id:
                if await increment_user_action(guild.id, entry.user.id, 'member_kick', guild):
                    await trigger_anti_nuke(guild, entry.user, 'Mass Kicking')
                break
    except:
        pass

@bot.event
async def on_webhooks_update(channel):
    """Handle webhook changes for anti-nuke protection"""
    if not hasattr(channel, 'guild') or not channel.guild:
        return
        
    try:
        async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.webhook_create, limit=1):
            if await increment_user_action(channel.guild.id, entry.user.id, 'webhook_create', channel.guild):
                await trigger_anti_nuke(channel.guild, entry.user, 'Mass Webhook Creation')
            break
    except:
        pass

@bot.event
async def on_message(message):
    # Ignore bot messages
    if message.author.bot:
        return

    # Handle media-only channels
    if message.guild and message.guild.id in media_only_channels:
        if message.channel.id in media_only_channels[message.guild.id]:
            # Check if message has media content
            has_media = (
                message.attachments or
                any(url in message.content.lower() for url in ["http://", "https://", "www.", ".com", ".gif", ".jpg", ".png", ".mp4", ".webm"]) or
                message.embeds
            )

            if not has_media and message.content.strip():
                # Delete text-only message and send brief warning
                try:
                    await message.delete()
                    warning = await message.channel.send(
                        f"📸 {message.author.mention}, this is a media-only channel! Please share images, videos, or media links only.",
                        delete_after=5
                    )
                except:
                    pass

    # Process commands if any (for compatibility)
    await bot.process_commands(message)

    # AFK check
    await on_message_afk_check(message)

# Setup progress tracking
SETUP_PROGRESS_FILE = "setup_progress.json"

class SetupProgress:
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.step = "start"
        self.created_roles = {}
        self.created_categories = {}
        self.created_channels = {}
        self.deleted_channels = 0
        self.deleted_roles = 0
        self.total_roles = 0
        self.total_categories = 0
        self.total_channels = 0
        self.current_category_index = 0
        self.current_channel_index = 0
        self.timestamp = time.time()

def save_setup_progress(progress):
    """Save setup progress to file"""
    try:
        if os.path.exists(SETUP_PROGRESS_FILE):
            with open(SETUP_PROGRESS_FILE, 'r') as f:
                data = json.load(f)
        else:
            data = {}

        # Convert progress to dict for JSON serialization
        progress_dict = {
            'guild_id': progress.guild_id,
            'step': progress.step,
            'created_roles': {name: role_id for name, role_id in progress.created_roles.items()},
            'created_categories': {name: cat_id for name, cat_id in progress.created_categories.items()},
            'created_channels': {name: chan_id for name, chan_id in progress.created_channels.items()},
            'deleted_channels': progress.deleted_channels,
            'deleted_roles': progress.deleted_roles,
            'total_roles': progress.total_roles,
            'total_categories': progress.total_categories,
            'total_channels': progress.total_channels,
            'current_category_index': progress.current_category_index,
            'current_channel_index': progress.current_channel_index,
            'timestamp': progress.timestamp
        }

        data[str(progress.guild_id)] = progress_dict

        with open(SETUP_PROGRESS_FILE, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"💾 Saved setup progress for guild {progress.guild_id} at step: {progress.step}")
    except Exception as e:
        print(f"❌ Failed to save setup progress: {e}")

def load_setup_progress(guild_id):
    """Load setup progress from file"""
    try:
        if not os.path.exists(SETUP_PROGRESS_FILE):
            return None

        with open(SETUP_PROGRESS_FILE, 'r') as f:
            data = json.load(f)

        guild_data = data.get(str(guild_id))
        if not guild_data:
            return None

        # Check if progress is too old (older than 1 hour)
        if time.time() - guild_data['timestamp'] > 3600:
            print(f"⏰ Setup progress for guild {guild_id} is too old, ignoring")
            clear_setup_progress(guild_id)
            return None

        progress = SetupProgress(guild_id)
        progress.step = guild_data['step']
        progress.created_roles = {name: int(role_id) for name, role_id in guild_data['created_roles'].items()}
        progress.created_categories = {name: int(cat_id) for name, cat_id in guild_data['created_categories'].items()}
        progress.created_channels = {name: int(chan_id) for name, chan_id in guild_data['created_channels'].items()}
        progress.deleted_channels = guild_data['deleted_channels']
        progress.deleted_roles = guild_data['deleted_roles']
        progress.total_roles = guild_data['total_roles']
        progress.total_categories = guild_data['total_categories']
        progress.total_channels = guild_data['total_channels']
        progress.current_category_index = guild_data['current_category_index']
        progress.current_channel_index = guild_data['current_channel_index']
        progress.timestamp = guild_data['timestamp']

        print(f"📂 Loaded setup progress for guild {guild_id} at step: {progress.step}")
        return progress
    except Exception as e:
        print(f"❌ Failed to load setup progress: {e}")
        return None

def clear_setup_progress(guild_id):
    """Clear setup progress for a guild"""
    try:
        if not os.path.exists(SETUP_PROGRESS_FILE):
            return

        with open(SETUP_PROGRESS_FILE, 'r') as f:
            data = json.load(f)

        if str(guild_id) in data:
            del data[str(guild_id)]

            with open(SETUP_PROGRESS_FILE, 'w') as f:
                json.dump(data, f, indent=2)

            print(f"🗑️ Cleared setup progress for guild {guild_id}")
    except Exception as e:
        print(f"❌ Failed to clear setup progress: {e}")

# Premium system and cooldown management
premium_servers = set()  # Set of guild IDs that have premium
user_cooldowns = {}  # {user_id: {command_name: timestamp}}
DEFAULT_COOLDOWN = 3  # 3 seconds default cooldown

def is_premium_server(guild_id):
    """Check if a server has premium status"""
    return guild_id in premium_servers

def add_premium_server(guild_id):
    """Add a server to premium list"""
    premium_servers.add(guild_id)
    return True

def remove_premium_server(guild_id):
    """Remove a server from premium list"""
    premium_servers.discard(guild_id)
    return True

def check_cooldown(user_id, command_name, guild_id=None):
    """Check if user is on cooldown for a command"""
    # Premium servers bypass cooldowns
    if guild_id and is_premium_server(guild_id):
        return True

    current_time = time.time()

    if user_id not in user_cooldowns:
        user_cooldowns[user_id] = {}

    if command_name in user_cooldowns[user_id]:
        time_passed = current_time - user_cooldowns[user_id][command_name]
        if time_passed < DEFAULT_COOLDOWN:
            return False

    user_cooldowns[user_id][command_name] = current_time
    return True

def get_cooldown_remaining(user_id, command_name):
    """Get remaining cooldown time in seconds"""
    if user_id not in user_cooldowns or command_name not in user_cooldowns[user_id]:
        return 0

    current_time = time.time()
    time_passed = current_time - user_cooldowns[user_id][command_name]
    remaining = DEFAULT_COOLDOWN - time_passed
    return max(0, remaining)

# Enhanced color scheme with premium gradient-inspired colors
COLORS = {
    'primary': 0x2F3136,
    'success': 0x00FF88,      # Bright green
    'error': 0xFF4757,        # Vibrant red
    'warning': 0xFFA726,      # Orange amber
    'info': 0x5DADE2,         # Sky blue
    'embed': 0x36393F,
    'aqua': 0x1DD1A1,         # Turquoise
    'purple': 0x8C7AE6,       # Soft purple
    'gold': 0xF39C12,         # Rich gold
    'red': 0xE55039,          # Deep red
    'green': 0x27AE60,        # Forest green
    'blue': 0x3742FA,         # Royal blue
    'pink': 0xFF3838,         # Hot pink
    'orange': 0xFF6348,       # Coral orange
    'teal': 0x0FB9B1,         # Deep teal
    'indigo': 0x4834D4,       # Deep indigo
    'cyan': 0x00D2D3,         # Electric cyan
    'lime': 0x7ED321,         # Electric lime
    'amber': 0xFFB142,        # Rich amber
    'deep_purple': 0x6C5CE7,  # Deep purple
    'light_blue': 0x74B9FF,   # Light blue
    'dark_aqua': 0x00A8CC,    # Dark aqua
    'neon_green': 0x32FF7E,   # Neon green
    'electric_blue': 0x18DCFF, # Electric blue
    'sunset_orange': 0xFF5722, # Sunset orange
    'lavender': 0xC44569,     # Lavender
    'mint': 0x00CEC9,         # Mint
    'coral': 0xFF7675         # Coral
}

# Bot stats tracking
bot_stats = {
    'commands_used': 0,
    'start_time': time.time(),
    'servers_joined': 0,
    'messages_sent': 0
}

# Auto-meme system storage
auto_meme_webhooks = {}  # {guild_id: webhook_url}

# Media-only channel system
media_only_channels = {}  # {guild_id: [channel_ids]}
MEDIA_ONLY_LIMIT_BASIC = 3  # Non-premium servers
MEDIA_ONLY_LIMIT_PREMIUM = float('inf')  # Premium servers (unlimited)

# Variables system for dynamic content
server_variables = {}  # {guild_id: {variable_name: value}}

# Default variables
DEFAULT_VARIABLES = {
    '{user}': 'The user being mentioned',
    '{user.name}': 'Username without discriminator',
    '{user.mention}': 'User mention (@user)',
    '{user.id}': 'User ID',
    '{user.avatar}': 'User avatar URL',
    '{user.created}': 'Account creation date',
    '{user.joined}': 'Server join date',
    '{guild.name}': 'Server/Guild name',
    '{guild.id}': 'Server/Guild ID',
    '{guild.icon}': 'Server icon URL',
    '{guild.owner}': 'Server owner mention',
    '{guild.membercount}': 'Total member count',
    '{guild.created}': 'Server creation date',
    '{channel}': 'Current channel mention',
    '{channel.name}': 'Current channel name',
    '{channel.id}': 'Current channel ID',
    '{date}': 'Current date',
    '{time}': 'Current time',
    '{timestamp}': 'Unix timestamp',
    '{random.number}': 'Random number 1-100',
    '{random.color}': 'Random hex color',
    '{bot.name}': 'Bot username',
    '{bot.mention}': 'Bot mention',
    '{invite.count}': 'User invite count',
    '{level}': 'User level (if leveling enabled)',
    '{rank}': 'User rank (if leveling enabled)'
}

# Autoresponder system
autoresponders = {}  # {guild_id: [{'trigger': str, 'response': str, 'match_type': str}]}

# Advanced Ticket system
ticket_systems = {}  # {guild_id: TicketSystem}
active_tickets = {}  # {channel_id: TicketData}
ticket_counter = {}  # {guild_id: int}

class TicketType:
    def __init__(self, name, emoji, description, category_name=None, color=0x3498db,
                 embed_title=None, embed_description=None, embed_thumbnail=None,
                 embed_image=None, embed_footer=None, embed_author=None):
        self.name = name
        self.emoji = emoji
        self.description = description
        self.category_name = category_name or f"🎫 {name} Tickets"
        self.color = color
        self.embed_title = embed_title or f"🎫 {name} Ticket"
        self.embed_description = embed_description or f"Support ticket for {name}"
        self.embed_thumbnail = embed_thumbnail
        self.embed_image = embed_image
        self.embed_footer = embed_footer or "React with 🔒 to close this ticket"
        self.embed_author = embed_author
        self.category_id = None

class TicketSystem:
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.enabled = True
        self.ticket_types = {}
        self.log_channel_id = None
        self.staff_roles = []
        self.embed_color = 0x3498db
        self.embed_title = "🎫 Support Ticket System"
        self.embed_description = "Select the type of support you need below!"
        self.embed_thumbnail = None
        self.embed_image = None
        self.embed_footer = "Choose your ticket type • Support Team"
        self.embed_author = None
        self.auto_categorize = True
        self.max_tickets_per_user = 3
        self.transcript_logs = True
        self.ping_staff = True
        self.welcome_message = "Hello {user.mention}! Thank you for creating a ticket. Please describe your issue and a staff member will assist you shortly."

    def add_ticket_type(self, ticket_type):
        self.ticket_types[ticket_type.name.lower()] = ticket_type

    def remove_ticket_type(self, name):
        if name.lower() in self.ticket_types:
            del self.ticket_types[name.lower()]

    def get_ticket_type(self, name):
        return self.ticket_types.get(name.lower())

class TicketData:
    def __init__(self, user_id, ticket_type, ticket_number, created_at, channel_id, category_id=None):
        self.user_id = user_id
        self.ticket_type = ticket_type
        self.ticket_number = ticket_number
        self.created_at = created_at
        self.channel_id = channel_id
        self.category_id = category_id
        self.claimed_by = None
        self.status = "open"  # open, claimed, closed
        self.transcript = []

def init_default_ticket_system(guild_id):
    """Initialize default ticket system with pre-configured ticket types"""
    system = TicketSystem(guild_id)

    # Default ticket types
    default_types = [
        TicketType("General Support", "🆘", "General help and support", color=0x3498db),
        TicketType("Bug Report", "🐛", "Report a bug or issue", color=0xe74c3c),
        TicketType("Feature Request", "✨", "Request a new feature", color=0x9b59b6),
        TicketType("Partnership", "🤝", "Business and partnership inquiries", color=0xf39c12),
        TicketType("Staff Application", "📋", "Apply for staff positions", color=0x2ecc71),
        TicketType("Report User", "⚠️", "Report a user for violations", color=0xff6b6b),
        TicketType("Ban Appeal", "🔓", "Appeal a ban or punishment", color=0x95a5a6),
        TicketType("Other", "❓", "Other issues not covered above", color=0x7f8c8d)
    ]

    for ticket_type in default_types:
        system.add_ticket_type(ticket_type)

    return system

# Music system
music_queues = {}  # {guild_id: [{'title': str, 'url': str, 'requester': user}]}
voice_clients = {}  # {guild_id: voice_client}

meme_database = [
    "https://i.imgur.com/oNObxMf.gif",
    "https://i.imgur.com/dBYw7gf.jpg",
    "https://i.imgur.com/xvjpQfK.png",
    "https://i.imgur.com/gAYjCGo.jpg",
    "https://i.imgur.com/Z5e8qn4.png",
    "https://i.imgur.com/KOgQ7nH.jpg",
    "https://i.imgur.com/0TfZl0x.gif",
    "https://i.imgur.com/WuQkgNP.jpg",
    "https://i.imgur.com/YhcQZxL.png",
    "https://i.imgur.com/vX4bW9t.jpg",
    "https://i.imgur.com/8YjKL3R.gif",
    "https://i.imgur.com/5pJ6Q2m.png",
    "https://i.imgur.com/nR2mX9k.jpg",
    "https://i.imgur.com/fG8kP5L.gif",
    "https://i.imgur.com/tY9mL6N.png"
]

meme_captions = [
    "When you finally understand the code you wrote 6 months ago 🧠",
    "POV: You're debugging at 3 AM and find the bug 🐛",
    "Me explaining why I need 32GB of RAM 💻",
    "When someone asks if you've tried turning it off and on again 🔄",
    "That feeling when your code works on the first try ✨",
    "When you realize you've been debugging for 3 hours because of a missing semicolon 😭",
    "Me when I see 'It works on my machine' 🤷‍♂️",
    "When you finally fix that one bug that's been haunting you 🎉",
    "POV: You're the only one who understands your own code 🤓",
    "When you're pair programming and your partner suggests using Internet Explorer 💀",
    "Me after successfully deploying to production on Friday 😎",
    "When you find a Stack Overflow answer that actually works 🙏",
    "That moment when you realize you've been overthinking a simple problem 🤯",
    "When you're pair programming and your partner suggests using Internet Explorer 💀",
    "Me when I see clean, commented code 😍"
]

# Error reporting function
async def report_error_to_owner(error, context=None):
    """Report errors to bot owner via DM"""
    try:
        owner = bot.get_user(BOT_OWNER_ID)
        if not owner:
            return

        error_embed = discord.Embed(
            title="🚨 Bot Error Report",
            description="An error occurred in the bot:",
            color=COLORS['error'],
            timestamp=discord.utils.utcnow()
        )

        error_embed.add_field(
            name="❌ Error",
            value=f"```python\n{str(error)[:1000]}\n```",
            inline=False
        )

        if context:
            error_embed.add_field(
                name="📍 Context",
                value=f"```{str(context)[:1000]}```",
                inline=False
            )

        # Add traceback
        tb = traceback.format_exc()
        if tb != "NoneType: None\n":
            error_embed.add_field(
                name="📋 Traceback",
                value=f"```python\n{tb[:1000]}\n```",
                inline=False
            )

        error_embed.add_field(
            name="⏰ Timestamp",
            value=f"<t:{int(time.time())}:F>",
            inline=True
        )

        await owner.send(embed=error_embed)
        print(f"📨 Error report sent to owner: {str(error)[:100]}")

    except Exception as e:
        print(f"❌ Failed to send error report: {e}")

# Variable replacement function
def replace_variables(text, user=None, guild=None, channel=None):
    """Replace variables in text with actual values"""
    if not text:
        return text

    result = text

    try:
        # User variables
        if user:
            result = result.replace('{user}', str(user))
            result = result.replace('{user.name}', user.name)
            result = result.replace('{user.mention}', user.mention)
            result = result.replace('{user.id}', str(user.id))
            result = result.replace('{user.avatar}', str(user.avatar.url) if user.avatar else str(user.default_avatar.url))
            result = result.replace('{user.created}', f"<t:{int(user.created_at.timestamp())}:F>")
            if hasattr(user, 'joined_at') and user.joined_at:
                result = result.replace('{user.joined}', f"<t:{int(user.joined_at.timestamp())}:F>")

        # Guild variables
        if guild:
            result = result.replace('{guild.name}', guild.name)
            result = result.replace('{guild.id}', str(guild.id))
            result = result.replace('{guild.icon}', str(guild.icon.url) if guild.icon else "No icon")
            result = result.replace('{guild.owner}', guild.owner.mention if guild.owner else "Unknown")
            result = result.replace('{guild.membercount}', str(guild.member_count))
            result = result.replace('{guild.created}', f"<t:{int(guild.created_at.timestamp())}:F>")

        # Channel variables
        if channel:
            result = result.replace('{channel}', channel.mention)
            result = result.replace('{channel.name}', channel.name)
            result = result.replace('{channel.id}', str(channel.id))

        # Time variables
        now = datetime.datetime.now()
        result = result.replace('{date}', now.strftime("%Y-%m-%d"))
        result = result.replace('{time}', now.strftime("%H:%M:%S"))
        result = result.replace('{timestamp}', str(int(time.time())))

        # Random variables
        result = result.replace('{random.number}', str(random.randint(1, 100)))
        result = result.replace('{random.color}', f"#{random.randint(0, 0xFFFFFF):06x}")

        # Bot variables
        if bot.user:
            result = result.replace('{bot.name}', bot.user.name)
            result = result.replace('{bot.mention}', bot.user.mention)

        # Placeholder for features that might not be implemented
        result = result.replace('{invite.count}', "0")
        result = result.replace('{level}', "1")
        result = result.replace('{rank}', "Unranked")

    except Exception as e:
        print(f"❌ Error replacing variables: {e}")

    return result

# Simple delay function
async def safe_sleep(seconds=0.5):
    """Simple sleep to avoid rate limits"""
    await asyncio.sleep(seconds)

# Dangerous command confirmation system
async def confirm_dangerous_action(interaction: discord.Interaction, action_name: str, description: str, timeout: int = 15):
    """
    Ask user to confirm a dangerous action within the specified timeout
    Returns True if confirmed, False if cancelled or timed out
    """
    confirm_embed = create_embed(
        title="⚠️ DANGEROUS ACTION CONFIRMATION",
        description=f"**You are about to perform a potentially destructive action:**\n\n🔥 **Action:** {action_name}\n📋 **Description:** {description}",
        color=COLORS['error']
    )

    confirm_embed.add_field(
        name="⏰ Time Limit",
        value=f"You have **{timeout} seconds** to confirm this action.",
        inline=True
    )

    confirm_embed.add_field(
        name="🎯 Required Action",
        value="Click ✅ to **CONFIRM** or ❌ to **CANCEL**",
        inline=True
    )

    confirm_embed.add_field(
        name="⚠️ WARNING",
        value="This action cannot be undone! Make sure you really want to proceed.",
        inline=False
    )

    confirm_embed.set_footer(text="⚠️ Think carefully before confirming destructive actions!")

    # Send confirmation message
    if not interaction.response.is_done():
        await interaction.response.send_message(embed=confirm_embed)
        message = await interaction.original_response()
    else:
        message = await interaction.followup.send(embed=confirm_embed, wait=True)

    # Add reaction buttons
    await message.add_reaction("✅")
    await message.add_reaction("❌")

    def check(reaction, user):
        return (user == interaction.user and
                str(reaction.emoji) in ["✅", "❌"] and
                reaction.message.id == message.id)

    try:
        # Wait for user reaction with timeout
        reaction, user = await bot.wait_for('reaction_add', timeout=timeout, check=check)

        if str(reaction.emoji) == "✅":
            # Confirmed
            confirmed_embed = create_success_embed(
                "Action Confirmed",
                f"You confirmed the action: **{action_name}**\nProceeding with execution...",
                interaction.user
            )
            await interaction.edit_original_response(embed=confirmed_embed)
            await safe_sleep(1.0)  # Brief pause before executing
            return True
        else:
            # Cancelled
            cancelled_embed = create_embed(
                title="❌ Action Cancelled",
                description=f"You cancelled the action: **{action_name}**\nNo changes were made.",
                color=COLORS['warning']
            )
            cancelled_embed.add_field(
                name="✅ Safety First",
                value="Good choice! It's always better to be safe with destructive actions.",
                inline=False
            )
            await interaction.edit_original_response(embed=cancelled_embed)
            return False

    except asyncio.TimeoutError:
        # Timed out
        timeout_embed = create_embed(
            title="⏰ Confirmation Timeout",
            description=f"You didn't confirm within {timeout} seconds.\nAction **{action_name}** was automatically cancelled for safety.",
            color=COLORS['error']
        )
        timeout_embed.add_field(
            name="🔒 Auto-Safety",
            value="Dangerous actions require explicit confirmation within the time limit.",
            inline=False
        )
        await interaction.edit_original_response(embed=timeout_embed)
        return False

# Utility functions
def create_embed(title=None, description=None, color=COLORS['primary'], fields=None, footer=None, thumbnail=None, image=None, author=None, animated=False):
    """Create a beautiful embed with enhanced styling and animations"""

    # Enhanced animated elements with better visual impact
    if animated and title:
        animation_chars = ["🌟", "✨", "💫", "⭐", "🎯", "🚀", "⚡", "🔥", "💎", "🌈"]
        title = f"{random.choice(animation_chars)} {title} {random.choice(animation_chars)}"

    # Add visual enhancements to description
    if description and not description.startswith('```'):
        # Add subtle visual separators for long descriptions
        if len(description) > 100:
            description = f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n{description}\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"

    embed = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())

    if fields:
        for field in fields:
            name = field.get('name', '\u200b')
            value = field.get('value', '\u200b')

            # Enhanced field styling with better visual separation
            if not field.get('inline', False) and len(str(value)) > 50:
                # Add subtle borders for code blocks
                if not value.startswith('```'):
                    value = f"```yaml\n{value}\n```"

            # Add visual indicators for field names
            if not name.startswith('```') and len(name) > 1:
                # Add emoji indicators based on field type
                if any(keyword in name.lower() for keyword in ['success', 'complete', 'done', 'enabled']):
                    name = f"✅ {name}"
                elif any(keyword in name.lower() for keyword in ['error', 'failed', 'disabled', 'denied']):
                    name = f"❌ {name}"
                elif any(keyword in name.lower() for keyword in ['warning', 'caution', 'attention']):
                    name = f"⚠️ {name}"
                elif any(keyword in name.lower() for keyword in ['info', 'status', 'current']):
                    name = f"ℹ️ {name}"

            embed.add_field(name=name, value=value, inline=field.get('inline', False))

    # Enhanced footer with dynamic elements and better formatting
    if footer:
        embed.set_footer(text=f"🎯 {footer} • Utility Core", icon_url=bot.user.avatar.url if bot.user.avatar else None)
    else:
        server_count = len(bot.guilds)
        embed.set_footer(text=f"⚙️ Utility Core • {server_count:,} servers • Advanced Bot System", icon_url=bot.user.avatar.url if bot.user.avatar else None)

    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    if author:
        embed.set_author(name=author.get('name'), icon_url=author.get('icon'), url=author.get('url'))

    return embed

def create_success_embed(title, description, user=None, animated=True):
    """Create a premium success embed with enhanced styling"""
    # Use custom emojis if available, fallback to Unicode
    emoji = get_custom_emoji('success', '✅')
    if not animated:
        emoji = '✅'

    # Add visual enhancement to description
    enhanced_description = f"🎊 **{description}** 🎊" if animated else f"**{description}**"

    embed = create_embed(
        title=f"{emoji} {title}",
        description=enhanced_description,
        color=COLORS['neon_green'],  # Using brighter success color
        animated=animated
    )

    if user:
        embed.set_author(
            name=f"🌟 Action by {user.display_name}",
            icon_url=user.avatar.url if user.avatar else user.default_avatar.url
        )

    # Enhanced success indicator with better visual appeal
    embed.add_field(
        name="🎯 Operation Status",
        value="🟢 **COMPLETED SUCCESSFULLY** ✨",
        inline=True
    )

    # Add timestamp for better context
    embed.add_field(
        name="⏰ Completed At",
        value=f"<t:{int(time.time())}:F>",
        inline=True
    )

    return embed

def create_error_embed(title, description, suggestion=None):
    """Create a premium error embed with helpful suggestions"""
    # Use custom emojis if available, fallback to Unicode
    emoji = get_custom_emoji('error', '❌')

    # Enhanced error description with better formatting
    enhanced_description = f"🚨 **{description}** 🚨"

    embed = create_embed(
        title=f"{emoji} {title}",
        description=enhanced_description,
        color=COLORS['error']
    )

    # Enhanced error status with better visual appeal
    embed.add_field(
        name="🎯 Operation Status",
        value="🔴 **OPERATION FAILED** ⚠️",
        inline=True
    )

    # Add error timestamp
    embed.add_field(
        name="⏰ Error Time",
        value=f"<t:{int(time.time())}:R>",
        inline=True
    )

    # Enhanced suggestion field with better formatting
    if suggestion:
        embed.add_field(
            name="💡 Helpful Suggestion",
            value=f"🔧 {suggestion}",
            inline=False
        )

    # Add support information
    embed.add_field(
        name="🆘 Need Help?",
        value=f"Contact <@{BOT_OWNER_ID}> for assistance with persistent errors.",
        inline=False
    )

    return embed

def create_info_embed(title, description, user=None, tip=None):
    """Create a premium info embed with helpful tips"""
    # Use custom emojis if available, fallback to Unicode
    emoji = get_custom_emoji('info', 'ℹ️')

    # Enhanced info description
    enhanced_description = f"📌 **{description}**"

    embed = create_embed(
        title=f"{emoji} {title}",
        description=enhanced_description,
        color=COLORS['electric_blue']  # Using more vibrant info color
    )

    if user:
        embed.set_author(
            name=f"🎯 Requested by {user.display_name}",
            icon_url=user.avatar.url if user.avatar else user.default_avatar.url
        )

    # Enhanced info status with better visual appeal
    embed.add_field(
        name="🎯 Information Status",
        value="🔵 **DATA RETRIEVED** ✨",
        inline=True
    )

    # Add retrieval timestamp
    embed.add_field(
        name="⏰ Retrieved At",
        value=f"<t:{int(time.time())}:R>",
        inline=True
    )

    # Enhanced tip field with better formatting
    if tip:
        embed.add_field(
            name="💎 Pro Tip",
            value=f"🌟 {tip}",
            inline=False
        )

    return embed

def create_loading_embed(title, description="Please wait while we process your request..."):
    """Create a loading embed for long operations"""
    loading_emojis = ["⏳", "🔄", "⚡", "🌀", "⏱️", "🔃", "🎯", "⚙️"]
    emoji = random.choice(loading_emojis)

    # Enhanced loading description with animation feel
    enhanced_description = f"⚡ **{description}** ⚡\n\n🔄 This may take a few moments..."

    embed = create_embed(
        title=f"{emoji} {title}",
        description=enhanced_description,
        color=COLORS['electric_blue']  # Using dynamic color for loading
    )

    # Enhanced processing status with visual appeal
    embed.add_field(
        name="🎯 Processing Status",
        value="🟡 **IN PROGRESS** ⚡",
        inline=True
    )

    # Add estimated time
    embed.add_field(
        name="⏰ Estimated Time",
        value="⏳ **Few seconds**",
        inline=True
    )

    # Add progress indicator
    embed.add_field(
        name="📊 Progress",
        value="🔄 **Working...** 🌀",
        inline=False
    )

    return embed

def create_warning_embed(title, description, action_required=None):
    """Create a premium warning embed"""
    warning_emojis = ["⚠️", "🚨", "⏰", "🔔", "🟡", "🔸", "📢"]
    emoji = random.choice(warning_emojis)

    # Enhanced warning description
    enhanced_description = f"⚡ **{description}** ⚡"

    embed = create_embed(
        title=f"{emoji} {title}",
        description=enhanced_description,
        color=COLORS['sunset_orange']  # Using more vibrant warning color
    )

    # Enhanced warning status
    embed.add_field(
        name="🎯 Alert Status",
        value="🟡 **ATTENTION REQUIRED** ⚠️",
        inline=True
    )

    # Add warning timestamp
    embed.add_field(
        name="⏰ Alert Time",
        value=f"<t:{int(time.time())}:R>",
        inline=True
    )

    if action_required:
        embed.add_field(
            name="🎯 Required Action",
            value=f"🔧 {action_required}",
            inline=False
        )

    # Add urgency indicator
    embed.add_field(
        name="📊 Priority Level",
        value="🟡 **MEDIUM** - Action recommended",
        inline=False
    )

    return embed

async def log_command_action(interaction, command_name, action_details, success=True):
    """Enhanced logging with better formatting"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    status = "✅ SUCCESS" if success else "❌ FAILED"
    bot_stats['commands_used'] += 1

    log_message = f"[{timestamp}] {status} | /{command_name} | {interaction.user} | {interaction.guild.name if interaction.guild else 'DM'} | {action_details}"
    print(log_message)

# PREMIUM TIER SYSTEM
PREMIUM_TIERS = {
    'basic': {
        'name': '🥉 Premium Basic',
        'color': 0xCD7F32,
        'features': ['No cooldowns', 'Basic priority support', 'Setup command access'],
        'badge': '🥉'
    },
    'pro': {
        'name': '🥈 Premium Pro', 
        'color': 0xC0C0C0,
        'features': ['All Basic features', 'Advanced ticket system', 'Custom badges', 'Priority queue'],
        'badge': '🥈'
    },
    'elite': {
        'name': '🥇 Premium Elite',
        'color': 0xFFD700,
        'features': ['All Pro features', 'Unlimited everything', 'Developer access', 'Custom bot features'],
        'badge': '🥇'
    }
}

premium_tiers = {}  # {guild_id: tier_name}

# BADGE SYSTEM
USER_BADGES = {
    'developer': {'emoji': '🔧', 'name': 'Developer', 'description': 'Bot developer'},
    'early_supporter': {'emoji': '🌟', 'name': 'Early Supporter', 'description': 'Early bot supporter'},
    'premium': {'emoji': '💎', 'name': 'Premium', 'description': 'Premium subscriber'},
    'staff': {'emoji': '👑', 'name': 'Staff', 'description': 'Bot staff member'},
    'partner': {'emoji': '🤝', 'name': 'Partner', 'description': 'Official partner'},
    'contributor': {'emoji': '🎯', 'name': 'Contributor', 'description': 'Code contributor'},
    'bug_hunter': {'emoji': '🐛', 'name': 'Bug Hunter', 'description': 'Found critical bugs'},
    'supporter': {'emoji': '❤️', 'name': 'Supporter', 'description': 'Community supporter'}
}

user_badges = {}  # {user_id: [badge_names]}

# ENHANCED COOLDOWN SYSTEM
HIGH_RISK_COMMANDS = ['setup', 'nickall', 'clear', 'nuke', 'lockdown']
PREMIUM_ONLY_COMMANDS = ['setup', 'antinuke']

def get_user_tier(guild_id):
    """Get premium tier for guild"""
    return premium_tiers.get(guild_id, None)

def check_enhanced_cooldown(user_id, command_name, guild_id=None):
    """Enhanced cooldown check with premium tiers and high-risk commands"""
    tier = get_user_tier(guild_id) if guild_id else None
    
    # Premium tiers bypass cooldowns
    if tier:
        return True
    
    # High-risk commands have longer cooldowns
    if command_name in HIGH_RISK_COMMANDS:
        cooldown_time = 30  # 30 seconds for high-risk
    else:
        cooldown_time = DEFAULT_COOLDOWN
    
    current_time = time.time()
    
    if user_id not in user_cooldowns:
        user_cooldowns[user_id] = {}
    
    if command_name in user_cooldowns[user_id]:
        time_passed = current_time - user_cooldowns[user_id][command_name]
        if time_passed < cooldown_time:
            return False
    
    user_cooldowns[user_id][command_name] = current_time
    return True

def get_enhanced_cooldown_remaining(user_id, command_name):
    """Get remaining cooldown time with enhanced system"""
    if user_id not in user_cooldowns or command_name not in user_cooldowns[user_id]:
        return 0
    
    cooldown_time = 30 if command_name in HIGH_RISK_COMMANDS else DEFAULT_COOLDOWN
    current_time = time.time()
    time_passed = current_time - user_cooldowns[user_id][command_name]
    remaining = cooldown_time - time_passed
    return max(0, remaining)

# HELP COMMAND WITH DROPDOWN MENU
@bot.tree.command(name="help", description="📚 Show all available commands and features")
async def help_command(interaction: discord.Interaction):
    """Improved help system with dropdown menu"""
    
    # Check if user has badges
    user_badge_list = user_badges.get(interaction.user.id, [])
    badge_display = " ".join([USER_BADGES[badge]['emoji'] for badge in user_badge_list if badge in USER_BADGES])
    
    # Get user's premium tier
    tier = get_user_tier(interaction.guild.id) if interaction.guild else None
    tier_display = PREMIUM_TIERS[tier]['badge'] if tier else ""
    
    # Create main embed
    embed = create_embed(
        title=f"📚 Utility Core - Command Help {tier_display}",
        description=f"**Advanced Discord bot with 78+ professional commands!**\n\n{f'**Your Badges:** {badge_display}' if badge_display else ''}\n\nSelect a category from the dropdown below to explore commands.",
        color=PREMIUM_TIERS[tier]['color'] if tier else COLORS['blue']
    )
    
    embed.add_field(
        name="🎯 Quick Stats",
        value=f"**Servers:** {len(bot.guilds):,}\n**Commands:** 78+\n**Uptime:** <t:{int(bot_stats['start_time'])}:R>",
        inline=True
    )
    
    embed.add_field(
        name="💎 Premium Status",
        value=f"**Tier:** {PREMIUM_TIERS[tier]['name'] if tier else '🆓 Free'}\n**Guild:** {'✅ Premium' if tier else '❌ Standard'}",
        inline=True
    )
    
    embed.add_field(
        name="🚀 Quick Links",
        value="• `/ping` - Test bot\n• `/serverinfo` - Server details\n• `/premium` - Upgrade server",
        inline=True
    )
    
    # Create dropdown view
    view = HelpDropdownView(interaction.user.id, tier)
    
    await interaction.response.send_message(embed=embed, view=view)
    await log_command_action(interaction, "help", "Showed main help menu")

# ENHANCED INTERACTIVE UI SYSTEM CLASSES

# Base Template Configuration Classes
class TemplateConfigData:
    """Data class for template configuration"""
    def __init__(self):
        self.name = ""
        self.description = ""
        self.main_roles = ["Admin", "Moderator", "Member", "Muted"]
        self.feature_roles = ["Memes", "Tickets", "Events", "Announcements"]
        self.categories = [
            {"name": "📋 Information", "channels": [{"name": "rules", "type": "text"}, {"name": "announcements", "type": "text"}]},
            {"name": "💬 General", "channels": [{"name": "general", "type": "text"}, {"name": "off-topic", "type": "text"}]},
            {"name": "🎭 Fun", "channels": [{"name": "memes", "type": "text"}, {"name": "media", "type": "text"}]},
            {"name": "🔊 Voice", "channels": [{"name": "General Voice", "type": "voice"}, {"name": "Music", "type": "voice"}]},
            {"name": "🔧 Staff", "channels": [{"name": "staff-chat", "type": "text"}, {"name": "logs", "type": "text"}]}
        ]
        self.enabled_features = {"memes": True, "tickets": True, "welcome": True, "autoroles": True}

class TemplateSetupView(discord.ui.View):
    """Main interactive template setup view"""
    def __init__(self, user_id, guild_id):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.config = TemplateConfigData()
        
    @discord.ui.button(label="📝 Set Name & Description", emoji="📝", style=discord.ButtonStyle.primary, row=0)
    async def set_name_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        modal = TemplateNameModal(self.config)
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="🎭 Edit Roles", emoji="🎭", style=discord.ButtonStyle.secondary, row=0)
    async def edit_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        view = RoleEditView(self.config, self.user_id)
        await interaction.response.send_message("🎭 **Role Configuration**", view=view, ephemeral=True)
        
    @discord.ui.button(label="📑 Edit Channels", emoji="📑", style=discord.ButtonStyle.secondary, row=0)
    async def edit_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        view = ChannelEditView(self.config, self.user_id)
        await interaction.response.send_message("📑 **Channel Configuration**", view=view, ephemeral=True)
        
    @discord.ui.button(label="🔄 Preview", emoji="🔄", style=discord.ButtonStyle.success, row=1)
    async def preview_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        await self.show_preview(interaction)
        
    @discord.ui.button(label="✅ Confirm", emoji="✅", style=discord.ButtonStyle.success, row=1)
    async def confirm_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        
        if not self.config.name or not self.config.description:
            await interaction.response.send_message("❌ Please set name and description first.", ephemeral=True)
            return
            
        await self.save_template(interaction)
        
    @discord.ui.button(label="❌ Cancel", emoji="❌", style=discord.ButtonStyle.danger, row=1)
    async def cancel_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        
        embed = create_info_embed("❌ Template Creation Cancelled", "Template creation has been cancelled.", interaction.user)
        await interaction.response.edit_message(embed=embed, view=None)
        
    async def show_preview(self, interaction):
        """Show template preview"""
        embed = create_embed(
            title=f"🔄 Template Preview: {self.config.name or 'Unnamed Template'}",
            description=f"**Description:** {self.config.description or 'No description'}\n\n**Server Structure Preview:**",
            color=COLORS['info']
        )
        
        # Role preview
        all_roles = self.config.main_roles + self.config.feature_roles
        role_preview = "\n".join([f"• **{role}**" for role in all_roles[:10]])
        if len(all_roles) > 10:
            role_preview += f"\n• ... and {len(all_roles) - 10} more roles"
        embed.add_field(name="🎭 Roles", value=role_preview, inline=True)
        
        # Channel preview  
        channel_count = sum(len(cat["channels"]) for cat in self.config.categories)
        category_preview = "\n".join([f"**{cat['name']}** ({len(cat['channels'])} channels)" for cat in self.config.categories[:5]])
        if len(self.config.categories) > 5:
            category_preview += f"\n... and {len(self.config.categories) - 5} more categories"
        embed.add_field(name="📑 Categories", value=category_preview, inline=True)
        
        # Features preview
        enabled_features = [f"• {feat.title()}" for feat, enabled in self.config.enabled_features.items() if enabled]
        embed.add_field(name="✨ Features", value="\n".join(enabled_features) or "No features enabled", inline=True)
        
        embed.add_field(name="📊 Summary", value=f"**{len(all_roles)}** roles • **{len(self.config.categories)}** categories • **{channel_count}** channels", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    async def save_template(self, interaction):
        """Save template to database"""
        try:
            # Convert config to database format
            roles_data = []
            for i, role in enumerate(self.config.main_roles + self.config.feature_roles):
                roles_data.append({
                    "name": role,
                    "color": 0x7289da if i < len(self.config.main_roles) else 0x99aab5,
                    "permissions": 8 if role == "Admin" else 0,
                    "hoist": True if role in ["Admin", "Moderator"] else False,
                    "mentionable": True,
                    "position": len(self.config.main_roles + self.config.feature_roles) - i
                })
            
            channels_data = []
            for category in self.config.categories:
                channels_data.append({
                    "category": category["name"],
                    "position": 0,
                    "channels": [{"name": ch["name"], "type": ch["type"], "position": i} for i, ch in enumerate(category["channels"])]
                })
            
            # Save to database
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO custom_templates (template_name, description, created_by, roles_data, channels_data, settings_data)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                self.config.name.lower(),
                self.config.description,
                interaction.user.id,
                json.dumps(roles_data),
                json.dumps(channels_data),
                json.dumps(self.config.enabled_features)
            ))
            
            conn.commit()
            conn.close()
            
            embed = create_success_embed(
                "✅ Template Created Successfully!",
                f"Template **{self.config.name}** has been created and is now available globally.",
                interaction.user
            )
            embed.add_field(name="📝 Template Name", value=f"`{self.config.name}`", inline=True)
            embed.add_field(name="📋 Description", value=self.config.description, inline=True)
            embed.add_field(name="🎭 Total Roles", value=str(len(self.config.main_roles + self.config.feature_roles)), inline=True)
            embed.add_field(name="📺 Categories", value=str(len(self.config.categories)), inline=True)
            embed.add_field(name="📊 Total Channels", value=str(sum(len(cat["channels"]) for cat in self.config.categories)), inline=True)
            embed.add_field(name="✨ Features", value=str(sum(1 for f in self.config.enabled_features.values() if f)), inline=True)
            embed.add_field(
                name="🚀 Usage",
                value=f"This template is now available in `/setup` command:\n`/setup advanced {self.config.name.lower()}`",
                inline=False
            )
            
            await interaction.response.edit_message(embed=embed, view=None)
            
        except Exception as e:
            embed = create_error_embed("❌ Template Creation Failed", f"Could not save template: {str(e)}")
            await interaction.response.edit_message(embed=embed, view=None)

class TemplateNameModal(discord.ui.Modal, title="📝 Template Name & Description"):
    """Modal for setting template name and description"""
    def __init__(self, config):
        super().__init__()
        self.config = config
        
    name = discord.ui.TextInput(
        label="Template Name",
        placeholder="Enter a unique name for your template...",
        min_length=3,
        max_length=30,
        required=True
    )
    
    description = discord.ui.TextInput(
        label="Description", 
        placeholder="Describe what this template creates...",
        min_length=10,
        max_length=200,
        required=True,
        style=discord.TextStyle.paragraph
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        # Check if template name already exists
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM custom_templates WHERE template_name = ?', (self.name.value.lower(),))
        if cursor.fetchone():
            conn.close()
            await interaction.response.send_message("❌ A template with that name already exists!", ephemeral=True)
            return
        conn.close()
        
        self.config.name = self.name.value
        self.config.description = self.description.value
        
        embed = create_success_embed(
            "✅ Name & Description Set",
            f"**Name:** {self.config.name}\n**Description:** {self.config.description}",
            interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class RoleEditView(discord.ui.View):
    """View for editing template roles"""
    def __init__(self, config, user_id):
        super().__init__(timeout=300)
        self.config = config
        self.user_id = user_id
        
    @discord.ui.select(
        placeholder="🎭 Select roles to edit...",
        options=[
            discord.SelectOption(label="Main Roles", description="Admin, Moderator, Member roles", emoji="👑", value="main"),
            discord.SelectOption(label="Feature Roles", description="Optional feature-based roles", emoji="✨", value="feature")
        ]
    )
    async def role_category_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
            
        category = select.values[0]
        if category == "main":
            modal = RoleEditModal(self.config, "main")
        else:
            modal = RoleEditModal(self.config, "feature")
        await interaction.response.send_modal(modal)

class RoleEditModal(discord.ui.Modal, title="🎭 Edit Roles"):
    """Modal for editing role lists"""
    def __init__(self, config, role_type):
        super().__init__()
        self.config = config
        self.role_type = role_type
        
        if role_type == "main":
            self.roles_input.default = ", ".join(config.main_roles)
            self.roles_input.label = "Main Roles (Admin, Mod, Member, etc.)"
        else:
            self.roles_input.default = ", ".join(config.feature_roles)
            self.roles_input.label = "Feature Roles (Optional roles)"
        
    roles_input = discord.ui.TextInput(
        label="Roles (comma-separated)",
        placeholder="Admin, Moderator, Member, Muted",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        roles = [role.strip() for role in self.roles_input.value.split(",") if role.strip()]
        
        if self.role_type == "main":
            self.config.main_roles = roles
            role_type_display = "Main Roles"
        else:
            self.config.feature_roles = roles
            role_type_display = "Feature Roles"
            
        embed = create_success_embed(
            f"✅ {role_type_display} Updated",
            f"**{len(roles)}** roles configured:\n{', '.join(roles[:10])}{'...' if len(roles) > 10 else ''}",
            interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ChannelEditView(discord.ui.View):
    """View for editing template channels and categories"""
    def __init__(self, config, user_id):
        super().__init__(timeout=300)
        self.config = config
        self.user_id = user_id
        
    @discord.ui.select(
        placeholder="📑 Select category to edit...",
        options=[
            discord.SelectOption(label=cat["name"], description=f"{len(cat['channels'])} channels", value=str(i))
            for i, cat in enumerate(TemplateConfigData().categories[:25])  # Discord limit
        ]
    )
    async def category_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
            
        category_index = int(select.values[0])
        modal = CategoryEditModal(self.config, category_index)
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="➕ Add Category", emoji="➕", style=discord.ButtonStyle.success, row=1)
    async def add_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        modal = AddCategoryModal(self.config)
        await interaction.response.send_modal(modal)

class CategoryEditModal(discord.ui.Modal, title="📑 Edit Category"):
    """Modal for editing individual categories"""
    def __init__(self, config, category_index):
        super().__init__()
        self.config = config
        self.category_index = category_index
        
        category = config.categories[category_index]
        self.category_name.default = category["name"]
        
        channels_text = ""
        for ch in category["channels"]:
            channels_text += f"{ch['name']} ({ch['type']}), "
        self.channels_input.default = channels_text.rstrip(", ")
        
    category_name = discord.ui.TextInput(
        label="Category Name",
        placeholder="📋 Information",
        max_length=50,
        required=True
    )
    
    channels_input = discord.ui.TextInput(
        label="Channels (format: name (type), name2 (voice))",
        placeholder="rules (text), announcements (text), voice-chat (voice)",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        # Parse channels
        channels = []
        for channel_def in self.channels_input.value.split(","):
            channel_def = channel_def.strip()
            if "(" in channel_def and ")" in channel_def:
                name = channel_def.split("(")[0].strip()
                channel_type = channel_def.split("(")[1].split(")")[0].strip()
                if channel_type in ["text", "voice"]:
                    channels.append({"name": name, "type": channel_type})
        
        self.config.categories[self.category_index] = {
            "name": self.category_name.value,
            "channels": channels
        }
        
        embed = create_success_embed(
            "✅ Category Updated",
            f"**{self.category_name.value}** configured with **{len(channels)}** channels",
            interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class AddCategoryModal(discord.ui.Modal, title="➕ Add New Category"):
    """Modal for adding new categories"""
    def __init__(self, config):
        super().__init__()
        self.config = config
        
    category_name = discord.ui.TextInput(
        label="Category Name",
        placeholder="🎮 Gaming",
        max_length=50,
        required=True
    )
    
    channels_input = discord.ui.TextInput(
        label="Channels (format: name (type), name2 (voice))",
        placeholder="gaming (text), gaming-voice (voice)",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        # Parse channels
        channels = []
        for channel_def in self.channels_input.value.split(","):
            channel_def = channel_def.strip()
            if "(" in channel_def and ")" in channel_def:
                name = channel_def.split("(")[0].strip()
                channel_type = channel_def.split("(")[1].split(")")[0].strip()
                if channel_type in ["text", "voice"]:
                    channels.append({"name": name, "type": channel_type})
        
        new_category = {
            "name": self.category_name.value,
            "channels": channels
        }
        self.config.categories.append(new_category)
        
        embed = create_success_embed(
            "✅ Category Added",
            f"**{self.category_name.value}** added with **{len(channels)}** channels",
            interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Enhanced Setup Configuration Views
class SetupConfigView(discord.ui.View):
    """Interactive setup configuration panel"""
    def __init__(self, user_id, guild_id):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.setup_mode = "advanced"
        self.template = None
        self.config_data = {}
        
    @discord.ui.select(
        placeholder="🚀 Choose setup mode...",
        options=[
            discord.SelectOption(label="🚀 Advanced Setup", description="100+ roles, full features", emoji="🚀", value="advanced"),
            discord.SelectOption(label="⚡ Basic Setup", description="Essential roles only", emoji="⚡", value="basic"),
            discord.SelectOption(label="🎨 Custom Template", description="Use a saved template", emoji="🎨", value="template")
        ]
    )
    async def setup_mode_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
            
        self.setup_mode = select.values[0]
        
        if self.setup_mode == "template":
            view = TemplateSelectView(self.user_id, self)
            await interaction.response.send_message("🎨 **Select Template**", view=view, ephemeral=True)
        else:
            embed = create_success_embed(
                f"✅ Setup Mode: {select.values[0].title()}",
                f"Selected setup mode: **{select.options[0].label if select.values[0] == 'advanced' else select.options[1].label}**",
                interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @discord.ui.button(label="🔄 Preview Setup", emoji="🔄", style=discord.ButtonStyle.success, row=1)
    async def preview_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        await self.show_setup_preview(interaction)
        
    @discord.ui.button(label="⚠️ Start Setup", emoji="⚠️", style=discord.ButtonStyle.danger, row=1)
    async def start_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        await self.confirm_setup(interaction)
        
    async def show_setup_preview(self, interaction):
        """Show what the setup will create"""
        embed = create_embed(
            title=f"🔄 Setup Preview: {self.setup_mode.title()} Mode",
            description="**This setup will create the following server structure:**",
            color=COLORS['warning']
        )
        
        if self.setup_mode == "advanced":
            embed.add_field(
                name="🎭 Roles (15+)",
                value="• **Admin** (Administrator)\n• **Moderator** (Manage Server)\n• **Helper** (Manage Messages)\n• **Member** (Default)\n• **Muted** (Restricted)\n• VIP, Verified, Bot, Events...",
                inline=True
            )
            embed.add_field(
                name="📑 Categories (6+)",
                value="• 📋 **Information**\n• 💬 **General Chat**\n• 🎭 **Entertainment**\n• 🔊 **Voice Channels**\n• 🔧 **Staff Area**\n• 📊 **Logs**",
                inline=True
            )
            embed.add_field(
                name="✨ Features",
                value="• Welcome/Goodbye System\n• Auto-Roles\n• Ticket System\n• AutoMod Protection\n• Anti-Nuke System\n• Logging",
                inline=True
            )
        elif self.setup_mode == "basic":
            embed.add_field(
                name="🎭 Roles (5)",
                value="• **Admin**\n• **Moderator** \n• **Member**\n• **Muted**\n• **Bot**",
                inline=True
            )
            embed.add_field(
                name="📑 Categories (3)",
                value="• 📋 **Information**\n• 💬 **General**\n• 🔊 **Voice**",
                inline=True
            )
            embed.add_field(
                name="✨ Features",
                value="• Basic Welcome System\n• Essential Moderation\n• Auto-Roles",
                inline=True
            )
        
        embed.add_field(
            name="⚠️ Important Warning",
            value="**This will DELETE all existing channels and roles before creating new ones!**\nThis action is IRREVERSIBLE.",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    async def confirm_setup(self, interaction):
        """Final confirmation before destructive setup"""
        embed = create_embed(
            title="⚠️ DANGER: Server Rebuild Confirmation",
            description="**ARE YOU ABSOLUTELY SURE?**\n\nThis will **DELETE ALL** existing channels and roles, then rebuild the entire server structure.\n\n**THIS ACTION IS IRREVERSIBLE!**",
            color=COLORS['error']
        )
        
        view = FinalSetupConfirmView(self.user_id, self.setup_mode, self.template)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class FinalSetupConfirmView(discord.ui.View):
    """Final confirmation view for destructive operations"""
    def __init__(self, user_id, setup_mode, template=None):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.setup_mode = setup_mode
        self.template = template
        
    @discord.ui.button(label="✅ YES, REBUILD SERVER", style=discord.ButtonStyle.danger)
    async def confirm_rebuild(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can confirm this action.", ephemeral=True)
            return
            
        embed = create_success_embed(
            "🚀 Server Rebuild Starting...",
            "The server rebuild process is starting. This may take several minutes.\n\n**Do not close Discord during this process!**",
            interaction.user
        )
        await interaction.response.edit_message(embed=embed, view=None)
        
        # Here you would call the actual setup function
        # await perform_server_setup(interaction, self.setup_mode, self.template)
        
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_rebuild(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
            
        embed = create_info_embed("❌ Setup Cancelled", "Server rebuild has been cancelled. No changes were made.", interaction.user)
        await interaction.response.edit_message(embed=embed, view=None)

class TemplateSelectView(discord.ui.View):
    """View for selecting custom templates"""
    def __init__(self, user_id, parent_view):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.parent_view = parent_view
        self.add_template_dropdown()
        
    def add_template_dropdown(self):
        """Add template selection dropdown"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT template_name, description FROM custom_templates LIMIT 20')
            templates = cursor.fetchall()
            conn.close()
            
            options = [
                discord.SelectOption(label="💻 Developer Community", description="Programming & tech community setup", value="developer"),
                discord.SelectOption(label="🌊 Aquaris", description="Premium aquatic-themed server", value="aquaris")
            ]
            
            for template_name, description in templates:
                options.append(discord.SelectOption(
                    label=f"🎨 {template_name.title()}",
                    description=description[:100],
                    value=template_name
                ))
                
            if options:
                dropdown = TemplateDropdown(options, self.user_id, self.parent_view)
                self.add_item(dropdown)
                
        except Exception as e:
            print(f"Failed to load templates: {e}")

class TemplateDropdown(discord.ui.Select):
    """Dropdown for template selection"""
    def __init__(self, options, user_id, parent_view):
        super().__init__(placeholder="🎨 Choose a template...", options=options)
        self.user_id = user_id
        self.parent_view = parent_view
        
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
            
        self.parent_view.template = self.values[0]
        embed = create_success_embed(
            "✅ Template Selected",
            f"Selected template: **{self.values[0].title()}**",
            interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Enhanced Ticket System UI Classes
class TicketSetupConfigView(discord.ui.View):
    """Interactive ticket system setup panel"""
    def __init__(self, user_id, guild_id):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.config = {
            "log_channel": None,
            "staff_roles": [],
            "categories_enabled": True,
            "max_tickets": 3,
            "welcome_message": "Hello {user.mention}! Thank you for creating a ticket. Please describe your issue and a staff member will assist you shortly.",
            "embed_color": COLORS['blue']
        }
        
    @discord.ui.button(label="📍 Set Log Channel", emoji="📍", style=discord.ButtonStyle.primary, row=0)
    async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        view = ChannelSelectView(self.user_id, self.config, "log_channel", interaction.guild)
        await interaction.response.send_message("📍 **Select Log Channel**", view=view, ephemeral=True)
        
    @discord.ui.button(label="👥 Add Staff Roles", emoji="👥", style=discord.ButtonStyle.secondary, row=0)
    async def add_staff_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        view = RoleSelectView(self.user_id, self.config, "staff_roles", interaction.guild)
        await interaction.response.send_message("👥 **Select Staff Roles**", view=view, ephemeral=True)
        
    @discord.ui.button(label="⚙️ Configure Settings", emoji="⚙️", style=discord.ButtonStyle.secondary, row=0)
    async def configure_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        modal = TicketSettingsModal(self.config)
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="🔄 Preview System", emoji="🔄", style=discord.ButtonStyle.success, row=1)
    async def preview_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        await self.show_ticket_preview(interaction)
        
    @discord.ui.button(label="✅ Apply Setup", emoji="✅", style=discord.ButtonStyle.success, row=1)
    async def apply_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        await self.apply_ticket_setup(interaction)
        
    async def show_ticket_preview(self, interaction):
        """Show ticket system preview"""
        embed = create_embed(
            title="🔄 Ticket System Preview",
            description="**Here's how your ticket system will look:**",
            color=COLORS['info']
        )
        
        # System overview
        log_channel_name = f"<#{self.config['log_channel']}>" if self.config['log_channel'] else "❌ Not set"
        staff_role_mentions = []
        if self.config['staff_roles']:
            for role_id in self.config['staff_roles']:
                staff_role_mentions.append(f"<@&{role_id}>")
        staff_display = ", ".join(staff_role_mentions) if staff_role_mentions else "❌ No staff roles"
        
        embed.add_field(
            name="⚙️ System Configuration",
            value=f"**Log Channel:** {log_channel_name}\n**Staff Roles:** {staff_display}\n**Max Tickets:** {self.config['max_tickets']} per user\n**Categories:** {'✅ Enabled' if self.config['categories_enabled'] else '❌ Disabled'}",
            inline=False
        )
        
        # Ticket types preview
        ticket_types = "🆘 **General Support**\n🐛 **Bug Report**\n✨ **Feature Request**\n🤝 **Partnership**\n📋 **Staff Application**\n⚠️ **Report User**\n🔓 **Ban Appeal**\n❓ **Other**"
        embed.add_field(
            name="🎫 Available Ticket Types (8)",
            value=ticket_types,
            inline=True
        )
        
        # Categories preview
        if self.config['categories_enabled']:
            categories_preview = "🆘 **General Support Tickets**\n🐛 **Bug Report Tickets**\n✨ **Feature Request Tickets**\n🤝 **Partnership Tickets**\n📋 **Staff Application Tickets**\n⚠️ **Report User Tickets**\n🔓 **Ban Appeal Tickets**\n❓ **Other Tickets**"
            embed.add_field(
                name="📑 Categories (8)",
                value=categories_preview,
                inline=True
            )
        
        # Welcome message preview
        preview_message = self.config['welcome_message'].replace("{user.mention}", interaction.user.mention)
        embed.add_field(
            name="💬 Welcome Message Preview",
            value=preview_message[:200] + ("..." if len(preview_message) > 200 else ""),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    async def apply_ticket_setup(self, interaction):
        """Apply the ticket system configuration"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            guild_id = interaction.guild.id
            
            # Initialize ticket system if not exists
            if guild_id not in ticket_systems:
                ticket_systems[guild_id] = init_default_ticket_system(guild_id)
                ticket_counter[guild_id] = 0

            system = ticket_systems[guild_id]
            
            # Apply configuration
            system.enabled = True
            system.log_channel_id = self.config['log_channel']
            system.staff_roles = self.config['staff_roles']
            system.max_tickets_per_user = self.config['max_tickets']
            system.welcome_message = self.config['welcome_message']
            system.embed_color = self.config['embed_color']
            
            setup_steps = []
            
            # Create categories if enabled
            if self.config['categories_enabled']:
                categories_created = 0
                for ticket_type in system.ticket_types.values():
                    try:
                        existing_category = discord.utils.get(interaction.guild.categories, name=ticket_type.category_name)
                        if not existing_category:
                            category = await interaction.guild.create_category(
                                name=ticket_type.category_name,
                                overwrites={
                                    interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                                    interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                                }
                            )
                            ticket_type.category_id = category.id
                            categories_created += 1
                        else:
                            ticket_type.category_id = existing_category.id
                    except Exception as e:
                        print(f"Failed to create category {ticket_type.category_name}: {e}")
                
                setup_steps.append(f"✅ Created **{categories_created}** ticket categories")
            
            setup_steps.append("✅ Ticket system enabled")
            if self.config['log_channel']:
                setup_steps.append(f"✅ Log channel: <#{self.config['log_channel']}>")
            if self.config['staff_roles']:
                setup_steps.append(f"✅ Staff roles: {len(self.config['staff_roles'])} configured")
            
            embed = create_success_embed(
                "🎫 Ticket System Setup Complete!",
                "Your advanced ticket system is now ready to use!",
                interaction.user
            )
            embed.add_field(
                name="📋 Configuration Applied",
                value="\n".join(setup_steps),
                inline=False
            )
            embed.add_field(
                name="🎫 Available Types",
                value=f"**{len(system.ticket_types)}** ticket types ready",
                inline=True
            )
            embed.add_field(
                name="⚙️ System Status",
                value="🟢 **ENABLED**",
                inline=True
            )
            embed.add_field(
                name="📋 Next Steps",
                value="Use `/ticket_panel` to create ticket panels in your channels",
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
            await log_command_action(interaction, "ticket_setup", f"Interactive setup completed with {len(setup_steps)} configurations")
            
        except Exception as e:
            embed = create_error_embed("Setup Failed", f"Could not apply ticket setup: {str(e)}")
            await interaction.followup.send(embed=embed)

class ChannelSelectView(discord.ui.View):
    """View for selecting channels"""
    def __init__(self, user_id, config, config_key, guild=None):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.config = config
        self.config_key = config_key
        self.guild = guild
        
        # Create channel options if guild is provided
        if guild:
            options = []
            for channel in guild.text_channels[:25]:  # Discord limit
                options.append(discord.SelectOption(
                    label=channel.name,
                    description=f"#{channel.name}",
                    value=str(channel.id)
                ))
                
            if options:
                dropdown = ChannelDropdown(options, user_id, config, config_key)
                self.add_item(dropdown)
                
    async def on_timeout(self):
        # Disable all components when view times out
        for item in self.children:
            item.disabled = True

class ChannelDropdown(discord.ui.Select):
    """Dropdown for channel selection"""
    def __init__(self, options, user_id, config, config_key):
        super().__init__(placeholder="📍 Select a channel...", options=options)
        self.user_id = user_id
        self.config = config
        self.config_key = config_key
        
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
            
        channel_id = int(self.values[0])
        self.config[self.config_key] = channel_id
        
        embed = create_success_embed(
            "✅ Channel Selected",
            f"Selected channel: <#{channel_id}>",
            interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class RoleSelectView(discord.ui.View):
    """View for selecting roles"""
    def __init__(self, user_id, config, config_key, guild=None):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.config = config
        self.config_key = config_key
        self.guild = guild
        
        # Create role options if guild is provided
        if guild:
            options = []
            for role in guild.roles[:25]:  # Discord limit
                if role.name != "@everyone" and not role.managed:
                    options.append(discord.SelectOption(
                        label=role.name,
                        description=f"@{role.name}",
                        value=str(role.id)
                    ))
                
            if options:
                dropdown = RoleDropdown(options, user_id, config, config_key)
                self.add_item(dropdown)
                
    async def on_timeout(self):
        # Disable all components when view times out
        for item in self.children:
            item.disabled = True

class RoleDropdown(discord.ui.Select):
    """Dropdown for role selection (multi-select)"""
    def __init__(self, options, user_id, config, config_key):
        super().__init__(placeholder="👥 Select staff roles...", options=options, max_values=min(len(options), 10))
        self.user_id = user_id
        self.config = config
        self.config_key = config_key
        
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
            
        role_ids = [int(value) for value in self.values]
        self.config[self.config_key] = role_ids
        
        role_mentions = [f"<@&{role_id}>" for role_id in role_ids]
        embed = create_success_embed(
            "✅ Staff Roles Selected",
            f"Selected **{len(role_ids)}** staff roles:\n{', '.join(role_mentions)}",
            interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class TicketSettingsModal(discord.ui.Modal, title="⚙️ Ticket System Settings"):
    """Modal for configuring ticket system settings"""
    def __init__(self, config):
        super().__init__()
        self.config = config
        
        self.max_tickets.default = str(config['max_tickets'])
        self.welcome_message.default = config['welcome_message']
        
    max_tickets = discord.ui.TextInput(
        label="Max Tickets Per User",
        placeholder="3",
        min_length=1,
        max_length=2,
        required=True
    )
    
    welcome_message = discord.ui.TextInput(
        label="Welcome Message",
        placeholder="Hello {user.mention}! Thank you for creating a ticket...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            max_tickets = int(self.max_tickets.value)
            if max_tickets < 1 or max_tickets > 10:
                await interaction.response.send_message("❌ Max tickets must be between 1-10!", ephemeral=True)
                return
                
            self.config['max_tickets'] = max_tickets
            self.config['welcome_message'] = self.welcome_message.value
            
            embed = create_success_embed(
                "✅ Settings Updated",
                f"**Max Tickets:** {max_tickets} per user\n**Welcome Message:** Updated",
                interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.response.send_message("❌ Max tickets must be a valid number!", ephemeral=True)

# Enhanced Welcome System UI Classes  
class WelcomeSetupConfigView(discord.ui.View):
    """Interactive welcome system setup panel"""
    def __init__(self, user_id, guild_id):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.config = {
            "channel": None,
            "message": "Welcome to {guild.name}, {user.mention}! 🎉",
            "embed_title": "Welcome!",
            "embed_description": "Welcome to our amazing server!",
            "embed_color": COLORS['success'],
            "dm_enabled": False
        }
        
    @discord.ui.button(label="📍 Set Channel", emoji="📍", style=discord.ButtonStyle.primary, row=0)
    async def set_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        view = ChannelSelectView(self.user_id, self.config, "channel", interaction.guild)
        await interaction.response.send_message("📍 **Select Welcome Channel**", view=view, ephemeral=True)
        
    @discord.ui.button(label="📝 Edit Message", emoji="📝", style=discord.ButtonStyle.secondary, row=0)
    async def edit_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        modal = WelcomeMessageModal(self.config)
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="🎨 Customize Embed", emoji="🎨", style=discord.ButtonStyle.secondary, row=0)
    async def customize_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        modal = WelcomeEmbedModal(self.config)
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="🔄 Preview", emoji="🔄", style=discord.ButtonStyle.success, row=1)
    async def preview_welcome(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        await self.show_welcome_preview(interaction)
        
    @discord.ui.button(label="✅ Apply Setup", emoji="✅", style=discord.ButtonStyle.success, row=1)
    async def apply_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can interact with this panel.", ephemeral=True)
            return
        
        if not self.config['channel']:
            await interaction.response.send_message("❌ Please select a welcome channel first!", ephemeral=True)
            return
            
        await self.apply_welcome_setup(interaction)
        
    async def show_welcome_preview(self, interaction):
        """Show welcome message preview"""
        if not self.config['channel']:
            await interaction.response.send_message("❌ Please select a channel first to preview the welcome message!", ephemeral=True)
            return
            
        # Create preview embed exactly as it would appear
        welcome_embed = discord.Embed(
            title=self.config['embed_title'],
            description=replace_variables(self.config['embed_description'], user=interaction.user, guild=interaction.guild),
            color=self.config['embed_color'],
            timestamp=discord.utils.utcnow()
        )
        
        welcome_embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)
        welcome_embed.add_field(name="👤 Member", value=interaction.user.mention, inline=True)
        welcome_embed.add_field(name="📊 Member Count", value=interaction.guild.member_count, inline=True)
        welcome_embed.add_field(name="🧪 Preview Mode", value="This is a preview", inline=True)
        welcome_embed.set_footer(text=f"Welcome System Preview • {interaction.guild.name}")
        
        preview_message = replace_variables(self.config['message'], user=interaction.user, guild=interaction.guild)
        
        preview_embed = create_embed(
            title="🔄 Welcome Message Preview",
            description=f"**Channel:** <#{self.config['channel']}>\n**Message:** {preview_message}",
            color=COLORS['info']
        )
        
        await interaction.response.send_message(f"📍 **Preview in <#{self.config['channel']}>:**\n{preview_message}", embed=welcome_embed, ephemeral=True)
        
    async def apply_welcome_setup(self, interaction):
        """Apply welcome system configuration"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO guild_settings
                (guild_id, welcome_enabled, welcome_channel_id, welcome_message, welcome_embed_title, welcome_embed_description, welcome_embed_color, welcome_dm_enabled)
                VALUES (?, 1, ?, ?, ?, ?, ?, ?)
            ''', (
                interaction.guild.id, 
                self.config['channel'], 
                self.config['message'], 
                self.config['embed_title'], 
                self.config['embed_description'], 
                self.config['embed_color'],
                1 if self.config['dm_enabled'] else 0
            ))

            conn.commit()
            conn.close()

            embed = create_success_embed(
                "👋 Welcome System Setup Complete!",
                f"Welcome messages will now be sent to <#{self.config['channel']}>",
                interaction.user
            )
            embed.add_field(name="💬 Message", value=self.config['message'][:100] + ("..." if len(self.config['message']) > 100 else ""), inline=False)
            embed.add_field(name="🎨 Embed Color", value=f"#{self.config['embed_color']:06x}", inline=True)
            embed.add_field(name="💌 DM Welcome", value="✅ Enabled" if self.config['dm_enabled'] else "❌ Disabled", inline=True)
            embed.add_field(name="📋 Variables Available", value="`{user.mention}`, `{guild.name}`, `{guild.membercount}`, `{user.name}`", inline=False)

            await interaction.followup.send(embed=embed)
            await log_command_action(interaction, "welcomesetup", f"Interactive welcome setup in #{bot.get_channel(self.config['channel']).name}")
            
        except Exception as e:
            embed = create_error_embed("Setup Failed", f"Could not apply welcome setup: {str(e)}")
            await interaction.followup.send(embed=embed)

class WelcomeMessageModal(discord.ui.Modal, title="📝 Welcome Message"):
    """Modal for editing welcome message"""
    def __init__(self, config):
        super().__init__()
        self.config = config
        
        self.message.default = config['message']
        
    message = discord.ui.TextInput(
        label="Welcome Message",
        placeholder="Welcome to {guild.name}, {user.mention}! 🎉",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        self.config['message'] = self.message.value
        
        preview = replace_variables(self.message.value, user=interaction.user, guild=interaction.guild)
        embed = create_success_embed(
            "✅ Welcome Message Updated",
            f"**Preview:** {preview[:150]}{'...' if len(preview) > 150 else ''}",
            interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class WelcomeEmbedModal(discord.ui.Modal, title="🎨 Welcome Embed Customization"):
    """Modal for customizing welcome embed"""
    def __init__(self, config):
        super().__init__()
        self.config = config
        
        self.embed_title.default = config['embed_title']
        self.embed_description.default = config['embed_description']
        
    embed_title = discord.ui.TextInput(
        label="Embed Title",
        placeholder="Welcome!",
        max_length=100,
        required=True
    )
    
    embed_description = discord.ui.TextInput(
        label="Embed Description",
        placeholder="Welcome to our amazing server!",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )
    
    embed_color = discord.ui.TextInput(
        label="Embed Color (hex like #ff0000 or color name)",
        placeholder="green",
        max_length=20,
        required=False
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        self.config['embed_title'] = self.embed_title.value
        self.config['embed_description'] = self.embed_description.value
        
        # Parse color
        if self.embed_color.value:
            if self.embed_color.value.startswith("#"):
                try:
                    self.config['embed_color'] = int(self.embed_color.value[1:], 16)
                except:
                    self.config['embed_color'] = COLORS['success']
            else:
                self.config['embed_color'] = COLORS.get(self.embed_color.value.lower(), COLORS['success'])
        
        embed = create_success_embed(
            "✅ Embed Customized",
            f"**Title:** {self.embed_title.value}\n**Description:** {self.embed_description.value[:100]}{'...' if len(self.embed_description.value) > 100 else ''}",
            interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

# HELP SYSTEM CLASSES
class HelpDropdownView(discord.ui.View):
    def __init__(self, user_id, tier=None):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.tier = tier
        self.add_item(HelpCategoryDropdown(tier))
        
    async def on_timeout(self):
        # Disable all components when view times out
        for item in self.children:
            item.disabled = True

class HelpCategoryDropdown(discord.ui.Select):
    def __init__(self, tier=None):
        self.tier = tier
        
        options = [
            discord.SelectOption(
                label="🛡️ Moderation",
                description="Ban, kick, timeout, and server moderation tools",
                emoji="🛡️",
                value="moderation"
            ),
            discord.SelectOption(
                label="🚫 AutoMod", 
                description="Automated moderation and word filtering",
                emoji="🚫",
                value="automod"
            ),
            discord.SelectOption(
                label="⚙️ Server Management",
                description="Setup, configuration, and admin tools",
                emoji="⚙️", 
                value="admin"
            ),
            discord.SelectOption(
                label="🎭 Role Management",
                description="Create, assign, and manage server roles",
                emoji="🎭",
                value="roles"
            ),
            discord.SelectOption(
                label="ℹ️ Information",
                description="Server info, user profiles, and statistics", 
                emoji="ℹ️",
                value="info"
            ),
            discord.SelectOption(
                label="🎵 Music & Media",
                description="Music commands and media tools",
                emoji="🎵",
                value="music"
            ),
            discord.SelectOption(
                label="🎮 Fun & Games",
                description="Entertainment commands and mini-games",
                emoji="🎮", 
                value="fun"
            ),
            discord.SelectOption(
                label="💎 Premium",
                description="Premium-only features and commands",
                emoji="💎",
                value="premium"
            ),
            discord.SelectOption(
                label="🛡️ Anti-Nuke",
                description="Advanced server protection and backup system",
                emoji="🛡️",
                value="antinuke"
            )
        ]
        
        super().__init__(placeholder="🔽 Select a command category...", options=options, min_values=1, max_values=1)
    
    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        
        if category == "moderation":
            embed = create_embed(
                title="🛡️ Moderation Commands",
                description="**Server moderation and member management tools**",
                color=COLORS['blue']
            )
            embed.add_field(
                name="👮 Basic Moderation",
                value="`/ban` - Ban a user\n`/kick` - Kick a user\n`/timeout` - Timeout a user\n`/warn` - Warn a user\n`/unban` - Unban a user",
                inline=True
            )
            embed.add_field(
                name="🧹 Message Management", 
                value="`/clear` - Delete messages\n`/purge` - Mass delete messages\n`/slowmode` - Set channel slowmode",
                inline=True
            )
            embed.add_field(
                name="📝 Advanced Tools",
                value="`/massban` - Ban multiple users\n`/masskick` - Kick multiple users\n`/lockdown` - Lock server channels",
                inline=True
            )
            
        elif category == "antinuke":
            embed = create_embed(
                title="🛡️ Advanced Anti-Nuke Protection",
                description="**Enterprise-grade server protection system**",
                color=COLORS['success']
            )
            embed.add_field(
                name="🛡️ Core Protection",
                value="`/antinuke enable` - Activate protection\n`/antinuke disable` - Deactivate protection\n`/antinuke status` - View protection status\n`/antinuke activity` - Live threat monitor",
                inline=False
            )
            embed.add_field(
                name="👥 Whitelist Management",
                value="`/whitelist add` - Add trusted user\n`/whitelist remove` - Remove user\n`/whitelist list` - View all trusted users\n`/whitelist clear` - Clear all users",
                inline=False
            )
            embed.add_field(
                name="💾 Backup & Restore",
                value="`/antinuke backup_enable` - Enable auto-backup\n`/antinuke backup_now` - Manual backup\n`/denuke` - **EMERGENCY SERVER RESTORE**",
                inline=False
            )
            embed.add_field(
                name="⚡ Advanced Features",
                value="• **Real-time raid detection**\n• **Owner DM notifications**\n• **Automatic permission removal**\n• **24/7 activity monitoring**\n• **Premium backup intervals**",
                inline=False
            )
            
        elif category == "info":
            embed = create_embed(
                title="ℹ️ Information Commands",
                description="**Server and user information tools**",
                color=COLORS['info']
            )
            embed.add_field(
                name="🏢 Server Info",
                value="`/serverinfo` - Server details\n`/channels` - Channel list\n`/roles` - Role information\n`/emojis` - Server emojis",
                inline=True
            )
            embed.add_field(
                name="👤 User Info",
                value="`/userinfo` - User profile\n`/avatar` - User avatar\n`/permissions` - User permissions\n`/activity` - User activity",
                inline=True
            )
            
        elif category == "automod":
            embed = create_embed(
                title="🚫 AutoMod Commands",
                description="**Automated moderation and content filtering**",
                color=COLORS['warning']
            )
            embed.add_field(
                name="📝 Word Management",
                value="`/banword` - Add word to filter\n`/removeword` - Remove banned word\n`/listbannedwords` - View all banned words",
                inline=True
            )
            embed.add_field(
                name="🛡️ AutoMod Control",
                value="`/automod status` - View system status\n`/automod list` - List all rules\n`/automod clear` - Clear all rules\n`/automod common` - Apply preset filters",
                inline=True
            )
            embed.add_field(
                name="🎯 Common Presets",
                value="• 🤬 Profanity Filter\n• 💊 Drug References\n• 🔞 Sexual Content\n• ⚔️ Violence/Threats\n• 🏴‍☠️ Piracy/Illegal\n• 💰 Scam/Spam",
                inline=False
            )
            
        elif category == "admin":
            embed = create_embed(
                title="⚙️ Server Management Commands",
                description="**Setup, configuration, and admin tools**",
                color=COLORS['purple']
            )
            embed.add_field(
                name="🚀 Server Setup",
                value="`/setup` - Interactive server rebuild\n`/create_template` - Interactive template creator\n`/enablecommunity` - Enable community features",
                inline=True
            )
            embed.add_field(
                name="🔧 Configuration",
                value="`/prefix` - Change command prefix\n`/welcomesetup` - Interactive welcome setup\n`/ticket_setup` - Interactive ticket setup\n`/autorole` - Configure auto roles",
                inline=True
            )
            embed.add_field(
                name="📊 Management",
                value="`/variables` - View all variables\n`/mediaonly` - Configure media channels\n`/automeme` - Setup auto memes",
                inline=True
            )
            
        elif category == "roles":
            embed = create_embed(
                title="🎭 Role Management Commands",
                description="**Create, assign, and manage server roles**",
                color=COLORS['aqua']
            )
            embed.add_field(
                name="🎨 Role Creation",
                value="`/createrole` - Create new role\n`/deleterole` - Delete existing role\n`/editrole` - Modify role properties",
                inline=True
            )
            embed.add_field(
                name="👥 Role Assignment",
                value="`/addrole` - Give role to user\n`/removerole` - Remove role from user\n`/massrole` - Bulk role assignment",
                inline=True
            )
            embed.add_field(
                name="⚙️ Auto Roles",
                value="`/autorole enable` - Enable auto roles\n`/autorole add` - Add auto role\n`/autorole remove` - Remove auto role\n`/autorole list` - View auto roles",
                inline=True
            )
            
        elif category == "music":
            embed = create_embed(
                title="🎵 Music & Media Commands",
                description="**Music commands and media tools**",
                color=COLORS['pink']
            )
            embed.add_field(
                name="🎶 Music Playback",
                value="`/play` - Play music from URL\n`/pause` - Pause current track\n`/resume` - Resume playback\n`/stop` - Stop music and disconnect",
                inline=True
            )
            embed.add_field(
                name="📋 Queue Management",
                value="`/queue` - View music queue\n`/skip` - Skip current track\n`/shuffle` - Shuffle queue\n`/clear_queue` - Clear all queued songs",
                inline=True
            )
            embed.add_field(
                name="📱 Media Tools",
                value="`/meme` - Generate random meme\n`/automeme` - Setup auto memes\n`/mediaonly` - Configure media channels",
                inline=True
            )
            
        elif category == "fun":
            embed = create_embed(
                title="🎮 Fun & Games Commands",
                description="**Entertainment commands and mini-games**",
                color=COLORS['lime']
            )
            embed.add_field(
                name="🎲 Random Games",
                value="`/coinflip` - Flip a coin\n`/dice` - Roll dice\n`/8ball` - Ask magic 8-ball\n`/random` - Random number",
                inline=True
            )
            embed.add_field(
                name="🎭 Entertainment",
                value="`/meme` - Random meme\n`/joke` - Tell a joke\n`/fact` - Random fact\n`/quote` - Inspirational quote",
                inline=True
            )
            embed.add_field(
                name="🎪 Interactive",
                value="`/poll` - Create poll\n`/giveaway` - Start giveaway\n`/remind` - Set reminder\n`/afk` - Set AFK status",
                inline=True
            )
            
        elif category == "premium":
            embed = create_embed(
                title="💎 Premium Commands",
                description="**Premium-only features and commands**",
                color=COLORS['gold']
            )
            embed.add_field(
                name="🚀 Exclusive Features",
                value="`/setup` - Interactive server rebuild\n`/create_template` - Interactive template creator\n`/antinuke` - Advanced protection\n`/premium` - Manage premium status",
                inline=True
            )
            embed.add_field(
                name="⚡ Performance",
                value="• No command cooldowns\n• Priority support\n• Unlimited media channels\n• Advanced customization",
                inline=True
            )
            embed.add_field(
                name="💎 Get Premium",
                value=f"Contact <@{BOT_OWNER_ID}> to upgrade your server!\n\n**Tiers:**\n🥉 Basic - $4.99/month\n🥈 Pro - $9.99/month\n🥇 Elite - $19.99/month",
                inline=False
            )
            
        # Add more categories as needed...
        else:
            embed = create_info_embed("Category Coming Soon", f"The **{category}** category will be available soon with more commands!", interaction.user)
        
        await interaction.response.edit_message(embed=embed, view=self.view)

# CUSTOM EMOJI SYSTEM
custom_emojis = {}
emoji_categories = {
    'protection': ['🛡️', '⚔️', '🔒', '🚫', '⚠️'],
    'success': ['✅', '💚', '🎉', '⭐', '✨'],
    'error': ['❌', '💥', '🚨', '⚠️', '🔴'],
    'info': ['ℹ️', '📊', '📈', '💡', '🔍'],
    'premium': ['💎', '👑', '🥇', '⭐', '✨'],
    'moderation': ['🛡️', '👮', '🚫', '⚒️', '🔨'],
    'fun': ['🎮', '🎭', '🎪', '🎨', '🎲'],
    'music': ['🎵', '🎶', '🔊', '📻', '🎧']
}

async def collect_custom_emojis():
    """Collect custom emojis from all servers the bot is in"""
    global custom_emojis
    custom_emojis = {
        'protection': [],
        'success': [], 
        'error': [],
        'info': [],
        'premium': [],
        'moderation': [],
        'fun': [],
        'music': []
    }
    
    # Collect emojis from all guilds
    for guild in bot.guilds:
        for emoji in guild.emojis:
            if emoji.available:
                emoji_name = emoji.name.lower()
                
                # Categorize emojis based on name
                if any(word in emoji_name for word in ['shield', 'protect', 'secure', 'guard', 'safe']):
                    custom_emojis['protection'].append(str(emoji))
                elif any(word in emoji_name for word in ['check', 'yes', 'success', 'good', 'correct', 'done']):
                    custom_emojis['success'].append(str(emoji))
                elif any(word in emoji_name for word in ['no', 'error', 'wrong', 'bad', 'fail', 'x']):
                    custom_emojis['error'].append(str(emoji))
                elif any(word in emoji_name for word in ['info', 'question', 'help', 'detail']):
                    custom_emojis['info'].append(str(emoji))
                elif any(word in emoji_name for word in ['premium', 'crown', 'diamond', 'gold', 'vip']):
                    custom_emojis['premium'].append(str(emoji))
                elif any(word in emoji_name for word in ['mod', 'admin', 'ban', 'kick', 'hammer']):
                    custom_emojis['moderation'].append(str(emoji))
                elif any(word in emoji_name for word in ['fun', 'game', 'play', 'party', 'celebrate']):
                    custom_emojis['fun'].append(str(emoji))
                elif any(word in emoji_name for word in ['music', 'song', 'note', 'sound', 'beat']):
                    custom_emojis['music'].append(str(emoji))
    
    print(f"🎨 Collected custom emojis: {sum(len(emojis) for emojis in custom_emojis.values())} total")

def get_custom_emoji(category, fallback=None):
    """Get a random custom emoji from category or fallback to Unicode"""
    if category in custom_emojis and custom_emojis[category]:
        import random
        return random.choice(custom_emojis[category])
    elif fallback:
        return fallback
    elif category in emoji_categories:
        import random
        return random.choice(emoji_categories[category])
    else:
        return '⚪'

# TEST COMMAND
@bot.tree.command(name="test", description="🧪 Test bot functionality and features")
async def test_command(interaction: discord.Interaction, feature: str = "all"):
    """Test various bot features and functionality"""

    if not interaction.user.guild_permissions.administrator:
        embed = create_error_embed("Permission Denied", "You need Administrator permission to run bot tests.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.defer()

    test_results = []
    guild = interaction.guild

    # Test bot permissions
    try:
        bot_permissions = guild.me.guild_permissions
        permission_tests = {
            "Manage Channels": bot_permissions.manage_channels,
            "Manage Roles": bot_permissions.manage_roles,
            "Kick Members": bot_permissions.kick_members,
            "Ban Members": bot_permissions.ban_members,
            "Manage Messages": bot_permissions.manage_messages,
            "Send Messages": bot_permissions.send_messages,
            "Embed Links": bot_permissions.embed_links,
            "Attach Files": bot_permissions.attach_files,
            "Manage Guild": bot_permissions.manage_guild
        }

        passed_perms = sum(permission_tests.values())
        total_perms = len(permission_tests)
        test_results.append(f"✅ Permissions: {passed_perms}/{total_perms} passed")

    except Exception as e:
        test_results.append(f"❌ Permission test failed: {str(e)}")

    # Test database connectivity
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]
        conn.close()
        test_results.append(f"✅ Database: {table_count} tables found")
    except Exception as e:
        test_results.append(f"❌ Database test failed: {str(e)}")

    # Test premium system
    try:
        is_premium = is_premium_server(guild.id)
        test_results.append(f"✅ Premium System: {'Premium' if is_premium else 'Standard'} server")
    except Exception as e:
        test_results.append(f"❌ Premium test failed: {str(e)}")

    # Test ticket system
    try:
        if guild.id in ticket_systems:
            system = ticket_systems[guild.id]
            test_results.append(f"✅ Ticket System: {len(system.ticket_types)} types configured")
        else:
            test_results.append("ℹ️ Ticket System: Not initialized")
    except Exception as e:
        test_results.append(f"❌ Ticket test failed: {str(e)}")

    # Test AutoMod capabilities
    try:
        automod_rules = await guild.fetch_automod_rules()
        test_results.append(f"✅ AutoMod: {len(automod_rules)} rules active")
    except Exception as e:
        test_results.append(f"⚠️ AutoMod: {str(e)}")

    # Test media-only system
    try:
        media_count = len(media_only_channels.get(guild.id, []))
        test_results.append(f"✅ Media-Only: {media_count} channels configured")
    except Exception as e:
        test_results.append(f"❌ Media-only test failed: {str(e)}")

    # Test auto-meme system
    try:
        has_automeme = guild.id in auto_meme_webhooks
        test_results.append(f"✅ Auto-Meme: {'Enabled' if has_automeme else 'Disabled'}")
    except Exception as e:
        test_results.append(f"❌ Auto-meme test failed: {str(e)}")

    # Test variable system
    try:
        test_var = replace_variables("{guild.name} has {guild.membercount} members", guild=guild)
        if guild.name in test_var:
            test_results.append("✅ Variable System: Working correctly")
        else:
            test_results.append("⚠️ Variable System: Partial functionality")
    except Exception as e:
        test_results.append(f"❌ Variable test failed: {str(e)}")

    # Test API latency
    try:
        latency = round(bot.latency * 1000, 2)
        if latency < 100:
            test_results.append(f"✅ API Latency: {latency}ms (Excellent)")
        elif latency < 300:
            test_results.append(f"✅ API Latency: {latency}ms (Good)")
        else:
            test_results.append(f"⚠️ API Latency: {latency}ms (High)")
    except Exception as e:
        test_results.append(f"❌ Latency test failed: {str(e)}")

    # Test embed creation
    try:
        test_embed = create_embed("Test", "Embed creation test", COLORS['success'])
        if test_embed.title == "Test":
            test_results.append("✅ Embed System: Working correctly")
        else:
            test_results.append("⚠️ Embed System: Issues detected")
    except Exception as e:
        test_results.append(f"❌ Embed test failed: {str(e)}")

    # Create comprehensive test report
    passed_tests = len([result for result in test_results if result.startswith("✅")])
    warning_tests = len([result for result in test_results if result.startswith("⚠️")])
    failed_tests = len([result for result in test_results if result.startswith("❌")])
    total_tests = len(test_results)

    # Determine overall status
    if failed_tests == 0 and warning_tests == 0:
        status_color = COLORS['success']
        status_text = "🟢 ALL SYSTEMS OPERATIONAL"
    elif failed_tests == 0:
        status_color = COLORS['warning']
        status_text = "🟡 MINOR ISSUES DETECTED"
    else:
        status_color = COLORS['error']
        status_text = "🔴 CRITICAL ISSUES FOUND"

    embed = create_embed(
        title="🧪 Bot System Test Results",
        description=f"**{status_text}**\n\nComprehensive system diagnostic completed for **{guild.name}**",
        color=status_color
    )

    embed.add_field(
        name="📊 Test Summary",
        value=f"**Passed:** {passed_tests} ✅\n**Warnings:** {warning_tests} ⚠️\n**Failed:** {failed_tests} ❌\n**Total:** {total_tests} tests",
        inline=True
    )

    embed.add_field(
        name="🎯 Success Rate",
        value=f"**{((passed_tests / total_tests) * 100):.1f}%**",
        inline=True
    )

    embed.add_field(
        name="⚙️ Bot Health",
        value=f"**Status:** {'Healthy' if failed_tests == 0 else 'Issues Detected'}\n**Uptime:** <t:{int(bot_stats['start_time'])}:R>",
        inline=True
    )

    # Split results into chunks for embed fields
    chunk_size = 10
    for i in range(0, len(test_results), chunk_size):
        chunk = test_results[i:i+chunk_size]
        embed.add_field(
            name=f"🔍 Test Results {i//chunk_size + 1}" if len(test_results) > chunk_size else "🔍 Detailed Results",
            value="\n".join(chunk),
            inline=False
        )

    embed.add_field(
        name="💡 Recommendations",
        value="• Fix any ❌ failed tests for optimal performance\n• Address ⚠️ warnings when possible\n• Run tests regularly to monitor bot health\n• Contact support if critical issues persist",
        inline=False
    )

    embed.add_field(
        name="🛠️ System Information",
        value=f"• **Python Version:** {platform.python_version()}\n• **Discord.py Version:** {discord.__version__}\n• **Servers:** {len(bot.guilds)}\n• **Commands Available:** 50+",
        inline=False
    )

    embed.set_footer(text=f"Test completed • {guild.name}", icon_url=guild.icon.url if guild.icon else None)

    await interaction.followup.send(embed=embed)
    await log_command_action(interaction, "test", f"Ran system test: {passed_tests}/{total_tests} passed")

# PREMIUM COMMANDS
@bot.tree.command(name="premium", description="💎 Manage premium server status")
async def premium_command(interaction: discord.Interaction, action: str, server_id: str = None):
    if interaction.user.id != BOT_OWNER_ID:
        embed = create_error_embed("Permission Denied", "Only the bot owner can manage premium status.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if action.lower() not in ["add", "remove", "list"]:
        embed = create_error_embed("Invalid Action", "Valid actions: `add`, `remove`, `list`")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if action.lower() == "list":
        if not premium_servers:
            embed = create_info_embed("Premium Servers", "No premium servers currently registered.")
        else:
            server_list = []
            for guild_id in premium_servers:
                guild = bot.get_guild(guild_id)
                server_list.append(f"• {guild.name} (`{guild_id}`)" if guild else f"• Unknown Server (`{guild_id}`)")

            embed = create_embed(
                title="💎 Premium Servers",
                description=f"**{len(premium_servers)}** servers have premium status:",
                color=COLORS['gold']
            )
            embed.add_field(
                name="🏢 Server List",
                value="\n".join(server_list[:15]) + (f"\n... and {len(server_list)-15} more" if len(server_list) > 15 else ""),
                inline=False
            )

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "premium", f"{action} premium for {len(premium_servers)} servers")
        return

    if not server_id:
        server_id = str(interaction.guild.id)

    try:
        guild_id = int(server_id)
        guild = bot.get_guild(guild_id)
        guild_name = guild.name if guild else "Unknown Server"

        if action.lower() == "add":
            if add_premium_server(guild_id):
                embed = create_success_embed(
                    "Premium Added",
                    f"**{guild_name}** is now a premium server!\n\n✨ Benefits:\n• No command cooldowns\n• Priority support\n• Exclusive features",
                    interaction.user
                )
            else:
                embed = create_info_embed("Already Premium", f"**{guild_name}** is already a premium server.")

        elif action.lower() == "remove":
            if remove_premium_server(guild_id):
                embed = create_success_embed(
                    "Premium Removed",
                    f"**{guild_name}** is no longer a premium server.",
                    interaction.user
                )
            else:
                embed = create_info_embed("Not Premium", f"**{guild_name}** was not a premium server.")

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "premium", f"{action} premium for {guild_name} ({guild_id})")

    except ValueError:
        embed = create_error_embed("Invalid Server ID", f"'{server_id}' is not a valid server ID.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="premiumstatus", description="💎 Check if current server has premium")
async def premium_status(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    is_premium = is_premium_server(guild_id)

    if is_premium:
        embed = create_embed(
            title="💎 Premium Server",
            description=f"**{interaction.guild.name}** has premium status!",
            color=COLORS['gold']
        )
        embed.add_field(
            name="✨ Active Benefits",
            value="• No command cooldowns\n• Priority support\n• Exclusive features\n• Enhanced performance\n• Unlimited setup usage",
            inline=False
        )
    else:
        embed = create_embed(
            title="🆓 Standard Server",
            description=f"**{interaction.guild.name}** is using the standard plan.",
            color=COLORS['info']
        )
        embed.add_field(
            name="⏱️ Current Limitations",
            value=f"• {DEFAULT_COOLDOWN}s command cooldowns\n• Standard support\n• Setup command requires premium",
            inline=False
        )
        embed.add_field(
            name="💎 Upgrade to Premium",
            value=f"Contact <@{BOT_OWNER_ID}> for premium access!",
            inline=False
        )

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "premiumstatus", f"Checked premium status: {is_premium}")

# Enhanced cooldown decorator
def enhanced_cooldown_check():
    async def predicate(interaction: discord.Interaction):
        command_name = interaction.command.name if interaction.command else "unknown"
        user_id = interaction.user.id
        guild_id = interaction.guild.id if interaction.guild else None
        
        # Check if command is premium-only
        if command_name in PREMIUM_ONLY_COMMANDS:
            tier = get_user_tier(guild_id)
            if not tier:
                embed = create_error_embed(
                    "💎 Premium Command",
                    f"The `/{command_name}` command requires a premium subscription!\n\n**Available Tiers:**\n🥉 Basic - $4.99/month\n🥈 Pro - $9.99/month\n🥇 Elite - $19.99/month\n\nContact the developer to upgrade your server!"
                )
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(embed=embed, ephemeral=True)
                return False

        if not check_enhanced_cooldown(user_id, command_name, guild_id):
            remaining = get_enhanced_cooldown_remaining(user_id, command_name)
            tier = get_user_tier(guild_id)
            
            cooldown_type = "⚠️ High-Risk Command" if command_name in HIGH_RISK_COMMANDS else "⏱️ Standard Cooldown"
            
            embed = create_error_embed(
                f"{cooldown_type}",
                f"You're on cooldown! Try again in **{remaining:.1f}** seconds.\n\n{'💎 Premium tiers have no cooldowns!' if not tier else 'This should not happen with premium...'}"
            )
            
            if command_name in HIGH_RISK_COMMANDS:
                embed.add_field(
                    name="🔒 Rate Limiting Protection",
                    value="High-risk commands have extended cooldowns to prevent abuse and rate limiting.",
                    inline=False
                )
            
            if not tier:
                embed.add_field(
                    name="💎 Upgrade to Premium",
                    value="Get instant access with no cooldowns!\n🥉 Basic: $4.99/month\n🥈 Pro: $9.99/month\n🥇 Elite: $19.99/month",
                    inline=False
                )
            
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
            return False
        return True
    return predicate

# VARIABLES COMMAND
@bot.tree.command(name="variables", description="📋 List all available variables for customization")
async def variables_command(interaction: discord.Interaction, category: str = "all"):
    """List all available variables for various features"""

    embed = create_embed(
        title="📋 Available Variables",
        description="Use these variables in nicknames, welcome messages, tickets, and more!",
        color=COLORS['blue']
    )

    if category.lower() in ["all", "user"]:
        embed.add_field(
            name="👤 User Variables",
            value="• `{user}` - Full username\n• `{user.name}` - Username only\n• `{user.mention}` - @mention\n• `{user.id}` - User ID\n• `{user.avatar}` - Avatar URL\n• `{user.created}` - Account creation\n• `{user.joined}` - Server join date",
            inline=False
        )

    if category.lower() in ["all", "server", "guild"]:
        embed.add_field(
            name="🏢 Server Variables",
            value="• `{guild.name}` - Server name\n• `{guild.id}` - Server ID\n• `{guild.icon}` - Server icon\n• `{guild.owner}` - Owner mention\n• `{guild.membercount}` - Member count\n• `{guild.created}` - Server creation",
            inline=False
        )

    if category.lower() in ["all", "channel"]:
        embed.add_field(
            name="📝 Channel Variables",
            value="• `{channel}` - Channel mention\n• `{channel.name}` - Channel name\n• `{channel.id}` - Channel ID",
            inline=False
        )

    if category.lower() in ["all", "time", "date"]:
        embed.add_field(
            name="⏰ Time Variables",
            value="• `{date}` - Current date\n• `{time}` - Current time\n• `{timestamp}` - Unix timestamp",
            inline=False
        )

    if category.lower() in ["all", "random"]:
        embed.add_field(
            name="🎲 Random Variables",
            value="• `{random.number}` - Random 1-100\n• `{random.color}` - Random hex color",
            inline=False
        )

    if category.lower() in ["all", "bot"]:
        embed.add_field(
            name="🤖 Bot Variables",
            value="• `{bot.name}` - Bot username\n• `{bot.mention}` - Bot mention",
            inline=False
        )

    if category.lower() in ["all", "extra"]:
        embed.add_field(
            name="✨ Extra Variables",
            value="• `{invite.count}` - User invites\n• `{level}` - User level\n• `{rank}` - User rank",
            inline=False
        )

    embed.add_field(
        name="🔧 Usage Examples",
        value="• `/nickall Welcome {user.name}!`\n• Welcome message: `Hello {user.mention}, welcome to {guild.name}!`\n• Ticket: `Support ticket for {user.name} - #{random.number}`",
        inline=False
    )

    embed.add_field(
        name="📚 Categories",
        value="Use `/variables <category>` to see specific variables:\n`user`, `server`, `channel`, `time`, `random`, `bot`, `extra`",
        inline=False
    )

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "variables", f"Listed variables for category: {category}")

# ENHANCED NICKALL COMMAND
@bot.tree.command(name="nickall", description="👥 Rename all members with advanced variable support")
@discord.app_commands.describe(
    nickname="New nickname pattern (supports variables: {user.name}, {guild.name}, {random.number}, etc.)"
)
async def nickall(interaction: discord.Interaction, nickname: str):
    if not interaction.user.guild_permissions.manage_nicknames:
        embed = create_error_embed("Permission Denied", "You need `Manage Nicknames` permission to use this command.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.manage_nicknames:
        embed = create_error_embed("Bot Permission Missing", "I need `Manage Nicknames` permission to rename members.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # DANGEROUS ACTION CONFIRMATION
    member_count = len([member for member in interaction.guild.members if not member.bot])
    confirmed = await confirm_dangerous_action(
        interaction,
        "Bulk Nickname Change",
        f"This will rename ALL {member_count} non-bot members in the server to pattern '{nickname}' with variable substitutions. This affects everyone's display name!"
    )

    if not confirmed:
        await log_command_action(interaction, "nickall", f"Nickall cancelled by user during confirmation for pattern '{nickname}'", False)
        return

    guild = interaction.guild
    renamed_count = 0
    failed_count = 0
    total_members = len([member for member in guild.members if not member.bot])

    # Create progress embed
    progress_embed = create_embed(
        title="👥 Renaming All Members",
        description=f"🎯 **Server:** {guild.name}\n🏷️ **Pattern:** {nickname}\n\n⚡ **Status:** Starting rename process...",
        color=COLORS['warning'],
        animated=True
    )

    progress_embed.add_field(
        name="📋 Available Variables",
        value="`{user.name}`, `{guild.name}`, `{random.number}`, `{date}`, `{time}` and more!\nUse `/variables` to see all options.",
        inline=False
    )

    progress_embed.add_field(name="👥 Total Members", value=str(total_members), inline=True)
    progress_embed.add_field(name="✅ Renamed", value="0", inline=True)
    progress_embed.add_field(name="❌ Failed", value="0", inline=True)

    progress_message = await interaction.followup.send(embed=progress_embed)

    for i, member in enumerate(guild.members):
        try:
            # Skip bots and users we can't rename
            if member.bot or member == guild.owner or member.top_role >= interaction.guild.me.top_role:
                continue

            # Replace variables in the nickname
            formatted_nickname = replace_variables(
                nickname,
                user=member,
                guild=guild,
                channel=interaction.channel
            )

            # Limit nickname length
            if len(formatted_nickname) > 32:
                formatted_nickname = formatted_nickname[:29] + "..."

            await member.edit(nick=formatted_nickname, reason=f"Bulk nickname change by {interaction.user}")
            renamed_count += 1
            print(f"✅ Renamed {member.name} to {formatted_nickname}")

            # Rate limiting
            await safe_sleep(1.0)

            # Update progress every 5 renames
            if renamed_count % 5 == 0:
                progress_embed.description = f"🎯 **Server:** {guild.name}\n🏷️ **Pattern:** {nickname}\n\n⚡ **Current:** {member.display_name}\n📊 **Progress:** {renamed_count + failed_count}/{total_members}"
                progress_embed.set_field_at(1, name="👥 Total Members", value=str(total_members), inline=True)
                progress_embed.set_field_at(2, name="✅ Renamed", value=str(renamed_count), inline=True)
                progress_embed.set_field_at(3, name="❌ Failed", value=str(failed_count), inline=True)

                try:
                    await progress_message.edit(embed=progress_embed)
                except:
                    pass

        except discord.HTTPException as e:
            if "Missing Permissions" in str(e) or "Forbidden" in str(e):
                failed_count += 1
                print(f"❌ Cannot rename {member.display_name}: Insufficient permissions")
            else:
                failed_count += 1
                print(f"❌ Failed to rename {member.display_name}: {e}")
            await safe_sleep(1.0)
        except Exception as e:
            failed_count += 1
            print(f"❌ Error renaming {member.display_name}: {e}")
            await safe_sleep(1.0)

    # Final result embed
    embed = create_success_embed("Nickname Change Complete!", f"Bulk renamed members in **{guild.name}**", interaction.user)
    embed.add_field(name="✅ Successfully Renamed", value=f"{renamed_count} members", inline=True)
    embed.add_field(name="❌ Failed", value=f"{failed_count} members", inline=True)
    embed.add_field(name="👥 Total Processed", value=f"{renamed_count + failed_count} members", inline=True)
    embed.add_field(name="🏷️ Pattern Used", value=f"`{nickname}`", inline=False)
    embed.add_field(
        name="📋 Variables Supported",
        value="User: `{user.name}`, `{user.mention}`\nServer: `{guild.name}`, `{guild.membercount}`\nTime: `{date}`, `{time}`\nRandom: `{random.number}`, `{random.color}`\n\nSee `/variables` for complete list!",
        inline=False
    )

    if failed_count > 0:
        embed.add_field(
            name="ℹ️ Common Failure Reasons",
            value="• Bot accounts (skipped)\n• Server owner (cannot rename)\n• Higher role hierarchy\n• Missing permissions",
            inline=False
        )

    await interaction.edit_original_response(embed=embed)
    await log_command_action(interaction, "nickall", f"Renamed {renamed_count} members to '{nickname}' pattern")

# AUTOMOD COMMANDS (FIXED WITH PROPER DISCORD.PY IMPLEMENTATION)
@bot.tree.command(name="banword", description="🚫 Add a word to Discord's AutoMod system")
@discord.app_commands.describe(
    word="Word to ban",
    action="Action to take when word is detected"
)
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name="🚫 Block Message", value="block"),
    discord.app_commands.Choice(name="⏰ Timeout User (5 min)", value="timeout"),
    discord.app_commands.Choice(name="🚨 Send Alert to Staff", value="alert")
])
async def banword(interaction: discord.Interaction, word: str, action: discord.app_commands.Choice[str] = None):
    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to use this command.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.manage_guild:
        embed = create_error_embed("Bot Permission Missing", "I need `Manage Server` permission to manage AutoMod rules.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.defer()

    try:
        # Validate word input
        if len(word) < 2:
            embed = create_error_embed("Invalid Word", "Word must be at least 2 characters long.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if len(word) > 60:
            embed = create_error_embed("Word Too Long", "Word must be 60 characters or less.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        clean_word = word.strip().lower()
        action_value = action.value if action else "block"

        # Check existing rules
        rules = await interaction.guild.fetch_automod_rules()
        word_filter_rule = None

        for rule in rules:
            if rule.name == "Utility Core Word Filter":
                word_filter_rule = rule
                break

        if word_filter_rule:
            # Get current keywords
            current_keywords = []
            if word_filter_rule.trigger.keyword_filter:
                current_keywords = list(word_filter_rule.trigger.keyword_filter)

            # Check if word already exists
            if clean_word in current_keywords:
                embed = create_info_embed("Word Already Banned", f"The word **{clean_word}** is already in the banned words list", interaction.user)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Add new word
            current_keywords.append(clean_word)

            # Create proper trigger metadata
            trigger_metadata = discord.AutoModTriggerMetadata(keyword_filter=current_keywords)

            # Create actions list
            actions = [discord.AutoModBlockMessageAction()]

            if action_value == "timeout":
                actions.append(discord.AutoModTimeoutAction(duration=300))  # 5 minutes
            elif action_value == "alert":
                # Find staff channel
                alert_channel = None
                for channel in interaction.guild.text_channels:
                    if any(keyword in channel.name.lower() for keyword in ["staff", "mod", "log", "automod"]):
                        alert_channel = channel
                        break
                
                if alert_channel:
                    actions.append(discord.AutoModSendAlertAction(channel=alert_channel))

            # Update existing rule
            await word_filter_rule.edit(
                trigger_metadata=trigger_metadata,
                actions=actions,
                reason=f"Added word '{clean_word}' by {interaction.user}"
            )
            action_text = "Updated existing AutoMod rule"

        else:
            # Create new rule
            trigger_metadata = discord.AutoModTriggerMetadata(keyword_filter=[clean_word])
            
            # Create actions
            actions = [discord.AutoModBlockMessageAction()]

            if action_value == "timeout":
                actions.append(discord.AutoModTimeoutAction(duration=300))
            elif action_value == "alert":
                alert_channel = None
                for channel in interaction.guild.text_channels:
                    if any(keyword in channel.name.lower() for keyword in ["staff", "mod", "log", "automod"]):
                        alert_channel = channel
                        break
                
                if alert_channel:
                    actions.append(discord.AutoModSendAlertAction(channel=alert_channel))

            # Create the rule
            word_filter_rule = await interaction.guild.create_automod_rule(
                name="Utility Core Word Filter",
                event_type=discord.AutoModEventType.message_send,
                trigger_type=discord.AutoModTriggerType.keyword,
                trigger_metadata=trigger_metadata,
                actions=actions,
                enabled=True,
                reason=f"Created by {interaction.user} for word filtering"
            )
            action_text = "Created new AutoMod rule"

        # Get final count
        final_count = len(word_filter_rule.trigger.keyword_filter) if word_filter_rule.trigger.keyword_filter else 1

        # Success embed
        embed = create_success_embed("Word Added to AutoMod", f"**{clean_word}** has been successfully added to the banned words list", interaction.user)
        embed.add_field(name="🎯 Word", value=f"`{clean_word}`", inline=True)
        embed.add_field(name="⚡ Action", value=action.name if action else "🚫 Block Message", inline=True)
        embed.add_field(name="📋 Result", value=action_text, inline=True)
        embed.add_field(name="🔧 Rule ID", value=f"`{word_filter_rule.id}`", inline=True)
        embed.add_field(name="✅ Status", value="🟢 Active and monitoring", inline=True)
        embed.add_field(name="📊 Total Words", value=f"`{final_count}`", inline=True)

        await interaction.followup.send(embed=embed)
        await log_command_action(interaction, "banword", f"Added word '{clean_word}' to AutoMod with action '{action_value}'")

    except discord.Forbidden:
        embed = create_error_embed("Permission Error", "I don't have permission to manage AutoMod rules. Ensure I have `Manage Server` permission and the server has Community features enabled.")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_command_action(interaction, "banword", f"Permission denied for AutoMod rule management", False)

    except discord.HTTPException as e:
        error_msg = str(e)
        print(f"AutoMod HTTP Error: {error_msg}")

        if "maximum number of rules" in error_msg.lower():
            embed = create_error_embed("Rule Limit Reached", "This server has reached the maximum number of AutoMod rules (10). Please delete some rules first using `/automod clear`.")
        elif "community" in error_msg.lower() or "boost" in error_msg.lower() or "feature not available" in error_msg.lower():
            embed = create_error_embed("Server Requirements", "AutoMod requires Community features to be enabled. Go to Server Settings > Community > Enable Community to use AutoMod.")
        elif "invalid form body" in error_msg.lower() or "keyword" in error_msg.lower():
            embed = create_error_embed("Invalid Word", f"The word '{word}' contains invalid characters for AutoMod. Words cannot contain special characters or be empty.")
        elif "rate limited" in error_msg.lower():
            embed = create_error_embed("Rate Limited", "Too many AutoMod requests. Please wait a moment and try again.")
        else:
            embed = create_error_embed("AutoMod Error", f"Discord AutoMod error: {error_msg}\n\n**Requirements:**\n• Community features enabled\n• Valid word format (no special chars)\n• Under 10 total rules\n• No rate limiting")

        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_command_action(interaction, "banword", f"HTTP error managing AutoMod rule for '{word}': {error_msg}", False)

    except Exception as e:
        print(f"Unexpected AutoMod Error: {str(e)}")
        embed = create_error_embed("AutoMod Failed", f"An unexpected error occurred:\n```{str(e)}```")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_command_action(interaction, "banword", f"Unexpected error adding word '{word}': {str(e)}", False)
        await report_error_to_owner(e, f"AutoMod banword command - Guild: {interaction.guild.name}")

@bot.tree.command(name="removeword", description="✅ Remove a word from AutoMod")
async def removeword(interaction: discord.Interaction, word: str):
    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to use this command.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.defer()

    try:
        rules = await interaction.guild.fetch_automod_rules()
        word_filter_rule = None

        for rule in rules:
            if rule.name == "Utility Core Word Filter":
                word_filter_rule = rule
                break

        if not word_filter_rule:
            embed = create_error_embed("No AutoMod Rule", "No word filter rule found. Use `/banword` to create one first.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Get current keywords
        current_keywords = []
        if word_filter_rule.trigger.keyword_filter:
            current_keywords = list(word_filter_rule.trigger.keyword_filter)

        clean_word = word.strip().lower()

        if clean_word in current_keywords:
            current_keywords.remove(clean_word)

            if current_keywords:
                # Update rule with remaining keywords
                trigger_metadata = discord.AutoModTriggerMetadata(keyword_filter=current_keywords)
                await word_filter_rule.edit(
                    trigger_metadata=trigger_metadata,
                    reason=f"Removed word '{clean_word}' by {interaction.user}"
                )
                result_text = "Updated AutoMod rule"
            else:
                # Delete rule if no keywords left
                await word_filter_rule.delete(reason=f"Removed last word by {interaction.user}")
                result_text = "Deleted empty AutoMod rule"

            embed = create_success_embed("Word Removed from AutoMod", f"**{clean_word}** has been removed from the banned words list", interaction.user)
            embed.add_field(name="🎯 Word Removed", value=f"`{clean_word}`", inline=True)
            embed.add_field(name="📋 Result", value=result_text, inline=True)

            await interaction.followup.send(embed=embed)
            await log_command_action(interaction, "removeword", f"Removed word '{clean_word}' from AutoMod")
        else:
            embed = create_error_embed("Word Not Found", f"The word **{clean_word}** is not in the banned words list.")
            await interaction.followup.send(embed=embed, ephemeral=True)

    except discord.Forbidden:
        embed = create_error_embed("Permission Error", "I don't have permission to manage AutoMod rules. Ensure I have `Manage Server` permission.")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_command_action(interaction, "removeword", f"Permission denied for AutoMod rule management", False)

    except discord.HTTPException as e:
        error_msg = str(e)
        if "rate limited" in error_msg.lower():
            embed = create_error_embed("Rate Limited", "Too many AutoMod requests. Please wait a moment and try again.")
        else:
            embed = create_error_embed("AutoMod Error", f"Discord AutoMod error: {error_msg}")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_command_action(interaction, "removeword", f"HTTP error removing word '{word}': {error_msg}", False)

    except Exception as e:
        embed = create_error_embed("Failed to Remove Word", f"Could not remove word from AutoMod: {str(e)}")
        await interaction.followup.send(embed=embed)
        await log_command_action(interaction, "removeword", f"Failed to remove word '{word}': {str(e)}", False)
        await report_error_to_owner(e, f"AutoMod removeword command - Guild: {interaction.guild.name}")

@bot.tree.command(name="listbannedwords", description="📋 List all banned words in AutoMod")
async def listbannedwords(interaction: discord.Interaction):
    try:
        rules = await interaction.guild.fetch_automod_rules()
        word_filter_rule = None

        for rule in rules:
            if rule.name == "Utility Core Word Filter":
                word_filter_rule = rule
                break

        if not word_filter_rule:
            embed = create_info_embed("No Banned Words", "No AutoMod word filter rule found. Use `/banword` to create one.", interaction.user)
            await interaction.response.send_message(embed=embed)
            return

        keywords = word_filter_rule.trigger.keyword_filter if word_filter_rule.trigger.keyword_filter else []

        if not keywords:
            embed = create_info_embed("Empty Word Filter", "The AutoMod rule exists but has no banned words.", interaction.user)
            await interaction.response.send_message(embed=embed)
            return

        # Format keywords for display
        word_list = [f"• `{word}`" for word in keywords]

        embed = create_embed(
            title="🚫 Banned Words List", 
            description="Words currently blocked by AutoMod", 
            color=COLORS['info']
        )

        embed.add_field(
            name=f'📋 Banned Words ({len(keywords)})',
            value='\n'.join(word_list[:20]),
            inline=False
        )

        if len(keywords) > 20:
            embed.add_field(name="➕ Additional", value=f"... and {len(keywords) - 20} more words", inline=False)

        embed.add_field(
            name="🔧 Rule Info",
            value=f"Rule ID: `{word_filter_rule.id}`\nStatus: {'🟢 Enabled' if word_filter_rule.enabled else '🔴 Disabled'}",
            inline=False
        )

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "listbannedwords", f"Listed {len(keywords)} banned words")

    except Exception as e:
        embed = create_error_embed("Failed to List Words", f"Could not retrieve banned words: {str(e)}")
        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "listbannedwords", f"Failed to list words: {str(e)}", False)
        await report_error_to_owner(e, f"AutoMod listbannedwords command - Guild: {interaction.guild.name}")

@bot.tree.command(name="automod", description="🛡️ AutoMod management and common word filters")
@discord.app_commands.describe(
    action="AutoMod action to perform",
    preset="Common word filter preset to apply"
)
@discord.app_commands.choices(
    action=[
        discord.app_commands.Choice(name="📊 View Status", value="status"),
        discord.app_commands.Choice(name="📋 List Rules", value="list"),
        discord.app_commands.Choice(name="🗑️ Clear All Rules", value="clear"),
        discord.app_commands.Choice(name="✨ Apply Common Filter", value="common")
    ],
    preset=[
        discord.app_commands.Choice(name="🤬 Profanity Filter", value="profanity"),
        discord.app_commands.Choice(name="💊 Drug/Substance References", value="drugs"),
        discord.app_commands.Choice(name="🔞 Sexual Content", value="sexual"),
        discord.app_commands.Choice(name="⚔️ Violence/Threats", value="violence"),
        discord.app_commands.Choice(name="🏴‍☠️ Piracy/Illegal", value="piracy"),
        discord.app_commands.Choice(name="💰 Scam/Spam", value="scam"),
        discord.app_commands.Choice(name="📈 All Common Filters", value="all")
    ]
)
async def automod(interaction: discord.Interaction, action: discord.app_commands.Choice[str], preset: discord.app_commands.Choice[str] = None):
    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to manage AutoMod.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if action.value == "status":
        try:
            rules = await interaction.guild.fetch_automod_rules()
            
            embed = create_embed(
                title="🛡️ AutoMod System Status",
                description=f"AutoMod status for **{interaction.guild.name}**",
                color=COLORS['blue']
            )

            embed.add_field(name="📊 Total Rules", value=f"{len(rules)}/10", inline=True)
            embed.add_field(name="🔧 Bot Permissions", value="✅ Manage Server" if interaction.guild.me.guild_permissions.manage_guild else "❌ Missing", inline=True)
            embed.add_field(name="🏢 Community Features", value="✅ Enabled" if "COMMUNITY" in interaction.guild.features else "❌ Required", inline=True)

            if rules:
                rule_list = []
                for rule in rules[:5]:
                    status = "🟢" if rule.enabled else "🔴"
                    rule_list.append(f"{status} {rule.name}")
                
                embed.add_field(name="📋 Active Rules", value="\n".join(rule_list), inline=False)
                
                if len(rules) > 5:
                    embed.add_field(name="➕ Additional", value=f"... and {len(rules) - 5} more rules", inline=False)
            else:
                embed.add_field(name="📋 Active Rules", value="No AutoMod rules configured", inline=False)

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            embed = create_error_embed("Status Check Failed", f"Could not check AutoMod status: {str(e)}")
            await interaction.response.send_message(embed=embed)

    elif action.value == "list":
        try:
            rules = await interaction.guild.fetch_automod_rules()
            
            if not rules:
                embed = create_info_embed("No AutoMod Rules", "No AutoMod rules are currently configured.", interaction.user)
                await interaction.response.send_message(embed=embed)
                return

            embed = create_embed(
                title="📋 AutoMod Rules List",
                description=f"**{len(rules)}** AutoMod rules configured",
                color=COLORS['blue']
            )

            for rule in rules:
                status = "🟢 Enabled" if rule.enabled else "🔴 Disabled"
                trigger_info = f"Type: {rule.trigger_type.name.title()}"
                
                if rule.trigger_type == discord.AutoModTriggerType.keyword and rule.trigger.keyword_filter:
                    word_count = len(rule.trigger.keyword_filter)
                    trigger_info += f" ({word_count} words)"

                embed.add_field(
                    name=f"{rule.name}",
                    value=f"{status}\n{trigger_info}\nID: `{rule.id}`",
                    inline=True
                )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            embed = create_error_embed("List Failed", f"Could not list AutoMod rules: {str(e)}")
            await interaction.response.send_message(embed=embed)

    elif action.value == "clear":
        # DANGEROUS ACTION CONFIRMATION
        confirmed = await confirm_dangerous_action(
            interaction,
            "Clear All AutoMod Rules",
            "This will DELETE ALL AutoMod rules in the server. This action cannot be undone!"
        )

        if not confirmed:
            return

        try:
            rules = await interaction.guild.fetch_automod_rules()
            deleted_count = 0

            for rule in rules:
                try:
                    await rule.delete(reason=f"Mass deletion by {interaction.user}")
                    deleted_count += 1
                    await asyncio.sleep(0.5)  # Rate limit protection
                except Exception as e:
                    print(f"Failed to delete rule {rule.name}: {e}")

            embed = create_success_embed("AutoMod Rules Cleared", f"Successfully deleted **{deleted_count}** AutoMod rules", interaction.user)
            await interaction.followup.send(embed=embed)

        except Exception as e:
            embed = create_error_embed("Clear Failed", f"Could not clear AutoMod rules: {str(e)}")
            await interaction.followup.send(embed=embed)

    elif action.value == "common":
        if not preset:
            embed = create_error_embed("Missing Preset", "Please select a preset filter to apply.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer()

        try:
            # Common word filters
            common_filters = {
                "profanity": ["damn", "hell", "crap", "stupid", "idiot", "moron", "dumb"],
                "drugs": ["weed", "marijuana", "cocaine", "heroin", "meth", "drugs", "smoking"],
                "sexual": ["porn", "sex", "xxx", "adult", "nude", "naked"],
                "violence": ["kill", "murder", "die", "death", "violence", "fight"],
                "piracy": ["pirate", "crack", "torrent", "illegal", "download", "free"],
                "scam": ["scam", "free money", "click here", "win now", "congratulations"],
                "all": ["damn", "hell", "weed", "porn", "kill", "scam", "pirate", "stupid"]
            }

            if preset.value == "all":
                # Combine all filters
                words_to_add = []
                for filter_words in common_filters.values():
                    if filter_words != common_filters["all"]:  # Avoid duplicating "all"
                        words_to_add.extend(filter_words)
                # Remove duplicates
                words_to_add = list(set(words_to_add))
            else:
                words_to_add = common_filters.get(preset.value, [])

            if not words_to_add:
                embed = create_error_embed("Invalid Preset", "Selected preset not found.")
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Get existing rule or create new one
            rules = await interaction.guild.fetch_automod_rules()
            word_filter_rule = None

            for rule in rules:
                if rule.name == "Utility Core Word Filter":
                    word_filter_rule = rule
                    break

            current_keywords = []
            if word_filter_rule and word_filter_rule.trigger.keyword_filter:
                current_keywords = list(word_filter_rule.trigger.keyword_filter)

            # Add new words (avoid duplicates)
            new_words = []
            for word in words_to_add:
                if word.lower() not in [w.lower() for w in current_keywords]:
                    new_words.append(word.lower())
                    current_keywords.append(word.lower())

            if not new_words:
                embed = create_info_embed("No New Words", f"All words from the {preset.name} filter are already in the banned list.", interaction.user)
                await interaction.followup.send(embed=embed)
                return

            # Create or update rule
            trigger_metadata = discord.AutoModTriggerMetadata(keyword_filter=current_keywords)
            actions = [discord.AutoModBlockMessageAction()]

            if word_filter_rule:
                await word_filter_rule.edit(
                    trigger_metadata=trigger_metadata,
                    reason=f"Applied {preset.name} filter by {interaction.user}"
                )
                action_text = "Updated existing rule"
            else:
                word_filter_rule = await interaction.guild.create_automod_rule(
                    name="Utility Core Word Filter",
                    event_type=discord.AutoModEventType.message_send,
                    trigger_type=discord.AutoModTriggerType.keyword,
                    trigger_metadata=trigger_metadata,
                    actions=actions,
                    enabled=True,
                    reason=f"Applied {preset.name} filter by {interaction.user}"
                )
                action_text = "Created new rule"

            embed = create_success_embed("Common Filter Applied", f"Successfully applied **{preset.name}** filter!", interaction.user)
            embed.add_field(name="✨ Filter Applied", value=preset.name, inline=True)
            embed.add_field(name="📝 New Words Added", value=f"{len(new_words)} words", inline=True)
            embed.add_field(name="📊 Total Words", value=f"{len(current_keywords)} words", inline=True)
            embed.add_field(name="🔧 Action", value=action_text, inline=False)
            
            if len(new_words) <= 10:
                embed.add_field(name="📋 Added Words", value=", ".join(f"`{w}`" for w in new_words), inline=False)
            else:
                embed.add_field(name="📋 Sample Added Words", value=", ".join(f"`{w}`" for w in new_words[:10]) + f" (+{len(new_words)-10} more)", inline=False)

            await interaction.followup.send(embed=embed)
            await log_command_action(interaction, "automod common", f"Applied {preset.name} filter with {len(new_words)} new words")

        except Exception as e:
            embed = create_error_embed("Filter Application Failed", f"Could not apply common filter: {str(e)}")
            await interaction.followup.send(embed=embed)
            await report_error_to_owner(e, f"AutoMod common filter - Guild: {interaction.guild.name}")

    else:
        embed = create_error_embed("Invalid Action", "Please select a valid action.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# PREMIUM SETUP COMMAND
async def template_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete for template names from database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT template_name, description FROM custom_templates')
        templates = cursor.fetchall()
        conn.close()
        
        # Add default templates
        choices = [
            discord.app_commands.Choice(name="💻 Developer Community", value="developer"),
            discord.app_commands.Choice(name="🌊 Aquaris", value="aquaris")
        ]
        
        # Add custom templates from database
        for template_name, description in templates:
            display_name = f"🎨 {template_name.title()}"
            if len(display_name) > 100:  # Discord limit
                display_name = display_name[:97] + "..."
            choices.append(discord.app_commands.Choice(name=display_name, value=template_name))
        
        # Filter based on current input
        if current:
            choices = [choice for choice in choices if current.lower() in choice.name.lower() or current.lower() in choice.value.lower()]
        
        return choices[:25]  # Discord limit
    except:
        return [
            discord.app_commands.Choice(name="💻 Developer Community", value="developer"),
            discord.app_commands.Choice(name="🌊 Aquaris", value="aquaris")
        ]

# ENHANCED SETUP COMMAND (Interactive UI)
@bot.tree.command(name="setup", description="💎⚙️ [PREMIUM] Interactive server setup with live preview")
async def setup_interactive(interaction: discord.Interaction):
    """Interactive server setup with configuration panels and live preview"""
    
    # Enhanced cooldown and premium check
    if not await enhanced_cooldown_check()(interaction):
        return

    # Check for premium status first
    tier = get_user_tier(interaction.guild.id)
    if not tier:
        embed = create_error_embed(
            "💎 Premium Feature",
            "The `/setup` command is a **premium feature** and requires premium server status!"
        )
        embed.add_field(
            name="✨ Why Premium?",
            value="• Complete server rebuilding is resource-intensive\n• Includes advanced auto-resume capability\n• Priority support during setup\n• Access to all setup modes",
            inline=False
        )
        embed.add_field(
            name="💎 Get Premium",
            value=f"Contact <@{BOT_OWNER_ID}> to upgrade your server to premium and unlock:\n• Setup command access\n• No command cooldowns\n• Priority support\n• Exclusive features",
            inline=False
        )
        embed.add_field(
            name="🆓 Alternative",
            value="Manual server setup is available for non-premium servers using individual commands like `/enablecommunity`",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if interaction.user != interaction.guild.owner:
        embed = create_error_embed("Permission Denied", "Only the server owner can use this command!")
        embed.add_field(
            name="🔒 Restriction Reason",
            value="This command completely rebuilds the server structure and should only be used by the server owner.",
            inline=False
        )
        embed.add_field(
            name="👑 Server Owner",
            value=f"{interaction.guild.owner.mention}" if interaction.guild.owner else "Unknown",
            inline=True
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Create main setup configuration embed
    embed = create_embed(
        title="🚀 Interactive Server Setup",
        description="**Configure your complete server rebuild with interactive controls**\n\nChoose setup mode, select templates, preview changes, and confirm when ready.",
        color=COLORS['gold']
    )
    
    embed.add_field(
        name="⚠️ IMPORTANT WARNING",
        value="**This will DELETE ALL existing channels and roles!**\nThis action is IRREVERSIBLE. Use preview to see what will be created.",
        inline=False
    )
    
    embed.add_field(
        name="🎯 Setup Options",
        value="• **🚀 Advanced Setup** - 100+ roles, full features\n• **⚡ Basic Setup** - Essential roles only\n• **🎨 Custom Template** - Use saved templates",
        inline=True
    )
    
    embed.add_field(
        name="✨ Features",
        value="• **🔄 Live Preview** - See structure before building\n• **📋 Template Selection** - Choose from saved templates\n• **⚙️ Interactive Config** - Point-and-click setup\n• **💾 Auto-Resume** - Continues if interrupted",
        inline=True
    )
    
    embed.add_field(
        name="📋 Current Status",
        value="❌ **Setup Mode:** Not selected\n❌ **Template:** Not selected\n⚙️ **Ready to configure**",
        inline=False
    )
    
    embed.set_footer(text="Configure your server rebuild step by step • Premium & Server Owner Only")
    
    # Create interactive view
    view = SetupConfigView(interaction.user.id, interaction.guild.id)
    
    await interaction.response.send_message(embed=embed, view=view)
    await log_command_action(interaction, "setup", "Started interactive server setup")

# LEGACY SETUP COMMAND (parameter-based)
@bot.tree.command(name="setup_legacy", description="💎⚙️ [PREMIUM] Legacy setup with parameters")
@discord.app_commands.describe(
    setup_mode="Choose the setup mode for your server",
    template="Optional: Choose a specialized template"
)
@discord.app_commands.choices(
    setup_mode=[
        discord.app_commands.Choice(name="🚀 Advanced Setup (100+ roles, full features)", value="advanced"),
        discord.app_commands.Choice(name="⚡ Basic Setup (essential roles only)", value="basic")
    ]
)
@discord.app_commands.autocomplete(template=template_autocomplete)
async def setup(interaction: discord.Interaction, setup_mode: discord.app_commands.Choice[str], template: str = None):
    """Creates the complete Utility Core server structure with roles, channels, and permissions with resume capability"""

    # Enhanced cooldown and premium check
    if not await enhanced_cooldown_check()(interaction):
        return

    # Check for premium status first
    tier = get_user_tier(interaction.guild.id)
    if not tier:
        embed = create_error_embed(
            "💎 Premium Feature",
            "The `/setup` command is a **premium feature** and requires premium server status!"
        )
        embed.add_field(
            name="✨ Why Premium?",
            value="• Complete server rebuilding is resource-intensive\n• Includes advanced auto-resume capability\n• Priority support during setup\n• Access to all setup modes",
            inline=False
        )
        embed.add_field(
            name="💎 Get Premium",
            value=f"Contact <@{BOT_OWNER_ID}> to upgrade your server to premium and unlock:\n• Setup command access\n• No command cooldowns\n• Priority support\n• Exclusive features",
            inline=False
        )
        embed.add_field(
            name="🆓 Alternative",
            value="Manual server setup is available for non-premium servers using individual commands like `/enablecommunity`",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if interaction.user != interaction.guild.owner:
        embed = create_error_embed("Permission Denied", "Only the server owner can use this command!")
        embed.add_field(
            name="🔒 Restriction Reason",
            value="This command completely rebuilds the server structure and should only be used by the server owner.",
            inline=False
        )
        embed.add_field(
            name="👑 Server Owner",
            value=f"{interaction.guild.owner.mention}" if interaction.guild.owner else "Unknown",
            inline=True
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # DANGEROUS ACTION CONFIRMATION
    confirmed = await confirm_dangerous_action(
        interaction,
        "Complete Server Setup",
        "This will DELETE ALL existing channels and roles, then rebuild the entire server structure with Utility Core layout. This action is IRREVERSIBLE!"
    )

    if not confirmed:
        await log_command_action(interaction, "setup", "Setup cancelled by user during confirmation", False)
        return

    # Defer the interaction to prevent timeout during long setup process
    try:
        if not interaction.response.is_done():
            await interaction.response.defer()
    except discord.InteractionResponded:
        pass  # Already responded, continue

    guild = interaction.guild

    try:
        # Check for existing setup progress
        existing_progress = load_setup_progress(guild.id)

        if existing_progress:
            # Resume setup
            resume_embed = create_embed(
                title="🔄 Resuming Setup",
                description=f"Found incomplete setup from <t:{int(existing_progress.timestamp)}:R>\n⚙️ Continuing from step: **{existing_progress.step}**",
                color=COLORS['warning']
            )
            resume_embed.add_field(
                name="📊 Progress So Far",
                value=f"🗑️ Deleted: {existing_progress.deleted_channels} channels, {existing_progress.deleted_roles} roles\n" +
                      f"🎭 Created: {len(existing_progress.created_roles)} roles\n" +
                      f"📁 Created: {len(existing_progress.created_categories)} categories",
                inline=False
            )
            await interaction.followup.send(embed=resume_embed)

            # Continue from where we left off
            progress = existing_progress
            print(f"🔄 RESUMING UTILITY CORE SETUP for {guild.name} ({guild.id}) from step: {progress.step}")
        else:
            # Start new setup
            status_embed = create_embed(
                title="⚙️ Utility Core Setup Started",
                description="Setting up your server with the advanced Utility Core layout...\n⚠️ This will delete existing channels and roles!",
                color=COLORS['aqua']
            )
            status_embed.add_field(
                name="📊 Current Server Stats",
                value=f"📁 Channels: {len(guild.channels)}\n🎭 Roles: {len(guild.roles)}\n👥 Members: {guild.member_count}",
                inline=False
            )
            status_embed.add_field(
                name="💾 Auto-Save Feature",
                value="Setup progress is automatically saved and can resume if interrupted!",
                inline=False
            )
            await interaction.followup.send(embed=status_embed)

            progress = SetupProgress(guild.id)
            print(f"⚙️ UTILITY CORE SETUP STARTED for {guild.name} ({guild.id})")
            print(f"📊 Initial stats: {len(guild.channels)} channels, {len(guild.roles)} roles, {guild.member_count} members")
            print(f"👤 Requested by: {interaction.user} ({interaction.user.id})")

            # Wait a moment before starting destructive operations
            await asyncio.sleep(1)

        # STEP 1: Disable community features (if not resuming)
        if progress.step == "start":
            try:
                print("🔧 Disabling community features...")
                await guild.edit(
                    community=False,
                    rules_channel=None,
                    public_updates_channel=None
                )
                print("✅ Community features disabled")
                progress.step = "community_disabled"
                save_setup_progress(progress)
            except Exception as e:
                print(f"⚠️ Could not disable community features (might not be enabled): {e}")
                progress.step = "community_disabled"
                save_setup_progress(progress)

        # STEP 2: Delete ALL existing channels (if not already done)
        if progress.step in ["start", "community_disabled"]:
            print("🗑️ Starting channel deletion...")
            total_channels = len(guild.channels)

            # Get all channels and delete them (including categories)
            all_channels = list(guild.channels)
            print(f"🔍 Found {len(all_channels)} channels to process...")

            for i, channel in enumerate(all_channels):
                try:
                    # Delete everything except AFK channel if it's set
                    if channel != guild.afk_channel:
                        print(f"🗑️ Deleting channel {i+1}/{total_channels}: {channel.name} ({channel.type.name})")
                        await channel.delete()
                        progress.deleted_channels += 1
                        print(f"✅ Successfully deleted: {channel.name}")

                        # Save progress every 5 deletions
                        if progress.deleted_channels % 5 == 0:
                            save_setup_progress(progress)

                        await safe_sleep(0.3)  # Simple delay
                    else:
                        print(f"⏭️ Skipping AFK channel: {channel.name}")
                except Exception as e:
                    print(f"❌ Error deleting channel {channel.name}: {e}")
                    await safe_sleep(1.0)

            print(f"✅ Channel deletion complete: {progress.deleted_channels}/{total_channels} deleted successfully")
            progress.step = "channels_deleted"
            save_setup_progress(progress)

        # STEP 3: Delete ALL existing roles (if not already done)
        if progress.step in ["start", "community_disabled", "channels_deleted"]:
            print("🗑️ Starting role deletion...")
            total_roles = len(guild.roles)

            # Get all roles and delete them in reverse order (highest first)
            all_roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)
            deletable_roles = []

            print(f"🔍 Found {len(all_roles)} roles...")

            # First, identify which roles can be deleted
            for role in all_roles:
                if (role.name != "@everyone" and
                    not role.managed and
                    role != guild.me.top_role and
                    role.position < guild.me.top_role.position):
                    deletable_roles.append(role)

            print(f"🎯 Found {len(deletable_roles)} deletable roles")

            # Now delete the identified roles
            for i, role in enumerate(deletable_roles):
                try:
                    print(f"🗑️ Deleting role {i+1}/{len(deletable_roles)}: {role.name}")
                    await role.delete()
                    progress.deleted_roles += 1
                    print(f"✅ Successfully deleted: {role.name}")

                    # Save progress every 3 deletions
                    if progress.deleted_roles % 3 == 0:
                        save_setup_progress(progress)

                    await safe_sleep(0.3)  # Simple delay
                except Exception as e:
                    print(f"❌ Error deleting role {role.name}: {e}")
                    await safe_sleep(1.0)

            print(f"✅ Role deletion complete: {progress.deleted_roles}/{len(deletable_roles)} deleted successfully")
            progress.step = "roles_deleted"
            save_setup_progress(progress)

        # Wait before creating new structure
        await asyncio.sleep(2.0)

        # Initialize created_roles dictionary
        created_roles = {}

        # STEP 4: Create roles (with resume capability)
        setup_mode_value = setup_mode.value if hasattr(setup_mode, 'value') else setup_mode
        template_value = template.value if template and hasattr(template, 'value') else template

        # Determine which roles to create based on mode and template
        custom_template_data = None
        
        # Check if template is a custom template from database
        if template_value and template_value not in ["developer", "aquaris"]:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT roles_data, channels_data, settings_data FROM custom_templates WHERE template_name = ?', (template_value,))
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    custom_template_data = {
                        'roles_data': json.loads(result[0]),
                        'channels_data': json.loads(result[1]),
                        'settings_data': json.loads(result[2])
                    }
                    print(f"📋 Using custom template: {template_value}")
            except Exception as e:
                print(f"❌ Error loading custom template: {e}")
                custom_template_data = None
        
        # Determine which roles to create based on mode and template
        if custom_template_data:
            # Use custom template data
            roles_data = custom_template_data['roles_data']
        elif template_value == "developer":
            roles_data = [
                # Administration roles
                {"name": "◈⋟・OWNER」", "color": 0xff0000, "permissions": discord.Permissions.all(), "hoist": True},
                {"name": "◈⋟・CO-OWNER」", "color": 0xff1a1a, "permissions": discord.Permissions.all(), "hoist": True},
                {"name": "◈⋟・ADMIN」", "color": 0xff3333, "permissions": discord.Permissions(administrator=True), "hoist": True},
                {"name": "◈⋟・MODERATOR」", "color": 0x3399ff, "permissions": discord.Permissions(manage_messages=True, kick_members=True, ban_members=True, mute_members=True), "hoist": True},

                # Developer roles
                {"name": "◈⋟・LEAD DEVELOPER」", "color": 0x00cc00, "permissions": discord.Permissions(manage_guild=True, manage_channels=True), "hoist": True},
                {"name": "◈⋟・SENIOR DEVELOPER」", "color": 0x00ff00, "permissions": discord.Permissions(manage_channels=True), "hoist": True},
                {"name": "◈⋟・FULL STACK DEVELOPER」", "color": 0x33ff33, "permissions": discord.Permissions(manage_channels=True), "hoist": True},
                {"name": "◈⋟・BACKEND DEVELOPER」", "color": 0x66ff66, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "◈⋟・FRONTEND DEVELOPER」", "color": 0x99ff99, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "◈⋟・MOBILE DEVELOPER」", "color": 0xccffcc, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "◈⋟・GAME DEVELOPER」", "color": 0x00aa00, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "◈⋟・AI/ML DEVELOPER」", "color": 0x009900, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "◈⋟・BLOCKCHAIN DEVELOPER」", "color": 0x008800, "permissions": discord.Permissions.none(), "hoist": True},

                # Designer & Creative roles
                {"name": "◈⋟・UI/UX DESIGNER」", "color": 0xff6600, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "◈⋟・GRAPHIC DESIGNER」", "color": 0xff8000, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・3D ARTIST」", "color": 0xff9933, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・ANIMATOR」", "color": 0xffb366, "permissions": discord.Permissions.none(), "hoist": False},

                # Technical roles
                {"name": "◈⋟・DEVOPS ENGINEER」", "color": 0x8000ff, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "◈⋟・SYSTEM ADMIN」", "color": 0x9933ff, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "◈⋟・DATABASE ADMIN」", "color": 0xb366ff, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・SECURITY EXPERT」", "color": 0xb366ff, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・QA TESTER」", "color": 0xe6ccff, "permissions": discord.Permissions.none(), "hoist": False},

                # Business & Project roles
                {"name": "◈⋟・PROJECT MANAGER」", "color": 0x0066cc, "permissions": discord.Permissions(manage_channels=True), "hoist": True},
                {"name": "◈⋟・PRODUCT OWNER」", "color": 0x0080ff, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "◈⋟・BUSINESS ANALYST」", "color": 0x3399ff, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・TECHNICAL WRITER」", "color": 0x66b3ff, "permissions": discord.Permissions.none(), "hoist": False},

                # Community & Support roles
                {"name": "◈⋟・PAID USER」", "color": 0xffd700, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "◈⋟・PREMIUM USER」", "color": 0xf47fff, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "◈⋟・BETA TESTER」", "color": 0x99aab5, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・CONTRIBUTOR」", "color": 0x43b581, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・COLLABORATOR」", "color": 0x7289da, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・PARTNER」", "color": 0x5865f2, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・INVESTOR」", "color": 0x2ecc71, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・USER」", "color": 0x708090, "permissions": discord.Permissions.none(), "hoist": False},

                # Technology Stack roles
                {"name": "◈⋟・PYTHON DEV」", "color": 0x3776ab, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・JAVASCRIPT DEV」", "color": 0xf7df1e, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・JAVA DEV」", "color": 0xed8b00, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・C++ DEV」", "color": 0x00599c, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・RUST DEV」", "color": 0x000000, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・GO DEV」", "color": 0x00add8, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・PHP DEV」", "color": 0x777bb4, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・REACT DEV」", "color": 0x61dafb, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・NODE.JS DEV」", "color": 0x339933, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "◈⋟・UNITY DEV」", "color": 0x000000, "permissions": discord.Permissions.none(), "hoist": False}
            ]
        elif template_value == "aquaris":
            roles_data = [
                # Administration roles
                {"name": "♦ OWNER ♦", "color": 0xff0000, "permissions": discord.Permissions.all(), "hoist": True},
                {"name": "♦ CO-OWNER ♦", "color": 0xff1a1a, "permissions": discord.Permissions.all(), "hoist": True},
                {"name": "♦ ADMIN ♦", "color": 0xff3333, "permissions": discord.Permissions(administrator=True), "hoist": True},
                {"name": "♦ MODERATOR ♦", "color": 0x3399ff, "permissions": discord.Permissions(manage_messages=True, kick_members=True, ban_members=True, mute_members=True), "hoist": True},

                # Gaming Staff roles
                {"name": "🎮 HEAD GAME MASTER", "color": 0x9b59b6, "permissions": discord.Permissions(manage_channels=True, manage_events=True), "hoist": True},
                {"name": "🎮 GAME MASTER", "color": 0x8e44ad, "permissions": discord.Permissions(manage_events=True), "hoist": True},
                {"name": "🎮 EVENT COORDINATOR", "color": 0x663399, "permissions": discord.Permissions(manage_events=True), "hoist": True},
                {"name": "🎮 TOURNAMENT ORGANIZER", "color": 0x552288, "permissions": discord.Permissions.none(), "hoist": True},

                # Pro Gaming roles
                {"name": "👑 PRO GAMER", "color": 0xffd700, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "🏆 ESPORTS PLAYER", "color": 0xffa500, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "⭐ TOURNAMENT CHAMPION", "color": 0xff6347, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "🥇 RANKED LEGEND", "color": 0xdaa520, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "🎯 SKILLED PLAYER", "color": 0x32cd32, "permissions": discord.Permissions.none(), "hoist": True},

                # Game-specific roles
                {"name": "🎮 VALORANT PLAYER", "color": 0xff4655, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "🎮 LEAGUE OF LEGENDS", "color": 0x0596aa, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "🎮 CS2 PLAYER", "color": 0x1e3a8a, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "🎮 FORTNITE PLAYER", "color": 0x7c3aed, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "🎮 MINECRAFT PLAYER", "color": 0x16a085, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "🎮 APEX LEGENDS", "color": 0xe67e22, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "🎮 OVERWATCH PLAYER", "color": 0xf39c12, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "🎮 ROCKET LEAGUE", "color": 0x3498db, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "🎮 FIFA PLAYER", "color": 0x27ae60, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "🎮 MOBILE GAMER", "color": 0x2ecc71, "permissions": discord.Permissions.none(), "hoist": False},

                # Platform roles
                {"name": "💻 PC GAMER", "color": 0x34495e, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "🎮 CONSOLE GAMER", "color": 0x2c3e50, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "📱 MOBILE GAMER", "color": 0x95a5a6, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "👓 VR GAMER", "color": 0x9b59b6, "permissions": discord.Permissions.none(), "hoist": False},

                # Community roles
                {"name": "🏅 VETERAN GAMER", "color": 0x8b4513, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "🎊 ACTIVE PLAYER", "color": 0xcd7f32, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "🎯 CASUAL GAMER", "color": 0x708090, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "🔰 NEWBIE GAMER", "color": 0x98fb98, "permissions": discord.Permissions.none(), "hoist": False},

                # Support roles
                {"name": "💎 NITRO BOOSTER", "color": 0xf47fff, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "🤝 PARTNER", "color": 0x5865f2, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "💰 SUPPORTER", "color": 0x00ff00, "permissions": discord.Permissions.none(), "hoist": False}
            ]
        elif setup_mode_value == "advanced":
            roles_data = [
                # Administration roles
                {"name": "⤿ Owner ⸃", "color": 0xff0000, "permissions": discord.Permissions.all(), "hoist": True},
                {"name": "⤿ Co-Owner ⸃", "color": 0xff1a1a, "permissions": discord.Permissions.all(), "hoist": True},
                {"name": "⤿ Head Admin ⸃", "color": 0xff3333, "permissions": discord.Permissions(administrator=True), "hoist": True},
                {"name": "⤿ Senior Admin ⸃", "color": 0xff4d4d, "permissions": discord.Permissions(administrator=True), "hoist": True},
                {"name": "⤿ Admin ⸃", "color": 0xff6666, "permissions": discord.Permissions(administrator=True), "hoist": True},
                {"name": "⤿ Junior Admin ⸃", "color": 0xff8080, "permissions": discord.Permissions(manage_guild=True, manage_channels=True, manage_roles=True, kick_members=True, ban_members=True), "hoist": True},

                # Moderation roles
                {"name": "⤿ Head Moderator ⸃", "color": 0x0066cc, "permissions": discord.Permissions(manage_messages=True, manage_channels=True, kick_members=True, ban_members=True, mute_members=True), "hoist": True},
                {"name": "⤿ Senior Moderator ⸃", "color": 0x0080ff, "permissions": discord.Permissions(manage_messages=True, kick_members=True, ban_members=True, mute_members=True), "hoist": True},
                {"name": "⤿ Moderator ⸃", "color": 0x3399ff, "permissions": discord.Permissions(manage_messages=True, kick_members=True, mute_members=True), "hoist": True},
                {"name": "⤿ Junior Moderator ⸃", "color": 0x99ccff, "permissions": discord.Permissions(manage_messages=True, mute_members=True), "hoist": True},
                {"name": "⤿ Trial Moderator ⸃", "color": 0x99ccff, "permissions": discord.Permissions(manage_messages=True), "hoist": True},
                {"name": "⤿ Support Team ⸃", "color": 0xcce6ff, "permissions": discord.Permissions(manage_messages=True), "hoist": True},

                # Development roles
                {"name": "⤿ Lead Developer ⸃", "color": 0x00cc00, "permissions": discord.Permissions(manage_guild=True, manage_channels=True), "hoist": True},
                {"name": "⤿ Backend Developer ⸃", "color": 0x00ff00, "permissions": discord.Permissions(manage_channels=True), "hoist": True},
                {"name": "⤿ Frontend Developer ⸃", "color": 0x33ff33, "permissions": discord.Permissions(manage_channels=True), "hoist": True},
                {"name": "⤿ Bot Developer ⸃", "color": 0x66ff66, "permissions": discord.Permissions(manage_channels=True), "hoist": True},
                {"name": "⤿ Game Developer ⸃", "color": 0x99ff99, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "⤿ Web Developer ⸃", "color": 0xccffcc, "permissions": discord.Permissions.none(), "hoist": True},

                # Creative Team roles
                {"name": "⤿ Lead Designer ⸃", "color": 0xff6600, "permissions": discord.Permissions(manage_channels=True), "hoist": True},
                {"name": "⤿ Graphic Designer ⸃", "color": 0xff8000, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Builder ⸃", "color": 0xff9933, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Animator ⸃", "color": 0xffb366, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Video Editor ⸃", "color": 0xffcc99, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Content Creator ⸃", "color": 0xffe6cc, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ GFX Artist ⸃", "color": 0xff4d00, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Writer ⸃", "color": 0xff6633, "permissions": discord.Permissions.none(), "hoist": False},

                # Event Team roles
                {"name": "⤿ Event Manager ⸃", "color": 0x8000ff, "permissions": discord.Permissions(manage_events=True, manage_channels=True), "hoist": True},
                {"name": "⤿ Event Host ⸃", "color": 0x9933ff, "permissions": discord.Permissions(manage_events=True), "hoist": False},
                {"name": "⤿ Event Staff ⸃", "color": 0xb366ff, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Community Organizer ⸃", "color": 0xcc99ff, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Game Master ⸃", "color": 0xe6ccff, "permissions": discord.Permissions.none(), "hoist": False},

                # Community Ranks roles
                {"name": "⤿ Veteran ⸃", "color": 0x8b4513, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "⤿ Elite Member ⸃", "color": 0xffd700, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "⤿ Trusted Member ⸃", "color": 0xc0c0c0, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "⤿ Active Member ⸃", "color": 0xcd7f32, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "⤿ Casual Member ⸃", "color": 0x708090, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Newcomer ⸃", "color": 0x98fb98, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Platinum ⸃", "color": 0xe5e4e2, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Diamond ⸃", "color": 0xb9f2ff, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Gold ⸃", "color": 0xffd700, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Silver ⸃", "color": 0xc0c0c0, "permissions": discord.Permissions.none(), "hoist": False},

                # Leveling roles
                {"name": "⤿ Level 100+ ⸃", "color": 0xff1493, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Level 90+ ⸃", "color": 0xff69b4, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Level 80+ ⸃", "color": 0xff6347, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Level 70+ ⸃", "color": 0xff7f50, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Level 60+ ⸃", "color": 0xffa500, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Level 50+ ⸃", "color": 0xffd700, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Level 40+ ⸃", "color": 0xadff2f, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Level 30+ ⸃", "color": 0x7fff00, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Level 20+ ⸃", "color": 0x00ff7f, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Level 10+ ⸃", "color": 0x00ffff, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Level 5+ ⸃", "color": 0x87ceeb, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Level 1+ ⸃", "color": 0x4169e1, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Rising Star ⸃", "color": 0x6495ed, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Fresh Wave ⸃", "color": 0x4682b4, "permissions": discord.Permissions.none(), "hoist": False},

                # Vanity & Support roles
                {"name": "⤿ Nitro Booster ⸃", "color": 0xf47fff, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "⤿ Premium Booster ⸃", "color": 0xff4500, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "⤿ Elite Booster ⸃", "color": 0xff6600, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "⤿ Partner ⸃", "color": 0x5865f2, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "⤿ Collaborator ⸃", "color": 0x7289da, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Beta Tester ⸃", "color": 0x99aab5, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Contributor ⸃", "color": 0x43b581, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Bug Hunter ⸃", "color": 0xf04747, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Donator ⸃", "color": 0xffd700, "permissions": discord.Permissions.none(), "hoist": False},
                {"name": "⤿ Supporter ⸃", "color": 0x00ff00, "permissions": discord.Permissions.none(), "hoist": False}
            ]
        elif setup_mode_value == "basic":  # Basic mode
            roles_data = [
                # Core Administration roles only
                {"name": "⤿ Owner ⸃", "color": 0xff0000, "permissions": discord.Permissions.all(), "hoist": True},
                {"name": "⤿ Admin ⸃", "color": 0xff6666, "permissions": discord.Permissions(administrator=True), "hoist": True},
                {"name": "⤿ Moderator ⸃", "color": 0x3399ff, "permissions": discord.Permissions(manage_messages=True, kick_members=True, ban_members=True, mute_members=True), "hoist": True},
                {"name": "⤿ Helper ⸃", "color": 0x99ccff, "permissions": discord.Permissions(manage_messages=True), "hoist": True},

                # Basic Community roles
                {"name": "⤿ Veteran ⸃", "color": 0x8b4513, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "⤿ Active Member ⸃", "color": 0xcd7f32, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "⤿ Member ⸃", "color": 0x708090, "permissions": discord.Permissions.none(), "hoist": False},

                # Basic Support roles
                {"name": "⤿ Nitro Booster ⸃", "color": 0xf47fff, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "⤿ Partner ⸃", "color": 0x5865f2, "permissions": discord.Permissions.none(), "hoist": True},
                {"name": "⤿ Supporter ⸃", "color": 0x00ff00, "permissions": discord.Permissions.none(), "hoist": False}
            ]

        # Create the roles for the selected template/mode
        if roles_data:
            print(f"🎭 Creating {len(roles_data)} roles...")
            for role_data in roles_data:
                try:
                    role = await guild.create_role(
                        name=role_data["name"],
                        color=discord.Color(role_data["color"]),
                        permissions=role_data["permissions"],
                        hoist=role_data["hoist"],
                        mentionable=True
                    )
                    created_roles[role_data["name"]] = role
                    print(f"✅ Created role: {role_data['name']}")
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"❌ Failed to create role {role_data['name']}: {e}")

            progress.step = "roles_created"
            save_setup_progress(progress)
        
        # Handle channel creation based on template
        if custom_template_data:
            # Convert custom template data to expected format
            channel_structure = []
            for item in custom_template_data['channels_data']:
                if isinstance(item, dict) and 'category' in item and item['category']:
                    # This is a category with channels
                    category_data = {
                        'category': item['category'],
                        'permissions': 'public',
                        'channels': []
                    }
                    if 'channels' in item:
                        category_data['channels'] = [{'name': ch['name'], 'type': ch['type']} for ch in item['channels']]
                    channel_structure.append(category_data)
                elif isinstance(item, dict) and ('name' in item and 'type' in item):
                    # This is a standalone channel without category
                    general_cat = None
                    for cat in channel_structure:
                        if cat['category'] == 'General':
                            general_cat = cat
                            break
                    
                    if not general_cat:
                        channel_structure.append({
                            'category': 'General',
                            'permissions': 'public',
                            'channels': []
                        })
                        general_cat = channel_structure[-1]
                    
                    general_cat['channels'].append({'name': item['name'], 'type': item['type']})
        else:
            # Original channel structure for advanced/basic modes
            channel_structure = [{
                "category": "🐚 Entrance",
                "permissions": "public",
                "channels": [
                    {"name": "⤿ 💧﹒welcome ⸃", "type": "text"},
                    {"name": "⤿ 💧﹒overview ⸃", "type": "text"},
                    {"name": "⤿ 💧﹒rules ⸃", "type": "text"},
                    {"name": "⤿ 💧﹒faq ⸃", "type": "text"},
                    {"name": "⤿ 💧﹒roles ⸃", "type": "text"}
                ]
            }, {
            "category": "⚓ Announcements",
            "permissions": "public",
            "channels": [
                {"name": "⤿ 🌊﹒announcements ⸃", "type": "text"},
                {"name": "⤿ 🌊﹒events ⸃", "type": "text"},
                {"name": "⤿ 🌊﹒giveaways ⸃", "type": "text"},
                {"name": "⤿ 🌊﹒socials ⸃", "type": "text"},
                {"name": "⤿ 🌊﹒updates ⸃", "type": "text"},
                {"name": "⤿ 🌊﹒polls ⸃", "type": "text"}
            ]
        }, {
            "category": "🐠 Essentials",
            "permissions": "public",
            "channels": [
                {"name": "⤿ 🪸﹒resources ⸃", "type": "text"},
                {"name": "⤿ 🪸﹒guides ⸃", "type": "text"},
                {"name": "⤿ 🪸﹒downloads ⸃", "type": "text"},
                {"name": "⤿ 🪸﹒tutorials ⸃", "type": "text"},
                {"name": "⤿ 🪸﹒marketplace ⸃", "type": "text"}
            ]
        }, {
            "category": "🐬 Lounge",
            "permissions": "public",
            "channels": [
                {"name": "⤿ 🐚﹒chat ⸃", "type": "text"},
                {"name": "⤿ 🐚﹒memes ⸃", "type": "text"},
                {"name": "⤿ 🐚﹒media ⸃", "type": "text"},
                {"name": "⤿ 🐚﹒bot-commands ⸃", "type": "text"},
                {"name": "⤿ 🐚﹒selfies ⸃", "type": "text"},
                {"name": "⤿ 🐚﹒quotes ⸃", "type": "text"},
                {"name": "⤿ 🐚﹒level-up ⸃", "type": "text"},
                {"name": "⌬ 🐟﹒general-vc ⸃", "type": "voice"},
                {"name": "⌬ 🐟﹒chill-vc ⸃", "type": "voice"},
                {"name": "⌬ 🐟﹒afk ⸃", "type": "voice"}
            ]
        }, {
            "category": "🦑 Promotions",
            "permissions": "public",
            "channels": [
                {"name": "⤿ 🦪﹒self-promo ⸃", "type": "text"},
                {"name": "⤿ 🦪﹒commissions ⸃", "type": "text"},
                {"name": "⤿ 🦪﹒partner-ads ⸃", "type": "text"},
                {"name": "⤿ 🦪﹒price-list ⸃", "type": "text"}
            ]
        }, {
            "category": "🐳 Games",
            "permissions": "public",
            "channels": [
                {"name": "⤿ 🐙﹒gaming-lobby ⸃", "type": "text"},
                {"name": "⤿ 🐙﹒trivia ⸃", "type": "text"},
                {"name": "⤿ 🐙﹒minigames ⸃", "type": "text"},
                {"name": "⤿ 🐙﹒truth-or-dare ⸃", "type": "text"},
                {"name": "⌬ 🐋﹒squad-vc ⸃", "type": "voice"},
                {"name": "⌬ 🐋﹒team-vc ⸃", "type": "voice"}
            ]
        }, {
            "category": "🎶 Music",
            "permissions": "public",
            "channels": [
                {"name": "⌬ 🎼﹒music-1 ⸃", "type": "voice"},
                {"name": "⌬ 🎼﹒music-2 ⸃", "type": "voice"},
                {"name": "⌬ 🎼﹒music-3 ⸃", "type": "voice"},
                {"name": "⌬ 🎼﹒karaoke ⸃", "type": "voice"}
            ]
        }, {
            "category": "🐡 Support Desk",
            "permissions": "public",
            "channels": [
                {"name": "⤿ 🪼﹒ticket ⸃", "type": "text"},
                {"name": "⤿ 🪼﹒report ⸃", "type": "text"},
                {"name": "⤿ 🪼﹒appeals ⸃", "type": "text"},
                {"name": "⤿ 🪼﹒partnership ⸃", "type": "text"}
            ]
        }, {
            "category": "🎫 Special Tickets",
            "permissions": "staff",
            "channels": [
                {"name": "⤿ 🎟️﹒priority-tickets ⸃", "type": "text"},
                {"name": "⤿ 🎟️﹒staff-reports ⸃", "type": "text"},
                {"name": "⤿ 🎟️﹒ban-appeals ⸃", "type": "text"},
                {"name": "⤿ 🎟️﹒partnership ⸃", "type": "text"}
            ]
        }, {
            "category": "🦀 Staff Office",
            "permissions": "staff",
            "channels": [
                {"name": "⤿ 🐠﹒staff-announcements ⸃", "type": "text"},
                {"name": "⤿ 🐠﹒staff-chat ⸃", "type": "text"},
                {"name": "⤿ 🐠﹒staff-logs ⸃", "type": "text"},
                {"name": "⤿ 🐠﹒staff-commands ⸃", "type": "text"},
                {"name": "⤿ 🐠﹒staff-meetings ⸃", "type": "text"},
                {"name": "⌬ 🐠﹒staff-vc ⸃", "type": "voice"}
            ]
        }, {
            "category": "🐢 Creative Spaces",
            "permissions": "public",
            "channels": [
                {"name": "⤿ 🐚﹒creativity ⸃", "type": "text"},
                {"name": "⤿ 🐚﹒art-showcase ⸃", "type": "text"},
                {"name": "⤿ 🐚﹒writing-hub ⸃", "type": "text"},
                {"name": "⤿ 🐚﹒coding-lab ⸃", "type": "text"},
                {"name": "⤿ 🐚﹒photography ⸃", "type": "text"},
                {"name": "⤿ 🐚﹒ideas ⸃", "type": "text"},
                {"name": "⌬ 🐟﹒creative-vc ⸃", "type": "voice"}
            ]
        }]

        # STEP 5: Create channel structure (with resume capability)
        if progress.step in ["start", "community_disabled", "channels_deleted", "roles_deleted", "creating_roles", "roles_created"]:
            category_start_index = 0
            progress.step = "creating_channels"
            progress.total_categories = len(channel_structure)
            progress.total_channels = sum(len(structure["channels"]) for structure in channel_structure)
            progress.current_category_index = 0
            progress.current_channel_index = 0
            save_setup_progress(progress)
        else:
            # Resume channel creation
            category_start_index = progress.current_category_index
            # Rebuild created_categories from progress
            for cat_name, cat_id in progress.created_categories.items():
                category = guild.get_channel(cat_id)
                if category:
                    created_roles[cat_name] = category # Using created_roles dict to store category objects temporarily
                else:
                    print(f"⚠️ Could not find previously created category: {cat_name} ({cat_id})")
                    # If category not found, it will be recreated

        total_channels_to_create = sum(len(structure["channels"]) for structure in channel_structure)
        print(f"📁 Creating channels... Starting from category {category_start_index + 1}/{len(channel_structure)}")

        for cat_index in range(category_start_index, len(channel_structure)):
            structure = channel_structure[cat_index]
            progress.current_category_index = cat_index
            try:
                # Check if category already exists from previous run
                category = None
                if structure["category"] in progress.created_categories:
                    category_id = progress.created_categories[structure["category"]]
                    category = guild.get_channel(category_id)
                    if category:
                        print(f"📁 Using existing category: {structure['category']}")
                    else:
                        print(f"⚠️ Previously created category not found, recreating: {structure['category']}")
                        category = None

                if not category:
                    print(f"📁 Creating category {cat_index + 1}/{len(channel_structure)}: {structure['category']}")
                    category = await guild.create_category(name=structure["category"])
                    progress.created_categories[structure["category"]] = category.id
                    await safe_sleep(0.3)

                # Set up permissions - Only if roles exist
                overwrites = {}
                if structure["permissions"] == "staff":
                    # Make visible but locked for everyone, accessible for staff
                    overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=True, send_messages=False, connect=False)
                    staff_roles = ["⤿ Owner ⸃", "⤿ Co-Owner ⸃", "⤿ Head Admin ⸃", "⤿ Senior Admin ⸃", "⤿ Admin ⸃", "⤿ Junior Admin ⸃", "⤿ Head Moderator ⸃", "⤿ Senior Moderator ⸃", "⤿ Moderator ⸃", "⤿ Junior Moderator ⸃", "⤿ Trial Moderator ⸃", "⤿ Support Team ⸃"]
                    for role_name in staff_roles:
                        if role_name in created_roles and created_roles[role_name] is not None:
                            overwrites[created_roles[role_name]] = discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True)

                elif structure["permissions"] == "heads":
                    # Make visible but locked for everyone, accessible for heads only
                    overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=True, send_messages=False, connect=False)
                    head_roles = ["⤿ Owner ⸃", "⤿ Co-Owner ⸃", "⤿ Head Admin ⸃", "⤿ Senior Admin ⸃", "⤿ Admin ⸃", "⤿ Head Moderator ⸃"]
                    for role_name in head_roles:
                        if role_name in created_roles and created_roles[role_name] is not None:
                            overwrites[created_roles[role_name]] = discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True)

                # Apply permissions only if we have valid overwrites
                if overwrites and len(overwrites) > 1:  # More than just @everyone
                    try:
                        await category.edit(overwrites=overwrites)
                        print(f"✅ Set permissions for category {structure['category']}")
                    except Exception as e:
                        print(f"❌ Failed to set permissions for category {structure['category']}: {e}")
                        await report_error_to_owner(e, f"Setup category permissions - Guild: {guild.name}, Category: {structure['category']}")
                else:
                    print(f"⚠️ Skipping permissions for {structure['category']} - roles not ready yet or no specific staff roles found")

                # Create channels in this category
                print(f"📝 Creating {len(structure['channels'])} channels in {structure['category']}...")

                for chan_index, channel_data in enumerate(structure["channels"]):
                    try:
                        # Check if channel already exists
                        channel_exists = False
                        # Iterate through channels within the current category
                        for existing_channel in category.channels:
                            if existing_channel.name == channel_data["name"]:
                                print(f"  ⏭️ Channel already exists: {channel_data['name']}")
                                progress.created_channels[channel_data["name"]] = existing_channel.id
                                channel_exists = True
                                break

                        if channel_exists:
                            continue

                        print(f"  📝 Creating channel {chan_index + 1}/{len(structure['channels'])}: {channel_data['name']}")

                        new_channel = None
                        if channel_data["type"] == "text":
                            new_channel = await guild.create_text_channel(channel_data["name"], category=category)
                        elif channel_data["type"] == "voice":
                            new_channel = await guild.create_voice_channel(channel_data["name"], category=category)

                        if new_channel:
                            progress.created_channels[channel_data["name"]] = new_channel.id
                            print(f"    ✅ Created: {channel_data['name']} (ID: {new_channel.id})")

                            # Save progress every 3 channels
                            if len(progress.created_channels) % 3 == 0:
                                save_setup_progress(progress)

                        await safe_sleep(0.5)  # Slightly longer delay for stability

                    except discord.HTTPException as e:
                        if "Maximum number of channels" in str(e):
                            print(f"    ⚠️ Channel limit reached, stopping channel creation")
                            break
                        else:
                            print(f"    ❌ HTTP error creating channel {channel_data['name']}: {e}")
                            await safe_sleep(1.0)
                    except Exception as e:
                        print(f"    ❌ Failed to create channel {channel_data['name']}: {e}")
                        await safe_sleep(1.0)

                # Update progress after completing this category
                progress.current_category_index = cat_index + 1
                progress.current_channel_index = 0
                save_setup_progress(progress)

            except Exception as e:
                print(f"❌ Failed to create category {structure['category']}: {e}")
                await safe_sleep(1.0)

        print(f"✅ Successfully created {len(progress.created_categories)} categories and {len(progress.created_channels)} channels")
        progress.step = "channels_created"
        save_setup_progress(progress)

        # Create hidden Raid-Logs channel for community updates
        print("Creating Raid-Logs channel...")
        try:
            raid_logs_overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }

            # Add admin roles to view raid logs
            admin_roles = ["⤿ Owner ⸃", "⤿ Co-Owner ⸃", "⤿ Head Admin ⸃", "⤿ Senior Admin ⸃", "⤿ Admin ⸃"]
            for role_name in admin_roles:
                if role_name in created_roles:
                    raid_logs_overwrites[created_roles[role_name]] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

            await guild.create_text_channel(
                "raid-logs",
                overwrites=raid_logs_overwrites,
                reason="Aquatica setup - Community updates channel"
            )
            print(f"✅ Created hidden raid-logs channel")
        except Exception as e:
            print(f"❌ Failed to create raid-logs channel: {e}")
            await report_error_to_owner(e, f"Setup raid-logs channel - Guild: {guild.name}")

        # Create Bot and Member roles with matching theme
        print("Creating Bot and Member roles...")
        try:
            # Create Member role with theme matching
            member_role = await guild.create_role(
                name="⤿ 👥﹒Member ⸃",
                color=discord.Color(0x95a5a6),
                hoist=False,
                mentionable=True,
                reason="Setup - Member role for all users"
            )
            created_roles["⤿ 👥﹒Member ⸃"] = member_role
            print(f"✅ Created Member role")

            # Create Bot role with theme matching
            bot_role = await guild.create_role(
                name="⤿ 🤖﹒Bot ⸃",
                color=discord.Color(0x3498db),
                hoist=True,
                mentionable=False,
                reason="Setup - Bot role for all bots"
            )
            created_roles["⤿ 🤖﹒Bot ⸃"] = bot_role
            print(f"✅ Created Bot role")

            # Assign roles to all members
            member_count = 0
            bot_count = 0
            for member in guild.members:
                try:
                    if member.bot:
                        await member.add_roles(bot_role, reason="Auto-assigned Bot role")
                        bot_count += 1
                    else:
                        await member.add_roles(member_role, reason="Auto-assigned Member role")
                        member_count += 1
                    await asyncio.sleep(0.2)  # Rate limit protection
                except Exception as e:
                    print(f"Failed to assign role to {member.name}: {e}")
                    await report_error_to_owner(e, f"Setup role assignment - Guild: {guild.name}, Member: {member.name}")

            print(f"✅ Assigned Member role to {member_count} users")
            print(f"✅ Assigned Bot role to {bot_count} bots")

        except Exception as e:
            print(f"❌ Failed to create/assign member roles: {e}")
            await report_error_to_owner(e, f"Setup member roles - Guild: {guild.name}")

        # Reposition existing color roles and create role panel
        print("Repositioning existing color roles and creating role panel...")
        try:
            # Find existing color roles
            existing_color_roles = []
            color_role_names = ["⤿ Crimson ⸃", "⤿ Sapphire ⸃", "⤿ Emerald ⸃", "⤿ Amethyst ⸃", "⤿ Obsidian ⸃", "⤿ Rose ⸃", "⤿ Cyan ⸃", "⤿ Midnight ⸃", "⤿ Azure ⸃", "⤿ Coral ⸃"]

            for role_name in color_role_names:
                if role_name in created_roles:
                    existing_color_roles.append(created_roles[role_name])

            # Find the lowest staff role position to place color roles just below
            staff_role_names = ["⤿ Support Team ⸃", "⤿ Trial Moderator ⸃", "⤿ Junior Moderator ⸃"]
            lowest_staff_position = guild.me.top_role.position

            for staff_role_name in staff_role_names:
                if staff_role_name in created_roles:
                    role_obj = created_roles[staff_role_name]
                    if role_obj.position < lowest_staff_position:
                        lowest_staff_position = role_obj.position

            # Reposition color roles just below staff
            target_position = max(1, lowest_staff_position - 1)
            for i, color_role in enumerate(existing_color_roles):
                try:
                    new_position = target_position - i
                    if new_position > 0:
                        await color_role.edit(position=new_position)
                        await asyncio.sleep(0.2)
                except Exception as e:
                    print(f"Failed to reposition {color_role.name}: {e}")
                    await report_error_to_owner(e, f"Setup reposition color role - Guild: {guild.name}, Role: {color_role.name}")

            print(f"✅ Repositioned {len(existing_color_roles)} color roles below staff")

            # Create color role panel in roles channel
            roles_channel = None
            for channel in guild.text_channels:
                if "roles" in channel.name.lower() and "💧" in channel.name:
                    roles_channel = channel
                    print(f"✅ Found roles channel: {channel.name}")
                    break

            if roles_channel:
                try:
                    # Fetch guild icon asynchronously
                    avatar_data = None
                    if guild.icon:
                        avatar_data = await guild.icon.read()

                    webhook = await roles_channel.create_webhook(
                        name="Color Roles Panel",
                        avatar=avatar_data,
                        reason="Setup - Color roles panel"
                    )

                    color_panel_embed = discord.Embed(
                        title="🎨 Color Roles Panel",
                        description="React to this message to get your favorite color role!\n\n**Available Colors:**",
                        color=0x9b59b6
                    )

                    # Add color role fields with emojis
                    color_info = [
                        ("🔴", "⤿ Crimson ⸃", "Deep red elegance"),
                        ("🔵", "⤿ Sapphire ⸃", "Royal blue beauty"),
                        ("💚", "⤿ Emerald ⸃", "Natural green charm"),
                        ("💜", "⤿ Amethyst ⸃", "Purple mystique"),
                        ("⚫", "⤿ Obsidian ⸃", "Dark mystery"),
                        ("🌹", "⤿ Rose ⸃", "Pink passion"),
                        ("🩵", "⤿ Cyan ⸃", "Ocean freshness"),
                        ("🌙", "⤿ Midnight ⸃", "Night sky depth"),
                        ("☁️", "⤿ Azure ⸃", "Sky blue serenity"),
                        ("🪸", "⤿ Coral ⸃", "Warm coral glow")
                    ]

                    for emoji, role_name, description in color_info:
                        color_panel_embed.add_field(
                            name=f"{emoji} {role_name}",
                            value=description,
                            inline=True
                        )

                    color_panel_embed.add_field(
                        name="📝 How to get roles:",
                        value="React with the corresponding emoji to get that color role!\nReact again to remove the role.",
                        inline=False
                    )

                    color_panel_embed.set_footer(text=f"Color Roles • {guild.name}", icon_url=guild.icon.url if guild.icon else None)

                    panel_message = await webhook.send(embed=color_panel_embed, username="Color Roles Panel", wait=True)

                    # Add reactions for each color
                    reactions = ["🔴", "🔵", "💚", "💜", "⚫", "🌹", "🩵", "🌙", "☁️", "🪸"]
                    for reaction in reactions:
                        await panel_message.add_reaction(reaction)
                        await asyncio.sleep(0.3)

                    print(f"✅ Created color role panel in {roles_channel.name}")

                except Exception as e:
                    print(f"❌ Failed to create color role panel: {e}")
                    await report_error_to_owner(e, f"Setup color role panel - Guild: {guild.name}, Channel: {roles_channel.name}")
            else:
                print("❌ Could not find roles channel for color panel")
                print("Available channels:")
                for ch in guild.text_channels:
                    if "roles" in ch.name.lower():
                        print(f"  - Found channel with 'roles': {ch.name}")

        except Exception as e:
            print(f"❌ Failed to reposition color roles: {e}")
            await report_error_to_owner(e, f"Setup reposition color roles - Guild: {guild.name}")

        # Enable Community Features
        print("Enabling Community Features...")
        try:
            # Find rules, announcements, and raid-logs channels
            rules_channel = None
            announcements_channel = None
            raid_logs_channel = None
            faq_channel = None

            for channel in guild.text_channels:
                if "rules" in channel.name.lower():
                    rules_channel = channel
                elif "announcement" in channel.name.lower():
                    announcements_channel = channel
                elif channel.name == "raid-logs":
                    raid_logs_channel = channel
                elif "faq" in channel.name.lower():
                    faq_channel = channel

            # Use raid-logs as community updates channel if available
            community_updates_channel = raid_logs_channel if raid_logs_channel else announcements_channel

            if rules_channel and community_updates_channel:
                await guild.edit(
                    community=True,
                    rules_channel=rules_channel,
                    public_updates_channel=community_updates_channel,
                    reason="Setup - Enable community features"
                )
                print(f"✅ Enabled community features with {community_updates_channel.name} as updates channel")

                # Create server rules webhook
                try:
                    # Fetch guild icon asynchronously
                    avatar_data = None
                    if guild.icon:
                        avatar_data = await guild.icon.read()

                    webhook = await rules_channel.create_webhook(
                        name="Server Rules",
                        avatar=avatar_data,
                        reason="Setup - Rules webhook"
                    )

                    rules_embed = discord.Embed(
                        title="📋 Server Rules",
                        description="Welcome to our community! Please follow these rules to ensure a positive experience for everyone.",
                        color=0x2ecc71
                    )

                    rules_embed.add_field(
                        name="1️⃣ Be Respectful",
                        value="Treat all members with respect and kindness.",
                        inline=False
                    )
                    rules_embed.add_field(
                        name="2️⃣ No Spam",
                        value="Avoid spamming messages, links, or mentions.",
                        inline=False
                    )
                    rules_embed.add_field(
                        name="3️⃣ Appropriate Content",
                        value="Keep all content appropriate and family-friendly.",
                        inline=False
                    )
                    rules_embed.add_field(
                        name="4️⃣ Follow Discord TOS",
                        value="All Discord Terms of Service apply here.",
                        inline=False
                    )
                    rules_embed.add_field(
                        name="5️⃣ Listen to Staff",
                        value="Respect staff decisions and follow their guidance.",
                        inline=False
                    )

                    rules_embed.set_footer(text=f"Last updated • {guild.name}", icon_url=guild.icon.url if guild.icon else None)

                    await webhook.send(embed=rules_embed, username="Server Rules")
                    print(f"✅ Posted server rules via webhook")

                except Exception as e:
                    print(f"❌ Failed to create rules webhook: {e}")
                    await report_error_to_owner(e, f"Setup rules webhook - Guild: {guild.name}, Channel: {rules_channel.name}")

                # Create FAQ webhook
                if faq_channel:
                    try:
                        avatar_data = None
                        if guild.icon:
                            avatar_data = await guild.icon.read()

                        faq_webhook = await faq_channel.create_webhook(
                            name="Server FAQ",
                            avatar=avatar_data,
                            reason="Setup - FAQ webhook"
                        )

                        faq_embed = discord.Embed(
                            title="❓ Frequently Asked Questions",
                            description="Here are answers to common questions about our server!",
                            color=0x3498db
                        )

                        faq_embed.add_field(
                            name="🤔 How do I get roles?",
                            value="Check the roles channel to see available roles and how to obtain them!",
                            inline=False
                        )
                        faq_embed.add_field(
                            name="🎵 Can I use music bots?",
                            value="Yes! Use the music voice channels for listening to music with friends.",
                            inline=False
                        )
                        faq_embed.add_field(
                            name="🎮 Where can I find gaming partners?",
                            value="Visit our gaming lobby channel to find people to play with!",
                            inline=False
                        )
                        faq_embed.add_field(
                            name="🆘 How do I get help?",
                            value="Create a ticket in the support desk or ask in general chat!",
                            inline=False
                        )

                        faq_embed.set_footer(text=f"FAQ • {guild.name}", icon_url=guild.icon.url if guild.icon else None)

                        await faq_webhook.send(embed=faq_embed, username="Server FAQ")
                        print(f"✅ Posted FAQ via webhook")

                    except Exception as e:
                        print(f"❌ Failed to create FAQ webhook: {e}")
                        await report_error_to_owner(e, f"Setup FAQ webhook - Guild: {guild.name}, Channel: {faq_channel.name}")
            else:
                print(f"❌ Could not enable community - missing rules or updates channel")

        except Exception as e:
            print(f"❌ Failed to enable community features: {e}")
            await report_error_to_owner(e, f"Setup community features - Guild: {guild.name}")

        # Auto-lock specific channels and categories
        print("Auto-locking announcement channels and specific categories...")
        locked_count = 0
        try:
            categories_to_lock = ["⤿ Owner ⸃", "⤿ Co-Owner ⸃", "⤿ Head Admin ⸃", "🐢 Creative Spaces"]

            for category in guild.categories:
                # Lock announcement channels
                if "announcement" in category.name.lower():
                    for channel in category.text_channels:
                        try:
                            overwrite = channel.overwrites_for(guild.default_role)
                            overwrite.send_messages = False
                            overwrite.add_reactions = False
                            await channel.set_permissions(guild.default_role, overwrite=overwrite)
                            locked_count += 1
                            await asyncio.sleep(0.2)
                        except Exception as e:
                            print(f"Failed to lock {channel.name}: {e}")
                            await report_error_to_owner(e, f"Setup auto-lock announcement channel - Guild: {guild.name}, Channel: {channel.name}")

                # Lock specific categories (first 3 and 5th)
                if any(lock_name in category.name for lock_name in categories_to_lock):
                    for channel in category.channels:
                        try:
                            overwrite = channel.overwrites_for(guild.default_role)
                            overwrite.view_channel = False
                            await channel.set_permissions(guild.default_role, overwrite=overwrite)
                            locked_count += 1
                            await asyncio.sleep(0.2)
                        except Exception as e:
                            print(f"Failed to lock {channel.name}: {e}")
                            await report_error_to_owner(e, f"Setup auto-lock category channel - Guild: {guild.name}, Channel: {channel.name}")

            print(f"✅ Auto-locked {locked_count} channels")

        except Exception as e:
            print(f"❌ Failed to auto-lock channels: {e}")
            await report_error_to_owner(e, f"Setup auto-lock - Guild: {guild.name}")

        # Generate backup template
        print("Generating backup template...")
        try:
            template = await guild.create_template(
                name=f"{guild.name} Backup",
                description=f"Automatic backup template for {guild.name} - Generated by Utility Core Setup"
            )
            print(f"✅ Created backup template: {template.code}")

        except Exception as e:
            print(f"❌ Failed to create backup template: {e}")
            await report_error_to_owner(e, f"Setup backup template - Guild: {guild.name}")

        # Setup media-only channel system
        print("Setting up media-only channel system...")
        try:
            media_channel = None
            for channel in guild.text_channels:
                if channel.name == "⤿ 🐚﹒media ⸃":
                    media_channel = channel
                    break

            if media_channel:
                # Add to media-only channels
                if guild.id not in media_only_channels:
                    media_only_channels[guild.id] = []
                if media_channel.id not in media_only_channels[guild.id]:
                    media_only_channels[guild.id].append(media_channel.id)

                # Send setup message to media channel
                media_setup_embed = discord.Embed(
                    title="📸 Media Only Channel Configured",
                    description="🎯 **This channel is now configured for media-only!**\n\n**What's allowed:**\n• 📷 Images and photos\n• 🎥 Videos and GIFs\n• 🔗 Media links (YouTube, Imgur, etc.)\n\n**What happens to text:**\n• 🗑️ Pure text messages will be deleted\n• ⚠️ Brief warning message will appear\n\n**Share your best content!** 🌟",
                    color=0x00ff88
                )
                media_setup_embed.add_field(
                    name="📊 Server Limits",
                    value=f"• Non-Premium: {MEDIA_ONLY_LIMIT_BASIC} channels\n• Premium: Unlimited channels",
                    inline=True
                )
                media_setup_embed.add_field(
                    name="🔧 Manual Setup",
                    value="Use `/mediaonly` command to configure more channels",
                    inline=True
                )
                media_setup_embed.set_footer(text="Auto-configured by setup", icon_url=guild.icon.url if guild.icon else None)

                await media_channel.send(embed=media_setup_embed)
                print(f"✅ Configured media-only system for {media_channel.name}")

            else:
                print("⚠️ No media channel found for media-only setup")

        except Exception as e:
            print(f"❌ Failed to setup media-only system: {e}")
            await report_error_to_owner(e, f"Setup media-only - Guild: {guild.name}")

        # Setup auto-meme webhook system
        print("Setting up auto-meme system...")
        try:
            memes_channel = None
            for channel in guild.text_channels:
                if channel.name == "⤿ 🐚﹒memes ⸃":
                    memes_channel = channel
                    break

            if memes_channel:
                avatar_data = None
                if guild.icon:
                    avatar_data = await guild.icon.read()

                meme_webhook = await memes_channel.create_webhook(
                    name="Meme Bot",
                    avatar=avatar_data,
                    reason="Setup - Auto meme webhook"
                )

                # Send initial meme message
                meme_embed = discord.Embed(
                    title="🎉 Meme Channel Activated!",
                    description="This channel will automatically post random memes every 1-10 minutes!\n\nEnjoy the fun content! 😄",
                    color=0xff6b6b
                )
                meme_embed.set_footer(text="Auto-Meme System Activated")

                await meme_webhook.send(embed=meme_embed, username="Meme Bot", avatar_url=bot.user.avatar.url if bot.user.avatar else None)
                print(f"✅ Setup auto-meme system in {memes_channel.name}")

                # Store webhook for future auto-meme functionality
                auto_meme_webhooks[guild.id] = meme_webhook.url
                print(f"✅ Auto-meme webhook created: {meme_webhook.url}")

            else:
                print("❌ Could not find memes channel for auto-meme setup")

        except Exception as e:
            print(f"❌ Failed to setup auto-meme system: {e}")
            await report_error_to_owner(e, f"Setup auto-meme - Guild: {guild.name}")

        # Find the general chat channel and send greeting
        general_channel = None
        bot_commands_channel = None

        for channel in guild.text_channels:
            if channel.name == "⤿ 🐚﹒chat ⸃":
                general_channel = channel
            elif "bot" in channel.name.lower() and "command" in channel.name.lower():
                bot_commands_channel = channel

        # Send greeting in chat channel
        if general_channel:
            try:
                greeting_embed = discord.Embed(
                    title=f"👋 Welcome to {guild.name}!",
                    description="Hi everyone! The server has been successfully set up with Utility Core.\n\n🎉 Everything is ready to go!",
                    color=0x00ff88
                )
                greeting_embed.add_field(
                    name="✨ New Features",
                    value="• Auto-assigned roles\n• Color role system\n• Community features\n• Professional layout",
                    inline=True
                )
                greeting_embed.add_field(
                    name="🔧 Setup Complete",
                    value="• All channels created\n• Permissions configured\n• Backup template saved",
                    inline=True
                )
                greeting_embed.set_footer(text="Powered by Utility Core", icon_url=guild.icon.url if guild.icon else None)

                await general_channel.send(f"🎉 {interaction.user.mention} Setup Complete!", embed=greeting_embed)
                print(f"✅ Sent greeting message in {general_channel.name}")

            except Exception as e:
                print(f"❌ Failed to send greeting: {e}")
                await report_error_to_owner(e, f"Setup greeting message - Guild: {guild.name}, Channel: {general_channel.name if general_channel else 'N/A'}")

        # Clear setup progress since we're done
        clear_setup_progress(guild.id)

        # Send success message in bot commands channel
        success_channel = bot_commands_channel if bot_commands_channel else interaction.channel

        # Final success embed
        embed = create_success_embed("🎉 Utility Core Setup Complete!", "Your server has been completely rebuilt with the advanced Utility Core layout!", interaction.user)
        embed.add_field(name="🗑️ Deleted", value=f"{progress.deleted_channels} channels\n{progress.deleted_roles} roles", inline=True)
        embed.add_field(name="🎭 Created Roles", value=f"{len(created_roles)} roles", inline=True)
        embed.add_field(name="📁 Created Channels", value=f"{len(progress.created_categories)} categories\n{len(progress.created_channels)} channels", inline=True)
        embed.add_field(
            name="✨ Enhanced Features",
            value="• Complete role hierarchy\n• Auto-assigned member/bot roles\n• Color role system\n• Community features enabled\n• Auto-locked announcement channels\n• Server rules webhook\n• Backup template created\n• Media-only channel system\n• Greeting message sent",
            inline=False
        )
        embed.add_field(
            name="🔐 Auto-Locked",
            value=f"• {locked_count} channels secured\n• First 3 categories private\n• 5th category private\n• Announcement channels locked",
            inline=True
        )
        embed.add_field(
            name="🎨 Color Roles",
            value="• 10 color roles created\n• Ready for role selection\n• Automatic assignment system",
            inline=True
        )

        if success_channel == bot_commands_channel:
            embed.set_footer(text="✅ Setup completed successfully in bot commands channel")
        else:
            embed.set_footer(text="✅ Setup completed successfully")
        embed.add_field(
            name="🔧 Next Steps",
            value="• Use `/enablecommunity` to enable Discord community features\n• Use `/lockdown` for emergency server lock\n• Customize channel topics and descriptions",
            inline=False
        )
        template_info = f" with {template_value} template" if template_value else ""
        embed.add_field(
            name="⚙️ Welcome",
            value=f"Your server is now a {setup_mode_value} Utility Core community{template_info}!",
            inline=False
        )

        # Try to send completion message
        try:
            if general_channel:
                await general_channel.send(f"🎉 {interaction.user.mention} Setup Complete!", embed=embed)
                print(f"✅ Setup completion message sent to {general_channel.name}")
            else:
                # Use followup instead of DM
                await interaction.followup.send(embed=embed)
                print("✅ Setup completion message sent via followup")
        except Exception as e:
            print(f"⚠️ Could not send completion message: {e}")
            # Last resort - try followup
            try:
                await interaction.followup.send(embed=embed)
            except:
                print("❌ Could not send completion message anywhere")

        await log_command_action(
            interaction, "setup",
            f"Complete server rebuild: deleted {progress.deleted_channels} channels, {progress.deleted_roles} roles; created {len(created_roles)} roles, {len(progress.created_categories)} categories, {len(progress.created_channels)} channels"
        )

    except Exception as e:
        # For errors, try to send to any available channel or DM
        embed = create_error_embed("Setup Failed", f"An error occurred during setup\n```{str(e)}```")

        try:
            # Try to find any text channel to send error to
            error_channel = None
            for channel in guild.text_channels:
                error_channel = channel
                break

            if error_channel:
                await error_channel.send(f"{interaction.user.mention}", embed=embed)
            else:
                await interaction.user.send(embed=embed)
        except:
            # If we can't send anywhere, try the original followup (might work if channel still exists)
            try:
                await interaction.followup.send(embed=embed)
            except:
                print(f"Setup error and couldn't send error message: {e}")

        await log_command_action(interaction, "setup", f"Setup failed: {str(e)}", False)
        print(f"Setup error: {e}")
        await report_error_to_owner(e, f"Setup command failure - Guild: {interaction.guild.name}")

# ENHANCED CREATE TEMPLATE COMMAND (Interactive UI)
@bot.tree.command(name="create_template", description="🛠️ [BOT OWNER] Create custom server template with interactive setup")
async def create_template(interaction: discord.Interaction):
    """Create a custom server template using interactive embed interface"""
    
    # Bot owner only
    if interaction.user.id != BOT_OWNER_ID:
        embed = create_error_embed("Permission Denied", "Only the bot owner can create new templates.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Create main template setup embed
    embed = create_embed(
        title="📂 Server Template Setup",
        description="**Create a custom server template with interactive configuration**\n\nUse the buttons below to configure your template settings, preview the structure, and confirm creation.",
        color=COLORS['purple']
    )
    
    embed.add_field(
        name="🎯 Template Builder",
        value="• **📝 Set Name & Description** - Basic template info\n• **🎭 Edit Roles** - Configure role hierarchy\n• **📑 Edit Channels** - Setup categories and channels",
        inline=False
    )
    
    embed.add_field(
        name="✨ Features",
        value="• **🔄 Live Preview** - See structure before creating\n• **✏️ Interactive Editing** - Point-and-click configuration\n• **📊 Smart Validation** - Prevents errors",
        inline=False
    )
    
    embed.add_field(
        name="📋 Current Status",
        value="❌ **Name:** Not set\n❌ **Description:** Not set\n⚙️ **Ready to configure**",
        inline=False
    )
    
    embed.set_footer(text="Use the buttons below to get started • Bot Owner Only")
    
    # Create interactive view
    view = TemplateSetupView(interaction.user.id, interaction.guild.id)
    
    await interaction.response.send_message(embed=embed, view=view)
    await log_command_action(interaction, "create_template", "Started interactive template creation")

# LEGACY CREATE TEMPLATE COMMAND (from current server structure)
@bot.tree.command(name="create_template_from_server", description="🛠️ [BOT OWNER] Create template from current server structure")
@discord.app_commands.describe(
    template_name="Name for the new template",
    description="Description of what this template creates"
)
async def create_template_from_server(interaction: discord.Interaction, template_name: str, description: str):
    """Create a custom server template by scanning the current server structure"""
    
    # Bot owner only
    if interaction.user.id != BOT_OWNER_ID:
        embed = create_error_embed("Permission Denied", "Only the bot owner can create new templates.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        guild = interaction.guild
        
        # Validate template name
        if len(template_name) < 3 or len(template_name) > 30:
            embed = create_error_embed("Invalid Name", "Template name must be between 3-30 characters.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Check if template already exists
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM custom_templates WHERE template_name = ?', (template_name.lower(),))
        if cursor.fetchone():
            embed = create_error_embed("Template Exists", f"A template named '{template_name}' already exists.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            conn.close()
            return
        
        # Scan current server structure
        roles_data = []
        for role in guild.roles:
            if role.name != "@everyone" and not role.managed:
                roles_data.append({
                    "name": role.name,
                    "color": role.color.value,
                    "permissions": role.permissions.value,
                    "hoist": role.hoist,
                    "mentionable": role.mentionable,
                    "position": role.position
                })
        
        # Scan channel structure
        channels_data = []
        for category in guild.categories:
            category_data = {
                "category": category.name,
                "position": category.position,
                "channels": []
            }
            
            for channel in category.channels:
                if isinstance(channel, discord.TextChannel):
                    channel_type = "text"
                elif isinstance(channel, discord.VoiceChannel):
                    channel_type = "voice"
                else:
                    continue
                    
                category_data["channels"].append({
                    "name": channel.name,
                    "type": channel_type,
                    "position": channel.position
                })
            
            channels_data.append(category_data)
        
        # Add channels without categories
        for channel in guild.channels:
            if not channel.category and isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                channel_type = "text" if isinstance(channel, discord.TextChannel) else "voice"
                channels_data.append({
                    "category": None,
                    "name": channel.name,
                    "type": channel_type,
                    "position": channel.position
                })
        
        # Save template to database
        cursor.execute('''
            INSERT INTO custom_templates (template_name, description, created_by, roles_data, channels_data, settings_data)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            template_name.lower(),
            description,
            interaction.user.id,
            json.dumps(roles_data),
            json.dumps(channels_data),
            json.dumps({"main_role": None, "bot_roles": []})  # Default settings
        ))
        
        conn.commit()
        conn.close()
        
        # Success embed
        embed = create_success_embed("Template Created!", f"Successfully created template **{template_name}**", interaction.user)
        embed.add_field(name="📝 Template Name", value=f"`{template_name}`", inline=True)
        embed.add_field(name="📋 Description", value=description, inline=True)
        embed.add_field(name="🏗️ Based On", value=f"{guild.name}", inline=True)
        embed.add_field(name="🎭 Roles", value=f"{len(roles_data)} roles captured", inline=True)
        embed.add_field(name="📺 Channels", value=f"{len([c for c in channels_data if isinstance(c, dict) and 'channels' in c])} categories captured", inline=True)
        embed.add_field(name="✅ Status", value="Available in `/setup` command", inline=True)
        
        embed.add_field(
            name="🚀 Usage",
            value=f"This template is now available globally and can be used with:\n`/setup advanced {template_name}`\nor\n`/setup basic {template_name}`",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
        await log_command_action(interaction, "create_template", f"Created template '{template_name}' from {guild.name}")
        
    except Exception as e:
        embed = create_error_embed("Template Creation Failed", f"Could not create template: {str(e)}")
        await interaction.followup.send(embed=embed)
        await report_error_to_owner(e, f"Create template command - Guild: {guild.name}")

# AUTO-MEME SYSTEM
@tasks.loop(minutes=random.randint(5, 15))
async def auto_meme_poster():
    """Automatically post memes to servers with auto-meme enabled"""
    try:
        for guild_id, webhook_url in auto_meme_webhooks.items():
            try:
                guild = bot.get_guild(guild_id)
                if not guild:
                    continue

                # Create webhook object from URL
                async with aiohttp.ClientSession() as session:
                    webhook = discord.Webhook.from_url(webhook_url, session=session)

                    # Get random meme
                    meme_url = random.choice(meme_database)
                    caption = random.choice(meme_captions)

                    # Create meme embed
                    meme_embed = discord.Embed(
                        title="🎭 Auto Meme",
                        description=caption,
                        color=random.choice([0xff6b6b, 0x4ecdc4, 0x45b7d1, 0x96ceb4, 0xffd93d, 0x6c5ce7])
                    )
                    meme_embed.set_image(url=meme_url)
                    meme_embed.set_footer(text=f"Auto-Meme System • {guild.name}", icon_url=guild.icon.url if guild.icon else None)

                    # Post meme
                    await webhook.send(embed=meme_embed, username="Meme Bot", avatar_url=bot.user.avatar.url if bot.user.avatar else None)
                    print(f"🎭 Posted auto-meme in {guild.name}")

                    # Small delay between servers
                    await asyncio.sleep(2)

            except Exception as e:
                print(f"❌ Failed to post auto-meme in guild {guild_id}: {e}")
                # Remove broken webhook
                if guild_id in auto_meme_webhooks:
                    del auto_meme_webhooks[guild_id]

    except Exception as e:
        print(f"❌ Auto-meme poster error: {e}")
        await report_error_to_owner(e, "Auto-meme poster system")

@auto_meme_poster.before_loop
async def before_auto_meme_poster():
    await bot.wait_until_ready()
    # Wait a bit before starting
    await asyncio.sleep(60)

@bot.tree.command(name="automeme", description="🎭 Manage auto-meme system for your server")
async def automeme(interaction: discord.Interaction, action: str):
    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to manage auto-memes.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild = interaction.guild

    if action.lower() == "enable":
        # Find memes channel
        memes_channel = None
        for channel in guild.text_channels:
            if "memes" in channel.name.lower():
                memes_channel = channel
                break

        if not memes_channel:
            embed = create_error_embed("No Memes Channel", "Please create a channel with 'memes' in the name first.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if guild.id in auto_meme_webhooks:
            embed = create_info_embed("Already Enabled", "Auto-memes are already enabled for this server!", interaction.user)
            await interaction.response.send_message(embed=embed)
            return

        try:
            # Create webhook
            avatar_data = None
            if guild.icon:
                avatar_data = await guild.icon.read()

            webhook = await memes_channel.create_webhook(
                name="Meme Bot",
                avatar=avatar_data,
                reason=f"Auto-meme system enabled by {interaction.user}"
            )

            auto_meme_webhooks[guild.id] = webhook.url

            embed = create_success_embed("Auto-Memes Enabled!", f"Auto-memes will now post in {memes_channel.mention} every 5-15 minutes!", interaction.user)
            embed.add_field(name="📊 Frequency", value="Every 5-15 minutes", inline=True)
            embed.add_field(name="📍 Channel", value=memes_channel.mention, inline=True)
            embed.add_field(name="🎭 Memes Available", value=f"{len(meme_database)} different memes", inline=True)

            await interaction.response.send_message(embed=embed)
            await log_command_action(interaction, "automeme", f"Enabled auto-memes in {memes_channel.name}")

        except Exception as e:
            embed = create_error_embed("Setup Failed", f"Could not setup auto-memes: {str(e)}")
            await interaction.response.send_message(embed=embed)
            await report_error_to_owner(e, f"Auto-meme enable - Guild: {guild.name}")

    elif action.lower() == "disable":
        if guild.id not in auto_meme_webhooks:
            embed = create_info_embed("Not Enabled", "Auto-memes are not enabled for this server.", interaction.user)
            await interaction.response.send_message(embed=embed)
            return

        # Remove webhook
        del auto_meme_webhooks[guild.id]

        embed = create_success_embed("Auto-Memes Disabled", "Auto-memes have been disabled for this server.", interaction.user)
        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "automeme", "Disabled auto-memes")

    elif action.lower() == "status":
        if guild.id in auto_meme_webhooks:
            embed = create_embed(
                title="🎭 Auto-Meme Status",
                description="Auto-memes are **ENABLED** for this server!",
                color=COLORS['success']
            )
            embed.add_field(name="📊 Frequency", value="Every 5-15 minutes", inline=True)
            embed.add_field(name="🎭 Available Memes", value=f"{len(meme_database)}", inline=True)
            # Get next iteration time safely
            try:
                next_iter_ts = int(auto_meme_poster.next_iteration.timestamp())
                embed.add_field(name="🎯 Next Meme", value=f"<t:{next_iter_ts}:R>", inline=True)
            except Exception as e:
                print(f"Could not get next meme iteration time: {e}")
                embed.add_field(name="🎯 Next Meme", value="Calculating...", inline=True)
        else:
            embed = create_embed(
                title="🎭 Auto-Meme Status",
                description="Auto-memes are **DISABLED** for this server.",
                color=COLORS['error']
            )
            embed.add_field(name="💡 Enable", value="Use `/automeme enable` to start posting memes!", inline=False)

        await interaction.response.send_message(embed=embed)
    else:
        embed = create_error_embed("Invalid Action", "Valid actions: `enable`, `disable`, `status`")
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="postmeme", description="🎭 Manually post a random meme")
async def postmeme(interaction: discord.Interaction):
    if not await cooldown_check()(interaction):
        return

    try:
        meme_url = random.choice(meme_database)
        caption = random.choice(meme_captions)

        embed = discord.Embed(
            title="🎭 Random Meme",
            description=caption,
            color=random.choice([0xff6b6b, 0x4ecdc4, 0x45b7d1, 0x96ceb4, 0xffd93d, 0x6c5ce7])
        )
        embed.set_image(url=meme_url)
        embed.set_footer(text=f"Requested by {interaction.user.display_name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "postmeme", "Posted random meme")

    except Exception as e:
        embed = create_error_embed("Meme Failed", f"Could not post meme: {str(e)}")
        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "postmeme", f"Failed to post meme: {str(e)}", False)
        await report_error_to_owner(e, f"Postmeme command - Guild: {interaction.guild.name}")

@bot.tree.command(name="mediaonly", description="📸 Configure media-only channels")
@discord.app_commands.describe(
    action="Choose what to do with media-only channels",
    channel="The channel to configure (leave empty for current channel)"
)
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name="➕ Enable media-only for channel", value="enable"),
    discord.app_commands.Choice(name="➖ Disable media-only for channel", value="disable"),
    discord.app_commands.Choice(name="📋 List all media-only channels", value="list"),
    discord.app_commands.Choice(name="📊 Show channel status", value="status")
])
async def mediaonly(interaction: discord.Interaction, action: discord.app_commands.Choice[str], channel: discord.TextChannel = None):
    if not await cooldown_check()(interaction):
        return

    if not interaction.user.guild_permissions.manage_channels:
        embed = create_error_embed("Permission Denied", "You need `Manage Channels` permission to configure media-only channels.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild = interaction.guild
    target_channel = channel or interaction.channel

    # Initialize guild entry if not exists
    if guild.id not in media_only_channels:
        media_only_channels[guild.id] = []

    current_count = len(media_only_channels[guild.id])
    is_premium = is_premium_server(guild.id)
    limit = MEDIA_ONLY_LIMIT_PREMIUM if is_premium else MEDIA_ONLY_LIMIT_BASIC

    if action.value == "enable":
        # Check if channel is already configured
        if target_channel.id in media_only_channels[guild.id]:
            embed = create_info_embed("Already Configured", f"{target_channel.mention} is already a media-only channel.", interaction.user)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Check limits for non-premium servers
        if not is_premium and current_count >= limit:
            embed = create_error_embed(
                "Channel Limit Reached",
                f"Non-premium servers can only have **{limit}** media-only channels.\n\n💎 **Upgrade to Premium** for unlimited media-only channels!"
            )
            embed.add_field(
                name="🏢 Current Media Channels",
                value=f"{current_count}/{limit}",
                inline=True
            )
            embed.add_field(
                name="💎 Premium Benefits",
                value="• Unlimited media-only channels\n• No command cooldowns\n• Priority support",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Add channel to media-only list
        media_only_channels[guild.id].append(target_channel.id)

        # Send configuration message to the channel
        config_embed = discord.Embed(
            title="📸 Media Only Channel Activated",
            description=f"🎯 **{target_channel.mention} is now a media-only channel!**\n\n**What's allowed:**\n• 📷 Images and photos\n• 🎥 Videos and GIFs\n• 🔗 Media links (YouTube, Imgur, etc.)\n\n**What happens to text:**\n• 🗑️ Pure text messages will be deleted\n• ⚠️ Brief warning message will appear\n\n**Share your best media content!** 🌟",
            color=0x00ff88
        )
        config_embed.add_field(
            name="📊 Server Status",
            value=f"Media Channels: {len(media_only_channels[guild.id])}/{limit if not is_premium else '∞'}\nPremium: {'✅ Yes' if is_premium else '❌ No'}",
            inline=True
        )
        config_embed.add_field(
            name="🔧 Management",
            value="Use `/mediaonly disable` to remove this configuration",
            inline=True
        )
        config_embed.set_footer(text=f"Configured by {interaction.user.display_name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)

        await target_channel.send(embed=config_embed)

        # Success response
        embed = create_success_embed("Media-Only Channel Enabled", f"Successfully configured {target_channel.mention} as a media-only channel!", interaction.user)
        embed.add_field(name="📊 Total Channels", value=f"{len(media_only_channels[guild.id])}/{limit if not is_premium else '∞'}", inline=True)
        embed.add_field(name="🚫 Auto-Delete", value="Text messages will be removed", inline=True)

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "mediaonly", f"Enabled media-only for {target_channel.name}")

    elif action.value == "disable":
        if target_channel.id not in media_only_channels[guild.id]:
            embed = create_info_embed("Not Configured", f"{target_channel.mention} is not a media-only channel.", interaction.user)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Remove from media-only list
        media_only_channels[guild.id].remove(target_channel.id)

        # Send deactivation message
        deactivation_embed = discord.Embed(
            title="📸 Media-Only Disabled",
            description=f"✅ **{target_channel.mention} is no longer a media-only channel.**\n\nUsers can now send text messages normally again!",
            color=0x95a5a6
        )
        deactivation_embed.set_footer(text=f"Disabled by {interaction.user.display_name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)

        await target_channel.send(embed=deactivation_embed)

        embed = create_success_embed("Media-Only Channel Disabled", f"Removed media-only configuration from {target_channel.mention}", interaction.user)
        embed.add_field(name="📊 Remaining Channels", value=f"{len(media_only_channels[guild.id])}/{limit if not is_premium else '∞'}", inline=True)

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "mediaonly", f"Disabled media-only for {target_channel.name}")

    elif action.value == "list":
        if not media_only_channels[guild.id]:
            embed = create_info_embed("No Media-Only Channels", "This server doesn't have any media-only channels configured.", interaction.user)
            embed.add_field(
                name="💡 Get Started",
                value="Use `/mediaonly enable` to configure a channel for media-only!",
                inline=False
            )
            await interaction.response.send_message(embed=embed)
            return

        channel_list = []
        for channel_id in media_only_channels[guild.id]:
            channel_obj = guild.get_channel(channel_id)
            if channel_obj:
                channel_list.append(f"📸 {channel_obj.mention}")
            else:
                # Clean up invalid channels
                media_only_channels[guild.id].remove(channel_id)

        embed = create_embed(
            title="📸 Media-Only Channels",
            description=f"**{len(channel_list)}** media-only channels configured:",
            color=COLORS['blue']
        )

        if channel_list:
            embed.add_field(
                name="🔸 Active Channels",
                value="\n".join(channel_list[:20]),  # Limit to 20 for embed limits
                inline=False
            )

            if len(channel_list) > 20:
                embed.add_field(
                    name="➕ More",
                    value=f"... and {len(channel_list) - 20} more channels",
                    inline=False
                )

        embed.add_field(
            name="📊 Server Limits",
            value=f"**Current:** {len(channel_list)}/{limit if not is_premium else '∞'}\n**Premium:** {'✅ Yes' if is_premium else '❌ No'}",
            inline=True
        )
        embed.add_field(
            name="🔧 Management",
            value="• `/mediaonly enable` - Add channel\n• `/mediaonly disable` - Remove channel",
            inline=True
        )

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "mediaonly", f"Listed {len(channel_list)} media-only channels")

    elif action.value == "status":
        is_media_only = target_channel.id in media_only_channels[guild.id]

        embed = create_embed(
            title="📊 Media-Only Channel Status",
            description=f"Status for {target_channel.mention}",
            color=COLORS['success'] if is_media_only else COLORS['info']
        )

        embed.add_field(
            name="📸 Media-Only Status",
            value="🟢 **ENABLED**" if is_media_only else "🔴 **DISABLED**",
            inline=True
        )
        embed.add_field(
            name="🗑️ Auto-Delete Text",
            value="✅ Yes" if is_media_only else "❌ No",
            inline=True
        )
        embed.add_field(
            name="📊 Server Summary",
            value=f"**Total:** {current_count}/{limit if not is_premium else '∞'}\n**Premium:** {'✅' if is_premium else '❌'}",
            inline=True
        )

        if is_media_only:
            embed.add_field(
                name="📋 Allowed Content",
                value="• Images and videos\n• Media links\n• YouTube/Twitch URLs",
                inline=False
            )
        else:
            embed.add_field(
                name="💡 Enable Media-Only",
                value="Use `/mediaonly enable` to configure this channel!",
                inline=False
            )

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "mediaonly", f"Checked status for {target_channel.name}")

# ADVANCED ANTI-NUKE & BACKUP SYSTEM
anti_nuke_settings = {}  # {guild_id: {'enabled': bool, 'whitelist': [user_ids], 'max_actions': int, 'owner_notifications': bool, 'backup_enabled': bool, 'backup_interval': int}}
server_backups = {}  # {guild_id: [{'timestamp': int, 'data': dict, 'name': str}]}
raid_alerts = {}  # {guild_id: {'last_alert': timestamp, 'alert_count': int}}
backup_tasks = {}  # {guild_id: task}

def is_whitelisted(guild_id, user_id):
    """Check if user is whitelisted for anti-nuke"""
    if guild_id not in anti_nuke_settings:
        return False
    return user_id in anti_nuke_settings[guild_id].get('whitelist', [])

def is_premium_server(guild_id):
    """Check if server has premium features (placeholder - can be connected to payment system)"""
    # For demo purposes, return True for all servers
    # In production, this would check against a premium database/API
    premium_servers = [1234567890, 987654321]  # Example premium server IDs
    return guild_id in premium_servers or True  # Temporarily allow all servers

# Enhanced anti-nuke tracking with raid detection
user_actions = {}  # {guild_id: {user_id: {'count': int, 'last_reset': timestamp, 'actions': []}}}
ANTI_NUKE_ACTIONS = ['channel_delete', 'channel_create', 'role_delete', 'role_create', 'member_ban', 'member_kick', 'webhook_create', 'webhook_delete']
ACTION_RESET_TIME = 300  # 5 minutes
RAID_DETECTION_THRESHOLD = 3  # Actions to consider suspicious
RAID_ALERT_COOLDOWN = 1800  # 30 minutes between raid alerts

def reset_user_actions(guild_id, user_id):
    """Reset user action count"""
    if guild_id in user_actions and user_id in user_actions[guild_id]:
        user_actions[guild_id][user_id]['count'] = 0
        user_actions[guild_id][user_id]['last_reset'] = time.time()
        user_actions[guild_id][user_id]['actions'] = []

async def increment_user_action(guild_id, user_id, action_type, guild_obj=None):
    """Increment user action count and check for nuke/raid behavior"""
    if guild_id not in anti_nuke_settings:
        anti_nuke_settings[guild_id] = {'enabled': False, 'whitelist': [], 'max_actions': 5, 'owner_notifications': True, 'backup_enabled': False, 'backup_interval': 24}
    
    if not anti_nuke_settings[guild_id]['enabled']:
        return False
    
    # Initialize tracking
    if guild_id not in user_actions:
        user_actions[guild_id] = {}
    if user_id not in user_actions[guild_id]:
        user_actions[guild_id][user_id] = {'count': 0, 'last_reset': time.time(), 'actions': []}
    
    # Check if we should reset (5 minutes passed)
    current_time = time.time()
    if current_time - user_actions[guild_id][user_id]['last_reset'] > ACTION_RESET_TIME:
        reset_user_actions(guild_id, user_id)
    
    # Add action to history
    user_actions[guild_id][user_id]['actions'].append({
        'type': action_type,
        'timestamp': current_time
    })
    
    # Increment count
    user_actions[guild_id][user_id]['count'] += 1
    
    # Check for raid behavior (even for whitelisted users - notify owner)
    if user_actions[guild_id][user_id]['count'] >= RAID_DETECTION_THRESHOLD:
        await notify_owner_of_suspicious_activity(guild_obj, user_id, action_type, user_actions[guild_id][user_id])
    
    # Check if limit exceeded for non-whitelisted users
    if not is_whitelisted(guild_id, user_id):
        max_actions = anti_nuke_settings[guild_id].get('max_actions', 5)
        if user_actions[guild_id][user_id]['count'] >= max_actions:
            return True  # Trigger anti-nuke
    
    return False

async def create_server_backup(guild):
    """Create a comprehensive server backup"""
    try:
        backup_data = {
            'guild_info': {
                'name': guild.name,
                'description': guild.description,
                'verification_level': str(guild.verification_level),
                'default_notifications': str(guild.default_notifications),
                'explicit_content_filter': str(guild.explicit_content_filter),
                'icon_url': str(guild.icon.url) if guild.icon else None,
                'banner_url': str(guild.banner.url) if guild.banner else None
            },
            'channels': [],
            'categories': [],
            'roles': [],
            'timestamp': int(time.time())
        }
        
        # Backup categories
        for category in guild.categories:
            backup_data['categories'].append({
                'name': category.name,
                'position': category.position,
                'overwrites': [{'id': overwrite[0].id, 'type': str(type(overwrite[0])), 'allow': overwrite[1].allow.value, 'deny': overwrite[1].deny.value} for overwrite in category.overwrites.items()]
            })
        
        # Backup channels
        for channel in guild.channels:
            if isinstance(channel, discord.TextChannel):
                channel_data = {
                    'name': channel.name,
                    'type': 'text',
                    'category': channel.category.name if channel.category else None,
                    'position': channel.position,
                    'topic': channel.topic,
                    'slowmode_delay': channel.slowmode_delay,
                    'nsfw': channel.nsfw,
                    'overwrites': [{'id': overwrite[0].id, 'type': str(type(overwrite[0])), 'allow': overwrite[1].allow.value, 'deny': overwrite[1].deny.value} for overwrite in channel.overwrites.items()]
                }
            elif isinstance(channel, discord.VoiceChannel):
                channel_data = {
                    'name': channel.name,
                    'type': 'voice',
                    'category': channel.category.name if channel.category else None,
                    'position': channel.position,
                    'bitrate': channel.bitrate,
                    'user_limit': channel.user_limit,
                    'overwrites': [{'id': overwrite[0].id, 'type': str(type(overwrite[0])), 'allow': overwrite[1].allow.value, 'deny': overwrite[1].deny.value} for overwrite in channel.overwrites.items()]
                }
            else:
                continue
            
            backup_data['channels'].append(channel_data)
        
        # Backup roles
        for role in guild.roles:
            if role.name != "@everyone":
                backup_data['roles'].append({
                    'name': role.name,
                    'color': role.color.value,
                    'hoist': role.hoist,
                    'mentionable': role.mentionable,
                    'permissions': role.permissions.value,
                    'position': role.position
                })
        
        # Store backup
        if guild.id not in server_backups:
            server_backups[guild.id] = []
        
        # Check if premium for backup limits
        is_premium = is_premium_server(guild.id)
        max_backups = 20 if is_premium else 10
        
        # Add new backup
        backup_name = f"Auto-Backup-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        server_backups[guild.id].append({
            'name': backup_name,
            'timestamp': backup_data['timestamp'],
            'data': backup_data
        })
        
        # Remove old backups if over limit
        if len(server_backups[guild.id]) > max_backups:
            server_backups[guild.id] = server_backups[guild.id][-max_backups:]
        
        print(f"📄 Created backup for {guild.name}: {backup_name}")
        return True
        
    except Exception as e:
        print(f"❌ Backup creation failed for {guild.name}: {e}")
        return False

async def notify_owner_of_suspicious_activity(guild, user_id, action_type, action_data):
    """Notify server owner of suspicious activity"""
    try:
        if not guild or not guild.owner:
            return
        
        guild_id = guild.id
        current_time = time.time()
        
        # Check cooldown to prevent spam
        if guild_id in raid_alerts:
            if current_time - raid_alerts[guild_id]['last_alert'] < RAID_ALERT_COOLDOWN:
                return
        else:
            raid_alerts[guild_id] = {'last_alert': 0, 'alert_count': 0}
        
        # Update alert tracking
        raid_alerts[guild_id]['last_alert'] = current_time
        raid_alerts[guild_id]['alert_count'] += 1
        
        user = guild.get_member(user_id) or bot.get_user(user_id)
        user_name = user.display_name if hasattr(user, 'display_name') else str(user) if user else f"User {user_id}"
        
        # Check if owner notifications are enabled
        if guild_id not in anti_nuke_settings or not anti_nuke_settings[guild_id].get('owner_notifications', True):
            return
        
        # Create DM embed
        embed = discord.Embed(
            title="🚨 SUSPICIOUS ACTIVITY DETECTED",
            description=f"**Server:** {guild.name}\n**Potential Raid Alert #{raid_alerts[guild_id]['alert_count']}**",
            color=COLORS['error'],
            timestamp=discord.utils.utcnow()
        )
        
        # User info
        is_whitelisted_user = is_whitelisted(guild_id, user_id)
        whitelist_status = "⚠️ **WHITELISTED USER**" if is_whitelisted_user else "❌ **NOT WHITELISTED**"
        
        embed.add_field(
            name="👤 Suspicious User",
            value=f"**Name:** {user_name}\n**ID:** {user_id}\n**Status:** {whitelist_status}",
            inline=False
        )
        
        # Activity details
        action_list = []
        for action in action_data['actions'][-5:]:  # Last 5 actions
            time_ago = int(current_time - action['timestamp'])
            action_list.append(f"• {action['type'].replace('_', ' ').title()} ({time_ago}s ago)")
        
        embed.add_field(
            name="⚡ Recent Actions",
            value=f"**Count:** {action_data['count']} actions in 5 minutes\n" + "\n".join(action_list),
            inline=False
        )
        
        # Recommendations
        recommendations = []
        if is_whitelisted_user:
            recommendations.append("• Review whitelist - trusted user acting suspiciously")
            recommendations.append("• Consider temporary removal from whitelist")
        else:
            recommendations.append("• User will be automatically restricted")
            recommendations.append("• Consider manual intervention if needed")
        
        recommendations.append("• Monitor server for additional suspicious activity")
        recommendations.append(f"• Use `/antinuke activity` to view full activity log")
        
        embed.add_field(
            name="💡 Recommendations",
            value="\n".join(recommendations),
            inline=False
        )
        
        embed.add_field(
            name="🛡️ Protection Status",
            value=f"**Anti-nuke:** {'✅ Enabled' if anti_nuke_settings[guild_id]['enabled'] else '❌ Disabled'}\n**Auto-backup:** {'✅ Active' if anti_nuke_settings[guild_id].get('backup_enabled', False) else '❌ Inactive'}",
            inline=True
        )
        
        # Send DM to owner
        try:
            await guild.owner.send(embed=embed)
            print(f"🚨 Sent raid alert to {guild.owner} for {guild.name}")
        except discord.Forbidden:
            # Try to send to a log channel if DM fails
            log_channel = None
            for channel in guild.text_channels:
                if any(keyword in channel.name.lower() for keyword in ["log", "audit", "mod", "admin", "owner", "antinuke"]):
                    log_channel = channel
                    break
            
            if log_channel:
                embed.add_field(name="⚠️ Notice", value="Could not DM server owner - posting here instead", inline=False)
                await log_channel.send(f"{guild.owner.mention}", embed=embed)
        
    except Exception as e:
        print(f"❌ Failed to send raid alert: {e}")

async def trigger_anti_nuke(guild, user, action_type):
    """Trigger anti-nuke protection with advanced response"""
    try:
        member = guild.get_member(user.id)
        actions_taken = []
        
        if member:
            # Remove dangerous permissions
            dangerous_roles = []
            for role in member.roles:
                if (role.permissions.administrator or role.permissions.manage_guild or 
                    role.permissions.manage_channels or role.permissions.manage_roles or
                    role.permissions.ban_members or role.permissions.kick_members):
                    dangerous_roles.append(role)
            
            if dangerous_roles:
                await member.remove_roles(*dangerous_roles, reason="🚨 Anti-nuke protection triggered")
                actions_taken.append(f"Removed {len(dangerous_roles)} dangerous roles")
            
            # Timeout user for 10 minutes
            try:
                await member.timeout(datetime.timedelta(minutes=10), reason="🚨 Anti-nuke protection - suspicious activity")
                actions_taken.append("Applied 10-minute timeout")
            except:
                pass
        
        # Create emergency backup if not recent
        if guild.id not in server_backups or not server_backups[guild.id]:
            if await create_server_backup(guild):
                actions_taken.append("Created emergency server backup")
        
        # Log to server
        log_channel = None
        for channel in guild.text_channels:
            if any(keyword in channel.name.lower() for keyword in ["log", "audit", "mod", "admin", "antinuke"]):
                log_channel = channel
                break
        
        if log_channel:
            embed = discord.Embed(
                title="🚨 ANTI-NUKE PROTECTION ACTIVATED",
                description=f"**Threat Detected:** {action_type}\n**User:** {user.mention} ({user})\n**User ID:** {user.id}",
                color=COLORS['error'],
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="⚡ Trigger Details",
                value=f"**Actions:** {user_actions[guild.id][user.id]['count']} in 5 minutes\n**Threshold:** {anti_nuke_settings[guild.id].get('max_actions', 5)}",
                inline=False
            )
            
            embed.add_field(
                name="🛡️ Actions Taken",
                value="\n".join([f"• {action}" for action in actions_taken]) if actions_taken else "• User flagged in system",
                inline=False
            )
            
            embed.add_field(
                name="📋 Next Steps",
                value="• Owner has been notified\n• User activity is being monitored\n• Consider manual review if needed\n• Use `/antinuke activity` for details",
                inline=False
            )
            
            await log_channel.send(embed=embed)
        
        # Always notify owner
        await notify_owner_of_suspicious_activity(guild, user.id, f"ANTI-NUKE TRIGGERED: {action_type}", user_actions[guild.id][user.id])
        
        print(f"🚨 Anti-nuke activated for {user} in {guild.name}: {', '.join(actions_taken)}")
        
    except Exception as e:
        print(f"❌ Anti-nuke error: {e}")

# Automatic backup scheduler
async def start_backup_scheduler():
    """Start automatic backup scheduling for all guilds"""
    while True:
        try:
            for guild_id, settings in anti_nuke_settings.items():
                if settings.get('backup_enabled', False):
                    guild = bot.get_guild(guild_id)
                    if guild:
                        # Check if it's time for backup
                        interval_hours = settings.get('backup_interval', 24)
                        last_backup_time = 0
                        
                        if guild_id in server_backups and server_backups[guild_id]:
                            last_backup_time = server_backups[guild_id][-1]['timestamp']
                        
                        current_time = time.time()
                        if current_time - last_backup_time >= (interval_hours * 3600):
                            await create_server_backup(guild)
                            print(f"📄 Auto-backup completed for {guild.name}")
            
            # Wait 1 hour before checking again
            await asyncio.sleep(3600)
            
        except Exception as e:
            print(f"❌ Backup scheduler error: {e}")
            await asyncio.sleep(3600)

# ADVANCED ANTI-NUKE COMMAND SYSTEM - SPLIT INTO SEPARATE COMMANDS

@bot.tree.command(name="antinuke_enable", description="🛡️ Enable advanced anti-nuke protection")
async def antinuke_enable(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        embed = create_error_embed("Permission Denied", "You need Administrator permission to manage anti-nuke.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild_id = interaction.guild.id
    if guild_id not in anti_nuke_settings:
        anti_nuke_settings[guild_id] = {
            'enabled': False, 'whitelist': [], 'max_actions': 5, 
            'owner_notifications': True, 'backup_enabled': False, 'backup_interval': 24
        }

    protection_emoji = get_custom_emoji('protection', '🛡️')
    anti_nuke_settings[guild_id]['enabled'] = True
    embed = create_success_embed(f"{protection_emoji} Anti-Nuke Protection Activated", "Advanced server protection is now **ACTIVE**!", interaction.user)
    embed.add_field(
        name=f"{protection_emoji} Protection Features", 
        value="• **Real-time threat detection**\n• **Automatic permission removal**\n• **Owner raid notifications**\n• **Emergency backup creation**\n• **Advanced audit logging**", 
        inline=False
    )
    embed.add_field(
        name="⚙️ Current Configuration",
        value=f"**Max Actions:** {anti_nuke_settings[guild_id]['max_actions']}\n**Whitelisted Users:** {len(anti_nuke_settings[guild_id]['whitelist'])}\n**Owner Alerts:** {'✅' if anti_nuke_settings[guild_id]['owner_notifications'] else '❌'}\n**Auto-Backup:** {'✅' if anti_nuke_settings[guild_id]['backup_enabled'] else '❌'}",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "antinuke_enable", "Enabled anti-nuke protection")

@bot.tree.command(name="antinuke_disable", description="❌ Disable anti-nuke protection")
async def antinuke_disable(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        embed = create_error_embed("Permission Denied", "You need Administrator permission to manage anti-nuke.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild_id = interaction.guild.id
    if guild_id not in anti_nuke_settings:
        anti_nuke_settings[guild_id] = {
            'enabled': False, 'whitelist': [], 'max_actions': 5, 
            'owner_notifications': True, 'backup_enabled': False, 'backup_interval': 24
        }

    anti_nuke_settings[guild_id]['enabled'] = False
    embed = create_success_embed("❌ Anti-Nuke Protection Disabled", "Server protection has been **DEACTIVATED**.", interaction.user)
    embed.add_field(name="⚠️ Critical Warning", value="Your server is now **VULNERABLE** to:\n• Mass channel deletion\n• Role destruction\n• Mass bans/kicks\n• Permission escalation attacks", inline=False)
    
    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "antinuke_disable", "Disabled anti-nuke protection")

@bot.tree.command(name="antinuke_config", description="⚙️ Configure anti-nuke protection settings")
@discord.app_commands.describe(
    max_actions="Maximum actions before triggering protection (1-20)",
    backup_interval="Backup interval in hours (Premium: 1-24, Free: 24 only)",
    enable_backup="Enable automatic server backups",
    reset_activity="Reset all user action counts"
)
async def antinuke_config(interaction: discord.Interaction, max_actions: int = None, backup_interval: int = None, enable_backup: bool = None, reset_activity: bool = False):
    if not interaction.user.guild_permissions.administrator:
        embed = create_error_embed("Permission Denied", "You need Administrator permission to manage anti-nuke.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild_id = interaction.guild.id
    if guild_id not in anti_nuke_settings:
        anti_nuke_settings[guild_id] = {
            'enabled': False, 'whitelist': [], 'max_actions': 5, 
            'owner_notifications': True, 'backup_enabled': False, 'backup_interval': 24
        }

    settings = anti_nuke_settings[guild_id]
    changes_made = []

    if max_actions is not None:
        if max_actions < 1 or max_actions > 20:
            embed = create_error_embed("Invalid Range", "Maximum actions must be between 1 and 20.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        else:
            settings['max_actions'] = max_actions
            changes_made.append(f"Action threshold: **{max_actions}**")

    if backup_interval is not None:
        is_premium = is_premium_server(guild_id)
        if not is_premium and backup_interval != 24:
            embed = create_error_embed("Premium Required", "Custom backup intervals require premium subscription.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        elif is_premium and (backup_interval < 1 or backup_interval > 24):
            embed = create_error_embed("Invalid Interval", "Premium users can set intervals between 1-24 hours.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        else:
            settings['backup_interval'] = backup_interval
            changes_made.append(f"Backup interval: **{backup_interval}h**")

    if enable_backup is not None:
        settings['backup_enabled'] = enable_backup
        if enable_backup and guild_id not in backup_tasks:
            asyncio.create_task(start_backup_scheduler())
        changes_made.append(f"Auto-backup: **{'Enabled' if enable_backup else 'Disabled'}**")

    if reset_activity:
        if guild_id in user_actions:
            user_actions[guild_id] = {}
        changes_made.append("Activity counts: **Reset**")

    if changes_made:
        embed = create_success_embed("⚙️ Configuration Updated", f"Anti-nuke settings have been updated successfully!", interaction.user)
        embed.add_field(name="🔧 Changes Made", value="\n".join(f"• {change}" for change in changes_made), inline=False)
    else:
        # Show current status
        protection_status = "🟢 **ACTIVE**" if settings['enabled'] else "🔴 **INACTIVE**"
        
        embed = create_embed(
            title=f"{get_custom_emoji('protection', '🛡️')} Anti-Nuke Configuration",
            description=f"**Server:** {interaction.guild.name}\n**Protection:** {protection_status}",
            color=COLORS['success'] if settings['enabled'] else COLORS['error']
        )
        
        embed.add_field(name="🔋 Protection Status", value=protection_status, inline=True)
        embed.add_field(name="⚙️ Action Threshold", value=f"{settings['max_actions']} actions", inline=True)
        embed.add_field(name="👥 Whitelisted Users", value=f"{len(settings['whitelist'])}", inline=True)
        
        embed.add_field(name="📬 Owner Notifications", value="✅ Enabled" if settings['owner_notifications'] else "❌ Disabled", inline=True)
        embed.add_field(name="💾 Auto-Backup", value="✅ Enabled" if settings.get('backup_enabled', False) else "❌ Disabled", inline=True)
        embed.add_field(name="⏰ Backup Interval", value=f"{settings.get('backup_interval', 24)}h", inline=True)
        
        # Show backup status
        backup_count = len(server_backups.get(guild_id, []))
        is_premium = is_premium_server(guild_id)
        max_backups = 20 if is_premium else 10
        
        last_backup_text = 'Never' if not server_backups.get(guild_id) else f'<t:{server_backups[guild_id][-1]["timestamp"]}:R>'
        plan_text = '🥇 Premium' if is_premium else '🆓 Free'
        
        embed.add_field(
            name="📄 Backup Status",
            value=f"**Stored:** {backup_count}/{max_backups} backups\n**Plan:** {plan_text}\n**Last Backup:** {last_backup_text}",
            inline=False
        )

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "antinuke_config", f"Configuration changes: {', '.join(changes_made) if changes_made else 'Viewed status'}")


# WHITELIST MANAGEMENT COMMANDS  
@bot.tree.command(name="whitelist", description="👥 Manage anti-nuke whitelist")
@discord.app_commands.describe(
    action="Whitelist action to perform",
    user="User to add/remove from whitelist"
)
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name="➕ Add User", value="add"),
    discord.app_commands.Choice(name="➖ Remove User", value="remove"),
    discord.app_commands.Choice(name="📋 List All", value="list"),
    discord.app_commands.Choice(name="🔄 Clear All", value="clear")
])
async def whitelist(interaction: discord.Interaction, action: discord.app_commands.Choice[str], user: discord.Member = None):
    if not interaction.user.guild_permissions.administrator:
        embed = create_error_embed("Permission Denied", "You need Administrator permission to manage whitelist.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild_id = interaction.guild.id
    if guild_id not in anti_nuke_settings:
        anti_nuke_settings[guild_id] = {
            'enabled': False, 'whitelist': [], 'max_actions': 5,
            'owner_notifications': True, 'backup_enabled': False, 'backup_interval': 24
        }

    if action.value == "add":
        if not user:
            embed = create_error_embed("Missing User", "Please specify a user to add to the whitelist.")
        else:
            if user.id not in anti_nuke_settings[guild_id]['whitelist']:
                anti_nuke_settings[guild_id]['whitelist'].append(user.id)
                embed = create_success_embed("✅ User Whitelisted", f"**{user.display_name}** is now **EXEMPT** from anti-nuke protection", interaction.user)
                embed.add_field(name="⚠️ Important", value="Whitelisted users can still trigger owner notifications if they perform suspicious actions.", inline=False)
                embed.add_field(name="👥 Total Whitelisted", value=f"{len(anti_nuke_settings[guild_id]['whitelist'])} users", inline=True)
            else:
                embed = create_info_embed("Already Whitelisted", f"**{user.display_name}** is already on the whitelist.", interaction.user)
    
    elif action.value == "remove":
        if not user:
            embed = create_error_embed("Missing User", "Please specify a user to remove from the whitelist.")
        else:
            if user.id in anti_nuke_settings[guild_id]['whitelist']:
                anti_nuke_settings[guild_id]['whitelist'].remove(user.id)
                embed = create_success_embed("❌ User Removed", f"**{user.display_name}** removed from whitelist and is now **PROTECTED AGAINST**", interaction.user)
                embed.add_field(name="👥 Remaining Whitelisted", value=f"{len(anti_nuke_settings[guild_id]['whitelist'])} users", inline=True)
            else:
                embed = create_info_embed("Not Whitelisted", f"**{user.display_name}** is not on the whitelist.", interaction.user)
    
    elif action.value == "list":
        whitelist = anti_nuke_settings[guild_id]['whitelist']
        if not whitelist:
            embed = create_info_embed("Empty Whitelist", "No users are currently whitelisted for anti-nuke protection.", interaction.user)
        else:
            embed = create_embed(
                title="👥 Anti-Nuke Whitelist",
                description=f"**{len(whitelist)}** users exempt from protection",
                color=COLORS['blue']
            )
            
            whitelist_chunks = []
            for i in range(0, len(whitelist), 10):
                chunk = whitelist[i:i+10]
                user_list = []
                
                for user_id in chunk:
                    user_obj = interaction.guild.get_member(user_id)
                    if user_obj:
                        user_list.append(f"• {user_obj.mention} **({user_obj.display_name})**")
                    else:
                        user_list.append(f"• <@{user_id}> **(User left server)**")
                
                whitelist_chunks.append("\n".join(user_list))
            
            for i, chunk in enumerate(whitelist_chunks[:3]):  # Show max 3 chunks (30 users)
                embed.add_field(
                    name=f"📋 Users {i*10+1}-{min((i+1)*10, len(whitelist))}",
                    value=chunk,
                    inline=False
                )
            
            if len(whitelist) > 30:
                embed.add_field(name="➕ Additional", value=f"... and {len(whitelist) - 30} more users", inline=False)
            
            embed.add_field(
                name="⚠️ Notice",
                value="Whitelisted users bypass automatic restrictions but owner is still notified of suspicious activity.",
                inline=False
            )
    
    elif action.value == "clear":
        if not anti_nuke_settings[guild_id]['whitelist']:
            embed = create_info_embed("Already Empty", "The whitelist is already empty.", interaction.user)
        else:
            count = len(anti_nuke_settings[guild_id]['whitelist'])
            anti_nuke_settings[guild_id]['whitelist'] = []
            embed = create_success_embed("🔄 Whitelist Cleared", f"Removed **{count}** users from the whitelist. All users are now subject to anti-nuke protection.", interaction.user)
    
    else:
        embed = create_error_embed("Invalid Action", "Please select a valid action from the dropdown menu.")

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "whitelist", f"Action: {action.value} {'for ' + user.display_name if user else ''}")

# SERVER RESTORATION SYSTEM
async def restore_server_from_backup(guild, backup_data, interaction):
    """Restore server from backup data"""
    try:
        restored_items = {'channels': 0, 'categories': 0, 'roles': 0, 'errors': []}
        
        # First, delete existing channels and categories (except system channels)
        for channel in guild.channels:
            if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel)):
                continue
            if channel.name.lower() in ['general', 'system messages']:
                continue
            try:
                await channel.delete(reason="🔄 Server restoration - cleaning up")
            except:
                pass
        
        # Delete existing roles (except @everyone and bot roles)
        for role in guild.roles:
            if role.name in ['@everyone'] or role.managed:
                continue
            try:
                await role.delete(reason="🔄 Server restoration - cleaning up")
            except:
                pass
        
        # Restore roles first
        role_mapping = {}
        for role_data in backup_data['roles']:
            try:
                new_role = await guild.create_role(
                    name=role_data['name'],
                    color=discord.Color(role_data['color']),
                    hoist=role_data['hoist'],
                    mentionable=role_data['mentionable'],
                    permissions=discord.Permissions(role_data['permissions']),
                    reason="🔄 Server restoration - restoring roles"
                )
                role_mapping[role_data['name']] = new_role
                restored_items['roles'] += 1
            except Exception as e:
                restored_items['errors'].append(f"Role '{role_data['name']}': {str(e)}")
        
        # Restore categories
        category_mapping = {}
        for cat_data in backup_data['categories']:
            try:
                overwrites = {}
                for overwrite_data in cat_data['overwrites']:
                    if overwrite_data['type'] == "<class 'discord.member.Member'>":
                        target = guild.get_member(overwrite_data['id'])
                    else:
                        target = guild.get_role(overwrite_data['id'])
                    
                    if target:
                        overwrites[target] = discord.PermissionOverwrite.from_pair(
                            discord.Permissions(overwrite_data['allow']),
                            discord.Permissions(overwrite_data['deny'])
                        )
                
                new_category = await guild.create_category(
                    name=cat_data['name'],
                    overwrites=overwrites,
                    position=cat_data['position'],
                    reason="🔄 Server restoration - restoring categories"
                )
                category_mapping[cat_data['name']] = new_category
                restored_items['categories'] += 1
            except Exception as e:
                restored_items['errors'].append(f"Category '{cat_data['name']}': {str(e)}")
        
        # Restore channels
        for channel_data in backup_data['channels']:
            try:
                category = category_mapping.get(channel_data['category'])
                
                overwrites = {}
                for overwrite_data in channel_data['overwrites']:
                    if overwrite_data['type'] == "<class 'discord.member.Member'>":
                        target = guild.get_member(overwrite_data['id'])
                    else:
                        target = guild.get_role(overwrite_data['id'])
                    
                    if target:
                        overwrites[target] = discord.PermissionOverwrite.from_pair(
                            discord.Permissions(overwrite_data['allow']),
                            discord.Permissions(overwrite_data['deny'])
                        )
                
                if channel_data['type'] == 'text':
                    await guild.create_text_channel(
                        name=channel_data['name'],
                        category=category,
                        topic=channel_data.get('topic'),
                        slowmode_delay=channel_data.get('slowmode_delay', 0),
                        nsfw=channel_data.get('nsfw', False),
                        overwrites=overwrites,
                        position=channel_data['position'],
                        reason="🔄 Server restoration - restoring text channels"
                    )
                elif channel_data['type'] == 'voice':
                    await guild.create_voice_channel(
                        name=channel_data['name'],
                        category=category,
                        bitrate=channel_data.get('bitrate', 64000),
                        user_limit=channel_data.get('user_limit', 0),
                        overwrites=overwrites,
                        position=channel_data['position'],
                        reason="🔄 Server restoration - restoring voice channels"
                    )
                
                restored_items['channels'] += 1
                
            except Exception as e:
                restored_items['errors'].append(f"Channel '{channel_data['name']}': {str(e)}")
        
        return restored_items
        
    except Exception as e:
        print(f"❌ Restoration error: {e}")
        return None

@bot.tree.command(name="denuke", description="🔄 Restore server from backup (EMERGENCY ONLY)")
@discord.app_commands.describe(backup_name="Backup to restore from (leave empty to see available backups)")
async def denuke(interaction: discord.Interaction, backup_name: str = None):
    if not interaction.user.guild_permissions.administrator:
        embed = create_error_embed("Permission Denied", "You need Administrator permission to restore server backups.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Extra safety check - only server owner can use this
    if interaction.user.id != interaction.guild.owner_id:
        embed = create_error_embed("Owner Only", "🚨 **CRITICAL COMMAND** - Only the server owner can restore from backups for security reasons.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild_id = interaction.guild.id
    
    if guild_id not in server_backups or not server_backups[guild_id]:
        embed = create_error_embed("No Backups", "No server backups are available. Use `/antinuke backup_now` to create your first backup.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # If no backup name provided, show available backups
    if not backup_name:
        backups = server_backups[guild_id]
        embed = create_embed(
            title="📄 Available Server Backups",
            description=f"**{len(backups)}** backups available for **{interaction.guild.name}**",
            color=COLORS['blue']
        )
        
        backup_list = []
        for i, backup in enumerate(reversed(backups[-10:])):  # Show last 10 backups
            timestamp = f"<t:{backup['timestamp']}:F>"
            relative = f"<t:{backup['timestamp']}:R>"
            backup_list.append(f"**{i+1}.** `{backup['name']}`\n   📅 {timestamp} ({relative})")
        
        embed.add_field(
            name="📋 Recent Backups",
            value="\n\n".join(backup_list) if backup_list else "No backups available",
            inline=False
        )
        
        embed.add_field(
            name="🔄 How to Restore",
            value="Use `/denuke backup_name:<backup_name>` to restore from a specific backup.\n\n⚠️ **WARNING:** This will completely rebuild your server!",
            inline=False
        )
        
        embed.add_field(
            name="🚨 CRITICAL WARNING",
            value="**Restoration will:**\n• Delete all current channels\n• Remove all current roles\n• Rebuild server from backup data\n• **This action is IRREVERSIBLE!**",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Find the specified backup
    backup_to_restore = None
    for backup in server_backups[guild_id]:
        if backup['name'] == backup_name:
            backup_to_restore = backup
            break
    
    if not backup_to_restore:
        available_names = [b['name'] for b in server_backups[guild_id][-5:]]  # Show last 5
        embed = create_error_embed(
            "Backup Not Found", 
            f"Backup '{backup_name}' not found.\n\n**Available backups:**\n• " + "\n• ".join(available_names)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Confirm restoration with the user
    confirm_embed = discord.Embed(
        title="🚨 CRITICAL CONFIRMATION REQUIRED",
        description=f"**You are about to COMPLETELY RESTORE your server!**\n\n**Backup:** `{backup_name}`\n**Created:** <t:{backup_to_restore['timestamp']}:F>\n**Server:** {interaction.guild.name}",
        color=COLORS['error']
    )
    
    confirm_embed.add_field(
        name="⚠️ THIS WILL PERMANENTLY:",
        value="• **DELETE** all current channels\n• **REMOVE** all current roles\n• **REPLACE** with backup data\n• **CANNOT BE UNDONE**",
        inline=False
    )
    
    confirm_embed.add_field(
        name="🔄 Backup Contains:",
        value=f"• **{len(backup_to_restore['data']['channels'])}** channels\n• **{len(backup_to_restore['data']['categories'])}** categories\n• **{len(backup_to_restore['data']['roles'])}** roles",
        inline=False
    )
    
    confirm_embed.add_field(
        name="✅ To Confirm Restoration:",
        value="Type **`RESTORE SERVER NOW`** exactly in the next 60 seconds",
        inline=False
    )
    
    await interaction.response.send_message(embed=confirm_embed, ephemeral=True)
    
    # Wait for confirmation
    def check(message):
        return (message.author.id == interaction.user.id and 
                message.channel.id == interaction.channel_id and
                message.content.strip() == "RESTORE SERVER NOW")
    
    try:
        await bot.wait_for('message', check=check, timeout=60.0)
    except asyncio.TimeoutError:
        timeout_embed = create_error_embed("Restoration Cancelled", "⏰ Confirmation timeout. Server restoration has been cancelled for safety.")
        await interaction.followup.send(embed=timeout_embed, ephemeral=True)
        return
    
    # Begin restoration process
    await interaction.followup.send("🔄 **BEGINNING SERVER RESTORATION** - This may take several minutes...", ephemeral=True)
    
    # Create emergency backup before restoration
    emergency_backup = await create_server_backup(interaction.guild)
    if emergency_backup:
        await interaction.followup.send("💾 **Emergency backup created** before restoration begins...", ephemeral=True)
    
    # Perform restoration
    restoration_result = await restore_server_from_backup(interaction.guild, backup_to_restore['data'], interaction)
    
    if restoration_result:
        # Success embed
        success_embed = discord.Embed(
            title="✅ SERVER RESTORATION COMPLETED",
            description=f"**{interaction.guild.name}** has been restored from backup `{backup_name}`",
            color=COLORS['success'],
            timestamp=discord.utils.utcnow()
        )
        
        success_embed.add_field(
            name="📊 Restoration Summary",
            value=f"• **Channels:** {restoration_result['channels']} restored\n• **Categories:** {restoration_result['categories']} restored\n• **Roles:** {restoration_result['roles']} restored",
            inline=False
        )
        
        if restoration_result['errors']:
            error_summary = "\n".join(restoration_result['errors'][:5])
            if len(restoration_result['errors']) > 5:
                error_summary += f"\n... and {len(restoration_result['errors']) - 5} more errors"
            
            success_embed.add_field(
                name="⚠️ Partial Errors",
                value=f"```{error_summary}```",
                inline=False
            )
        
        success_embed.add_field(
            name="💾 Emergency Backup",
            value="An emergency backup of your previous server state was created before restoration.",
            inline=False
        )
        
        await interaction.followup.send(embed=success_embed)
        
        # Log to server owner
        try:
            owner_embed = discord.Embed(
                title="🔄 Server Restoration Completed",
                description=f"**Server:** {interaction.guild.name}\n**Restored by:** {interaction.user}\n**Backup Used:** {backup_name}",
                color=COLORS['info'],
                timestamp=discord.utils.utcnow()
            )
            await interaction.guild.owner.send(embed=owner_embed)
        except:
            pass
        
        print(f"🔄 Server restoration completed for {interaction.guild.name} using backup {backup_name}")
        
    else:
        # Failure embed
        failure_embed = create_error_embed(
            "Restoration Failed", 
            f"Could not restore server from backup `{backup_name}`. Check bot permissions and try again.\n\n**Emergency backup was created** - your server data is safe."
        )
        await interaction.followup.send(embed=failure_embed)

    await log_command_action(interaction, "denuke", f"Attempted restoration using backup: {backup_name}")

# Start backup scheduler when bot is ready
@bot.event
async def on_ready():
    print(f"⚙️ Utility Core Ready! Logged in as {bot.user}")
    print(f"🆔 Bot ID: {bot.user.id}")
    print(f"🏢 Servers: {len(bot.guilds)}")
    print(f"👥 Users: {sum(guild.member_count for guild in bot.guilds)}")

    try:
        # Sync slash commands
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

    # Set bot status
    try:
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(bot.guilds)} servers | /help for commands"
            )
        )
        print("🔄 Status changed to normal activity")
    except Exception as e:
        print(f"⚠️ Could not set status: {e}")

    # Start auto-meme system
    if not auto_meme_poster.is_running():
        auto_meme_poster.start()
        print("🎭 Auto-meme system started")
    else:
        print("🎭 Auto-meme system already running")
    
    # Start backup scheduler
    asyncio.create_task(start_backup_scheduler())
    print("📄 Backup scheduler started")
    print("🛡️ Advanced anti-nuke system ready!")
    print("🔄 Denuke restoration system ready!")
    print("💾 Server backup system ready!")
    
    # Collect custom emojis from all servers
    await collect_custom_emojis()

@bot.tree.command(name="clone", description="🔄 Clone a channel or category")
async def clone(interaction: discord.Interaction, target: discord.TextChannel = None, name: str = None):
    if not interaction.user.guild_permissions.manage_channels:
        embed = create_error_embed("Permission Denied", "You need Manage Channels permission.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    target_channel = target or interaction.channel
    clone_name = name or f"{target_channel.name}-clone"

    try:
        cloned = await target_channel.clone(name=clone_name)
        embed = create_success_embed("Channel Cloned", f"Cloned {target_channel.mention} as {cloned.mention}", interaction.user)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = create_error_embed("Clone Failed", f"Could not clone channel: {str(e)}")
        await interaction.response.send_message(embed=embed)

# ENHANCED TICKET SETUP COMMAND (Interactive UI)
@bot.tree.command(name="ticket_setup", description="🎫 Setup and configure ticket system with interactive interface")
async def ticket_setup_interactive(interaction: discord.Interaction):
    """Setup ticket system using interactive embed interface"""
    if not interaction.user.guild_permissions.administrator:
        embed = create_error_embed("Permission Denied", "You need Administrator permission to setup the ticket system.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Create main ticket setup embed
    embed = create_embed(
        title="🎫 Ticket System Setup",
        description="**Configure your advanced ticket system with interactive controls**\n\nUse the buttons below to configure settings, preview the system, and apply the setup.",
        color=COLORS['blue']
    )
    
    embed.add_field(
        name="🎯 Configuration Options",
        value="• **📍 Set Log Channel** - Where ticket logs are sent\n• **👥 Add Staff Roles** - Roles that can manage tickets\n• **⚙️ Configure Settings** - Max tickets, welcome message, etc.",
        inline=False
    )
    
    embed.add_field(
        name="✨ System Features",
        value="• **🔄 Live Preview** - See how panels will look\n• **📋 8 Ticket Types** - General, Bug Report, Feature Request, etc.\n• **📊 Auto Categories** - Organized ticket management\n• **📝 Transcripts** - Automatic ticket logging",
        inline=False
    )
    
    embed.add_field(
        name="📋 Current Status",
        value="❌ **Log Channel:** Not set\n❌ **Staff Roles:** Not configured\n⚙️ **Ready to configure**",
        inline=False
    )
    
    embed.set_footer(text="Configure your ticket system step by step • Administrator Only")
    
    # Create interactive view
    view = TicketSetupConfigView(interaction.user.id, interaction.guild.id)
    
    await interaction.response.send_message(embed=embed, view=view)
    await log_command_action(interaction, "ticket_setup", "Started interactive ticket setup")

# LEGACY TICKET SETUP COMMAND (parameter-based)  
@bot.tree.command(name="ticket_setup_legacy", description="🎫 Legacy ticket setup with parameters")
@discord.app_commands.describe(
    create_categories="Create default ticket categories",
    log_channel="Channel for ticket logs",
    staff_role="Staff role for ticket access"
)
async def ticket_setup(interaction: discord.Interaction, create_categories: bool = True, log_channel: discord.TextChannel = None, staff_role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        embed = create_error_embed("Permission Denied", "You need Administrator permission to setup the ticket system.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild_id = interaction.guild.id
    
    # Initialize ticket system if not exists
    if guild_id not in ticket_systems:
        ticket_systems[guild_id] = init_default_ticket_system(guild_id)
        ticket_counter[guild_id] = 0

    system = ticket_systems[guild_id]
    
    # Enable the system
    system.enabled = True
    
    # Configure log channel
    if log_channel:
        system.log_channel_id = log_channel.id
    
    # Add staff role
    if staff_role:
        if staff_role.id not in system.staff_roles:
            system.staff_roles.append(staff_role.id)
    
    setup_info = []
    
    # Create categories if requested
    if create_categories:
        categories_created = 0
        for ticket_type in system.ticket_types.values():
            try:
                # Check if category already exists
                existing_category = discord.utils.get(interaction.guild.categories, name=ticket_type.category_name)
                if not existing_category:
                    category = await interaction.guild.create_category(
                        name=ticket_type.category_name,
                        overwrites={
                            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                        }
                    )
                    ticket_type.category_id = category.id
                    categories_created += 1
                else:
                    ticket_type.category_id = existing_category.id
            except Exception as e:
                print(f"Failed to create category {ticket_type.category_name}: {e}")
        
        setup_info.append(f"Categories: **{categories_created} created**")
    
    if log_channel:
        setup_info.append(f"Log channel: {log_channel.mention}")
    
    if staff_role:
        setup_info.append(f"Staff role: {staff_role.mention}")
    
    ticket_emoji = get_custom_emoji('ticket', '🎫')
    embed = create_success_embed(f"{ticket_emoji} Ticket System Setup", "Ticket system has been configured successfully!", interaction.user)
    
    if setup_info:
        embed.add_field(name="🔧 Configuration", value="\n".join(f"• {info}" for info in setup_info), inline=False)
    
    embed.add_field(
        name=f"{ticket_emoji} Available Types",
        value=f"**{len(system.ticket_types)}** ticket types configured",
        inline=True
    )
    embed.add_field(
        name="⚙️ System Status",
        value="🟢 **ENABLED**",
        inline=True
    )
    embed.add_field(
        name="📋 Next Steps",
        value="Use `/ticket_panel` to create a ticket panel\nUse `/ticket_config` to customize settings",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "ticket_setup", f"Setup completed with {len(setup_info)} configurations")

@bot.tree.command(name="ticket_panel", description="🎫 Create and manage ticket panels")
@discord.app_commands.describe(
    channel="Channel to create the panel in",
    title="Custom title for the panel",
    description="Custom description for the panel"
)
async def ticket_panel(interaction: discord.Interaction, channel: discord.TextChannel = None, title: str = None, description: str = None):
    if not interaction.user.guild_permissions.manage_channels:
        embed = create_error_embed("Permission Denied", "You need Manage Channels permission to create ticket panels.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild_id = interaction.guild.id
    
    # Initialize ticket system if not exists
    if guild_id not in ticket_systems:
        ticket_systems[guild_id] = init_default_ticket_system(guild_id)
        ticket_counter[guild_id] = 0

    system = ticket_systems[guild_id]
    target_channel = channel or interaction.channel
    
    # Customize panel if provided
    if title:
        system.embed_title = title
    if description:
        system.embed_description = description
    
    # Create the ticket panel
    await create_ticket_panel_in_channel(interaction, system, target_channel)

@bot.tree.command(name="ticket_config", description="⚙️ Configure ticket system settings")
@discord.app_commands.describe(
    max_tickets="Maximum tickets per user (1-10)",
    log_channel="Channel for ticket logs",
    auto_categorize="Automatically create categories for tickets",
    staff_ping="Ping staff when tickets are created",
    transcript_logs="Enable ticket transcript logging"
)
async def ticket_config(interaction: discord.Interaction, max_tickets: int = None, log_channel: discord.TextChannel = None, auto_categorize: bool = None, staff_ping: bool = None, transcript_logs: bool = None):
    if not interaction.user.guild_permissions.administrator:
        embed = create_error_embed("Permission Denied", "You need Administrator permission to configure the ticket system.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild_id = interaction.guild.id
    
    # Initialize ticket system if not exists
    if guild_id not in ticket_systems:
        ticket_systems[guild_id] = init_default_ticket_system(guild_id)
        ticket_counter[guild_id] = 0

    system = ticket_systems[guild_id]
    changes_made = []
    
    if max_tickets is not None:
        if max_tickets < 1 or max_tickets > 10:
            embed = create_error_embed("Invalid Range", "Maximum tickets per user must be between 1 and 10.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        system.max_tickets_per_user = max_tickets
        changes_made.append(f"Max tickets per user: **{max_tickets}**")
    
    if log_channel:
        system.log_channel_id = log_channel.id
        changes_made.append(f"Log channel: {log_channel.mention}")
    
    if auto_categorize is not None:
        system.auto_categorize = auto_categorize
        changes_made.append(f"Auto-categorize: **{'Enabled' if auto_categorize else 'Disabled'}**")
    
    if staff_ping is not None:
        system.ping_staff = staff_ping
        changes_made.append(f"Staff ping: **{'Enabled' if staff_ping else 'Disabled'}**")
    
    if transcript_logs is not None:
        system.transcript_logs = transcript_logs
        changes_made.append(f"Transcript logs: **{'Enabled' if transcript_logs else 'Disabled'}**")
    
    if changes_made:
        embed = create_success_embed("⚙️ Configuration Updated", "Ticket system settings have been updated!", interaction.user)
        embed.add_field(name="🔧 Changes Made", value="\n".join(f"• {change}" for change in changes_made), inline=False)
    else:
        # Show current configuration
        embed = create_embed(
            title=f"{get_custom_emoji('settings', '⚙️')} Ticket System Configuration",
            description=f"**Server:** {interaction.guild.name}",
            color=COLORS['blue']
        )
        
        embed.add_field(name="🎫 System Status", value="🟢 Enabled" if system.enabled else "🔴 Disabled", inline=True)
        embed.add_field(name="📋 Ticket Types", value=f"{len(system.ticket_types)}", inline=True)
        embed.add_field(name="👤 Max per User", value=f"{system.max_tickets_per_user}", inline=True)
        
        embed.add_field(name="📂 Auto-Categorize", value="✅ Enabled" if system.auto_categorize else "❌ Disabled", inline=True)
        embed.add_field(name="🔔 Staff Ping", value="✅ Enabled" if system.ping_staff else "❌ Disabled", inline=True)
        embed.add_field(name="📝 Transcript Logs", value="✅ Enabled" if system.transcript_logs else "❌ Disabled", inline=True)
        
        log_channel_text = f"<#{system.log_channel_id}>" if system.log_channel_id else "Not set"
        staff_roles_text = f"{len(system.staff_roles)} roles" if system.staff_roles else "None"
        
        embed.add_field(name="📊 Log Channel", value=log_channel_text, inline=True)
        embed.add_field(name="👮 Staff Roles", value=staff_roles_text, inline=True)
        embed.add_field(name="💬 Welcome Message", value="Configured" if system.welcome_message else "Default", inline=True)
    
    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "ticket_config", f"Configuration changes: {', '.join(changes_made) if changes_made else 'Viewed status'}")

@bot.tree.command(name="ticket_logging", description="📊 View ticket logs and statistics")
@discord.app_commands.describe(
    show_stats="Show comprehensive ticket statistics",
    list_active="List all active tickets",
    user="Show tickets for specific user"
)
async def ticket_logging(interaction: discord.Interaction, show_stats: bool = True, list_active: bool = False, user: discord.Member = None):
    guild_id = interaction.guild.id
    
    # Initialize ticket system if not exists
    if guild_id not in ticket_systems:
        ticket_systems[guild_id] = init_default_ticket_system(guild_id)
        ticket_counter[guild_id] = 0

    system = ticket_systems[guild_id]
    
    if show_stats and not list_active and not user:
        await show_ticket_stats(interaction, system)
    elif list_active:
        await list_active_tickets(interaction, system)
    elif user:
        await show_user_tickets(interaction, system, user)
    else:
        embed = create_info_embed("Ticket Logging", "Use the parameters to view statistics, active tickets, or user-specific tickets.", interaction.user)
        await interaction.response.send_message(embed=embed)

async def create_ticket_panel(interaction, system):
    """Create an advanced ticket panel with dropdown menu"""

    # Create main embed
    embed = discord.Embed(
        title=system.embed_title,
        description=system.embed_description,
        color=system.embed_color,
        timestamp=discord.utils.utcnow()
    )

    if system.embed_thumbnail:
        embed.set_thumbnail(url=system.embed_thumbnail)
    if system.embed_image:
        embed.set_image(url=system.embed_image)
    if system.embed_author:
        embed.set_author(name=system.embed_author.get('name', ''),
                        icon_url=system.embed_author.get('icon_url', ''))

    embed.set_footer(text=system.embed_footer,
                    icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

    # Add information fields
    embed.add_field(
        name="📋 Available Support Types",
        value=f"Select from **{len(system.ticket_types)}** different ticket types using the dropdown below!",
        inline=False
    )

    embed.add_field(
        name="⏱️ Response Time",
        value="Staff typically respond within **15 minutes** during active hours",
        inline=True
    )

    embed.add_field(
        name="🔢 Active Tickets",
        value=f"{len([t for t in active_tickets.values() if t.status == 'open'])} tickets currently open",
        inline=True
    )

    # Create dropdown view
    view = TicketDropdownView(system)

    await interaction.response.send_message(embed=embed, view=view)
    await log_command_action(interaction, "ticket create", f"Created ticket panel with {len(system.ticket_types)} types")

async def show_ticket_stats(interaction, system):
    """Show comprehensive ticket statistics"""
    guild_tickets = [t for t in active_tickets.values() if t.channel_id in [c.id for c in interaction.guild.channels]]

    total_tickets = ticket_counter.get(interaction.guild.id, 0)
    open_tickets = len([t for t in guild_tickets if t.status == "open"])
    closed_tickets = total_tickets - open_tickets

    embed = create_embed(
        title="📊 Ticket System Statistics",
        description=f"Comprehensive statistics for **{interaction.guild.name}**",
        color=COLORS['blue']
    )

    embed.add_field(name="🎫 Total Tickets", value=f"{total_tickets:,}", inline=True)
    embed.add_field(name="🟢 Open Tickets", value=f"{open_tickets:,}", inline=True)
    embed.add_field(name="🔴 Closed Tickets", value=f"{closed_tickets:,}", inline=True)

    # Ticket type breakdown
    type_stats = {}
    for ticket in guild_tickets:
        ticket_type = ticket.ticket_type.name if ticket.ticket_type else "Unknown"
        type_stats[ticket_type] = type_stats.get(ticket_type, 0) + 1

    if type_stats:
        stats_text = "\n".join([f"{ticket_type}: {count}" for ticket_type, count in type_stats.items()])
        embed.add_field(name="📋 Tickets by Type", value=stats_text[:1024], inline=False)

    embed.add_field(
        name="⚙️ System Status",
        value=f"{'🟢 Enabled' if system.enabled else '🔴 Disabled'}\nAuto-categorize: {'✅' if system.auto_categorize else '❌'}\nMax per user: {system.max_tickets_per_user}",
        inline=True
    )

    await interaction.response.send_message(embed=embed)

async def list_active_tickets(interaction, system):
    """List all active tickets with details"""
    guild_tickets = [t for t in active_tickets.values()
                    if t.channel_id in [c.id for c in interaction.guild.channels] and t.status == "open"]

    if not guild_tickets:
        embed = create_info_embed("No Active Tickets", "There are currently no open tickets in this server.", interaction.user)
        embed.add_field(
            name="💡 Get Started",
            value="Use `/ticket create` to create a ticket panel",
            inline=False
        )
        await interaction.response.send_message(embed=embed)
        return

    embed = create_embed(
        title="📋 Active Tickets",
        description=f"**{len(guild_tickets)}** open tickets in **{interaction.guild.name}**",
        color=COLORS['blue']
    )

    for i, ticket in enumerate(guild_tickets[:10]):  # Limit to 10 for embed space
        channel = interaction.guild.get_channel(ticket.channel_id)
        user = interaction.guild.get_member(ticket.user_id)

        if channel and user:
            status_emoji = "🟢" if ticket.status == "open" else "🟡" if ticket.status == "claimed" else "🔴"
            embed.add_field(
                name=f"{status_emoji} Ticket #{ticket.ticket_number}",
                value=f"**User:** {user.mention}\n**Type:** {ticket.ticket_type.name if ticket.ticket_type else 'Unknown'}\n**Channel:** {channel.mention}\n**Created:** <t:{int(ticket.created_at)}:R>",
                inline=True
            )

    if len(guild_tickets) > 10:
        embed.add_field(name="➕ More", value=f"... and {len(guild_tickets) - 10} more tickets", inline=False)

    await interaction.response.send_message(embed=embed)

async def quick_ticket_setup(interaction, system):
    """Quick setup wizard for ticket system"""
    embed = create_embed(
        title="🚀 Quick Ticket Setup",
        description="Setting up your advanced ticket system with default configuration...",
        color=COLORS['aqua']
    )

    await interaction.response.defer()

    setup_steps = []

    # Create categories for each ticket type if auto-categorize is enabled
    if system.auto_categorize:
        for ticket_type in system.ticket_types.values():
            try:
                # Check if category already exists
                category = None
                for cat in interaction.guild.categories:
                    if cat.name == ticket_type.category_name:
                        category = cat
                        break

                if not category:
                    category = await interaction.guild.create_category(ticket_type.category_name)
                    setup_steps.append(f"✅ Created category: {ticket_type.category_name}")
                else:
                    setup_steps.append(f"ℹ️ Found existing category: {ticket_type.category_name}")

                ticket_type.category_id = category.id
                await asyncio.sleep(0.5)  # Rate limiting

            except Exception as e:
                setup_steps.append(f"❌ Failed to create category for {ticket_type.name}: {str(e)}")

    # Find or create logs channel
    log_channel = None
    for channel in interaction.guild.text_channels:
        if "ticket" in channel.name.lower() and "log" in channel.name.lower():
            log_channel = channel
            break

    if not log_channel:
        try:
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }

            # Add admin roles
            for role in interaction.guild.roles:
                if any(keyword in role.name.lower() for keyword in ["admin", "mod", "staff", "support", "helper"]):
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

            log_channel = await interaction.guild.create_text_channel("ticket-logs", overwrites=overwrites)
            system.log_channel_id = log_channel.id
            setup_steps.append(f"✅ Created logs channel: {log_channel.mention}")
        except Exception as e:
            setup_steps.append(f"❌ Failed to create logs channel: {str(e)}")
    else:
        system.log_channel_id = log_channel.id
        setup_steps.append(f"ℹ️ Found existing logs channel: {log_channel.mention}")

    # Update system settings
    system.enabled = True
    setup_steps.append("✅ Enabled ticket system")

    # Create success embed
    embed = create_success_embed("Ticket System Setup Complete!", "Your advanced ticket system is now ready to use!", interaction.user)
    embed.add_field(
        name="📋 Setup Summary",
        value="\n".join(setup_steps[:10]),  # Limit for embed space
        inline=False
    )

    embed.add_field(
        name="🎯 Next Steps",
        value=f"• Use `/ticket create` to create a ticket panel\n• Use `/ticketconfig` to customize settings\n• Use `/ticket stats` to view statistics",
        inline=False
    )

    embed.add_field(
        name="⚙️ System Features",
        value=f"• {len(system.ticket_types)} ticket types configured\n• Auto-categorization enabled\n• Transcript logging enabled\n• Staff ping notifications enabled",
        inline=False
    )

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="ticketconfig", description="🔧 Configure the advanced ticket system")
@discord.app_commands.describe(
    setting="Setting to configure",
    value="New value for the setting",
    channel="Channel for welcome messages",
    color="Embed color (hex code like #ff0000 or color name)"
)
@discord.app_commands.choices(setting=[
    discord.app_commands.Choice(name="🎨 Embed Color", value="embed_color"),
    discord.app_commands.Choice(name="📝 Embed Title", value="embed_title"),
    discord.app_commands.Choice(name="📋 Embed Description", value="embed_description"),
    discord.app_commands.Choice(name="🖼️ Embed Thumbnail", value="embed_thumbnail"),
    discord.app_commands.Choice(name="🖼️ Embed Image", value="embed_image"),
    discord.app_commands.Choice(name="👤 Embed Author", value="embed_author"),
    discord.app_commands.Choice(name="📄 Embed Footer", value="embed_footer"),
    discord.app_commands.Choice(name="📁 Auto Categorize", value="auto_categorize"),
    discord.app_commands.Choice(name="📊 Max Tickets Per User", value="max_tickets"),
    discord.app_commands.Choice(name="💬 Welcome Message", value="welcome_message"),
    discord.app_commands.Choice(name="📊 Toggle System", value="toggle_system"),
    discord.app_commands.Choice(name="📋 View Current Config", value="view_config")
])
async def ticketconfig(interaction: discord.Interaction, setting: discord.app_commands.Choice[str],
                      value: str = None, channel: discord.TextChannel = None, color: str = None):
    """Configure the advanced ticket system"""

    if not interaction.user.guild_permissions.administrator:
        embed = create_error_embed("Permission Denied", "You need `Administrator` permission to configure the ticket system.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild_id = interaction.guild.id

    if guild_id not in ticket_systems:
        ticket_systems[guild_id] = init_default_ticket_system(guild_id)

    system = ticket_systems[guild_id]

    if setting.value == "view_config":
        await show_ticket_config(interaction, system)
        return

    if not value and setting.value != "toggle_system":
        embed = create_error_embed("Missing Value", f"Please provide a value for {setting.name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        if setting.value == "embed_color":
            # Parse color
            if color.startswith("#"):
                parsed_color = int(color[1:], 16)
            elif color.lower() in COLORS:
                parsed_color = COLORS[color.lower()]
            else:
                parsed_color = int(color)
            system.embed_color = parsed_color

        elif setting.value == "embed_title":
            system.embed_title = value

        elif setting.value == "embed_description":
            system.embed_description = value

        elif setting.value == "embed_thumbnail":
            if value.lower() in ["none", "null", "remove"]:
                system.embed_thumbnail = None
            else:
                system.embed_thumbnail = value

        elif setting.value == "embed_image":
            if value.lower() in ["none", "null", "remove"]:
                system.embed_image = None
            else:
                system.embed_image = value

        elif setting.value == "embed_footer":
            system.embed_footer = value

        elif setting.value == "auto_categorize":
            system.auto_categorize = value.lower() in ["true", "yes", "1", "on", "enable"]

        elif setting.value == "max_tickets":
            system.max_tickets_per_user = int(value)

        elif setting.value == "welcome_message":
            system.welcome_message = value

        elif setting.value == "toggle_system":
            system.enabled = not system.enabled

        embed = create_success_embed("Configuration Updated", f"Successfully updated {setting.name}", interaction.user)

        if setting.value == "toggle_system":
            embed.add_field(name="New Status", value=f"{'🟢 Enabled' if system.enabled else '🔴 Disabled'}", inline=True)
        else:
            embed.add_field(name="New Value", value=f"`{value or color}`", inline=True)

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "ticketconfig", f"Updated {setting.value} to {value or color}")

    except ValueError:
        embed = create_error_embed("Invalid Value", f"Invalid value for {setting.name}. Please check the format.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        embed = create_error_embed("Configuration Failed", f"Failed to update configuration: {str(e)}")
        await interaction.response.send_message(embed=embed)

async def show_ticket_config(interaction, system):
    """Display current ticket system configuration"""
    embed = create_embed(
        title="🔧 Ticket System Configuration",
        description=f"Current settings for **{interaction.guild.name}**",
        color=system.embed_color
    )

    # Basic settings
    embed.add_field(
        name="⚙️ System Settings",
        value=f"**Status:** {'🟢 Enabled' if system.enabled else '🔴 Disabled'}\n**Auto Categorize:** {'✅ Yes' if system.auto_categorize else '❌ No'}\n**Max Tickets/User:** {system.max_tickets_per_user}\n**Transcript Logs:** {'✅ Yes' if system.transcript_logs else '❌ No'}",
        inline=False
    )

    # Embed settings
    embed.add_field(
        name="🎨 Embed Appearance",
        value=f"**Title:** {system.embed_title}\n**Color:** #{system.embed_color:06x}\n**Footer:** {system.embed_footer}\n**Thumbnail:** {'Set' if system.embed_thumbnail else 'None'}",
        inline=False
    )

    # Ticket types
    types_list = []
    for ticket_type in list(system.ticket_types.values())[:5]:
        types_list.append(f"{ticket_type.emoji} {ticket_type.name}")

    embed.add_field(
        name="🎫 Available Ticket Types",
        value="\n".join(types_list) + (f"\n... and {len(system.ticket_types) - 5} more" if len(system.ticket_types) > 5 else ""),
        inline=False
    )

    embed.add_field(
        name="💬 Welcome Message Preview",
        value=system.welcome_message[:100] + ("..." if len(system.welcome_message) > 100 else ""),
        inline=False
    )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="tickettype", description="🎭 Manage ticket types")
@discord.app_commands.describe(
    action="Action to perform",
    name="Name of the ticket type",
    emoji="Emoji for the ticket type",
    description="Description of the ticket type",
    color="Hex color code (e.g., #3498db)"
)
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name="➕ Add Ticket Type", value="add"),
    discord.app_commands.Choice(name="➖ Remove Ticket Type", value="remove"),
    discord.app_commands.Choice(name="✏️ Edit Ticket Type", value="edit"),
    discord.app_commands.Choice(name="📋 List Ticket Types", value="list")
])
async def tickettype(interaction: discord.Interaction, action: discord.app_commands.Choice[str],
                    name: str = None, emoji: str = None, description: str = None, color: str = None):
    if not interaction.user.guild_permissions.manage_channels:
        embed = create_error_embed("Permission Denied", "You need `Manage Channels` permission to manage ticket types.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild_id = interaction.guild.id

    if guild_id not in ticket_systems:
        ticket_systems[guild_id] = init_default_ticket_system(guild_id)

    system = ticket_systems[guild_id]

    if action.value == "list":
        embed = create_embed(
            title="🎭 Ticket Types",
            description=f"**{len(system.ticket_types)}** ticket types configured",
            color=COLORS['blue']
        )

        for ticket_type in system.ticket_types.values():
            embed.add_field(
                name=f"{ticket_type.emoji} {ticket_type.name}",
                value=f"**Description:** {ticket_type.description}\n**Category:** {ticket_type.category_name}\n**Color:** #{ticket_type.color:06x}",
                inline=True
            )

        await interaction.response.send_message(embed=embed)
        return

    if not name:
        embed = create_error_embed("Missing Name", "Please provide a ticket type name.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if action.value == "add":
        if not all([emoji, description]):
            embed = create_error_embed("Missing Information", "Please provide emoji and description for the new ticket type.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Parse color
        ticket_color = 0x3498db
        if color:
            try:
                if color.startswith("#"):
                    ticket_color = int(color[1:], 16)
                else:
                    ticket_color = int(color, 16)
            except:
                ticket_color = 0x3498db

        new_type = TicketType(name, emoji, description, color=ticket_color)
        system.add_ticket_type(new_type)

        embed = create_success_embed("Ticket Type Added", f"Added new ticket type: {emoji} {name}", interaction.user)

    elif action.value == "remove":
        ticket_type = system.get_ticket_type(name)
        if not ticket_type:
            embed = create_error_embed("Type Not Found", f"Ticket type '{name}' not found.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        system.remove_ticket_type(name)
        embed = create_success_embed("Ticket Type Removed", f"Removed ticket type: {name}", interaction.user)

    await interaction.response.send_message(embed=embed)

# The original `closeticket` command definition was removed to prevent duplicates.
# The following is the single, correct definition.
@bot.tree.command(name="closeticket", description="🔒 Close a support ticket with transcript")
async def closeticket(interaction: discord.Interaction, reason: str = "Resolved"):
    channel_id = interaction.channel.id

    if channel_id not in active_tickets:
        embed = create_error_embed("Not a Ticket", "This command can only be used in ticket channels.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    ticket_data = active_tickets[channel_id]

    # Create transcript if logging is enabled
    guild_id = interaction.guild.id
    if guild_id in ticket_systems and ticket_systems[guild_id].transcript_logs:
        await create_ticket_transcript(interaction, ticket_data, reason)

    # Create closing embed
    embed = create_warning_embed(
        "🔒 Ticket Closing",
        f"This ticket is being closed by {interaction.user.mention}.\n**Reason:** {reason}"
    )
    embed.add_field(name="⏰ Auto-Delete", value="Channel will be deleted in **10 seconds**", inline=True)
    embed.add_field(name="📋 Transcript", value="Logs have been saved" if guild_id in ticket_systems and ticket_systems[guild_id].transcript_logs else "No transcript logging", inline=True)

    await interaction.response.send_message(embed=embed)

    # Wait and delete
    await asyncio.sleep(10)
    try:
        # Remove from active tickets
        if channel_id in active_tickets:
            del active_tickets[channel_id]

        await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}: {reason}")
    except:
        pass

async def create_ticket_transcript(interaction, ticket_data, close_reason):
    """Create a transcript log of the ticket"""
    try:
        guild = interaction.guild
        system = ticket_systems.get(guild.id)

        if not system or not system.log_channel_id:
            return

        log_channel = guild.get_channel(system.log_channel_id)
        if not log_channel:
            return

        # Fetch messages from the ticket channel
        messages = []
        async for message in interaction.channel.history(limit=None, oldest_first=True):
            if not message.author.bot or message.embeds:
                messages.append(message)

        # Create transcript embed
        embed = create_embed(
            title="📋 Ticket Transcript",
            description=f"Ticket #{ticket_data.ticket_number} - {ticket_data.ticket_type.name if ticket_data.ticket_type else 'Unknown'}",
            color=0x2ecc71
        )

        user = guild.get_member(ticket_data.user_id)
        closer = interaction.user

        embed.add_field(name="👤 Ticket Creator", value=user.mention if user else "Unknown User", inline=True)
        embed.add_field(name="🔒 Closed By", value=closer.mention, inline=True)
        embed.add_field(name="📅 Duration", value=f"<t:{int(ticket_data.created_at)}:R> - <t:{int(time.time())}:R>", inline=True)
        embed.add_field(name="📝 Close Reason", value=close_reason, inline=False)
        embed.add_field(name="💬 Total Messages", value=len(messages), inline=True)

        # Create text transcript
        transcript_text = f"Ticket #{ticket_data.ticket_number} Transcript\n"
        transcript_text += f"Created: {datetime.datetime.fromtimestamp(ticket_data.created_at)}\n"
        transcript_text += f"Closed: {datetime.datetime.now()}\n"
        transcript_text += f"User: {user} ({user.id})\n" if user else "User: Unknown\n"
        transcript_text += f"Closed by: {closer} ({closer.id})\n"
        transcript_text += f"Reason: {close_reason}\n"
        transcript_text += "="*50 + "\n\n"

        for msg in messages[-50:]:  # Last 50 messages
            timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            transcript_text += f"[{timestamp}] {msg.author}: {msg.content}\n"
            if msg.attachments:
                for attachment in msg.attachments:
                    transcript_text += f"    [Attachment: {attachment.filename}]\n"

        # Send transcript
        transcript_file = discord.File(
            io.StringIO(transcript_text),
            filename=f"ticket-{ticket_data.ticket_number}-transcript.txt"
        )

        await log_channel.send(embed=embed, file=transcript_file)

    except Exception as e:
        print(f"Failed to create transcript: {e}")

# Ticket Dropdown View and Components
class TicketDropdownView(discord.ui.View):
    def __init__(self, ticket_system):
        super().__init__(timeout=None)
        self.ticket_system = ticket_system

        # Create dropdown
        self.dropdown = TicketTypeDropdown(ticket_system)
        self.add_item(self.dropdown)

        # Add control buttons
        self.add_item(RefreshPanelButton())
        self.add_item(CloseTicketButton())

class TicketTypeDropdown(discord.ui.Select):
    def __init__(self, ticket_system):
        self.ticket_system = ticket_system

        # Create options from ticket types
        options = []
        for ticket_type in list(ticket_system.ticket_types.values())[:25]:  # Discord limit
            options.append(discord.SelectOption(
                label=ticket_type.name,
                description=ticket_type.description[:100],  # Discord limit
                emoji=ticket_type.emoji,
                value=ticket_type.name.lower()
            ))

        super().__init__(
            placeholder="🎫 Select the type of support you need...",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        await create_user_ticket(interaction, self.ticket_system, self.values[0])

class RefreshPanelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Refresh Panel",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        embed = create_info_embed(
            "Panel Refreshed",
            f"Ticket panel refreshed at <t:{int(time.time())}:f>",
            interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class CloseTicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Close Ticket",
            emoji="🔒",
            style=discord.ButtonStyle.danger,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.channel.id not in active_tickets:
            embed = create_error_embed("Not a Ticket", "This is not a ticket channel.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Check permissions
        ticket_data = active_tickets[interaction.channel.id]
        is_ticket_owner = interaction.user.id == ticket_data.user_id
        is_staff = any(role.name.lower() in ["admin", "mod", "staff", "support"] for role in interaction.user.roles)

        if not (is_ticket_owner or is_staff):
            embed = create_error_embed("Permission Denied", "Only the ticket creator or staff can close tickets.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Create modal for close reason
        modal = CloseTicketModal()
        await interaction.response.send_modal(modal)

class CloseTicketModal(discord.ui.Modal, title="Close Ticket"):
    def __init__(self):
        super().__init__()

    reason = discord.ui.TextInput(
        label="Close Reason",
        placeholder="Why are you closing this ticket?",
        default="Resolved",
        max_length=500,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Call the closeticket function
        channel_id = interaction.channel.id
        if channel_id in active_tickets:
            ticket_data = active_tickets[channel_id]

            # Create transcript if logging is enabled
            guild_id = interaction.guild.id
            if guild_id in ticket_systems and ticket_systems[guild_id].transcript_logs:
                await create_ticket_transcript(interaction, ticket_data, self.reason.value)

            embed = create_warning_embed(
                "🔒 Ticket Closing",
                f"This ticket is being closed by {interaction.user.mention}.\n**Reason:** {self.reason.value}"
            )
            embed.add_field(name="⏰ Auto-Delete", value="Channel will be deleted in **10 seconds**", inline=True)

            await interaction.response.send_message(embed=embed)

            await asyncio.sleep(10)
            try:
                if channel_id in active_tickets:
                    del active_tickets[channel_id]
                await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}: {self.reason.value}")
            except:
                pass

async def create_user_ticket(interaction, ticket_system, ticket_type_name):
    """Create a new ticket for a user"""

    if not ticket_system.enabled:
        embed = create_error_embed("System Disabled", "The ticket system is currently disabled.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild = interaction.guild
    user = interaction.user

    # Check if user has too many open tickets
    user_tickets = [t for t in active_tickets.values()
                   if t.user_id == user.id and t.status == "open"]

    if len(user_tickets) >= ticket_system.max_tickets_per_user:
        embed = create_error_embed(
            "Too Many Tickets",
            f"You can only have {ticket_system.max_tickets_per_user} open tickets at once.\nPlease close existing tickets before creating new ones."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Get ticket type
    ticket_type = ticket_system.get_ticket_type(ticket_type_name)
    if not ticket_type:
        embed = create_error_embed("Invalid Type", "Selected ticket type not found.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Increment counter
    if guild.id not in ticket_counter:
        ticket_counter[guild.id] = 0
    ticket_counter[guild.id] += 1
    ticket_number = ticket_counter[guild.id]

    await interaction.response.defer(ephemeral=True)

    try:
        # Find or create category
        category = None
        if ticket_system.auto_categorize and ticket_type.category_id:
            category = guild.get_channel(ticket_type.category_id)

        if not category:
            # Find a general ticket category or create one
            for cat in guild.categories:
                if "ticket" in cat.name.lower():
                    category = cat
                    break

            if not category:
                category = await guild.create_category("🎫 Support Tickets")

        # Create channel name
        channel_name = f"ticket-{ticket_number:04d}-{user.name}".lower()
        channel_name = ''.join(c for c in channel_name if c.isalnum() or c in '-_')

        # Set up permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True, manage_messages=True)
        }

        # Add staff roles from system configuration or auto-detect
        staff_roles = ticket_system.staff_roles or []
        if not staff_roles:
            for role in guild.roles:
                if any(keyword in role.name.lower() for keyword in ["admin", "mod", "staff", "support", "helper"]):
                    staff_roles.append(role.id)

        for role_id in staff_roles:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True, manage_messages=True)

        # Create the ticket channel
        ticket_channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"🎫 {ticket_type.name} ticket for {user} | Ticket #{ticket_number:04d}"
        )

        # Create ticket data
        ticket_data = TicketData(
            user_id=user.id,
            ticket_type=ticket_type,
            ticket_number=ticket_number,
            created_at=time.time(),
            channel_id=ticket_channel.id,
            category_id=category.id
        )

        active_tickets[ticket_channel.id] = ticket_data

        # Create ticket embed
        ticket_embed = discord.Embed(
            title=ticket_type.embed_title,
            description= ticket_type.embed_description,
            color=ticket_type.color,
            timestamp=discord.utils.utcnow()
        )

        if ticket_type.embed_thumbnail:
            ticket_embed.set_thumbnail(url=ticket_type.embed_thumbnail)
        if ticket_type.embed_image:
            ticket_embed.set_image(url=ticket_type.embed_image)
        if ticket_type.embed_author:
            ticket_embed.set_author(
                name=ticket_type.embed_author.get('name', ''),
                icon_url=ticket_type.embed_author.get('icon_url', ''),
                url=ticket_type.embed_author.get('url', '')
            )

        ticket_embed.set_footer(text=ticket_type.embed_footer, icon_url=guild.icon.url if guild.icon else None)

        ticket_embed.add_field(name="👤 Created By", value=user.mention, inline=True)
        ticket_embed.add_field(name="🎫 Ticket Number", value=f"#{ticket_number:04d}", inline=True)
        ticket_embed.add_field(name="📅 Created At", value=f"<t:{int(time.time())}:F>", inline=True)
        ticket_embed.add_field(name="🎭 Type", value=f"{ticket_type.emoji} {ticket_type.name}", inline=True)
        ticket_embed.add_field(name="📊 Status", value="🟢 Open", inline=True)
        ticket_embed.add_field(name="🔒 Close Ticket", value="Use the button below or `/closeticket`", inline=True)

        ticket_embed.set_footer(text=ticket_type.embed_footer, icon_url=guild.icon.url if guild.icon else None)

        # Send welcome message
        welcome_msg = replace_variables(
            ticket_system.welcome_message,
            user=user,
            guild=guild,
            channel=ticket_channel
        )

        # Create ticket view with close button
        ticket_view = TicketChannelView()

        # Send initial messages
        await ticket_channel.send(f"👋 {user.mention}", embed=ticket_embed, view=ticket_view)
        if welcome_msg != ticket_system.welcome_message or len(welcome_msg) > 50:
            welcome_embed = create_embed(
                title="💬 Welcome Message",
                description=welcome_msg,
                color=COLORS['blue']
            )
            await ticket_channel.send(embed=welcome_embed)

        # Ping staff if enabled
        if ticket_system.ping_staff and staff_roles:
            staff_mentions = []
            for role_id in staff_roles[:3]:  # Limit mentions
                role = guild.get_role(role_id)
                if role:
                    staff_mentions.append(role.mention)

            if staff_mentions:
                ping_embed = create_embed(
                    title="🔔 Staff Notification",
                    description=f"New {ticket_type.name} ticket created!\nStaff: {' '.join(staff_mentions)}",
                    color=COLORS['warning']
                )
                ping_msg = await ticket_channel.send(embed=ping_embed)
                # Delete ping after 10 seconds
                await asyncio.sleep(10)
                try:
                    await ping_msg.delete()
                except:
                    pass

        # Success response
        success_embed = create_success_embed(
            "🎫 Ticket Created!",
            f"Your {ticket_type.name} ticket has been created!\n\n**Channel:** {ticket_channel.mention}\n**Ticket #:** {ticket_number:04d}",
            user
        )
        success_embed.add_field(name="⏰ Response Time", value="Staff typically respond within 15 minutes", inline=True)
        success_embed.add_field(name="🔒 To Close", value="Use the close button or `/closeticket`", inline=True)

        await interaction.followup.send(embed=success_embed, ephemeral=True)

        # Log creation
        await log_command_action(interaction, "create_ticket", f"Created {ticket_type.name} ticket #{ticket_number}")

    except Exception as e:
        embed = create_error_embed("Ticket Creation Failed", f"Failed to create ticket: {str(e)}")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await report_error_to_owner(e, f"Ticket creation - Guild: {guild.name}, User: {user}")

class TicketChannelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", emoji="🔒", style=discord.ButtonStyle.danger)
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel.id not in active_tickets:
            embed = create_error_embed("Not a Ticket", "This is not a ticket channel.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        ticket_data = active_tickets[interaction.channel.id]
        is_ticket_owner = interaction.user.id == ticket_data.user_id
        is_staff = any(role.name.lower() in ["admin", "mod", "staff", "support"] for role in interaction.user.roles)

        if not (is_ticket_owner or is_staff):
            embed = create_error_embed("Permission Denied", "Only the ticket creator or staff can close tickets.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        modal = CloseTicketModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Claim Ticket", emoji="🏷️", style=discord.ButtonStyle.secondary)
    async def claim_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel.id not in active_tickets:
            await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)
            return

        ticket_data = active_tickets[interaction.channel.id]

        # Check if user is staff
        is_staff = any(role.name.lower() in ["admin", "mod", "staff", "support"] for role in interaction.user.roles)
        if not is_staff:
            await interaction.response.send_message("Only staff can claim tickets.", ephemeral=True)
            return

        if ticket_data.claimed_by:
            claimer = interaction.guild.get_member(ticket_data.claimed_by)
            embed = create_info_embed("Already Claimed", f"This ticket is already claimed by {claimer.mention if claimer else 'Unknown User'}", interaction.user)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        ticket_data.claimed_by = interaction.user.id
        ticket_data.status = "claimed"

        embed = create_success_embed("Ticket Claimed", f"{interaction.user.mention} has claimed this ticket!", interaction.user)
        await interaction.response.send_message(embed=embed)

        # Update channel topic
        try:
            new_topic = f"🎫 {ticket_data.ticket_type.name} ticket | Ticket #{ticket_data.ticket_number:04d} | Claimed by {interaction.user.display_name}"
            await interaction.channel.edit(topic=new_topic)
        except:
            pass

# MODERATION COMMANDS
@bot.tree.command(name="ban", description="🔨 Ban a user from the server")
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.ban_members:
        embed = create_error_embed("Permission Denied", "You need `Ban Members` permission to use this command.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.ban_members:
        embed = create_error_embed("Bot Permission Missing", "I need `Ban Members` permission to ban users.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if user.top_role >= interaction.user.top_role:
        embed = create_error_embed("Insufficient Permissions", "You cannot ban someone with a higher or equal role.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        await user.ban(reason=f"Banned by {interaction.user}: {reason}")
        embed = create_success_embed("User Banned", f"Successfully banned {user.mention}\n**Reason:** {reason}", interaction.user)
        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "ban", f"Banned {user} for: {reason}")
    except Exception as e:
        embed = create_error_embed("Ban Failed", f"Could not ban {user.mention}: {str(e)}")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="kick", description="👢 Kick a user from the server")
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.kick_members:
        embed = create_error_embed("Permission Denied", "You need `Kick Members` permission to use this command.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.kick_members:
        embed = create_error_embed("Bot Permission Missing", "I need `Kick Members` permission to kick users.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if user.top_role >= interaction.user.top_role:
        embed = create_error_embed("Insufficient Permissions", "You cannot kick someone with a higher or equal role.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        await user.kick(reason=f"Kicked by {interaction.user}: {reason}")
        embed = create_success_embed("User Kicked", f"Successfully kicked {user.mention}\n**Reason:** {reason}", interaction.user)
        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "kick", f"Kicked {user} for: {reason}")
    except Exception as e:
        embed = create_error_embed("Kick Failed", f"Could not kick {user.mention}: {str(e)}")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="timeout", description="⏰ Timeout a user temporarily")
async def timeout(interaction: discord.Interaction, user: discord.Member, duration: int, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.moderate_members:
        embed = create_error_embed("Permission Denied", "You need `Moderate Members` permission to timeout users.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.moderate_members:
        embed = create_error_embed("Bot Permission Missing", "I need `Moderate Members` permission to timeout users.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if user.top_role >= interaction.user.top_role:
        embed = create_error_embed("Insufficient Permissions", "You cannot timeout someone with a higher or equal role.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if duration > 2419200:  # 28 days in seconds
        embed = create_error_embed("Duration Too Long", "Timeout duration cannot exceed 28 days.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        timeout_until = discord.utils.utcnow() + datetime.timedelta(seconds=duration)
        await user.timeout(timeout_until, reason=f"Timed out by {interaction.user}: {reason}")

        embed = create_success_embed("User Timed Out", f"Successfully timed out {user.mention}\n**Duration:** {duration} seconds\n**Reason:** {reason}", interaction.user)
        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "timeout", f"Timed out {user} for {duration}s: {reason}")
    except Exception as e:
        embed = create_error_embed("Timeout Failed", f"Could not timeout {user.mention}: {str(e)}")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="unban", description="🔓 Unban a user from the server")
async def unban(interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.ban_members:
        embed = create_error_embed("Permission Denied", "You need `Ban Members` permission to use this command.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        user_id_int = int(user_id)
        user = await bot.fetch_user(user_id_int)
        await interaction.guild.unban(user, reason=f"Unbanned by {interaction.user}: {reason}")

        embed = create_success_embed("User Unbanned", f"Successfully unbanned {user}\n**Reason:** {reason}", interaction.user)
        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "unban", f"Unbanned {user} ({user_id}): {reason}")
    except ValueError:
        embed = create_error_embed("Invalid User ID", "Please provide a valid user ID.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        embed = create_error_embed("Unban Failed", f"Could not unban user: {str(e)}")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="clear", description="🗑️ Delete multiple messages")
async def clear(interaction: discord.Interaction, amount: int):
    if not interaction.user.guild_permissions.manage_messages:
        embed = create_error_embed("Permission Denied", "You need `Manage Messages` permission to use this command.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.manage_messages:
        embed = create_error_embed("Bot Permission Missing", "I need `Manage Messages` permission to delete messages.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if amount > 100:
        embed = create_error_embed("Too Many Messages", "You can only delete up to 100 messages at once.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        await interaction.response.defer()
        deleted = await interaction.channel.purge(limit=amount)

        embed = create_success_embed("Messages Cleared", f"Successfully deleted {len(deleted)} messages", interaction.user)
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_command_action(interaction, "clear", f"Deleted {len(deleted)} messages")
    except Exception as e:
        embed = create_error_embed("Clear Failed", f"Could not delete messages: {str(e)}")
        await interaction.followup.send(embed=embed, ephemeral=True)

# INFORMATION COMMANDS
@bot.tree.command(name="serverinfo", description="📊 Get detailed server information")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild

    embed = create_embed(
        title=f"📊 {guild.name} Server Information",
        description=f"Detailed information about **{guild.name}**",
        color=COLORS['blue']
    )

    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)

    # Basic info
    embed.add_field(name="🆔 Server ID", value=guild.id, inline=True)
    embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
    embed.add_field(name="📅 Created", value=f"<t:{int(guild.created_at.timestamp())}:F>", inline=True)

    # Member stats
    total_members = guild.member_count
    online_members = len([m for m in guild.members if m.status != discord.Status.offline])
    bot_count = len([m for m in guild.members if m.bot])

    embed.add_field(name="👥 Members", value=f"**Total:** {total_members}\n**Online:** {online_members}\n**Bots:** {bot_count}", inline=True)

    # Channel stats
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    categories = len(guild.categories)

    embed.add_field(name="📁 Channels", value=f"**Text:** {text_channels}\n**Voice:** {voice_channels}\n**Categories:** {categories}", inline=True)

    # Role and emoji stats
    embed.add_field(name="🎭 Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="😀 Emojis", value=len(guild.emojis), inline=True)
    embed.add_field(name="🔒 Verification", value=guild.verification_level.name.title(), inline=True)
    embed.add_field(name="🛡️ MFA Level", value=guild.mfa_level, inline=True)

    # Features
    features = []
    if guild.features:
        feature_names = {
            'COMMUNITY': '🌍 Community',
            'PARTNERED': '🤝 Partnered',
            'VERIFIED': '✅ Verified',
            'DISCOVERABLE': '🔍 Discoverable',
            'BANNER': '🎨 Banner',
            'VANITY_URL': '🔗 Vanity URL',
            'INVITE_SPLASH': '💫 Invite Splash',
            'ANIMATED_ICON': '🎭 Animated Icon'
        }
        for feature in guild.features:
            if feature in feature_names:
                features.append(feature_names[feature])

    if features:
        embed.add_field(name="✨ Features", value="\n".join(features[:5]), inline=False)

    embed.set_footer(text=f"Server Information • {guild.name}", icon_url=guild.icon.url if guild.icon else None)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "serverinfo", f"Viewed server info for {guild.name}")

@bot.tree.command(name="userinfo", description="👤 Get detailed user information")
async def userinfo(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user

    embed = create_embed(
        title=f"👤 {target_user.display_name}",
        description=f"Information about {target_user.mention}",
        color=target_user.color if target_user.color != discord.Color.default() else COLORS['blue']
    )

    embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url)

    # Basic info
    embed.add_field(name="🆔 User ID", value=target_user.id, inline=True)
    embed.add_field(name="👤 Username", value=target_user.name, inline=True)
    embed.add_field(name="🏷️ Display Name", value=target_user.display_name, inline=True)

    # Account info
    embed.add_field(name="📅 Account Created", value=f"<t:{int(target_user.created_at.timestamp())}:F>", inline=True)
    embed.add_field(name="📥 Joined Server", value=f"<t:{int(target_user.joined_at.timestamp())}:F>" if target_user.joined_at else "Unknown", inline=True)
    embed.add_field(name="🤖 Bot", value="Yes" if target_user.bot else "No", inline=True)

    # Status and activity
    status_emojis = {
        discord.Status.online: "🟢 Online",
        discord.Status.idle: "🟡 Idle",
        discord.Status.dnd: "🔴 Do Not Disturb",
        discord.Status.offline: "⚫ Offline"
    }
    embed.add_field(name="📱 Status", value=status_emojis.get(target_user.status, "Unknown"), inline=True)

    # Roles
    roles = [role.mention for role in target_user.roles if role != interaction.guild.default_role]
    if roles:
        roles_text = ", ".join(roles[:10])
        if len(target_user.roles) > 11:
            roles_text += f" (+{len(target_user.roles) - 11} more)"
        embed.add_field(name="🎭 Roles", value=roles_text, inline=False)

    # Permissions
    key_perms = []
    if target_user.guild_permissions.administrator:
        key_perms.append("👑 Administrator")
    if target_user.guild_permissions.manage_guild:
        key_perms.append("⚙️ Manage Server")
    if target_user.guild_permissions.manage_channels:
        key_perms.append("📁 Manage Channels")
    if target_user.guild_permissions.manage_roles:
        key_perms.append("🎭 Manage Roles")
    if target_user.guild_permissions.kick_members:
        key_perms.append("👢 Kick Members")
    if target_user.guild_permissions.ban_members:
        key_perms.append("🔨 Ban Members")

    if key_perms:
        embed.add_field(name="🔑 Key Permissions", value="\n".join(key_perms[:5]), inline=True)

    embed.set_footer(text=f"User Information • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "userinfo", f"Viewed user info for {target_user}")

@bot.tree.command(name="avatar", description="🖼️ Display user's avatar")
async def avatar(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user

    embed = create_embed(
        title=f"🖼️ {target_user.display_name}'s Avatar",
        description=f"Avatar for {target_user.mention}",
        color=target_user.color if target_user.color != discord.Color.default() else COLORS['blue']
    )

    avatar_url = target_user.avatar.url if target_user.avatar else target_user.default_avatar.url
    embed.set_image(url=avatar_url)

    embed.add_field(name="🔗 Avatar URL", value=f"[Click here]({avatar_url})", inline=True)
    embed.add_field(name="📱 User", value=target_user.mention, inline=True)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "avatar", f"Viewed avatar for {target_user}")

@bot.tree.command(name="ping", description="🏓 Check bot latency")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000, 2)

    if latency < 100:
        color = COLORS['success']
        status = "🟢 Excellent"
    elif latency < 300:
        color = COLORS['warning']
        status = "🟡 Good"
    else:
        color = COLORS['error']
        status = "🔴 Poor"

    embed = create_embed(
        title="🏓 Pong!",
        description="Bot latency information",
        color=color
    )

    embed.add_field(name="📶 Latency", value=f"{latency}ms", inline=True)
    embed.add_field(name="📊 Status", value=status, inline=True)
    embed.add_field(name="⏰ Uptime", value=f"<t:{int(bot_stats['start_time'])}:R>", inline=True)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "ping", f"Latency: {latency}ms")

# UTILITY COMMANDS
@bot.tree.command(name="say", description="💬 Make the bot say something")
async def say(interaction: discord.Interaction, message: str, channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.manage_messages:
        embed = create_error_embed("Permission Denied", "You need `Manage Messages` permission to use this command.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    target_channel = channel or interaction.channel

    if not target_channel.permissions_for(interaction.guild.me).send_messages:
        embed = create_error_embed("Cannot Send", f"I don't have permission to send messages in {target_channel.mention}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        # Replace variables in the message
        formatted_message = replace_variables(message, user=interaction.user, guild=interaction.guild, channel=target_channel)

        await target_channel.send(formatted_message)

        embed = create_success_embed("Message Sent", f"Successfully sent message to {target_channel.mention}", interaction.user)
        embed.add_field(name="📝 Message Preview", value=formatted_message[:100] + ("..." if len(formatted_message) > 100 else ""), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)
        await log_command_action(interaction, "say", f"Sent message to {target_channel.name}")
    except Exception as e:
        embed = create_error_embed("Send Failed", f"Could not send message: {str(e)}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="embed", description="📋 Create a custom embed")
async def embed_command(interaction: discord.Interaction, title: str, description: str, color: str = "blue"):
    if not interaction.user.guild_permissions.manage_messages:
        embed = create_error_embed("Permission Denied", "You need `Manage Messages` permission to use this command.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Parse color
    embed_color = COLORS.get(color.lower(), COLORS['blue'])
    if color.startswith("#"):
        try:
            embed_color = int(color[1:], 16)
        except:
            embed_color = COLORS['blue']

    # Replace variables
    formatted_title = replace_variables(title, user=interaction.user, guild=interaction.guild, channel=interaction.channel)
    formatted_desc = replace_variables(description, user=interaction.user, guild=interaction.guild, channel=interaction.channel)

    # Create embed
    custom_embed = discord.Embed(
        title=formatted_title,
        description=formatted_desc,
        color=embed_color,
        timestamp=discord.utils.utcnow()
    )

    custom_embed.set_footer(text=f"Created by {interaction.user.display_name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)

    await interaction.response.send_message(embed=custom_embed)
    await log_command_action(interaction, "embed", f"Created custom embed: {title}")

# ENHANCED WELCOME SYSTEM COMMAND (Interactive UI)
@bot.tree.command(name="welcomesetup", description="👋 Setup welcome system with interactive interface")
async def welcomesetup_interactive(interaction: discord.Interaction):
    """Setup welcome system using interactive embed interface"""
    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to setup welcome messages.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Create main welcome setup embed
    embed = create_embed(
        title="👋 Welcome System Setup",
        description="**Configure your welcome system with interactive controls**\n\nCustomize welcome messages, channels, embeds, and more with live previews.",
        color=COLORS['success']
    )
    
    embed.add_field(
        name="🎯 Configuration Options",
        value="• **📍 Set Channel** - Where welcome messages are sent\n• **📝 Edit Message** - Customize welcome text with variables\n• **🎨 Customize Embed** - Title, description, and colors",
        inline=False
    )
    
    embed.add_field(
        name="✨ Features Available",
        value="• **🔄 Live Preview** - See exactly how messages will look\n• **📋 Variable Support** - Dynamic user/server info\n• **💌 DM Options** - Optional direct message welcome\n• **🎨 Full Customization** - Colors, titles, descriptions",
        inline=False
    )
    
    embed.add_field(
        name="📋 Current Status",
        value="❌ **Channel:** Not set\n❌ **Message:** Using default\n⚙️ **Ready to configure**",
        inline=False
    )
    
    embed.set_footer(text="Configure your welcome system step by step • Manage Server Permission Required")
    
    # Create interactive view
    view = WelcomeSetupConfigView(interaction.user.id, interaction.guild.id)
    
    await interaction.response.send_message(embed=embed, view=view)
    await log_command_action(interaction, "welcomesetup", "Started interactive welcome setup")

# LEGACY WELCOME SETUP COMMAND (parameter-based)
@bot.tree.command(name="welcomesetup_legacy", description="👋 Legacy welcome setup with parameters")
@discord.app_commands.describe(
    channel="Channel for welcome messages",
    message="Welcome message (supports variables like {user.mention}, {guild.name})",
    embed_color="Embed color (hex like #ff0000 or color name)"
)
async def welcomesetup(interaction: discord.Interaction, channel: discord.TextChannel, 
                      message: str = "Welcome to {guild.name}, {user.mention}! 🎉", 
                      embed_color: str = "green"):
    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to setup welcome messages.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Parse color
    color_value = COLORS.get(embed_color.lower(), COLORS['success'])
    if embed_color.startswith("#"):
        try:
            color_value = int(embed_color[1:], 16)
        except:
            color_value = COLORS['success']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR REPLACE INTO guild_settings
        (guild_id, welcome_enabled, welcome_channel_id, welcome_message, welcome_embed_title, welcome_embed_description, welcome_embed_color)
        VALUES (?, 1, ?, ?, ?, ?, ?)
    ''', (interaction.guild.id, channel.id, message, "Welcome!", "Welcome to our amazing server!", color_value))

    conn.commit()
    conn.close()

    embed = create_success_embed("Welcome System Setup Complete!", f"Welcome messages will be sent to {channel.mention}", interaction.user)
    embed.add_field(name="💬 Message Preview", value=replace_variables(message, user=interaction.user, guild=interaction.guild)[:100], inline=False)
    embed.add_field(name="🎨 Color", value=f"#{color_value:06x}", inline=True)
    embed.add_field(name="📋 Variables Supported", value="`{user.mention}`, `{guild.name}`, `{guild.membercount}`, `{user.name}`", inline=False)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "welcomesetup", f"Setup welcome in {channel.name}")

@bot.tree.command(name="welcometest", description="🧪 Test welcome message with any user")
@discord.app_commands.describe(user="User to test welcome message with (optional)")
async def welcometest(interaction: discord.Interaction, user: discord.Member = None):
    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to test welcome messages.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    test_user = user or interaction.user

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM guild_settings WHERE guild_id = ? AND welcome_enabled = 1', (interaction.guild.id,))
    settings = cursor.fetchone()
    conn.close()

    if not settings:
        embed = create_error_embed("Welcome System Disabled", "Welcome system is not enabled. Use `/welcomesetup` to enable it.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    welcome_channel = interaction.guild.get_channel(settings[2])
    if not welcome_channel:
        embed = create_error_embed("Channel Not Found", "Welcome channel no longer exists.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Create test welcome embed
    welcome_embed = discord.Embed(
        title=settings[4] or "Welcome!",
        description=replace_variables(settings[5] or "Welcome to our server!", user=test_user, guild=interaction.guild),
        color=settings[6] or COLORS['success'],
        timestamp=discord.utils.utcnow()
    )

    welcome_embed.set_thumbnail(url=test_user.avatar.url if test_user.avatar else test_user.default_avatar.url)
    welcome_embed.add_field(name="👤 Member", value=test_user.mention, inline=True)
    welcome_embed.add_field(name="📊 Member Count", value=interaction.guild.member_count, inline=True)
    welcome_embed.add_field(name="🧪 Test Mode", value="This is a test message", inline=True)

    welcome_message = replace_variables(settings[3] or "Welcome {user.mention}!", user=test_user, guild=interaction.guild)

    await welcome_channel.send(f"🧪 **TEST MESSAGE** - {welcome_message}", embed=welcome_embed)

    embed = create_success_embed("Welcome Test Sent!", f"Test welcome message sent to {welcome_channel.mention} for {test_user.mention}", interaction.user)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="welcomeconfig", description="⚙️ Advanced welcome system configuration")
@discord.app_commands.describe(
    setting="Setting to configure",
    value="New value for the setting",
    channel="Channel for welcome messages"
)
@discord.app_commands.choices(setting=[
    discord.app_commands.Choice(name="📝 Welcome Message", value="message"),
    discord.app_commands.Choice(name="🎨 Embed Color", value="color"),
    discord.app_commands.Choice(name="📋 Embed Title", value="title"),
    discord.app_commands.Choice(name="📄 Embed Description", value="description"),
    discord.app_commands.Choice(name="📍 Welcome Channel", value="channel"),
    discord.app_commands.Choice(name="💌 DM Welcome", value="dm_enabled"),
    discord.app_commands.Choice(name="🔄 Toggle System", value="toggle"),
    discord.app_commands.Choice(name="📊 Show Config", value="show")
])
async def welcomeconfig(interaction: discord.Interaction, setting: discord.app_commands.Choice[str], 
                       value: str = None, channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to configure welcome.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    guild_id = interaction.guild.id

    if setting.value == "show":
        cursor.execute('SELECT * FROM guild_settings WHERE guild_id = ?', (guild_id,))
        settings = cursor.fetchone()
        conn.close()

        if not settings:
            embed = create_info_embed("No Configuration", "Welcome system is not configured. Use `/welcomesetup` first.")
            await interaction.response.send_message(embed=embed)
            return

        welcome_channel = interaction.guild.get_channel(settings[2]) if settings[2] else None
        
        embed = create_embed(
            title="⚙️ Welcome System Configuration",
            description="Current welcome system settings",
            color=settings[6] or COLORS['blue']
        )

        embed.add_field(name="🔧 Status", value="🟢 Enabled" if settings[1] else "🔴 Disabled", inline=True)
        embed.add_field(name="📍 Channel", value=welcome_channel.mention if welcome_channel else "Not set", inline=True)
        embed.add_field(name="💌 DM Welcome", value="✅ Yes" if settings[7] else "❌ No", inline=True)
        embed.add_field(name="💬 Message", value=(settings[3] or "Default")[:100], inline=False)
        embed.add_field(name="📋 Embed Title", value=settings[4] or "Welcome!", inline=True)
        embed.add_field(name="🎨 Color", value=f"#{(settings[6] or COLORS['success']):06x}", inline=True)

        await interaction.response.send_message(embed=embed)
        return

    if not value and setting.value != "toggle":
        if setting.value == "channel" and not channel:
            embed = create_error_embed("Missing Value", "Please provide a value or channel for this setting.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            conn.close()
            return

    try:
        if setting.value == "message":
            cursor.execute('UPDATE guild_settings SET welcome_message = ? WHERE guild_id = ?', (value, guild_id))
        elif setting.value == "color":
            color_value = COLORS.get(value.lower(), COLORS['success'])
            if value.startswith("#"):
                color_value = int(value[1:], 16)
            cursor.execute('UPDATE guild_settings SET welcome_embed_color = ? WHERE guild_id = ?', (color_value, guild_id))
        elif setting.value == "title":
            cursor.execute('UPDATE guild_settings SET welcome_embed_title = ? WHERE guild_id = ?', (value, guild_id))
        elif setting.value == "description":
            cursor.execute('UPDATE guild_settings SET welcome_embed_description = ? WHERE guild_id = ?', (value, guild_id))
        elif setting.value == "channel":
            target_channel = channel
            cursor.execute('UPDATE guild_settings SET welcome_channel_id = ? WHERE guild_id = ?', (target_channel.id, guild_id))
        elif setting.value == "dm_enabled":
            dm_value = value.lower() in ["true", "yes", "1", "on", "enable"]
            cursor.execute('UPDATE guild_settings SET welcome_dm_enabled = ? WHERE guild_id = ?', (dm_value, guild_id))
        elif setting.value == "toggle":
            cursor.execute('SELECT welcome_enabled FROM guild_settings WHERE guild_id = ?', (guild_id,))
            current = cursor.fetchone()
            new_status = not (current[0] if current else False)
            cursor.execute('UPDATE guild_settings SET welcome_enabled = ? WHERE guild_id = ?', (new_status, guild_id))

        conn.commit()
        conn.close()

        embed = create_success_embed("Configuration Updated", f"Successfully updated {setting.name}", interaction.user)
        if setting.value == "toggle":
            embed.add_field(name="New Status", value="🟢 Enabled" if new_status else "🔴 Disabled", inline=True)
        else:
            embed.add_field(name="New Value", value=str(value or channel.mention if channel else "Updated"), inline=True)

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "welcomeconfig", f"Updated {setting.value}")

    except Exception as e:
        embed = create_error_embed("Configuration Failed", f"Failed to update setting: {str(e)}")
        await interaction.response.send_message(embed=embed)
        conn.close()

# TICKET PANEL COMMANDS
@bot.tree.command(name="ticketpanel", description="🎫 Advanced ticket panel management")
@discord.app_commands.describe(action="Action to perform with ticket panels")
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name="🎫 Setup Comprehensive Panel", value="setup"),
    discord.app_commands.Choice(name="⚙️ Configure Panel Settings", value="config"),
    discord.app_commands.Choice(name="📋 List Panel Information", value="list")
])
async def ticketpanel(interaction: discord.Interaction, action: discord.app_commands.Choice[str]):
    if not interaction.user.guild_permissions.manage_channels:
        embed = create_error_embed("Permission Denied", "You need `Manage Channels` permission to manage ticket panels.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild_id = interaction.guild.id

    if guild_id not in ticket_systems:
        ticket_systems[guild_id] = init_default_ticket_system(guild_id)
        ticket_counter[guild_id] = 0

    system = ticket_systems[guild_id]

    if action.value == "setup":
        await setup_comprehensive_ticket_panel(interaction, system)
    elif action.value == "config":
        await configure_ticket_panel(interaction, system)
    elif action.value == "list":
        await list_ticket_panel_info(interaction, system)

async def setup_comprehensive_ticket_panel(interaction, system):
    """Setup a comprehensive ticket panel with advanced features"""
    
    embed = create_embed(
        title="🎫 Comprehensive Ticket Panel Setup",
        description="Setting up advanced ticket system with 25+ ticket types and full customization...",
        color=COLORS['blue']
    )
    
    await interaction.response.defer()

    # Enhanced ticket types with better categorization
    enhanced_ticket_types = [
        # Support Categories
        TicketType("General Support", "🆘", "General help and assistance", color=0x3498db),
        TicketType("Technical Support", "🔧", "Technical issues and troubleshooting", color=0xe74c3c),
        TicketType("Account Issues", "👤", "Account problems and access issues", color=0x9b59b6),
        TicketType("Billing Support", "💳", "Payment and billing inquiries", color=0xf39c12),
        TicketType("Bug Report", "🐛", "Report bugs and issues", color=0xe74c3c),
        TicketType("Feature Request", "✨", "Request new features", color=0x2ecc71),
        
        # Business Categories  
        TicketType("Partnership", "🤝", "Business partnerships and collaborations", color=0x3498db),
        TicketType("Sponsorship", "💰", "Sponsorship opportunities", color=0xf39c12),
        TicketType("Media Inquiry", "📰", "Press and media requests", color=0x9b59b6),
        TicketType("Business Support", "🏢", "Business-related inquiries", color=0x34495e),
        
        # Community Categories
        TicketType("Staff Application", "📋", "Apply for staff positions", color=0x2ecc71),
        TicketType("Report User", "⚠️", "Report users for violations", color=0xe74c3c),
        TicketType("Report Staff", "🚨", "Report staff misconduct", color=0xe74c3c),
        TicketType("Ban Appeal", "🔓", "Appeal bans or punishments", color=0x95a5a6),
        TicketType("Community Feedback", "💬", "Feedback about the community", color=0x3498db),
        
        # Creative Categories
        TicketType("Commission Request", "🎨", "Art and creative commissions", color=0xe67e22),
        TicketType("Content Creation", "📺", "Content collaboration requests", color=0x9b59b6),
        TicketType("Event Planning", "🎉", "Community event planning", color=0xf39c12),
        TicketType("Giveaway Support", "🎁", "Giveaway management and support", color=0x2ecc71),
        
        # Development Categories
        TicketType("Development Help", "💻", "Programming and development assistance", color=0x2c3e50),
        TicketType("API Support", "🔌", "API integration and support", color=0x34495e),
        TicketType("Bot Issues", "🤖", "Bot-related problems", color=0x7f8c8d),
        
        # Special Categories
        TicketType("VIP Support", "👑", "Priority support for VIP members", color=0xf1c40f),
        TicketType("Emergency", "🚨", "Urgent emergency assistance", color=0xc0392b),
        TicketType("Other", "❓", "Other issues not covered above", color=0x95a5a6)
    ]

    # Clear existing and add enhanced types
    system.ticket_types.clear()
    for ticket_type in enhanced_ticket_types:
        system.add_ticket_type(ticket_type)

    # Create advanced panel embed
    panel_embed = discord.Embed(
        title="🎫 Advanced Support Ticket System",
        description="**Need help? Create a support ticket!**\n\nSelect the type of support you need from the dropdown below. Our team will assist you as soon as possible.\n\n✨ **Features:**\n• 25+ specialized ticket types\n• Automatic categorization\n• Real-time statistics\n• Professional support team",
        color=0x5865f2
    )

    panel_embed.add_field(
        name="📊 Ticket Statistics",
        value=f"🟢 **Active Tickets:** {len([t for t in active_tickets.values() if t.status == 'open'])}\n📈 **Total Processed:** {ticket_counter.get(interaction.guild.id, 0):,}\n⭐ **Available Types:** {len(system.ticket_types)}",
        inline=True
    )

    panel_embed.add_field(
        name="⏱️ Response Times",
        value="🚨 **Emergency:** < 5 minutes\n👑 **VIP Support:** < 10 minutes\n🆘 **General:** < 30 minutes\n📋 **Applications:** < 24 hours",
        inline=True
    )

    panel_embed.add_field(
        name="📋 Support Hours",
        value="🕐 **Active Support:** 24/7\n🌟 **Peak Hours:** 9 AM - 11 PM EST\n📞 **Emergency Line:** Always available",
        inline=True
    )

    panel_embed.add_field(
        name="🎯 Before Creating a Ticket",
        value="• Check <#general> for common solutions\n• Read our FAQ section\n• Search existing tickets\n• Be specific about your issue",
        inline=False
    )

    panel_embed.set_footer(
        text=f"Support System • {interaction.guild.name} • React below to create a ticket",
        icon_url=interaction.guild.icon.url if interaction.guild.icon else None
    )

    panel_embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)

    # Create advanced dropdown view
    view = AdvancedTicketDropdownView(system)

    await interaction.followup.send(embed=panel_embed, view=view)

    # Send setup completion message
    completion_embed = create_success_embed(
        "🎫 Comprehensive Ticket Panel Created!",
        f"Advanced ticket system with {len(enhanced_ticket_types)} ticket types has been set up!",
        interaction.user
    )
    completion_embed.add_field(name="✨ Features", value="• 25+ ticket types\n• Advanced dropdown menu\n• Real-time statistics\n• Auto-categorization", inline=True)
    completion_embed.add_field(name="📊 Categories", value="• Support (6 types)\n• Business (4 types)\n• Community (5 types)\n• Creative (4 types)\n• Development (3 types)\n• Special (3 types)", inline=True)

    await interaction.followup.send(embed=completion_embed, ephemeral=True)
    await log_command_action(interaction, "ticketpanel setup", f"Created comprehensive panel with {len(enhanced_ticket_types)} types")

async def configure_ticket_panel(interaction, system):
    """Configure ticket panel settings"""
    embed = create_embed(
        title="⚙️ Ticket Panel Configuration",
        description="Current ticket panel settings and options",
        color=COLORS['blue']
    )

    embed.add_field(name="🎫 System Status", value="🟢 Enabled" if system.enabled else "🔴 Disabled", inline=True)
    embed.add_field(name="📊 Ticket Types", value=f"{len(system.ticket_types)} configured", inline=True)
    embed.add_field(name="📁 Auto-Categorize", value="✅ Yes" if system.auto_categorize else "❌ No", inline=True)
    embed.add_field(name="🎨 Panel Color", value=f"#{system.embed_color:06x}", inline=True)
    embed.add_field(name="👥 Max per User", value=f"{system.max_tickets_per_user} tickets", inline=True)
    embed.add_field(name="📝 Transcripts", value="✅ Yes" if system.transcript_logs else "❌ No", inline=True)

    embed.add_field(
        name="🔧 Available Settings",
        value="Use `/ticketconfig` to modify:\n• Embed colors and text\n• Maximum tickets per user\n• Auto-categorization\n• Welcome messages\n• System toggle",
        inline=False
    )

    await interaction.response.send_message(embed=embed)

async def list_ticket_panel_info(interaction, system):
    """List comprehensive ticket panel information"""
    total_tickets = ticket_counter.get(interaction.guild.id, 0)
    active_tickets_count = len([t for t in active_tickets.values() if t.channel_id in [c.id for c in interaction.guild.channels] and t.status == "open"])

    embed = create_embed(
        title="📋 Ticket Panel Information",
        description=f"Complete information for **{interaction.guild.name}** ticket system",
        color=COLORS['blue']
    )

    embed.add_field(name="📊 Statistics", value=f"**Total Tickets:** {total_tickets:,}\n**Active Tickets:** {active_tickets_count}\n**Available Types:** {len(system.ticket_types)}", inline=True)
    embed.add_field(name="⚙️ System Info", value=f"**Status:** {'🟢 Active' if system.enabled else '🔴 Inactive'}\n**Auto-Cat:** {'✅' if system.auto_categorize else '❌'}\n**Transcripts:** {'✅' if system.transcript_logs else '❌'}", inline=True)
    embed.add_field(name="👥 Limits", value=f"**Max per User:** {system.max_tickets_per_user}\n**Staff Ping:** {'✅' if system.ping_staff else '❌'}", inline=True)

    # Show ticket types by category
    categories = {
        "🆘 Support": ["General Support", "Technical Support", "Account Issues", "Billing Support", "Bug Report", "Feature Request"],
        "🏢 Business": ["Partnership", "Sponsorship", "Media Inquiry", "Business Support"],
        "👥 Community": ["Staff Application", "Report User", "Report Staff", "Ban Appeal", "Community Feedback"],
        "🎨 Creative": ["Commission Request", "Content Creation", "Event Planning", "Giveaway Support"],
        "💻 Development": ["Development Help", "API Support", "Bot Issues"],
        "⭐ Special": ["VIP Support", "Emergency", "Other"]
    }

    for category, type_names in categories.items():
        available_types = [name for name in type_names if name.lower() in system.ticket_types]
        if available_types:
            embed.add_field(name=category, value=f"{len(available_types)} types available", inline=True)

    embed.add_field(
        name="🎯 Panel Features",
        value="• Advanced dropdown selection\n• Real-time statistics display\n• Professional support categorization\n• Emergency priority handling\n• VIP member prioritization",
        inline=False
    )

    await interaction.response.send_message(embed=embed)

class AdvancedTicketDropdownView(discord.ui.View):
    def __init__(self, ticket_system):
        super().__init__(timeout=None)
        self.ticket_system = ticket_system

        # Create categorized dropdowns
        self.add_item(SupportTicketDropdown(ticket_system))
        self.add_item(BusinessTicketDropdown(ticket_system))
        self.add_item(CommunityTicketDropdown(ticket_system))

        # Add utility buttons
        self.add_item(RefreshStatsButton())
        self.add_item(EmergencyTicketButton())

class SupportTicketDropdown(discord.ui.Select):
    def __init__(self, ticket_system):
        self.ticket_system = ticket_system

        support_types = ["General Support", "Technical Support", "Account Issues", "Billing Support", "Bug Report", "Feature Request"]
        options = []

        for type_name in support_types:
            ticket_type = ticket_system.get_ticket_type(type_name)
            if ticket_type:
                options.append(discord.SelectOption(
                    label=ticket_type.name,
                    description=ticket_type.description[:100],
                    emoji=ticket_type.emoji,
                    value=ticket_type.name.lower()
                ))

        super().__init__(
            placeholder="🆘 Support & Technical Issues...",
            options=options,
            min_values=1,
            max_values=1,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        await create_user_ticket(interaction, self.ticket_system, self.values[0])

class BusinessTicketDropdown(discord.ui.Select):
    def __init__(self, ticket_system):
        self.ticket_system = ticket_system

        business_types = ["Partnership", "Sponsorship", "Media Inquiry", "Business Support", "Commission Request", "Content Creation"]
        options = []

        for type_name in business_types:
            ticket_type = ticket_system.get_ticket_type(type_name)
            if ticket_type:
                options.append(discord.SelectOption(
                    label=ticket_type.name,
                    description=ticket_type.description[:100],
                    emoji=ticket_type.emoji,
                    value=ticket_type.name.lower()
                ))

        super().__init__(
            placeholder="🏢 Business & Partnerships...",
            options=options,
            min_values=1,
            max_values=1,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        await create_user_ticket(interaction, self.ticket_system, self.values[0])

class CommunityTicketDropdown(discord.ui.Select):
    def __init__(self, ticket_system):
        self.ticket_system = ticket_system

        community_types = ["Staff Application", "Report User", "Report Staff", "Ban Appeal", "Community Feedback", "VIP Support", "Other"]
        options = []

        for type_name in community_types:
            ticket_type = ticket_system.get_ticket_type(type_name)
            if ticket_type:
                options.append(discord.SelectOption(
                    label=ticket_type.name,
                    description=ticket_type.description[:100],
                    emoji=ticket_type.emoji,
                    value=ticket_type.name.lower()
                ))

        super().__init__(
            placeholder="👥 Community & Applications...",
            options=options,
            min_values=1,
            max_values=1,
            row=2
        )

    async def callback(self, interaction: discord.Interaction):
        await create_user_ticket(interaction, self.ticket_system, self.values[0])

class RefreshStatsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Refresh Stats",
            emoji="📊",
            style=discord.ButtonStyle.secondary,
            row=3
        )

    async def callback(self, interaction: discord.Interaction):
        active_count = len([t for t in active_tickets.values() if t.channel_id in [c.id for c in interaction.guild.channels] and t.status == "open"])
        total_count = ticket_counter.get(interaction.guild.id, 0)

        embed = create_embed(
            title="📊 Real-Time Ticket Statistics",
            description=f"Updated at <t:{int(time.time())}:f>",
            color=COLORS['blue']
        )
        embed.add_field(name="🟢 Active Tickets", value=f"{active_count}", inline=True)
        embed.add_field(name="📈 Total Processed", value=f"{total_count:,}", inline=True)
        embed.add_field(name="⚡ System Status", value="🟢 Operational", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

class EmergencyTicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Emergency",
            emoji="🚨",
            style=discord.ButtonStyle.danger,
            row=3
        )

    async def callback(self, interaction: discord.Interaction):
        # Create emergency ticket directly
        guild_id = interaction.guild.id
        if guild_id in ticket_systems:
            emergency_type = ticket_systems[guild_id].get_ticket_type("emergency")
            if emergency_type:
                await create_user_ticket(interaction, ticket_systems[guild_id], "emergency")
            else:
                embed = create_error_embed("Emergency Type Not Found", "Emergency ticket type is not configured.")
                await interaction.response.send_message(embed=embed, ephemeral=True)

# GOODBYE SYSTEM COMMANDS
@bot.tree.command(name="goodbyesetup", description="👋 Quick goodbye system setup")
@discord.app_commands.describe(
    channel="Channel for goodbye messages",
    message="Goodbye message (supports variables like {user.name}, {guild.name})",
    embed_color="Embed color (hex like #ff0000 or color name)"
)
async def goodbyesetup(interaction: discord.Interaction, channel: discord.TextChannel,
                      message: str = "Goodbye {user.name}, thanks for being part of {guild.name}! 👋",
                      embed_color: str = "orange"):
    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to setup goodbye messages.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Parse color
    color_value = COLORS.get(embed_color.lower(), COLORS['warning'])
    if embed_color.startswith("#"):
        try:
            color_value = int(embed_color[1:], 16)
        except:
            color_value = COLORS['warning']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR REPLACE INTO guild_settings
        (guild_id, goodbye_enabled, goodbye_channel_id, goodbye_message, goodbye_embed_title, goodbye_embed_description, goodbye_embed_color)
        VALUES (?, 1, ?, ?, ?, ?, ?)
    ''', (interaction.guild.id, channel.id, message, "Farewell!", "Thanks for being part of our community!", color_value))

    conn.commit()
    conn.close()

    embed = create_success_embed("Goodbye System Setup Complete!", f"Goodbye messages will be sent to {channel.mention}", interaction.user)
    embed.add_field(name="💬 Message Preview", value=replace_variables(message, user=interaction.user, guild=interaction.guild)[:100], inline=False)
    embed.add_field(name="🎨 Color", value=f"#{color_value:06x}", inline=True)
    embed.add_field(name="📋 Variables Supported", value="`{user.name}`, `{guild.name}`, `{guild.membercount}`, `{user.mention}`", inline=False)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "goodbyesetup", f"Setup goodbye in {channel.name}")

@bot.tree.command(name="goodbyetest", description="🧪 Test goodbye message with any user")
@discord.app_commands.describe(user="User to test goodbye message with (optional)")
async def goodbyetest(interaction: discord.Interaction, user: discord.Member = None):
    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to test goodbye messages.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    test_user = user or interaction.user

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM guild_settings WHERE guild_id = ? AND goodbye_enabled = 1', (interaction.guild.id,))
    settings = cursor.fetchone()
    conn.close()

    if not settings:
        embed = create_error_embed("Goodbye System Disabled", "Goodbye system is not enabled. Use `/goodbyesetup` to enable it.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    goodbye_channel = interaction.guild.get_channel(settings[9])
    if not goodbye_channel:
        embed = create_error_embed("Channel Not Found", "Goodbye channel no longer exists.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Create test goodbye embed
    goodbye_embed = discord.Embed(
        title=settings[11] or "Farewell!",
        description=replace_variables(settings[12] or "Thanks for being part of our community!", user=test_user, guild=interaction.guild),
        color=settings[13] or COLORS['warning'],
        timestamp=discord.utils.utcnow()
    )

    goodbye_embed.set_thumbnail(url=test_user.avatar.url if test_user.avatar else test_user.default_avatar.url)
    goodbye_embed.add_field(name="👤 Member", value=f"{test_user.name}#{test_user.discriminator}", inline=True)
    goodbye_embed.add_field(name="📊 Members Left", value=interaction.guild.member_count, inline=True)
    goodbye_embed.add_field(name="🧪 Test Mode", value="This is a test message", inline=True)

    goodbye_message = replace_variables(settings[10] or "Goodbye {user.name}!", user=test_user, guild=interaction.guild)

    await goodbye_channel.send(f"🧪 **TEST MESSAGE** - {goodbye_message}", embed=goodbye_embed)

    embed = create_success_embed("Goodbye Test Sent!", f"Test goodbye message sent to {goodbye_channel.mention} for {test_user.mention}", interaction.user)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="goodbyeconfig", description="⚙️ Advanced goodbye system configuration")
@discord.app_commands.describe(
    setting="Setting to configure",
    value="New value for the setting",
    channel="Channel for goodbye messages"
)
@discord.app_commands.choices(setting=[
    discord.app_commands.Choice(name="📝 Goodbye Message", value="message"),
    discord.app_commands.Choice(name="🎨 Embed Color", value="color"),
    discord.app_commands.Choice(name="📋 Embed Title", value="title"),
    discord.app_commands.Choice(name="📄 Embed Description", value="description"),
    discord.app_commands.Choice(name="📍 Goodbye Channel", value="channel"),
    discord.app_commands.Choice(name="🔄 Toggle System", value="toggle"),
    discord.app_commands.Choice(name="📊 Show Config", value="show")
])
async def goodbyeconfig(interaction: discord.Interaction, setting: discord.app_commands.Choice[str],
                       value: str = None, channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to configure goodbye.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    guild_id = interaction.guild.id

    if setting.value == "show":
        cursor.execute('SELECT * FROM guild_settings WHERE guild_id = ?', (guild_id,))
        settings = cursor.fetchone()
        conn.close()

        if not settings:
            embed = create_info_embed("No Configuration", "Goodbye system is not configured. Use `/goodbyesetup` first.")
            await interaction.response.send_message(embed=embed)
            return

        goodbye_channel = interaction.guild.get_channel(settings[9]) if settings[9] else None

        embed = create_embed(
            title="⚙️ Goodbye System Configuration",
            description="Current goodbye system settings",
            color=settings[13] or COLORS['warning']
        )

        embed.add_field(name="🔧 Status", value="🟢 Enabled" if settings[8] else "🔴 Disabled", inline=True)
        embed.add_field(name="📍 Channel", value=goodbye_channel.mention if goodbye_channel else "Not set", inline=True)
        embed.add_field(name="💬 Message", value=(settings[10] or "Default")[:100], inline=False)
        embed.add_field(name="📋 Embed Title", value=settings[11] or "Farewell!", inline=True)
        embed.add_field(name="🎨 Color", value=f"#{(settings[13] or COLORS['warning']):06x}", inline=True)

        await interaction.response.send_message(embed=embed)
        return

    if not value and setting.value != "toggle":
        if setting.value == "channel" and not channel:
            embed = create_error_embed("Missing Value", "Please provide a value or channel for this setting.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            conn.close()
            return

    try:
        if setting.value == "message":
            cursor.execute('UPDATE guild_settings SET goodbye_message = ? WHERE guild_id = ?', (value, guild_id))
        elif setting.value == "color":
            color_value = COLORS.get(value.lower(), COLORS['warning'])
            if value.startswith("#"):
                color_value = int(value[1:], 16)
            cursor.execute('UPDATE guild_settings SET goodbye_embed_color = ? WHERE guild_id = ?', (color_value, guild_id))
        elif setting.value == "title":
            cursor.execute('UPDATE guild_settings SET goodbye_embed_title = ? WHERE guild_id = ?', (value, guild_id))
        elif setting.value == "description":
            cursor.execute('UPDATE guild_settings SET goodbye_embed_description = ? WHERE guild_id = ?', (value, guild_id))
        elif setting.value == "channel":
            target_channel = channel
            cursor.execute('UPDATE guild_settings SET goodbye_channel_id = ? WHERE guild_id = ?', (target_channel.id, guild_id))
        elif setting.value == "toggle":
            cursor.execute('SELECT goodbye_enabled FROM guild_settings WHERE guild_id = ?', (guild_id,))
            current = cursor.fetchone()
            new_status = not (current[0] if current else False)
            cursor.execute('UPDATE guild_settings SET goodbye_enabled = ? WHERE guild_id = ?', (new_status, guild_id))

        conn.commit()
        conn.close()

        embed = create_success_embed("Configuration Updated", f"Successfully updated {setting.name}", interaction.user)
        if setting.value == "toggle":
            embed.add_field(name="New Status", value="🟢 Enabled" if new_status else "🔴 Disabled", inline=True)
        else:
            embed.add_field(name="New Value", value=str(value or channel.mention if channel else "Updated"), inline=True)

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "goodbyeconfig", f"Updated {setting.value}")

    except Exception as e:
        embed = create_error_embed("Configuration Failed", f"Failed to update setting: {str(e)}")
        await interaction.response.send_message(embed=embed)
        conn.close()

# WELCOME/GOODBYE SYSTEM
@bot.tree.command(name="welcome", description="👋 Configure welcome messages")
@discord.app_commands.describe(
    action="Action to perform",
    channel="Channel for welcome messages",
    message="Welcome message (supports variables)",
    embed_title="Title for welcome embed",
    embed_description="Description for welcome embed"
)
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name="🟢 Enable", value="enable"),
    discord.app_commands.Choice(name="🔴 Disable", value="disable"),
    discord.app_commands.Choice(name="⚙️ Configure", value="configure"),
    discord.app_commands.Choice(name="📊 Status", value="status"),
    discord.app_commands.Choice(name="🧪 Test", value="test")
])
async def welcome(interaction: discord.Interaction, action: discord.app_commands.Choice[str],
                 channel: discord.TextChannel = None, message: str = None,
                 embed_title: str = None, embed_description: str = None):

    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to configure welcome messages.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    guild_id = interaction.guild.id

    if action.value == "enable":
        if not channel:
            embed = create_error_embed("Missing Channel", "Please specify a channel for welcome messages.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            conn.close()
            return

        cursor.execute('''
            INSERT OR REPLACE INTO guild_settings
            (guild_id, welcome_enabled, welcome_channel_id, welcome_message, welcome_embed_title, welcome_embed_description)
            VALUES (?, 1, ?, ?, ?, ?)
        ''', (guild_id, channel.id,
              message or "Welcome to {guild.name}, {user.mention}! 🎉",
              embed_title or "Welcome!",
              embed_description or "Welcome to our awesome server!"))

        conn.commit()
        conn.close()

        embed = create_success_embed("Welcome System Enabled", f"Welcome messages will be sent to {channel.mention}", interaction.user)
        await interaction.response.send_message(embed=embed)

    elif action.value == "disable":
        cursor.execute('UPDATE guild_settings SET welcome_enabled = 0 WHERE guild_id = ?', (guild_id,))
        conn.commit()
        conn.close()

        embed = create_success_embed("Welcome System Disabled", "Welcome messages have been disabled", interaction.user)
        await interaction.response.send_message(embed=embed)

    elif action.value == "status":
        cursor.execute('SELECT * FROM guild_settings WHERE guild_id = ?', (guild_id,))
        settings = cursor.fetchone()
        conn.close()

        if settings and settings[1]:  # welcome_enabled
            welcome_channel = interaction.guild.get_channel(settings[2])
            embed = create_embed(
                title="👋 Welcome System Status",
                description="Welcome system is **ENABLED**",
                color=COLORS['success']
            )
            embed.add_field(name="📍 Channel", value=welcome_channel.mention if welcome_channel else "Channel not found", inline=True)
            embed.add_field(name="💬 Message", value=settings[3] or "Default message", inline=False)
        else:
            embed = create_embed(
                title="👋 Welcome System Status",
                description="Welcome system is **DISABLED**",
                color=COLORS['error']
            )

        await interaction.response.send_message(embed=embed)

    elif action.value == "test":
        if not interaction.user.guild_permissions.manage_guild:
            embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to test welcome messages.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        test_user = interaction.user # Default to interaction user for testing

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM guild_settings WHERE guild_id = ? AND welcome_enabled = 1', (interaction.guild.id,))
        settings = cursor.fetchone()
        conn.close()

        if not settings:
            embed = create_error_embed("Welcome System Disabled", "Welcome system is not enabled. Use `/welcome enable` to enable it.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        welcome_channel = interaction.guild.get_channel(settings[2])
        if not welcome_channel:
            embed = create_error_embed("Channel Not Found", "Welcome channel no longer exists.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Create test welcome embed
        welcome_embed = discord.Embed(
            title=settings[4] or "Welcome!",
            description=replace_variables(settings[5] or "Welcome to our server!", user=test_user, guild=interaction.guild),
            color=settings[6] or COLORS['success'],
            timestamp=discord.utils.utcnow()
        )

        welcome_embed.set_thumbnail(url=test_user.avatar.url if test_user.avatar else test_user.default_avatar.url)
        welcome_embed.add_field(name="👤 Member", value=test_user.mention, inline=True)
        welcome_embed.add_field(name="📊 Member Count", value=interaction.guild.member_count, inline=True)
        welcome_embed.add_field(name="🧪 Test Mode", value="This is a test message", inline=True)

        welcome_message = replace_variables(settings[3] or "Welcome {user.mention}!", user=test_user, guild=interaction.guild)

        await welcome_channel.send(f"🧪 **TEST MESSAGE** - {welcome_message}", embed=welcome_embed)

        embed = create_success_embed("Welcome Test Sent!", f"Test welcome message sent to {welcome_channel.mention} for {test_user.mention}", interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await log_command_action(interaction, "welcome", f"Tested welcome for {test_user}")

    else: # configure or other actions
        embed = create_error_embed("Invalid Action", "Please choose a valid action: enable, disable, configure, status, test.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_member_join(member):
    """Handle member join for welcome messages"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM guild_settings WHERE guild_id = ? AND welcome_enabled = 1', (member.guild.id,))
        settings = cursor.fetchone()
        conn.close()

        if not settings:
            return

        welcome_channel = member.guild.get_channel(settings[2])  # welcome_channel_id
        if not welcome_channel:
            return

        # Create welcome embed
        welcome_embed = discord.Embed(
            title=settings[4] or "Welcome!",
            description=replace_variables(settings[5] or "Welcome to our server!", user=member, guild=member.guild),
            color=settings[6] or COLORS['success'],
            timestamp=discord.utils.utcnow()
        )

        welcome_embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        welcome_embed.add_field(name="👤 Member", value=member.mention, inline=True)
        welcome_embed.add_field(name="📊 Member Count", value=member.guild.member_count, inline=True)
        welcome_embed.add_field(name="📅 Account Created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)

        # Send welcome message
        welcome_message = replace_variables(settings[3] or "Welcome {user.mention}!", user=member, guild=member.guild)
        await welcome_channel.send(welcome_message, embed=welcome_embed)

        # Auto-role assignment
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT role_id FROM auto_roles WHERE guild_id = ?', (member.guild.id,))
        auto_roles = cursor.fetchall()
        conn.close()

        for role_row in auto_roles:
            role = member.guild.get_role(role_row[0])
            if role:
                try:
                    await member.add_roles(role, reason="Auto-role assignment")
                except:
                    pass

    except Exception as e:
        print(f"Error in welcome system: {e}")
        await report_error_to_owner(e, f"Welcome system - Guild: {member.guild.name}")

# AUTO-ROLE SYSTEM
@bot.tree.command(name="autorole", description="🎭 Configure automatic role assignment")
@discord.app_commands.describe(
    action="Action to perform",
    role="Role to add/remove from auto-assignment"
)
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name="➕ Add Role", value="add"),
    discord.app_commands.Choice(name="➖ Remove Role", value="remove"),
    discord.app_commands.Choice(name="📋 List Roles", value="list"),
    discord.app_commands.Choice(name="🧪 Test", value="test")
])
async def autorole(interaction: discord.Interaction, action: discord.app_commands.Choice[str], role: discord.Role = None):
    if not interaction.user.guild_permissions.manage_roles:
        embed = create_error_embed("Permission Denied", "You need `Manage Roles` permission to configure auto-roles.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    guild_id = interaction.guild.id

    if action.value == "add":
        if not role:
            embed = create_error_embed("Missing Role", "Please specify a role to add to auto-assignment.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            conn.close()
            return

        if role.position >= interaction.guild.me.top_role.position:
            embed = create_error_embed("Role Too High", "I cannot assign roles higher than my highest role.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            conn.close()
            return

        cursor.execute('INSERT OR IGNORE INTO auto_roles (guild_id, role_id) VALUES (?, ?)', (guild_id, role.id))
        conn.commit()

        if cursor.rowcount > 0:
            embed = create_success_embed("Auto-Role Added", f"{role.mention} will now be automatically assigned to new members", interaction.user)
        else:
            embed = create_info_embed("Already Added", f"{role.mention} is already in the auto-role list", interaction.user)

        conn.close()
        await interaction.response.send_message(embed=embed)

    elif action.value == "remove":
        if not role:
            embed = create_error_embed("Missing Role", "Please specify a role to remove from auto-assignment.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            conn.close()
            return

        cursor.execute('DELETE FROM auto_roles WHERE guild_id = ? AND role_id = ?', (guild_id, role.id))
        conn.commit()

        if cursor.rowcount > 0:
            embed = create_success_embed("Auto-Role Removed", f"{role.mention} will no longer be automatically assigned", interaction.user)
        else:
            embed = create_info_embed("Not Found", f"{role.mention} was not in the auto-role list", interaction.user)

        conn.close()
        await interaction.response.send_message(embed=embed)

    elif action.value == "list":
        cursor.execute('SELECT role_id FROM auto_roles WHERE guild_id = ?', (guild_id,))
        auto_roles = cursor.fetchall()
        conn.close()

        if not auto_roles:
            embed = create_info_embed("No Auto-Roles", "No roles are configured for automatic assignment", interaction.user)
            await interaction.response.send_message(embed=embed)
            return

        role_list = []
        for role_row in auto_roles:
            role_obj = interaction.guild.get_role(role_row[0])
            if role_obj:
                role_list.append(role_obj.mention)

        embed = create_embed(
            title="🎭 Auto-Role List",
            description=f"**{len(role_list)}** roles configured for automatic assignment:",
            color=COLORS['blue']
        )

        embed.add_field(name="📋 Roles", value="\n".join(role_list) if role_list else "No valid roles found", inline=False)
        await interaction.response.send_message(embed=embed)

# POLL SYSTEM
@bot.tree.command(name="poll", description="📊 Create an interactive poll")
@discord.app_commands.describe(
    question="The poll question",
    option1="First poll option",
    option2="Second poll option",
    option3="Third poll option (optional)",
    option4="Fourth poll option (optional)",
    option5="Fifth poll option (optional)"
)
async def poll(interaction: discord.Interaction, question: str, option1: str, option2: str,
               option3: str = None, option4: str = None, option5: str = None):

    options = [option1, option2]
    if option3: options.append(option3)
    if option4: options.append(option4)
    if option5: options.append(option5)

    if len(options) > 5:
        embed = create_error_embed("Too Many Options", "Polls can have a maximum of 5 options.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Create poll embed
    poll_embed = discord.Embed(
        title="📊 Poll",
        description=f"**{question}**\n\nReact with the corresponding emoji to vote!",
        color=COLORS['blue'],
        timestamp=discord.utils.utcnow()
    )

    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

    for i, option in enumerate(options):
        poll_embed.add_field(name=f"{emojis[i]} Option {i+1}", value=option, inline=False)

    poll_embed.set_footer(text=f"Poll by {interaction.user.display_name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)

    await interaction.response.send_message(embed=poll_embed)
    message = await interaction.original_response()

    # Add reactions
    for i in range(len(options)):
        await message.add_reaction(emojis[i])

    await log_command_action(interaction, "poll", f"Created poll: {question}")

# AFK SYSTEM
@bot.tree.command(name="afk", description="😴 Set your AFK status")
async def afk(interaction: discord.Interaction, reason: str = "I'm currently AFK"):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR REPLACE INTO afk_users (user_id, guild_id, reason, timestamp)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ''', (interaction.user.id, interaction.guild.id, reason))

    conn.commit()
    conn.close()

    embed = create_success_embed("AFK Status Set", f"You are now AFK: **{reason}**\n\nI'll mention this when someone pings you!", interaction.user)
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await log_command_action(interaction, "afk", f"Set AFK: {reason}")

@bot.event
async def on_message_afk_check(message):
    """Check for AFK users in messages"""
    if message.author.bot:
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if message author is AFK and remove them
    cursor.execute('SELECT reason FROM afk_users WHERE user_id = ? AND guild_id = ?',
                  (message.author.id, message.guild.id))
    afk_user = cursor.fetchone()

    if afk_user:
        cursor.execute('DELETE FROM afk_users WHERE user_id = ? AND guild_id = ?',
                      (message.author.id, message.guild.id))
        conn.commit()

        embed = create_info_embed("Welcome Back!", f"Removed your AFK status: **{afk_user[0]}**", message.author)
        await message.channel.send(embed=embed, delete_after=10)

    # Check for mentioned AFK users
    for mentioned_user in message.mentions:
        cursor.execute('SELECT reason, timestamp FROM afk_users WHERE user_id = ? AND guild_id = ?',
                      (mentioned_user.id, message.guild.id))
        afk_mentioned = cursor.fetchone()

        if afk_mentioned:
            timestamp = afk_mentioned[1] if afk_mentioned[1] else "Unknown time"
            embed = create_info_embed("User is AFK", f"💤 **{mentioned_user.display_name}** is currently AFK\n**Reason:** {afk_mentioned[0]}\n**Since:** {timestamp}")
            await message.channel.send(embed=embed, delete_after=15)

    conn.close()

# REMINDER SYSTEM
@bot.tree.command(name="remind", description="⏰ Set a reminder")
@discord.app_commands.describe(
    time="Time for reminder (e.g., 10m, 1h, 2d)",
    reminder="What to remind you about"
)
async def remind(interaction: discord.Interaction, time: str, reminder: str):
    # Parse time
    time_units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    time_match = None

    for unit in time_units:
        if time.endswith(unit):
            try:
                amount = int(time[:-1])
                time_match = amount * time_units[unit]
                break
            except ValueError:
                continue

    if not time_match:
        embed = create_error_embed("Invalid Time", "Please use format like: 10m, 1h, 2d")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if time_match > 2592000:  # 30 days
        embed = create_error_embed("Time Too Long", "Reminders cannot be longer than 30 days.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    remind_time = time.time() + time_match

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO reminders (user_id, channel_id, message, remind_time, created_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (interaction.user.id, interaction.channel.id, reminder, remind_time))

    conn.commit()
    conn.close()

    embed = create_success_embed("Reminder Set", f"I'll remind you about: **{reminder}**\n⏰ **When:** <t:{int(remind_time)}:F>", interaction.user)
    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "remind", f"Set reminder for {time}: {reminder}")

# CUSTOM PREFIX SYSTEM
@bot.tree.command(name="prefix", description="🔧 Set custom server prefix")
async def prefix(interaction: discord.Interaction, new_prefix: str = None):
    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to change the prefix.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    if new_prefix:
        if len(new_prefix) > 5:
            embed = create_error_embed("Prefix Too Long", "Prefix cannot be longer than 5 characters.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            conn.close()
            return

        cursor.execute('''
            INSERT OR REPLACE INTO guild_settings (guild_id, custom_prefix)
            VALUES (?, ?)
        ''', (interaction.guild.id, new_prefix))

        conn.commit()
        embed = create_success_embed("Prefix Updated", f"Server prefix changed to: **{new_prefix}**", interaction.user)
    else:
        cursor.execute('SELECT custom_prefix FROM guild_settings WHERE guild_id = ?', (interaction.guild.id,))
        result = cursor.fetchone()
        current_prefix = result[0] if result else "!"

        embed = create_info_embed("Current Prefix", f"Server prefix: **{current_prefix}**", interaction.user)

    conn.close()
    await interaction.response.send_message(embed=embed)

# GOODBYE SYSTEM
@bot.tree.command(name="goodbye", description="👋 Configure goodbye messages")
@discord.app_commands.describe(
    action="Action to perform",
    channel="Channel for goodbye messages",
    message="Goodbye message (supports variables)",
    embed_title="Title for goodbye embed",
    embed_description="Description for goodbye embed"
)
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name="🟢 Enable", value="enable"),
    discord.app_commands.Choice(name="🔴 Disable", value="disable"),
    discord.app_commands.Choice(name="⚙️ Configure", value="configure"),
    discord.app_commands.Choice(name="📊 Status", value="status"),
    discord.app_commands.Choice(name="🧪 Test", value="test")
])
async def goodbye(interaction: discord.Interaction, action: discord.app_commands.Choice[str],
                 channel: discord.TextChannel = None, message: str = None,
                 embed_title: str = None, embed_description: str = None):

    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to configure goodbye messages.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    guild_id = interaction.guild.id

    if action.value == "enable":
        if not channel:
            embed = create_error_embed("Missing Channel", "Please specify a channel for goodbye messages.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            conn.close()
            return

        cursor.execute('''
            INSERT OR REPLACE INTO guild_settings
            (guild_id, goodbye_enabled, goodbye_channel_id, goodbye_message, goodbye_embed_title, goodbye_embed_description)
            VALUES (?, 1, ?, ?, ?, ?)
        ''', (guild_id, channel.id,
              message or "Goodbye {user.name}, thanks for being part of {guild.name}! 👋",
              embed_title or "Goodbye!",
              embed_description or "Thanks for being part of our community!"))

        conn.commit()
        conn.close()

        embed = create_success_embed("Goodbye System Enabled", f"Goodbye messages will be sent to {channel.mention}", interaction.user)
        await interaction.response.send_message(embed=embed)

    elif action.value == "disable":
        cursor.execute('UPDATE guild_settings SET goodbye_enabled = 0 WHERE guild_id = ?', (guild_id,))
        conn.commit()
        conn.close()

        embed = create_success_embed("Goodbye System Disabled", "Goodbye messages have been disabled", interaction.user)
        await interaction.response.send_message(embed=embed)

    elif action.value == "status":
        cursor.execute('SELECT * FROM guild_settings WHERE guild_id = ?', (guild_id,))
        settings = cursor.fetchone()
        conn.close()

        if settings and settings[8]:  # goodbye_enabled
            goodbye_channel = interaction.guild.get_channel(settings[9])
            embed = create_embed(
                title="👋 Goodbye System Status",
                description="Goodbye system is **ENABLED**",
                color=COLORS['success']
            )
            embed.add_field(name="📍 Channel", value=goodbye_channel.mention if goodbye_channel else "Channel not found", inline=True)
            embed.add_field(name="💬 Message", value=settings[10] or "Default message", inline=False)
        else:
            embed = create_embed(
                title="👋 Goodbye System Status",
                description="Goodbye system is **DISABLED**",
                color=COLORS['error']
            )

        await interaction.response.send_message(embed=embed)

    elif action.value == "test":
        if not interaction.user.guild_permissions.manage_guild:
            embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to test goodbye messages.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        test_user = interaction.user # Default to interaction user for testing

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM guild_settings WHERE guild_id = ? AND goodbye_enabled = 1', (interaction.guild.id,))
        settings = cursor.fetchone()
        conn.close()

        if not settings:
            embed = create_error_embed("Goodbye System Disabled", "Goodbye system is not enabled. Use `/goodbye enable` to enable it.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        goodbye_channel = interaction.guild.get_channel(settings[9])
        if not goodbye_channel:
            embed = create_error_embed("Channel Not Found", "Goodbye channel no longer exists.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Create test goodbye embed
        goodbye_embed = discord.Embed(
            title=settings[11] or "Goodbye!",
            description=replace_variables(settings[12] or "Thanks for being part of our server!", user=test_user, guild=interaction.guild),
            color=settings[13] or COLORS['warning'],
            timestamp=discord.utils.utcnow()
        )

        goodbye_embed.set_thumbnail(url=test_user.avatar.url if test_user.avatar else test_user.default_avatar.url)
        goodbye_embed.add_field(name="👤 Member", value=f"{test_user.name}#{test_user.discriminator}", inline=True)
        goodbye_embed.add_field(name="📊 Members Left", value=interaction.guild.member_count, inline=True)
        goodbye_embed.add_field(name="🧪 Test Mode", value="This is a test message", inline=True)

        goodbye_message = replace_variables(settings[10] or "Goodbye {user.name}!", user=test_user, guild=interaction.guild)

        await goodbye_channel.send(f"🧪 **TEST MESSAGE** - {goodbye_message}", embed=goodbye_embed)

        embed = create_success_embed("Goodbye Test Sent!", f"Test goodbye message sent to {goodbye_channel.mention} for {test_user.mention}", interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await log_command_action(interaction, "goodbye", f"Tested goodbye for {test_user}")

    else: # configure or other actions
        embed = create_error_embed("Invalid Action", "Please choose a valid action: enable, disable, configure, status, test.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_member_remove(member):
    """Handle member leave for goodbye messages"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM guild_settings WHERE guild_id = ? AND goodbye_enabled = 1', (member.guild.id,))
        settings = cursor.fetchone()
        conn.close()

        if not settings:
            return

        goodbye_channel = member.guild.get_channel(settings[9])  # goodbye_channel_id
        if not goodbye_channel:
            return

        # Create goodbye embed
        goodbye_embed = discord.Embed(
            title=settings[11] or "Goodbye!",
            description=replace_variables(settings[12] or "Thanks for being part of our community!", user=member, guild=member.guild),
            color=settings[13] or COLORS['warning'],
            timestamp=discord.utils.utcnow()
        )

        goodbye_embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        goodbye_embed.add_field(name="👤 Member", value=f"{member.name}#{member.discriminator}", inline=True)
        goodbye_embed.add_field(name="📊 Members Left", value=member.guild.member_count, inline=True)
        goodbye_embed.add_field(name="📅 Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "Unknown", inline=True)

        # Send goodbye message
        goodbye_message = replace_variables(settings[10] or "Goodbye {user.name}!", user=member, guild=member.guild)
        await goodbye_channel.send(goodbye_message, embed=goodbye_embed)

    except Exception as e:
        print(f"Error in goodbye system: {e}")
        await report_error_to_owner(e, f"Goodbye system - Guild: {member.guild.name}")

# EMBED BUILDER COMMAND
@bot.tree.command(name="embedbuilder", description="🎨 Advanced embed builder with multiple fields")
@discord.app_commands.describe(
    title="Embed title",
    description="Embed description",
    color="Embed color (hex or color name)",
    footer="Embed footer text",
    thumbnail="Thumbnail URL",
    image="Image URL",
    author="Author name",
    field1="Field 1 (format: name|value|inline)",
    field2="Field 2 (format: name|value|inline)",
    field3="Field 3 (format: name|value|inline)"
)
async def embedbuilder(interaction: discord.Interaction, title: str = None, description: str = None,
                      color: str = "blue", footer: str = None, thumbnail: str = None,
                      image: str = None, author: str = None, field1: str = None,
                      field2: str = None, field3: str = None):

    if not interaction.user.guild_permissions.manage_messages:
        embed = create_error_embed("Permission Denied", "You need `Manage Messages` permission to use embed builder.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Parse color
    embed_color = COLORS.get(color.lower(), COLORS['blue'])
    if color.startswith("#"):
        try:
            embed_color = int(color[1:], 16)
        except:
            embed_color = COLORS['blue']

    # Create embed
    custom_embed = discord.Embed(
        title=replace_variables(title, user=interaction.user, guild=interaction.guild) if title else None,
        description=replace_variables(description, user=interaction.user, guild=interaction.guild) if description else None,
        color=embed_color,
        timestamp=discord.utils.utcnow()
    )

    # Add fields
    for field in [field1, field2, field3]:
        if field:
            try:
                parts = field.split("|")
                if len(parts) >= 2:
                    name = parts[0]
                    value = parts[1]
                    inline = parts[2].lower() in ["true", "yes", "1"] if len(parts) > 2 else False
                    custom_embed.add_field(
                        name=replace_variables(name, user=interaction.user, guild=interaction.guild),
                        value=replace_variables(value, user=interaction.user, guild=interaction.guild),
                        inline=inline
                    )
            except:
                pass

    # Set additional properties
    if footer:
        custom_embed.set_footer(text=replace_variables(footer, user=interaction.user, guild=interaction.guild))
    if thumbnail:
        custom_embed.set_thumbnail(url=thumbnail)
    if image:
        custom_embed.set_image(url=image)
    if author:
        custom_embed.set_author(name=replace_variables(author, user=interaction.user, guild=interaction.guild))

    await interaction.response.send_message(embed=custom_embed)
    await log_command_action(interaction, "embedbuilder", f"Created advanced embed: {title or 'No title'}")

# REACTION ROLE SYSTEM
@bot.tree.command(name="reactionrole", description="⚡ Setup reaction role system")
@discord.app_commands.describe(
    action="Action to perform",
    message_id="Message ID for reaction roles",
    emoji="Emoji for the reaction",
    role="Role to assign/remove"
)
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name="➕ Add Reaction Role", value="add"),
    discord.app_commands.Choice(name="➖ Remove Reaction Role", value="remove"),
    discord.app_commands.Choice(name="📋 List Reaction Roles", value="list"),
    discord.app_commands.Choice(name="🗑️ Clear All", value="clear")
])
async def reactionrole(interaction: discord.Interaction, action: discord.app_commands.Choice[str],
                      message_id: str = None, emoji: str = None, role: discord.Role = None):

    if not interaction.user.guild_permissions.manage_roles:
        embed = create_error_embed("Permission Denied", "You need `Manage Roles` permission to setup reaction roles.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    guild_id = interaction.guild.id

    if action.value == "add":
        if not all([message_id, emoji, role]):
            embed = create_error_embed("Missing Information", "Please provide message ID, emoji, and role.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            conn.close()
            return

        try:
            msg_id = int(message_id)
            # Try to fetch the message to verify it exists
            message = await interaction.channel.fetch_message(msg_id)

            cursor.execute('''
                INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id)
                VALUES (?, ?, ?, ?)
            ''', (guild_id, msg_id, str(emoji), role.id))

            conn.commit()
            conn.close()

            # Add reaction to message
            await message.add_reaction(emoji)

            embed = create_success_embed("Reaction Role Added", f"React with {emoji} on message {msg_id} to get {role.mention}", interaction.user)
            await interaction.response.send_message(embed=embed)

        except ValueError:
            embed = create_error_embed("Invalid Message ID", "Please provide a valid message ID.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            conn.close()
        except discord.NotFound:
            embed = create_error_embed("Message Not Found", "Could not find message with that ID in this channel.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            conn.close()
        except Exception as e:
            embed = create_error_embed("Setup Failed", f"Could not setup reaction role: {str(e)}")
            await interaction.response.send_message(embed=embed)
            conn.close()

    elif action.value == "list":
        cursor.execute('SELECT message_id, emoji, role_id FROM reaction_roles WHERE guild_id = ?', (guild_id,))
        reaction_roles = cursor.fetchall()
        conn.close()

        if not reaction_roles:
            embed = create_info_embed("No Reaction Roles", "No reaction roles are configured for this server.", interaction.user)
            await interaction.response.send_message(embed=embed)
            return

        embed = create_embed(
            title="⚡ Reaction Roles",
            description=f"**{len(reaction_roles)}** reaction roles configured:",
            color=COLORS['blue']
        )

        for msg_id, emoji, role_id in reaction_roles[:10]:  # Limit to 10
            role_obj = interaction.guild.get_role(role_id)
            embed.add_field(
                name=f"{emoji} Reaction Role",
                value=f"**Message:** {msg_id}\n**Role:** {role_obj.mention if role_obj else 'Deleted Role'}",
                inline=True
            )

        await interaction.response.send_message(embed=embed)

@bot.event
async def on_reaction_add(reaction, user):
    """Handle reaction role assignment"""
    if user.bot:
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT role_id FROM reaction_roles
            WHERE guild_id = ? AND message_id = ? AND emoji = ?
        ''', (reaction.message.guild.id, reaction.message.id, str(reaction.emoji)))

        result = cursor.fetchone()
        conn.close()

        if result:
            role = reaction.message.guild.get_role(result[0])
            if role:
                member = reaction.message.guild.get_member(user.id)
                if member and role not in member.roles:
                    await member.add_roles(role, reason="Reaction role assignment")
    except Exception as e:
        print(f"Error in reaction role add: {e}")

@bot.event
async def on_reaction_remove(reaction, user):
    """Handle reaction role removal"""
    if user.bot:
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT role_id FROM reaction_roles
            WHERE guild_id = ? AND message_id = ? AND emoji = ?
        ''', (reaction.message.guild.id, reaction.message.id, str(reaction.emoji)))

        result = cursor.fetchone()
        conn.close()

        if result:
            role = reaction.message.guild.get_role(result[0])
            if role:
                member = reaction.message.guild.get_member(user.id)
                if member and role in member.roles:
                    await member.remove_roles(role, reason="Reaction role removal")
    except Exception as e:
        print(f"Error in reaction role remove: {e}")

# ADDITIONAL MODERATION COMMANDS
@bot.tree.command(name="mute", description="🔇 Mute a user")
async def mute(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.moderate_members:
        embed = create_error_embed("Permission Denied", "You need `Moderate Members` permission to mute users.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Find or create muted role
    muted_role = None
    for role in interaction.guild.roles:
        if role.name.lower() == "muted":
            muted_role = role
            break

    if not muted_role:
        try:
            muted_role = await interaction.guild.create_role(
                name="Muted",
                color=discord.Color.dark_grey(),
                reason="Auto-created muted role"
            )

            # Set permissions for all channels
            for channel in interaction.guild.channels:
                await channel.set_permissions(muted_role, send_messages=False, speak=False, add_reactions=False)
        except Exception as e:
            embed = create_error_embed("Mute Failed", f"Could not create/setup muted role: {str(e)}")
            await interaction.response.send_message(embed=embed)
            return

    try:
        await user.add_roles(muted_role, reason=f"Muted by {interaction.user}: {reason}")
        embed = create_success_embed("User Muted", f"Successfully muted {user.mention}\n**Reason:** {reason}", interaction.user)
        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "mute", f"Muted {user} for: {reason}")
    except Exception as e:
        embed = create_error_embed("Mute Failed", f"Could not mute {user.mention}: {str(e)}")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="unmute", description="🔊 Unmute a user")
async def unmute(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.moderate_members:
        embed = create_error_embed("Permission Denied", "You need `Moderate Members` permission to unmute users.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    muted_role = None
    for role in interaction.guild.roles:
        if role.name.lower() == "muted":
            muted_role = role
            break

    if not muted_role:
        embed = create_error_embed("No Muted Role", "No muted role found in this server.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if muted_role not in user.roles:
        embed = create_info_embed("User Not Muted", f"{user.mention} is not muted.", interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        await user.remove_roles(muted_role, reason=f"Unmuted by {interaction.user}: {reason}")
        embed = create_success_embed("User Unmuted", f"Successfully unmuted {user.mention}\n**Reason:** {reason}", interaction.user)
        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "unmute", f"Unmuted {user} for: {reason}")
    except Exception as e:
        embed = create_error_embed("Unmute Failed", f"Could not unmute {user.mention}: {str(e)}")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="warn", description="⚠️ Warn a user")
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str):
    if not interaction.user.guild_permissions.moderate_members:
        embed = create_error_embed("Permission Denied", "You need `Moderate Members` permission to warn users.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        # Send warning DM
        warning_embed = discord.Embed(
            title="⚠️ Warning",
            description=f"You have been warned in **{interaction.guild.name}**",
            color=COLORS['warning']
        )
        warning_embed.add_field(name="Reason", value=reason, inline=False)
        warning_embed.add_field(name="Warned by", value=interaction.user.mention, inline=True)
        warning_embed.set_footer(text=f"Warning from {interaction.guild.name}")

        try:
            await user.send(embed=warning_embed)
            dm_status = "✅ DM sent"
        except:
            dm_status = "❌ DM failed"

        embed = create_success_embed("User Warned", f"Successfully warned {user.mention}\n**Reason:** {reason}\n**DM Status:** {dm_status}", interaction.user)
        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "warn", f"Warned {user} for: {reason}")

    except Exception as e:
        embed = create_error_embed("Warning Failed", f"Could not warn {user.mention}: {str(e)}")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="lockdown", description="🔒 Emergency server lockdown")
async def lockdown(interaction: discord.Interaction, reason: str = "Emergency lockdown"):
    if not interaction.user.guild_permissions.administrator:
        embed = create_error_embed("Permission Denied", "You need `Administrator` permission for emergency lockdown.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    confirmed = await confirm_dangerous_action(
        interaction,
        "Server Lockdown",
        "This will lock ALL channels in the server, preventing @everyone from sending messages. Only staff will be able to communicate."
    )

    if not confirmed:
        return

    try:
        locked_count = 0
        for channel in interaction.guild.text_channels:
            try:
                overwrite = channel.overwrites_for(interaction.guild.default_role)
                overwrite.send_messages = False
                await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
                locked_count += 1
                await asyncio.sleep(0.5)  # Rate limiting
            except:
                pass

        embed = create_warning_embed("🔒 Server Lockdown Active", f"Server is now in lockdown mode!\n**Reason:** {reason}\n**Channels Locked:** {locked_count}")
        await interaction.edit_original_response(embed=embed)
        await log_command_action(interaction, "lockdown", f"Server lockdown: {reason} - {locked_count} channels locked")

    except Exception as e:
        embed = create_error_embed("Lockdown Failed", f"Could not complete lockdown: {str(e)}")
        await interaction.edit_original_response(embed=embed)

@bot.tree.command(name="unlock", description="🔓 Remove server lockdown")
async def unlock(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        embed = create_error_embed("Permission Denied", "You need `Administrator` permission to remove lockdown.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.defer()

    try:
        unlocked_count = 0
        for channel in interaction.guild.text_channels:
            try:
                overwrite = channel.overwrites_for(interaction.guild.default_role)
                if overwrite.send_messages is False:
                    overwrite.send_messages = None
                    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
                    unlocked_count += 1
                await asyncio.sleep(0.5)  # Rate limiting
            except:
                pass

        embed = create_success_embed("🔓 Server Unlocked", f"Server lockdown has been removed!\n**Channels Unlocked:** {unlocked_count}", interaction.user)
        await interaction.followup.send(embed=embed)
        await log_command_action(interaction, "unlock", f"Server unlocked - {unlocked_count} channels restored")

    except Exception as e:
        embed = create_error_embed("Unlock Failed", f"Could not remove lockdown: {str(e)}")
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="slowmode", description="🐌 Set channel slowmode")
async def slowmode(interaction: discord.Interaction, seconds: int, channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.manage_channels:
        embed = create_error_embed("Permission Denied", "You need `Manage Channels` permission to set slowmode.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    target_channel = channel or interaction.channel

    if seconds > 21600:  # 6 hours
        embed = create_error_embed("Too Long", "Slowmode cannot exceed 6 hours (21600 seconds).")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        await target_channel.edit(slowmode_delay=seconds)

        if seconds == 0:
            embed = create_success_embed("Slowmode Disabled", f"Slowmode disabled in {target_channel.mention}", interaction.user)
        else:
            embed = create_success_embed("Slowmode Set", f"Slowmode set to **{seconds} seconds** in {target_channel.mention}", interaction.user)

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "slowmode", f"Set slowmode to {seconds}s in {target_channel.name}")

    except Exception as e:
        embed = create_error_embed("Slowmode Failed", f"Could not set slowmode: {str(e)}")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="nuke", description="💥 Delete and recreate channel")
async def nuke(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.manage_channels:
        embed = create_error_embed("Permission Denied", "You need `Manage Channels` permission to nuke channels.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    target_channel = channel or interaction.channel

    confirmed = await confirm_dangerous_action(
        interaction,
        "Channel Nuke",
        f"This will DELETE #{target_channel.name} and recreate it with the same settings. ALL MESSAGES WILL BE LOST!"
    )

    if not confirmed:
        return

    try:
        # Store channel info
        channel_name = target_channel.name
        channel_topic = target_channel.topic
        channel_category = target_channel.category
        channel_position = target_channel.position
        channel_overwrites = target_channel.overwrites
        channel_slowmode = target_channel.slowmode_delay

        # Delete and recreate
        await target_channel.delete(reason=f"Channel nuked by {interaction.user}")

        new_channel = await interaction.guild.create_text_channel(
            name=channel_name,
            topic=channel_topic,
            category=channel_category,
            position=channel_position,
            overwrites=channel_overwrites,
            slowmode_delay=channel_slowmode,
            reason=f"Channel nuked by {interaction.user}"
        )

        # Send nuke confirmation
        nuke_embed = discord.Embed(
            title="💥 Channel Nuked!",
            description=f"#{channel_name} has been successfully nuked and recreated!",
            color=COLORS['success']
        )
        nuke_embed.add_field(name="🗑️ Action", value="Channel deleted and recreated", inline=True)
        nuke_embed.add_field(name="👤 Nuked by", value=interaction.user.mention, inline=True)
        nuke_embed.set_footer(text="All previous messages have been deleted")

        await new_channel.send(embed=nuke_embed)
        await log_command_action(interaction, "nuke", f"Nuked channel {channel_name}")

    except Exception as e:
        embed = create_error_embed("Nuke Failed", f"Could not nuke channel: {str(e)}")
        try:
            await interaction.edit_original_response(embed=embed)
        except:
            pass

# BOTINFO COMMAND
@bot.tree.command(name="botinfo", description="Show bot information and statistics")
async def botinfo(interaction: discord.Interaction):
    uptime_seconds = int(time.time() - bot_stats['start_time'])
    uptime_str = f"<t:{int(bot_stats['start_time'])}:R>"

    embed = create_embed(
        title="Bot Information",
        description="Core bot statistics and information",
        color=COLORS['blue']
    )

    embed.add_field(name="Bot Version", value="v2.1.0", inline=True)
    embed.add_field(name="Developer", value="<@1209807688435892285>", inline=True)
    embed.add_field(name="Uptime", value=uptime_str, inline=True)

    embed.add_field(name="Servers", value=f"{len(bot.guilds):,}", inline=True)
    embed.add_field(name="Users", value=f"{sum(guild.member_count for guild in bot.guilds):,}", inline=True)
    embed.add_field(name="Commands Used", value=f"{bot_stats['commands_used']:,}", inline=True)

    embed.add_field(name="Python Version", value=platform.python_version(), inline=True)
    embed.add_field(name="Discord.py Version", value=discord.__version__, inline=True)
    embed.add_field(name="Latency", value=f"{round(bot.latency * 1000)}ms", inline=True)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "botinfo", "Viewed bot information")

@bot.tree.command(name="servercreated", description="Show when the server was created")
async def servercreated(interaction: discord.Interaction):
    guild = interaction.guild
    created_timestamp = int(guild.created_at.timestamp())
    days_ago = (discord.utils.utcnow() - guild.created_at).days

    embed = create_embed(
        title="Server Creation Date",
        description=f"**{guild.name}** was created:",
        color=COLORS['blue']
    )

    embed.add_field(name="Created", value=f"<t:{created_timestamp}:F>", inline=True)
    embed.add_field(name="Days Ago", value=f"{days_ago:,} days", inline=True)
    embed.add_field(name="Relative", value=f"<t:{created_timestamp}:R>", inline=True)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "servercreated", f"Checked server creation date")

@bot.tree.command(name="joinedat", description="Show when a user joined the server")
async def joinedat(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user

    if not target_user.joined_at:
        embed = create_error_embed("No Join Date", "Could not retrieve join date for this user")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    joined_timestamp = int(target_user.joined_at.timestamp())
    days_ago = (discord.utils.utcnow() - target_user.joined_at).days

    embed = create_embed(
        title="Server Join Date",
        description=f"**{target_user.display_name}** joined the server:",
        color=COLORS['blue']
    )

    embed.add_field(name="Joined", value=f"<t:{joined_timestamp}:F>", inline=True)
    embed.add_field(name="Days Ago", value=f"{days_ago:,} days", inline=True)
    embed.add_field(name="Relative", value=f"<t:{joined_timestamp}:R>", inline=True)

    embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "joinedat", f"Checked join date for {target_user}")

@bot.tree.command(name="channelinfo", description="Show detailed information about a channel")
async def channelinfo(interaction: discord.Interaction, channel: discord.TextChannel = None):
    target_channel = channel or interaction.channel

    embed = create_embed(
        title="Channel Information",
        description=f"Details about {target_channel.mention}",
        color=COLORS['blue']
    )

    embed.add_field(name="Channel ID", value=target_channel.id, inline=True)
    embed.add_field(name="Type", value=target_channel.type.name.title(), inline=True)
    embed.add_field(name="Category", value=target_channel.category.name if target_channel.category else "None", inline=True)

    embed.add_field(name="Created", value=f"<t:{int(target_channel.created_at.timestamp())}:F>", inline=True)
    embed.add_field(name="Position", value=target_channel.position, inline=True)
    embed.add_field(name="NSFW", value="Yes" if target_channel.nsfw else "No", inline=True)

    if target_channel.topic:
        embed.add_field(name="Topic", value=target_channel.topic[:100] + ("..." if len(target_channel.topic) > 100 else ""), inline=False)

    embed.add_field(name="Slowmode", value=f"{target_channel.slowmode_delay} seconds" if target_channel.slowmode_delay else "Disabled", inline=True)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "channelinfo", f"Viewed info for {target_channel.name}")

@bot.tree.command(name="boosters", description="List all server boosters")
async def boosters(interaction: discord.Interaction):
    guild = interaction.guild
    boosters = [member for member in guild.members if member.premium_since]

    if not boosters:
        embed = create_info_embed("No Boosters", "This server has no Nitro boosters", interaction.user)
        await interaction.response.send_message(embed=embed)
        return

    embed = create_embed(
        title="Server Boosters",
        description=f"**{len(boosters)}** members are boosting **{guild.name}**",
        color=0xf47fff
    )

    booster_list = []
    for member in boosters[:20]:  # Limit to 20
        boost_since = f"<t:{int(member.premium_since.timestamp())}:R>"
        booster_list.append(f"{member.mention} - {boost_since}")

    if booster_list:
        embed.add_field(name="Boosters", value="\n".join(booster_list), inline=False)

    if len(boosters) > 20:
        embed.add_field(name="More", value=f"... and {len(boosters) - 20} more boosters", inline=False)

    embed.add_field(name="Boost Level", value=f"Level {guild.premium_tier}", inline=True)
    embed.add_field(name="Total Boosts", value=f"{guild.premium_subscription_count}", inline=True)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "boosters", f"Listed {len(boosters)} boosters")

@bot.tree.command(name="rolelist", description="List all users with a specific role")
async def rolelist(interaction: discord.Interaction, role: discord.Role):
    members_with_role = role.members

    if not members_with_role:
        embed = create_info_embed("No Members", f"No members have the {role.mention} role", interaction.user)
        await interaction.response.send_message(embed=embed)
        return

    embed = create_embed(
        title="Role Members",
        description=f"**{len(members_with_role)}** members have {role.mention}",
        color=role.color if role.color != discord.Color.default() else COLORS['blue']
    )

    member_list = []
    for member in members_with_role[:20]:  # Limit to 20
        join_date = f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "Unknown"
        member_list.append(f"{member.mention} - {join_date}")

    if member_list:
        embed.add_field(name="Members", value="\n".join(member_list), inline=False)

    if len(members_with_role) > 20:
        embed.add_field(name="More", value=f"... and {len(members_with_role) - 20} more members", inline=False)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "rolelist", f"Listed {len(members_with_role)} members with {role.name}")

@bot.tree.command(name="online", description="List all online members")
async def online(interaction: discord.Interaction):
    online_members = [member for member in interaction.guild.members if member.status == discord.Status.online]

    if not online_members:
        embed = create_info_embed("No Online Members", "No members are currently online", interaction.user)
        await interaction.response.send_message(embed=embed)
        return

    embed = create_embed(
        title="Online Members",
        description=f"**{len(online_members)}** members are currently online",
        color=0x43b581
    )

    member_list = []
    for member in online_members[:20]:  # Limit to 20
        activity = ""
        if member.activity:
            activity = f" - {member.activity.name}"
        member_list.append(f"{member.mention}{activity}")

    if member_list:
        embed.add_field(name="Online Members", value="\n".join(member_list), inline=False)

    if len(online_members) > 20:
        embed.add_field(name="More", value=f"... and {len(online_members) - 20} more online", inline=False)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "online", f"Listed {len(online_members)} online members")

@bot.tree.command(name="serverstats", description="Show complete server statistics")
async def serverstats(interaction: discord.Interaction):
    guild = interaction.guild

    # Count different types of channels and members
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    categories = len(guild.categories)
    total_channels = text_channels + voice_channels

    total_members = guild.member_count
    humans = len([m for m in guild.members if not m.bot])
    bots = len([m for m in guild.members if m.bot])
    online = len([m for m in guild.members if m.status != discord.Status.offline])

    roles = len(guild.roles)
    emojis = len(guild.emojis)

    embed = create_embed(
        title="Complete Server Statistics",
        description=f"Full statistics for **{guild.name}**",
        color=COLORS['blue']
    )

    embed.add_field(name="Total Members", value=f"{total_members:,}", inline=True)
    embed.add_field(name="Humans", value=f"{humans:,}", inline=True)
    embed.add_field(name="Bots", value=f"{bots:,}", inline=True)

    embed.add_field(name="Online", value=f"{online:,}", inline=True)
    embed.add_field(name="Text Channels", value=f"{text_channels}", inline=True)
    embed.add_field(name="Voice Channels", value=f"{voice_channels}", inline=True)

    embed.add_field(name="Categories", value=f"{categories}", inline=True)
    embed.add_field(name="Total Roles", value=f"{roles}", inline=True)
    embed.add_field(name="Custom Emojis", value=f"{emojis}", inline=True)

    embed.add_field(name="Boost Level", value=f"Level {guild.premium_tier}", inline=True)
    embed.add_field(name="Boosts", value=f"{guild.premium_subscription_count}", inline=True)
    embed.add_field(name="Verification Level", value=guild.verification_level.name.title(), inline=True)

    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.set_footer(text=f"Server ID: {guild.id}")

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "serverstats", f"Viewed complete server statistics")

@bot.tree.command(name="userage", description="Calculate how old a user account is")
async def userage(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user

    created_timestamp = int(target_user.created_at.timestamp())
    age_days = (discord.utils.utcnow() - target_user.created_at).days
    age_years = age_days / 365.25

    embed = create_embed(
        title="Account Age",
        description=f"Account age for **{target_user.display_name}**",
        color=COLORS['blue']
    )

    embed.add_field(name="Created", value=f"<t:{created_timestamp}:F>", inline=True)
    embed.add_field(name="Days Old", value=f"{age_days:,} days", inline=True)
    embed.add_field(name="Years Old", value=f"{age_years:.1f} years", inline=True)

    embed.add_field(name="Relative", value=f"<t:{created_timestamp}:R>", inline=False)

    embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "userage", f"Checked account age for {target_user}")

@bot.tree.command(name="serverage", description="Calculate how old the server is")
async def serverage(interaction: discord.Interaction):
    guild = interaction.guild

    created_timestamp = int(guild.created_at.timestamp())
    age_days = (discord.utils.utcnow() - guild.created_at).days
    age_years = age_days / 365.25

    embed = create_embed(
        title="Server Age",
        description=f"Age information for **{guild.name}**",
        color=COLORS['blue']
    )

    embed.add_field(name="Created", value=f"<t:{created_timestamp}:F>", inline=True)
    embed.add_field(name="Days Old", value=f"{age_days:,} days", inline=True)
    embed.add_field(name="Years Old", value=f"{age_years:.1f} years", inline=True)

    embed.add_field(name="Relative", value=f"<t:{created_timestamp}:R>", inline=False)

    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "serverage", f"Checked server age")

@bot.tree.command(name="permissionscheck", description="Check if a user has a specific permission")
async def permissionscheck(interaction: discord.Interaction, user: discord.Member, permission: str):
    # Map common permission names
    permission_map = {
        'admin': 'administrator',
        'administrator': 'administrator',
        'manage_server': 'manage_guild',
        'manage_guild': 'manage_guild',
        'manage_channels': 'manage_channels',
        'manage_roles': 'manage_roles',
        'kick': 'kick_members',
        'kick_members': 'kick_members',
        'ban': 'ban_members',
        'ban_members': 'ban_members',
        'manage_messages': 'manage_messages',
        'send_messages': 'send_messages',
        'read_messages': 'read_messages',
        'view_channel': 'view_channel',
        'connect': 'connect',
        'speak': 'speak',
        'mute_members': 'mute_members',
        'deafen_members': 'deafen_members',
        'move_members': 'move_members'
    }

    perm_name = permission_map.get(permission.lower())
    if not perm_name:
        embed = create_error_embed("Invalid Permission", f"Unknown permission: {permission}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    has_permission = getattr(user.guild_permissions, perm_name, False)

    embed = create_embed(
        title="Permission Check",
        description=f"Permission check for **{user.display_name}**",
        color=COLORS['success'] if has_permission else COLORS['error']
    )

    embed.add_field(name="User", value=user.mention, inline=True)
    embed.add_field(name="Permission", value=perm_name.replace('_', ' ').title(), inline=True)
    embed.add_field(name="Has Permission", value="Yes" if has_permission else "No", inline=True)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "permissionscheck", f"Checked {perm_name} for {user}")

# ADDITIONAL INFO COMMANDS
@bot.tree.command(name="members", description="Show member statistics")
async def members(interaction: discord.Interaction):
    guild = interaction.guild

    total = guild.member_count
    humans = len([m for m in guild.members if not m.bot])
    bots = len([m for m in guild.members if m.bot])
    online = len([m for m in guild.members if m.status != discord.Status.offline])
    idle = len([m for m in guild.members if m.status == discord.Status.idle])
    dnd = len([m for m in guild.members if m.status == discord.Status.dnd])
    offline = len([m for m in guild.members if m.status == discord.Status.offline])

    embed = create_embed(
        title="👥 Member Statistics",
        description=f"Member breakdown for **{guild.name}**",
        color=COLORS['blue']
    )

    embed.add_field(name="📊 Total Members", value=f"{total:,}", inline=True)
    embed.add_field(name="👤 Humans", value=f"{humans:,}", inline=True)
    embed.add_field(name="🤖 Bots", value=f"{bots:,}", inline=True)

    embed.add_field(name="🟢 Online", value=f"{online:,}", inline=True)
    embed.add_field(name="🟡 Idle", value=f"{idle:,}", inline=True)
    embed.add_field(name="🔴 DND", value=f"{dnd:,}", inline=True)

    embed.add_field(name="⚫ Offline", value=f"{offline:,}", inline=True)
    embed.add_field(name="📈 Growth Rate", value="📊 Data not available", inline=True)
    embed.add_field(name="🎯 Activity", value=f"{((online + idle + dnd) / total * 100):.1f}% active", inline=True)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "members", f"Viewed member stats: {total} total")

@bot.tree.command(name="channels", description="📁 Show channel statistics")
async def channels(interaction: discord.Interaction):
    guild = interaction.guild

    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    stage_channels = len(guild.stage_channels)
    categories = len(guild.categories)
    threads = len(guild.threads)

    embed = create_embed(
        title="📁 Channel Statistics",
        description=f"Channel breakdown for **{guild.name}**",
        color=COLORS['blue']
    )

    embed.add_field(name="💬 Text Channels", value=f"{text_channels}", inline=True)
    embed.add_field(name="🔊 Voice Channels", value=f"{voice_channels}", inline=True)
    embed.add_field(name="🎭 Stage Channels", value=f"{stage_channels}", inline=True)

    embed.add_field(name="📂 Categories", value=f"{categories}", inline=True)
    embed.add_field(name="🧵 Threads", value=f"{threads}", inline=True)
    embed.add_field(name="📊 Total", value=f"{text_channels + voice_channels + stage_channels}", inline=True)

    # Show channel list preview
    text_preview = []
    for channel in guild.text_channels[:5]:
        text_preview.append(f"• {channel.mention}")

    voice_preview = []
    for channel in guild.voice_channels[:5]:
        voice_preview.append(f"• {channel.name}")

    if text_preview:
        embed.add_field(name="📝 Text Channels Preview", value="\n".join(text_preview), inline=True)

    if voice_preview:
        embed.add_field(name="🔊 Voice Channels Preview", value="\n".join(voice_preview), inline=True)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "channels", f"Viewed channel stats: {text_channels + voice_channels} total")

@bot.tree.command(name="roles", description="🎭 List all server roles")
async def roles(interaction: discord.Interaction):
    guild = interaction.guild
    roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)

    embed = create_embed(
        title="🎭 Server Roles",
        description=f"**{len(roles)}** roles in **{guild.name}**",
        color=COLORS['blue']
    )

    # Show roles with member counts
    role_list = []
    for role in roles[:20]:  # Limit to 20
        if role.name != "@everyone":
            member_count = len(role.members)
            role_list.append(f"{role.mention} - {member_count} members")

    if role_list:
        embed.add_field(name="📋 Roles (Top 20)", value="\n".join(role_list), inline=False)

    embed.add_field(name="📊 Statistics", value=f"**Total Roles:** {len(roles)}\n**Hoisted Roles:** {len([r for r in roles if r.hoist])}\n**Mentionable:** {len([r for r in roles if r.mentionable])}", inline=True)

    if len(roles) > 20:
        embed.add_field(name="➕ More", value=f"... and {len(roles) - 20} more roles", inline=False)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "roles", f"Listed {len(roles)} roles")

@bot.tree.command(name="emojis", description="😀 Show server emojis")
async def emojis(interaction: discord.Interaction):
    guild = interaction.guild

    if not guild.emojis:
        embed = create_info_embed("No Custom Emojis", "This server doesn't have any custom emojis.", interaction.user)
        await interaction.response.send_message(embed=embed)
        return

    embed = create_embed(
        title="😀 Server Emojis",
        description=f"**{len(guild.emojis)}** custom emojis in **{guild.name}**",
        color=COLORS['blue']
    )

    # Show emojis in chunks
    emoji_chunks = []
    current_chunk = []

    for emoji in guild.emojis[:50]:  # Limit to 50
        current_chunk.append(str(emoji))
        if len(current_chunk) == 10:
            emoji_chunks.append(" ".join(current_chunk))
            current_chunk = []

    if current_chunk:
        emoji_chunks.append(" ".join(current_chunk))

    for i, chunk in enumerate(emoji_chunks[:5]):  # Limit to 5 fields
        embed.add_field(name=f"Emojis {i*10 + 1}-{i*10 + len(chunk.split())}", value=chunk, inline=False)

    if len(guild.emojis) > 50:
        embed.add_field(name="➕ More", value=f"... and {len(guild.emojis) - 50} more emojis", inline=False)

    embed.add_field(name="📊 Statistics", value=f"**Total:** {len(guild.emojis)}\n**Animated:** {len([e for e in guild.emojis if e.animated])}\n**Static:** {len([e for e in guild.emojis if not e.animated])}", inline=True)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "emojis", f"Listed {len(guild.emojis)} emojis")

@bot.tree.command(name="invites", description="🔗 Show server invite information")
async def invites(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to view invites.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        invites = await interaction.guild.invites()

        if not invites:
            embed = create_info_embed("No Invites", "This server has no active invites.", interaction.user)
            await interaction.response.send_message(embed=embed)
            return

        embed = create_embed(
            title="🔗 Server Invites",
            description=f"**{len(invites)}** active invites in **{interaction.guild.name}**",
            color=COLORS['blue']
        )

        total_uses = sum(invite.uses for invite in invites)
        embed.add_field(name="📊 Total Uses", value=f"{total_uses:,}", inline=True)
        embed.add_field(name="🔗 Active Invites", value=f"{len(invites)}", inline=True)

        # Show top invites
        top_invites = sorted(invites, key=lambda i: i.uses, reverse=True)[:5]

        invite_list = []
        for invite in top_invites:
            inviter = invite.inviter.display_name if invite.inviter else "Unknown"
            expires = f"<t:{int(invite.expires_at.timestamp())}:R>" if invite.expires_at else "Never"
            invite_list.append(f"**{invite.code}** - {invite.uses} uses - by {inviter} - expires {expires}")

        if invite_list:
            embed.add_field(name="🏆 Top Invites", value="\n".join(invite_list), inline=False)

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "invites", f"Viewed {len(invites)} invites")

    except Exception as e:
        embed = create_error_embed("Invites Failed", f"Could not fetch invites: {str(e)}")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="bans", description="🔨 Show server ban list")
async def bans(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.ban_members:
        embed = create_error_embed("Permission Denied", "You need `Ban Members` permission to view bans.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        bans = [ban async for ban in interaction.guild.bans()]

        if not bans:
            embed = create_info_embed("No Bans", "This server has no active bans.", interaction.user)
            await interaction.response.send_message(embed=embed)
            return

        embed = create_embed(
            title="🔨 Server Bans",
            description=f"**{len(bans)}** banned users in **{interaction.guild.name}**",
            color=COLORS['error']
        )

        # Show recent bans
        ban_list = []
        for ban in bans[:10]:  # Limit to 10
            user = ban.user
            reason = ban.reason or "No reason provided"
            ban_list.append(f"**{user}** (`{user.id}`)\n└ {reason[:50]}{'...' if len(reason) > 50 else ''}")

        if ban_list:
            embed.add_field(name="📋 Recent Bans", value="\n".join(ban_list), inline=False)

        if len(bans) > 10:
            embed.add_field(name="➕ More", value=f"... and {len(bans) - 10} more bans", inline=False)

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "bans", f"Viewed {len(bans)} bans")

    except Exception as e:
        embed = create_error_embed("Bans Failed", f"Could not fetch bans: {str(e)}")
        await interaction.response.send_message(embed=embed)

# UTILITY COMMANDS
@bot.tree.command(name="backup", description="💾 Create server template backup")
async def backup(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to create backups.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.defer()

    try:
        template = await interaction.guild.create_template(
            name=f"{interaction.guild.name} Backup",
            description=f"Backup template for {interaction.guild.name} - Created by {interaction.user}"
        )

        embed = create_success_embed("Backup Created", f"Server template backup created successfully!", interaction.user)
        embed.add_field(name="📋 Template Code", value=f"`{template.code}`", inline=True)
        embed.add_field(name="🔗 Template URL", value=f"[Click here](https://discord.new/{template.code})", inline=True)
        embed.add_field(name="📊 Includes", value="• All channels\n• All roles\n• Permissions\n• Settings", inline=False)

        await interaction.followup.send(embed=embed)
        await log_command_action(interaction, "backup", f"Created template backup: {template.code}")

    except Exception as e:
        embed = create_error_embed("Backup Failed", f"Could not create backup: {str(e)}")
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="createinvite", description="🔗 Create a server invite")
async def createinvite(interaction: discord.Interaction, max_uses: int = 0, max_age: int = 0):
    if not interaction.user.guild_permissions.create_instant_invite:
        embed = create_error_embed("Permission Denied", "You need `Create Invite` permission to create invites.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        invite = await interaction.channel.create_invite(
            max_uses=max_uses,
            max_age=max_age,
            reason=f"Invite created by {interaction.user}"
        )

        embed = create_success_embed("Invite Created", f"Server invite created successfully!", interaction.user)
        embed.add_field(name="🔗 Invite URL", value=f"[{invite.url}]({invite.url})", inline=False)
        embed.add_field(name="📊 Max Uses", value=f"{max_uses if max_uses > 0 else 'Unlimited'}", inline=True)
        embed.add_field(name="⏰ Max Age", value=f"{max_age if max_age > 0 else 'Permanent'} seconds", inline=True)
        embed.add_field(name="📋 Code", value=f"`{invite.code}`", inline=True)

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "createinvite", f"Created invite: {invite.code}")

    except Exception as e:
        embed = create_error_embed("Invite Failed", f"Could not create invite: {str(e)}")
        await interaction.response.send_message(embed=embed)

# ROLE MANAGEMENT COMMANDS
@bot.tree.command(name="addrole", description="➕ Add a role to a user")
async def addrole(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    if not interaction.user.guild_permissions.manage_roles:
        embed = create_error_embed("Permission Denied", "You need `Manage Roles` permission to add roles.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if role.position >= interaction.guild.me.top_role.position:
        embed = create_error_embed("Role Too High", "I cannot add roles higher than my highest role.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if role in user.roles:
        embed = create_info_embed("Role Already Added", f"{user.mention} already has the {role.mention} role.", interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        await user.add_roles(role, reason=f"Role added by {interaction.user}")
        embed = create_success_embed("Role Added", f"Successfully added {role.mention} to {user.mention}", interaction.user)
        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "addrole", f"Added {role.name} to {user}")
    except Exception as e:
        embed = create_error_embed("Add Role Failed", f"Could not add role: {str(e)}")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="removerole", description="➖ Remove a role from a user")
async def removerole(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    if not interaction.user.guild_permissions.manage_roles:
        embed = create_error_embed("Permission Denied", "You need `Manage Roles` permission to remove roles.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if role not in user.roles:
        embed = create_info_embed("Role Not Found", f"{user.mention} doesn't have the {role.mention} role.", interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        await user.remove_roles(role, reason=f"Role removed by {interaction.user}")
        embed = create_success_embed("Role Removed", f"Successfully removed {role.mention} from {user.mention}", interaction.user)
        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "removerole", f"Removed {role.name} from {user}")
    except Exception as e:
        embed = create_error_embed("Remove Role Failed", f"Could not remove role: {str(e)}")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="createrole", description="🎭 Create a new role")
async def createrole(interaction: discord.Interaction, name: str, color: str = None):
    if not interaction.user.guild_permissions.manage_roles:
        embed = create_error_embed("Permission Denied", "You need `Manage Roles` permission to create roles.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Parse color
    role_color = discord.Color.default()
    if color:
        if color.startswith("#"):
            try:
                role_color = discord.Color(int(color[1:], 16))
            except:
                role_color = discord.Color.default()
        elif color.lower() in COLORS:
            role_color = discord.Color(COLORS[color.lower()])

    try:
        role = await interaction.guild.create_role(
            name=name,
            color=role_color,
            reason=f"Role created by {interaction.user}"
        )

        embed = create_success_embed("Role Created", f"Successfully created role {role.mention}", interaction.user)
        embed.add_field(name="🎭 Role Name", value=role.name, inline=True)
        embed.add_field(name="🎨 Color", value=f"#{role.color.value:06x}", inline=True)
        embed.add_field(name="🆔 Role ID", value=role.id, inline=True)

        await interaction.response.send_message(embed=embed)
        await log_command_action(interaction, "createrole", f"Created role: {name}")

    except Exception as e:
        embed = create_error_embed("Create Role Failed", f"Could not create role: {str(e)}")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="deleterole", description="🗑️ Delete a role")
async def deleterole(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.manage_roles:
        embed = create_error_embed("Permission Denied", "You need `Manage Roles` permission to delete roles.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if role.position >= interaction.guild.me.top_role.position:
        embed = create_error_embed("Role Too High", "I cannot delete roles higher than my highest role.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    confirmed = await confirm_dangerous_action(
        interaction,
        "Delete Role",
        f"This will permanently delete the role {role.name} and remove it from all {len(role.members)} members who have it."
    )

    if not confirmed:
        return

    try:
        role_name = role.name
        member_count = len(role.members)
        await role.delete(reason=f"Role deleted by {interaction.user}")

        embed = create_success_embed("Role Deleted", f"Successfully deleted role **{role_name}**\nRemoved from {member_count} members", interaction.user)
        await interaction.edit_original_response(embed=embed)
        await log_command_action(interaction, "deleterole", f"Deleted role: {role_name}")

    except Exception as e:
        embed = create_error_embed("Delete Role Failed", f"Could not delete role: {str(e)}")
        await interaction.edit_original_response(embed=embed)

@bot.tree.command(name="roleinfo", description="🎭 Get detailed role information")
async def roleinfo(interaction: discord.Interaction, role: discord.Role):
    embed = create_embed(
        title=f"🎭 {role.name}",
        description=f"Information about {role.mention}",
        color=role.color if role.color != discord.Color.default() else COLORS['blue']
    )

    embed.add_field(name="🆔 Role ID", value=role.id, inline=True)
    embed.add_field(name="🎨 Color", value=f"#{role.color.value:06x}", inline=True)
    embed.add_field(name="📅 Created", value=f"<t:{int(role.created_at.timestamp())}:F>", inline=True)

    embed.add_field(name="👥 Members", value=len(role.members), inline=True)
    embed.add_field(name="📊 Position", value=role.position, inline=True)
    embed.add_field(name="🔗 Mentionable", value="Yes" if role.mentionable else "No", inline=True)

    embed.add_field(name="📋 Hoisted", value="Yes" if role.hoist else "No", inline=True)
    embed.add_field(name="🤖 Managed", value="Yes" if role.managed else "No", inline=True)
    embed.add_field(name="🎯 Permissions", value=len([p for p, v in role.permissions if v]), inline=True)

    # Show key permissions
    key_perms = []
    if role.permissions.administrator:
        key_perms.append("👑 Administrator")
    if role.permissions.manage_guild:
        key_perms.append("⚙️ Manage Server")
    if role.permissions.manage_channels:
        key_perms.append("📁 Manage Channels")
    if role.permissions.manage_roles:
        key_perms.append("🎭 Manage Roles")
    if role.permissions.kick_members:
        key_perms.append("👢 Kick Members")
    if role.permissions.ban_members:
        key_perms.append("🔨 Ban Members")

    if key_perms:
        embed.add_field(name="🔑 Key Permissions", value="\n".join(key_perms[:5]), inline=False)

    # Show some members with this role
    if role.members:
        member_list = [member.mention for member in role.members[:5]]
        embed.add_field(name="👥 Members (Preview)", value="\n".join(member_list), inline=False)

        if len(role.members) > 5:
            embed.add_field(name="➕ More", value=f"... and {len(role.members) - 5} more members", inline=False)

    await interaction.response.send_message(embed=embed)
    await log_command_action(interaction, "roleinfo", f"Viewed role info for {role.name}")

# EVENT COMMAND FOR COMMUNITY FEATURES
@bot.tree.command(name="enablecommunity", description="🌍 Enable Discord community features")
async def enablecommunity(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        embed = create_error_embed("Permission Denied", "You need `Administrator` permission to enable community features.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if interaction.guild.community:
        embed = create_info_embed("Already Enabled", "Community features are already enabled for this server.", interaction.user)
        await interaction.response.send_message(embed=embed)
        return

    await interaction.response.defer()

    try:
        # Find rules and public updates channels
        rules_channel = None
        updates_channel = None

        for channel in interaction.guild.text_channels:
            if "rules" in channel.name.lower() and not rules_channel:
                rules_channel = channel
            elif any(word in channel.name.lower() for word in ["announcement", "updates", "news"]) and not updates_channel:
                updates_channel = channel

        # Create channels if they don't exist
        if not rules_channel:
            rules_channel = await interaction.guild.create_text_channel("rules")

        if not updates_channel:
            updates_channel = await interaction.guild.create_text_channel("announcements")

        # Enable community
        await interaction.guild.edit(
            community=True,
            rules_channel=rules_channel,
            public_updates_channel=updates_channel
        )

        embed = create_success_embed("Community Enabled", "Discord community features have been enabled!", interaction.user)
        embed.add_field(name="📋 Rules Channel", value=rules_channel.mention, inline=True)
        embed.add_field(name="📢 Updates Channel", value=updates_channel.mention, inline=True)
        embed.add_field(name="✨ New Features", value="• Server discovery\n• Welcome screen\n• Membership screening\n• Stage channels\n• Events", inline=False)

        await interaction.followup.send(embed=embed)
        await log_command_action(interaction, "enablecommunity", "Enabled community features")

    except Exception as e:
        embed = create_error_embed("Community Failed", f"Could not enable community features: {str(e)}")
        await interaction.followup.send(embed=embed)

async def load_cogs():
    """Load all cog modules"""
    cogs_to_load = [
        'cogs.premium',
        'cogs.economy', 
        'cogs.leveling',
        'cogs.music',
        'cogs.giveaways',
        'cogs.moderation',
        'cogs.fun',
        'cogs.utility'
    ]
    
    for cog in cogs_to_load:
        try:
            await bot.load_extension(cog)
            print(f"✅ Loaded {cog}")
        except Exception as e:
            print(f"❌ Failed to load {cog}: {e}")

async def main():
    """Main bot startup function"""
    print("⚙️ Starting Ultimate All-in-One Discord Bot...")
    print("✨ Loading premium system, economy, leveling, music, giveaways, moderation, and fun features!")
    print("💎 Premium features enabled with AI integration!")
    print("🎵 Music system with YouTube integration ready!")
    print("🎉 Advanced giveaway system loaded!")
    print("🛡️ Comprehensive moderation and AutoMod ready!")
    print("📊 Leveling system with rank cards activated!")
    print("💰 Complete economy system with gambling ready!")
    
    # Load all cogs
    await load_cogs()
    
    # Start the bot
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
