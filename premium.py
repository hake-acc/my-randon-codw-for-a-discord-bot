import discord
from discord.ext import commands
import sqlite3
from datetime import datetime, timedelta
import secrets
import asyncio

DATABASE_FILE = "bot_database.db"

# Premium system color scheme
PREMIUM_COLORS = {
    'gold': 0xFFD700,
    'premium': 0x9932CC,
    'success': 0x00FF00,
    'error': 0xFF0000,
    'warning': 0xFFA500
}

def create_embed(title, description, color=PREMIUM_COLORS['premium']):
    """Create a consistent embed"""
    embed = discord.Embed(title=title, description=description, color=color)
    embed.timestamp = datetime.now()
    return embed

def create_success_embed(title, description, user=None):
    """Create a success embed"""
    embed = create_embed(title, description, PREMIUM_COLORS['success'])
    if user:
        embed.set_footer(text=f"Requested by {user.display_name}", icon_url=user.display_avatar.url)
    return embed

def create_error_embed(title, description):
    """Create an error embed"""
    return create_embed(title, description, PREMIUM_COLORS['error'])

class PremiumSystem(commands.Cog):
    """Complete premium system with database-backed storage and feature gating"""
    
    def __init__(self, bot):
        self.bot = bot
        self.init_premium_database()
    
    def init_premium_database(self):
        """Initialize premium system database tables"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            # Premium users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS premium_users (
                    user_id INTEGER PRIMARY KEY,
                    expires_at TIMESTAMP NOT NULL,
                    tier TEXT NOT NULL DEFAULT 'basic',
                    granted_by INTEGER,
                    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Premium guilds table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS premium_guilds (
                    guild_id INTEGER PRIMARY KEY,
                    expires_at TIMESTAMP NOT NULL,
                    tier TEXT NOT NULL DEFAULT 'basic',
                    granted_by INTEGER,
                    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Premium codes table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS premium_codes (
                    code TEXT PRIMARY KEY,
                    duration_days INTEGER NOT NULL,
                    tier TEXT NOT NULL DEFAULT 'basic',
                    type TEXT NOT NULL DEFAULT 'user',
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    used_by INTEGER,
                    used_at TIMESTAMP,
                    active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Premium transactions log
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS premium_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id INTEGER NOT NULL,
                    target_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    tier TEXT,
                    duration_days INTEGER,
                    performed_by INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            print("✅ Premium system database initialized")
            
        except Exception as e:
            print(f"❌ Premium database initialization failed: {e}")
    
    def is_premium_user(self, user_id: int) -> bool:
        """Check if user has active premium"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT expires_at FROM premium_users 
                WHERE user_id = ? AND active = 1 AND expires_at > datetime('now')
            ''', (user_id,))
            result = cursor.fetchone()
            conn.close()
            return bool(result)
        except:
            return False
    
    def is_premium_guild(self, guild_id: int) -> bool:
        """Check if guild has active premium"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT expires_at FROM premium_guilds 
                WHERE guild_id = ? AND active = 1 AND expires_at > datetime('now')
            ''', (guild_id,))
            result = cursor.fetchone()
            conn.close()
            return bool(result)
        except:
            return False
    
    def get_premium_status(self, user_id: int = None, guild_id: int = None) -> dict:
        """Get detailed premium status"""
        status = {
            'user_premium': False,
            'guild_premium': False,
            'user_expires': None,
            'guild_expires': None,
            'user_tier': None,
            'guild_tier': None
        }
        
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            if user_id:
                cursor.execute('''
                    SELECT expires_at, tier FROM premium_users 
                    WHERE user_id = ? AND active = 1 AND expires_at > datetime('now')
                ''', (user_id,))
                user_result = cursor.fetchone()
                if user_result:
                    status['user_premium'] = True
                    status['user_expires'] = user_result[0]
                    status['user_tier'] = user_result[1]
            
            if guild_id:
                cursor.execute('''
                    SELECT expires_at, tier FROM premium_guilds 
                    WHERE guild_id = ? AND active = 1 AND expires_at > datetime('now')
                ''', (guild_id,))
                guild_result = cursor.fetchone()
                if guild_result:
                    status['guild_premium'] = True
                    status['guild_expires'] = guild_result[0]
                    status['guild_tier'] = guild_result[1]
            
            conn.close()
            
        except Exception as e:
            print(f"Error getting premium status: {e}")
        
        return status
    
    def generate_premium_code(self, duration_days: int, tier: str = 'basic', code_type: str = 'user', created_by: int = None) -> str:
        """Generate a new premium code"""
        code = f"PREMIUM-{secrets.token_urlsafe(16)}"
        
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO premium_codes (code, duration_days, tier, type, created_by)
                VALUES (?, ?, ?, ?, ?)
            ''', (code, duration_days, tier, code_type, created_by))
            conn.commit()
            conn.close()
            return code
        except Exception as e:
            print(f"Error generating premium code: {e}")
            return None
    
    def redeem_premium_code(self, code: str, user_id: int = None, guild_id: int = None) -> dict:
        """Redeem a premium code"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            # Check if code exists and is unused
            cursor.execute('''
                SELECT duration_days, tier, type FROM premium_codes 
                WHERE code = ? AND active = 1 AND used_by IS NULL
            ''', (code,))
            code_data = cursor.fetchone()
            
            if not code_data:
                conn.close()
                return {'success': False, 'error': 'Invalid or already used code'}
            
            duration_days, tier, code_type = code_data
            expires_at = datetime.now() + timedelta(days=duration_days)
            
            # Apply premium based on code type
            if code_type == 'user' and user_id is not None:
                # Check for existing premium
                cursor.execute('SELECT expires_at FROM premium_users WHERE user_id = ? AND active = 1', (user_id,))
                existing = cursor.fetchone()
                
                if existing:
                    # Extend existing premium
                    current_expires = datetime.fromisoformat(existing[0])
                    if current_expires > datetime.now():
                        expires_at = current_expires + timedelta(days=duration_days)
                    
                    cursor.execute('''
                        UPDATE premium_users SET expires_at = ?, tier = ? WHERE user_id = ?
                    ''', (expires_at.isoformat(), tier, user_id))
                else:
                    # Grant new premium
                    cursor.execute('''
                        INSERT INTO premium_users (user_id, expires_at, tier, granted_by)
                        VALUES (?, ?, ?, ?)
                    ''', (user_id, expires_at.isoformat(), tier, user_id))
                
                target_id = user_id
                
            elif code_type == 'guild' and guild_id is not None:
                # Check for existing premium
                cursor.execute('SELECT expires_at FROM premium_guilds WHERE guild_id = ? AND active = 1', (guild_id,))
                existing = cursor.fetchone()
                
                if existing:
                    # Extend existing premium
                    current_expires = datetime.fromisoformat(existing[0])
                    if current_expires > datetime.now():
                        expires_at = current_expires + timedelta(days=duration_days)
                    
                    cursor.execute('''
                        UPDATE premium_guilds SET expires_at = ?, tier = ? WHERE guild_id = ?
                    ''', (expires_at.isoformat(), tier, guild_id))
                else:
                    # Grant new premium
                    cursor.execute('''
                        INSERT INTO premium_guilds (guild_id, expires_at, tier, granted_by)
                        VALUES (?, ?, ?, ?)
                    ''', (guild_id, expires_at.isoformat(), tier, user_id))
                
                target_id = guild_id
            else:
                conn.close()
                return {'success': False, 'error': 'Invalid code type or missing target'}
            
            # Mark code as used
            cursor.execute('''
                UPDATE premium_codes SET used_by = ?, used_at = datetime('now') WHERE code = ?
            ''', (user_id, code))
            
            # Log transaction
            cursor.execute('''
                INSERT INTO premium_transactions (target_id, target_type, action, tier, duration_days, performed_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (target_id, code_type, 'redeem', tier, duration_days, user_id))
            
            conn.commit()
            conn.close()
            
            return {
                'success': True,
                'tier': tier,
                'duration_days': duration_days,
                'expires_at': expires_at,
                'type': code_type
            }
            
        except Exception as e:
            print(f"Error redeeming premium code: {e}")
            return {'success': False, 'error': f'Database error: {str(e)}'}
    
    async def premium_required(self, interaction: discord.Interaction, feature_name: str = "feature") -> bool:
        """Check if user/guild has premium and show upgrade message if not"""
        user_premium = self.is_premium_user(interaction.user.id)
        guild_premium = self.is_premium_guild(interaction.guild.id) if interaction.guild else False
        
        if user_premium or guild_premium:
            return True
        
        embed = create_error_embed(
            "Premium Required",
            f"**{feature_name}** is a premium-only feature!"
        )
        
        embed.add_field(
            name="✨ Get Premium",
            value="Use `/premium redeem <code>` with your premium code\nor contact support for premium access",
            inline=False
        )
        
        embed.add_field(
            name="💎 Premium Benefits",
            value="• Unlimited commands & features\n• Advanced moderation tools\n• Music system with filters\n• Custom embed themes\n• Priority support",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    
    @discord.app_commands.command(name="premium", description="💎 Manage your premium status")
    @discord.app_commands.describe(action="What would you like to do?")
    @discord.app_commands.choices(action=[
        discord.app_commands.Choice(name="📊 Check Status", value="status"),
        discord.app_commands.Choice(name="🎫 Redeem Code", value="redeem"),
        discord.app_commands.Choice(name="ℹ️ Information", value="info")
    ])
    async def premium(self, interaction: discord.Interaction, action: discord.app_commands.Choice[str]):
        """Premium system management"""
        
        if action.value == "status":
            await self.show_premium_status(interaction)
        elif action.value == "redeem":
            await self.show_redeem_interface(interaction)
        elif action.value == "info":
            await self.show_premium_info(interaction)
    
    async def show_premium_status(self, interaction: discord.Interaction):
        """Show current premium status"""
        status = self.get_premium_status(interaction.user.id, interaction.guild.id if interaction.guild else None)
        
        embed = create_embed(
            title="💎 Premium Status",
            description="**Your current premium subscription details**",
            color=PREMIUM_COLORS['gold'] if (status['user_premium'] or status['guild_premium']) else PREMIUM_COLORS['error']
        )
        
        # User Premium Status
        if status['user_premium']:
            embed.add_field(
                name="👤 Personal Premium",
                value=f"✅ **Active** ({status['user_tier'].title()})\n📅 Expires: {status['user_expires'][:10]}",
                inline=True
            )
        else:
            embed.add_field(
                name="👤 Personal Premium",
                value="❌ **Not Active**\nUpgrade for personal benefits",
                inline=True
            )
        
        # Guild Premium Status
        if interaction.guild:
            if status['guild_premium']:
                embed.add_field(
                    name="🏰 Server Premium",
                    value=f"✅ **Active** ({status['guild_tier'].title()})\n📅 Expires: {status['guild_expires'][:10]}",
                    inline=True
                )
            else:
                embed.add_field(
                    name="🏰 Server Premium",
                    value="❌ **Not Active**\nUpgrade for server benefits",
                    inline=True
                )
        
        # Show available features
        if status['user_premium'] or status['guild_premium']:
            embed.add_field(
                name="🎯 Active Benefits",
                value="• Unlimited commands\n• Advanced moderation\n• Music system access\n• Custom embed themes\n• Priority support",
                inline=False
            )
        else:
            embed.add_field(
                name="💎 Premium Benefits",
                value="• **Unlimited Commands** - No cooldowns\n• **Advanced Features** - Full moderation suite\n• **Music System** - YouTube/Spotify with filters\n• **Custom Themes** - Personalized embed colors\n• **Priority Support** - Faster help response",
                inline=False
            )
        
        embed.set_footer(text="Use /premium redeem to activate premium with a code")
        await interaction.response.send_message(embed=embed)
    
    async def show_redeem_interface(self, interaction: discord.Interaction):
        """Show code redemption interface"""
        view = PremiumRedeemView(interaction.user.id, self)
        
        embed = create_embed(
            title="🎫 Redeem Premium Code",
            description="**Enter your premium code to activate premium features**",
            color=PREMIUM_COLORS['gold']
        )
        
        embed.add_field(
            name="📝 How to Redeem",
            value="Click the button below and enter your premium code",
            inline=False
        )
        
        embed.add_field(
            name="🎯 Code Types",
            value="• **User Premium** - Benefits follow you across servers\n• **Server Premium** - Benefits apply to this entire server",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, view=view)
    
    async def show_premium_info(self, interaction: discord.Interaction):
        """Show premium information and benefits"""
        embed = create_embed(
            title="💎 Premium Information",
            description="**Unlock the full potential of this Discord bot**",
            color=PREMIUM_COLORS['premium']
        )
        
        embed.add_field(
            name="🎯 Premium Features",
            value="• **No Cooldowns** - Use commands without waiting\n• **Advanced Moderation** - Full AutoMod suite\n• **Music System** - YouTube/Spotify with premium filters\n• **Unlimited Tickets** - No panel limits\n• **Custom Themes** - Personalized embed colors\n• **Advanced Economy** - Extra daily rewards",
            inline=False
        )
        
        embed.add_field(
            name="🎫 Getting Premium",
            value="Premium codes are available through:\n• Bot owner/admin distribution\n• Special events and giveaways\n• Partner server rewards",
            inline=False
        )
        
        embed.add_field(
            name="📊 Current Status",
            value="Use `/premium status` to check your current subscription",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    # Owner-only premium management commands
    @discord.app_commands.command(name="premium_admin", description="🔧 [OWNER] Manage premium subscriptions")
    @discord.app_commands.describe(
        action="Admin action to perform",
        target="User or server to manage",
        duration="Duration in days",
        tier="Premium tier"
    )
    @discord.app_commands.choices(
        action=[
            discord.app_commands.Choice(name="🎁 Grant Premium", value="grant"),
            discord.app_commands.Choice(name="🗑️ Revoke Premium", value="revoke"),
            discord.app_commands.Choice(name="🎫 Generate Code", value="generate"),
            discord.app_commands.Choice(name="📊 View Status", value="view")
        ],
        tier=[
            discord.app_commands.Choice(name="⭐ Basic", value="basic"),
            discord.app_commands.Choice(name="💎 Premium", value="premium"),
            discord.app_commands.Choice(name="🌟 Ultimate", value="ultimate")
        ]
    )
    async def premium_admin(self, interaction: discord.Interaction, 
                           action: discord.app_commands.Choice[str],
                           target: str = None,
                           duration: int = 30,
                           tier: discord.app_commands.Choice[str] = None):
        """Owner-only premium management"""
        
        # Check if user is bot owner
        if interaction.user.id != 1123311707676610661:  # Replace with actual bot owner ID
            embed = create_error_embed("Access Denied", "Only the bot owner can use premium admin commands.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if action.value == "generate":
            # Generate premium code
            tier_value = tier.value if tier else "basic"
            code = self.generate_premium_code(duration, tier_value, "user", interaction.user.id)
            
            if code:
                embed = create_success_embed(
                    "🎫 Premium Code Generated",
                    f"**Code:** `{code}`\n**Duration:** {duration} days\n**Tier:** {tier_value.title()}\n**Type:** User Premium",
                    interaction.user
                )
                embed.add_field(
                    name="📋 Instructions",
                    value="Share this code with users to redeem via `/premium redeem`",
                    inline=False
                )
            else:
                embed = create_error_embed("Generation Failed", "Could not generate premium code.")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Add other admin actions (grant, revoke, view) here as needed

class PremiumRedeemView(discord.ui.View):
    """Interactive premium code redemption"""
    
    def __init__(self, user_id: int, premium_system):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.premium_system = premium_system
    
    @discord.ui.button(label="🎫 Enter Premium Code", style=discord.ButtonStyle.primary, emoji="🎫")
    async def redeem_code(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can redeem codes.", ephemeral=True)
            return
        
        modal = PremiumRedeemModal(self.premium_system)
        await interaction.response.send_modal(modal)

class PremiumRedeemModal(discord.ui.Modal):
    """Modal for entering premium codes"""
    
    def __init__(self, premium_system):
        super().__init__(title="🎫 Redeem Premium Code")
        self.premium_system = premium_system
        
        self.code_input = discord.ui.TextInput(
            label="Premium Code",
            placeholder="Enter your premium code here...",
            max_length=100,
            required=True
        )
        self.add_item(self.code_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        code = self.code_input.value.strip()
        
        # Attempt redemption
        result = self.premium_system.redeem_premium_code(
            code, 
            user_id=interaction.user.id,
            guild_id=interaction.guild.id if interaction.guild else None
        )
        
        if result['success']:
            embed = create_success_embed(
                "🎉 Premium Activated!",
                f"Successfully redeemed premium code!\n\n**Tier:** {result['tier'].title()}\n**Duration:** {result['duration_days']} days\n**Expires:** {result['expires_at'].strftime('%Y-%m-%d')}",
                interaction.user
            )
            embed.add_field(
                name="🎯 What's Next?",
                value="You now have access to all premium features! Use commands without cooldowns and enjoy advanced functionality.",
                inline=False
            )
        else:
            embed = create_error_embed(
                "❌ Redemption Failed",
                f"Could not redeem code: {result['error']}"
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Helper functions for other cogs to use
def is_premium_user(user_id: int) -> bool:
    """Check if user has premium (for use in other cogs)"""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT expires_at FROM premium_users 
            WHERE user_id = ? AND active = 1 AND expires_at > datetime('now')
        ''', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return bool(result)
    except:
        return False

def is_premium_guild(guild_id: int) -> bool:
    """Check if guild has premium (for use in other cogs)"""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT expires_at FROM premium_guilds 
            WHERE guild_id = ? AND active = 1 AND expires_at > datetime('now')
        ''', (guild_id,))
        result = cursor.fetchone()
        conn.close()
        return bool(result)
    except:
        return False

def require_premium(feature_name: str = "feature"):
    """Decorator to require premium for command usage"""
    def decorator(func):
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            user_premium = is_premium_user(interaction.user.id)
            guild_premium = is_premium_guild(interaction.guild.id) if interaction.guild else False
            
            if not (user_premium or guild_premium):
                embed = create_error_embed(
                    "Premium Required",
                    f"**{feature_name}** requires premium access!"
                )
                embed.add_field(
                    name="🎫 Get Premium",
                    value="Use `/premium redeem <code>` to activate premium features",
                    inline=False
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            return await func(self, interaction, *args, **kwargs)
        return wrapper
    return decorator

async def setup(bot):
    await bot.add_cog(PremiumSystem(bot))