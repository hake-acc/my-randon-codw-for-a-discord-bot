import discord
from discord.ext import commands
import sqlite3
import random
import asyncio
from datetime import datetime, timedelta
from cogs.premium import is_premium_user, is_premium_guild, require_premium

DATABASE_FILE = "bot_database.db"

COLORS = {
    'success': 0x00FF00,
    'error': 0xFF0000,
    'warning': 0xFFA500,
    'info': 0x0099FF,
    'gold': 0xFFD700
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

class EconomySystem(commands.Cog):
    """Complete economy system with wallet, shop, gambling, and rewards"""
    
    def __init__(self, bot):
        self.bot = bot
        self.init_economy_database()
        self.daily_cooldowns = {}
        self.weekly_cooldowns = {}
    
    def init_economy_database(self):
        """Initialize economy database tables"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            # User economy data
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_economy (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    wallet INTEGER DEFAULT 0,
                    bank INTEGER DEFAULT 0,
                    last_daily TIMESTAMP,
                    last_weekly TIMESTAMP,
                    daily_streak INTEGER DEFAULT 0,
                    total_earned INTEGER DEFAULT 0,
                    total_spent INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id)
                )
            ''')
            
            # Shop items
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS shop_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    price INTEGER NOT NULL,
                    type TEXT NOT NULL DEFAULT 'role',
                    item_data TEXT,
                    stock INTEGER DEFAULT -1,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active BOOLEAN DEFAULT 1
                )
            ''')
            
            # User purchases
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    price_paid INTEGER NOT NULL,
                    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Economy settings per guild
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS economy_settings (
                    guild_id INTEGER PRIMARY KEY,
                    currency_name TEXT DEFAULT 'coins',
                    currency_symbol TEXT DEFAULT '💰',
                    daily_amount INTEGER DEFAULT 100,
                    weekly_amount INTEGER DEFAULT 500,
                    work_enabled BOOLEAN DEFAULT 1,
                    gambling_enabled BOOLEAN DEFAULT 1,
                    shop_enabled BOOLEAN DEFAULT 1,
                    max_wallet INTEGER DEFAULT 10000,
                    max_bank INTEGER DEFAULT 100000
                )
            ''')
            
            conn.commit()
            conn.close()
            print("✅ Economy system database initialized")
            
        except Exception as e:
            print(f"❌ Economy database initialization failed: {e}")
    
    def get_user_balance(self, user_id: int, guild_id: int) -> dict:
        """Get user's economy data"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT wallet, bank, daily_streak, total_earned, total_spent 
                FROM user_economy WHERE user_id = ? AND guild_id = ?
            ''', (user_id, guild_id))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'wallet': result[0],
                    'bank': result[1],
                    'daily_streak': result[2],
                    'total_earned': result[3],
                    'total_spent': result[4]
                }
            else:
                # Create new user
                self.create_user_economy(user_id, guild_id)
                return {'wallet': 0, 'bank': 0, 'daily_streak': 0, 'total_earned': 0, 'total_spent': 0}
                
        except Exception as e:
            print(f"Error getting user balance: {e}")
            return {'wallet': 0, 'bank': 0, 'daily_streak': 0, 'total_earned': 0, 'total_spent': 0}
    
    def create_user_economy(self, user_id: int, guild_id: int):
        """Create new user economy entry"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO user_economy (user_id, guild_id)
                VALUES (?, ?)
            ''', (user_id, guild_id))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error creating user economy: {e}")
    
    def update_balance(self, user_id: int, guild_id: int, wallet_change: int = 0, bank_change: int = 0):
        """Update user's balance"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            # Ensure user exists
            self.create_user_economy(user_id, guild_id)
            
            # Update balance
            cursor.execute('''
                UPDATE user_economy 
                SET wallet = wallet + ?, bank = bank + ?, 
                    total_earned = total_earned + ?
                WHERE user_id = ? AND guild_id = ?
            ''', (wallet_change, bank_change, max(0, wallet_change + bank_change), user_id, guild_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error updating balance: {e}")
            return False
    
    @discord.app_commands.command(name="balance", description="💰 Check your current balance")
    @discord.app_commands.describe(user="Check another user's balance")
    async def balance(self, interaction: discord.Interaction, user: discord.Member = None):
        """Check user balance"""
        target_user = user or interaction.user
        balance_data = self.get_user_balance(target_user.id, interaction.guild.id)
        
        embed = create_embed(
            title=f"💰 {target_user.display_name}'s Balance",
            description="**Current economy status**",
            color=COLORS['gold']
        )
        
        embed.add_field(
            name="💵 Wallet",
            value=f"**{balance_data['wallet']:,}** coins",
            inline=True
        )
        
        embed.add_field(
            name="🏦 Bank",
            value=f"**{balance_data['bank']:,}** coins",
            inline=True
        )
        
        embed.add_field(
            name="💎 Total",
            value=f"**{balance_data['wallet'] + balance_data['bank']:,}** coins",
            inline=True
        )
        
        embed.add_field(
            name="📊 Statistics",
            value=f"Daily Streak: **{balance_data['daily_streak']}**\nTotal Earned: **{balance_data['total_earned']:,}**\nTotal Spent: **{balance_data['total_spent']:,}**",
            inline=False
        )
        
        embed.set_thumbnail(url=target_user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="daily", description="💰 Claim your daily reward")
    async def daily(self, interaction: discord.Interaction):
        """Claim daily reward"""
        user_id = interaction.user.id
        guild_id = interaction.guild.id
        
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            # Check if user can claim daily
            cursor.execute('''
                SELECT last_daily, daily_streak FROM user_economy 
                WHERE user_id = ? AND guild_id = ?
            ''', (user_id, guild_id))
            result = cursor.fetchone()
            
            if result and result[0]:
                last_daily = datetime.fromisoformat(result[0])
                if datetime.now() - last_daily < timedelta(hours=20):  # 20 hour cooldown
                    time_left = timedelta(hours=24) - (datetime.now() - last_daily)
                    hours, remainder = divmod(time_left.total_seconds(), 3600)
                    minutes = remainder // 60
                    
                    embed = create_error_embed(
                        "Daily Cooldown",
                        f"You already claimed your daily reward!\n\n⏰ **Time remaining:** {int(hours)}h {int(minutes)}m"
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
            
            # Calculate reward
            base_reward = 100
            streak_bonus = min((result[1] if result else 0) * 10, 200)  # Max 200 bonus
            premium_bonus = 50 if (is_premium_user(user_id) or is_premium_guild(guild_id)) else 0
            total_reward = base_reward + streak_bonus + premium_bonus
            
            # Update streak
            new_streak = (result[1] + 1) if result and result[0] and (datetime.now() - datetime.fromisoformat(result[0])) < timedelta(hours=48) else 1
            
            # Apply reward
            self.create_user_economy(user_id, guild_id)
            cursor.execute('''
                UPDATE user_economy 
                SET wallet = wallet + ?, last_daily = datetime('now'), daily_streak = ?,
                    total_earned = total_earned + ?
                WHERE user_id = ? AND guild_id = ?
            ''', (total_reward, new_streak, total_reward, user_id, guild_id))
            
            conn.commit()
            conn.close()
            
            embed = create_success_embed(
                "🎁 Daily Reward Claimed!",
                f"You received **{total_reward:,} coins**!",
                interaction.user
            )
            
            embed.add_field(
                name="💰 Breakdown",
                value=f"Base Reward: **{base_reward}**\nStreak Bonus: **{streak_bonus}**\n{'Premium Bonus: **' + str(premium_bonus) + '**' if premium_bonus > 0 else ''}",
                inline=True
            )
            
            embed.add_field(
                name="🔥 Streak",
                value=f"**{new_streak} day{'s' if new_streak != 1 else ''}**\nKeep claiming to increase your bonus!",
                inline=True
            )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            embed = create_error_embed("Error", f"Could not process daily reward: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="weekly", description="💎 Claim your weekly reward")
    async def weekly(self, interaction: discord.Interaction):
        """Claim weekly reward"""
        user_id = interaction.user.id
        guild_id = interaction.guild.id
        
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            # Check if user can claim weekly
            cursor.execute('''
                SELECT last_weekly FROM user_economy 
                WHERE user_id = ? AND guild_id = ?
            ''', (user_id, guild_id))
            result = cursor.fetchone()
            
            if result and result[0]:
                last_weekly = datetime.fromisoformat(result[0])
                if datetime.now() - last_weekly < timedelta(days=7):
                    time_left = timedelta(days=7) - (datetime.now() - last_weekly)
                    days = time_left.days
                    hours = time_left.seconds // 3600
                    
                    embed = create_error_embed(
                        "Weekly Cooldown",
                        f"You already claimed your weekly reward!\n\n⏰ **Time remaining:** {days}d {hours}h"
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
            
            # Calculate reward
            base_reward = 500
            premium_bonus = 200 if (is_premium_user(user_id) or is_premium_guild(guild_id)) else 0
            total_reward = base_reward + premium_bonus
            
            # Apply reward
            self.create_user_economy(user_id, guild_id)
            cursor.execute('''
                UPDATE user_economy 
                SET wallet = wallet + ?, last_weekly = datetime('now'),
                    total_earned = total_earned + ?
                WHERE user_id = ? AND guild_id = ?
            ''', (total_reward, total_reward, user_id, guild_id))
            
            conn.commit()
            conn.close()
            
            embed = create_success_embed(
                "🎁 Weekly Reward Claimed!",
                f"You received **{total_reward:,} coins**!",
                interaction.user
            )
            
            embed.add_field(
                name="💰 Breakdown",
                value=f"Base Reward: **{base_reward}**\n{'Premium Bonus: **' + str(premium_bonus) + '**' if premium_bonus > 0 else 'No premium bonus'}",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            embed = create_error_embed("Error", f"Could not process weekly reward: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="work", description="💼 Work to earn coins")
    async def work(self, interaction: discord.Interaction):
        """Work command to earn coins"""
        user_id = interaction.user.id
        guild_id = interaction.guild.id
        
        # Cooldown check (1 hour)
        cooldown_key = f"{user_id}_{guild_id}_work"
        if cooldown_key in self.daily_cooldowns:
            time_left = self.daily_cooldowns[cooldown_key] - datetime.now()
            if time_left.total_seconds() > 0:
                minutes = int(time_left.total_seconds() // 60)
                embed = create_error_embed(
                    "Work Cooldown",
                    f"You need to rest! Try again in **{minutes} minutes**."
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
        
        # Set cooldown
        cooldown_duration = 30 if (is_premium_user(user_id) or is_premium_guild(guild_id)) else 60  # Premium gets shorter cooldown
        self.daily_cooldowns[cooldown_key] = datetime.now() + timedelta(minutes=cooldown_duration)
        
        # Calculate earnings
        base_earnings = random.randint(10, 50)
        premium_bonus = random.randint(5, 15) if (is_premium_user(user_id) or is_premium_guild(guild_id)) else 0
        total_earnings = base_earnings + premium_bonus
        
        # Apply earnings
        self.update_balance(user_id, guild_id, total_earnings)
        
        # Random work scenarios
        work_scenarios = [
            "delivered packages",
            "coded a website",
            "helped at a cafe",
            "walked dogs",
            "tutored students",
            "designed graphics",
            "wrote articles",
            "cleaned offices"
        ]
        
        scenario = random.choice(work_scenarios)
        
        embed = create_success_embed(
            "💼 Work Complete!",
            f"You {scenario} and earned **{total_earnings:,} coins**!",
            interaction.user
        )
        
        if premium_bonus > 0:
            embed.add_field(
                name="💎 Premium Bonus",
                value=f"Extra **{premium_bonus}** coins from premium!",
                inline=False
            )
        
        embed.set_footer(text=f"Next work available in {cooldown_duration} minutes")
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="gamble", description="🎰 Gamble your coins")
    @discord.app_commands.describe(
        game="Choose gambling game",
        amount="Amount to gamble"
    )
    @discord.app_commands.choices(game=[
        discord.app_commands.Choice(name="🎰 Slots", value="slots"),
        discord.app_commands.Choice(name="🪙 Coinflip", value="coinflip"),
        discord.app_commands.Choice(name="🃏 Blackjack", value="blackjack")
    ])
    async def gamble(self, interaction: discord.Interaction, 
                    game: discord.app_commands.Choice[str], 
                    amount: int):
        """Gambling system"""
        user_id = interaction.user.id
        guild_id = interaction.guild.id
        
        # Check if gambling is enabled
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('SELECT gambling_enabled FROM economy_settings WHERE guild_id = ?', (guild_id,))
            result = cursor.fetchone()
            conn.close()
            
            if result and not result[0]:
                embed = create_error_embed("Gambling Disabled", "Gambling is disabled in this server.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
        except:
            pass
        
        # Validate amount
        if amount <= 0:
            embed = create_error_embed("Invalid Amount", "You must gamble at least 1 coin!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        balance = self.get_user_balance(user_id, guild_id)
        if balance['wallet'] < amount:
            embed = create_error_embed(
                "Insufficient Funds",
                f"You only have **{balance['wallet']:,} coins** in your wallet!"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Play the game
        if game.value == "slots":
            await self.play_slots(interaction, amount)
        elif game.value == "coinflip":
            await self.play_coinflip(interaction, amount)
        elif game.value == "blackjack":
            await self.play_blackjack(interaction, amount)
    
    async def play_slots(self, interaction: discord.Interaction, amount: int):
        """Play slots game"""
        user_id = interaction.user.id
        guild_id = interaction.guild.id
        
        # Deduct amount first
        self.update_balance(user_id, guild_id, -amount)
        
        # Slot symbols
        symbols = ["🍒", "🍋", "🍊", "🍇", "⭐", "💎", "🔔", "🍀"]
        weights = [20, 18, 16, 14, 12, 8, 6, 6]  # Higher numbers = more common
        
        # Spin the slots
        result = random.choices(symbols, weights=weights, k=3)
        
        # Calculate winnings
        winnings = 0
        multiplier = 0
        
        if result[0] == result[1] == result[2]:  # Three of a kind
            if result[0] == "💎":
                multiplier = 10
            elif result[0] == "⭐":
                multiplier = 8
            elif result[0] == "🔔":
                multiplier = 6
            elif result[0] == "🍀":
                multiplier = 5
            else:
                multiplier = 3
            winnings = amount * multiplier
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:  # Two of a kind
            multiplier = 1.5
            winnings = int(amount * multiplier)
        
        # Apply winnings
        if winnings > 0:
            self.update_balance(user_id, guild_id, winnings)
        
        # Create result embed
        embed = create_embed(
            title="🎰 Slot Machine",
            description=f"**{' | '.join(result)}**\n\n{'🎉 **WINNER!**' if winnings > 0 else '💸 **Better luck next time!**'}",
            color=COLORS['success'] if winnings > 0 else COLORS['error']
        )
        
        embed.add_field(
            name="💰 Results",
            value=f"Bet: **{amount:,}** coins\n{'Winnings: **' + str(winnings) + '** coins' if winnings > 0 else 'Lost: **' + str(amount) + '** coins'}\n{'Multiplier: **x' + str(multiplier) + '**' if multiplier > 0 else ''}",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    async def play_coinflip(self, interaction: discord.Interaction, amount: int):
        """Play coinflip game"""
        view = CoinflipView(interaction.user.id, amount, self)
        
        embed = create_embed(
            title="🪙 Coinflip",
            description=f"**Gambling {amount:,} coins**\n\nChoose heads or tails!",
            color=COLORS['warning']
        )
        
        embed.add_field(
            name="🎯 Rules",
            value="Win = **Double your bet**\nLose = **Lose your bet**",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, view=view)
    
    async def play_blackjack(self, interaction: discord.Interaction, amount: int):
        """Play blackjack game"""
        # Deduct amount first
        self.update_balance(interaction.user.id, interaction.guild.id, -amount)
        
        view = BlackjackView(interaction.user.id, amount, self)
        await view.start_game(interaction)
    
    @discord.app_commands.command(name="shop", description="🛒 Browse the server shop")
    async def shop(self, interaction: discord.Interaction):
        """Show server shop"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT name, description, price, type, stock 
                FROM shop_items WHERE guild_id = ? AND active = 1
                ORDER BY price ASC
            ''', (interaction.guild.id,))
            items = cursor.fetchall()
            conn.close()
            
            if not items:
                embed = create_embed(
                    title="🛒 Server Shop",
                    description="**The shop is currently empty**\n\nAdmins can add items using `/shop_admin add`",
                    color=COLORS['warning']
                )
            else:
                embed = create_embed(
                    title="🛒 Server Shop",
                    description="**Available items for purchase**",
                    color=COLORS['gold']
                )
                
                for i, (name, desc, price, item_type, stock) in enumerate(items[:10]):  # Show first 10
                    stock_text = f"Stock: {stock}" if stock > 0 else "Unlimited" if stock == -1 else "Out of Stock"
                    embed.add_field(
                        name=f"{i+1}. {name}",
                        value=f"{desc or 'No description'}\n**Price:** {price:,} coins\n**Type:** {item_type.title()}\n**{stock_text}**",
                        inline=True
                    )
            
            embed.set_footer(text="Use /buy <item_name> to purchase items")
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            embed = create_error_embed("Shop Error", f"Could not load shop: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)

class CoinflipView(discord.ui.View):
    """Interactive coinflip game"""
    
    def __init__(self, user_id: int, amount: int, economy_system):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.amount = amount
        self.economy = economy_system
    
    @discord.ui.button(label="Heads", style=discord.ButtonStyle.primary, emoji="🔵")
    async def heads(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your game!", ephemeral=True)
            return
        await self.flip_coin(interaction, "heads")
    
    @discord.ui.button(label="Tails", style=discord.ButtonStyle.secondary, emoji="🔴")
    async def tails(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your game!", ephemeral=True)
            return
        await self.flip_coin(interaction, "tails")
    
    async def flip_coin(self, interaction: discord.Interaction, choice: str):
        """Execute coinflip"""
        # Deduct amount
        self.economy.update_balance(self.user_id, interaction.guild.id, -self.amount)
        
        # Flip coin
        result = random.choice(["heads", "tails"])
        won = choice == result
        
        # Calculate winnings
        winnings = self.amount * 2 if won else 0
        if winnings > 0:
            self.economy.update_balance(self.user_id, interaction.guild.id, winnings)
        
        # Create result embed
        embed = create_embed(
            title="🪙 Coinflip Result",
            description=f"**You chose:** {choice.title()}\n**Result:** {result.title()}\n\n{'🎉 **YOU WON!**' if won else '💸 **You lost!**'}",
            color=COLORS['success'] if won else COLORS['error']
        )
        
        embed.add_field(
            name="💰 Results",
            value=f"Bet: **{self.amount:,}** coins\n{'Won: **' + str(winnings) + '** coins' if won else 'Lost: **' + str(self.amount) + '** coins'}",
            inline=False
        )
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)

class BlackjackView(discord.ui.View):
    """Interactive blackjack game"""
    
    def __init__(self, user_id: int, amount: int, economy_system):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.amount = amount
        self.economy = economy_system
        self.deck = self.create_deck()
        self.player_hand = []
        self.dealer_hand = []
        self.game_over = False
    
    def create_deck(self):
        """Create a shuffled deck"""
        suits = ["♠️", "♥️", "♦️", "♣️"]
        ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        deck = [f"{rank}{suit}" for suit in suits for rank in ranks]
        random.shuffle(deck)
        return deck
    
    def card_value(self, card):
        """Get card value for blackjack"""
        rank = card[:-2] if len(card) > 2 else card[:-1]
        if rank in ["J", "Q", "K"]:
            return 10
        elif rank == "A":
            return 11
        else:
            return int(rank)
    
    def hand_value(self, hand):
        """Calculate hand value with ace handling"""
        value = sum(self.card_value(card) for card in hand)
        aces = sum(1 for card in hand if card[:-1].startswith("A") or card[:-2].startswith("A"))
        
        while value > 21 and aces > 0:
            value -= 10
            aces -= 1
        
        return value
    
    def hand_display(self, hand, hide_first=False):
        """Display hand as string"""
        if hide_first:
            return f"🎴 {' '.join(hand[1:])}"
        return f"{' '.join(hand)}"
    
    async def start_game(self, interaction: discord.Interaction):
        """Start blackjack game"""
        # Deal initial cards
        self.player_hand = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]
        
        await self.update_game_display(interaction)
    
    async def update_game_display(self, interaction: discord.Interaction, final=False):
        """Update game display"""
        player_value = self.hand_value(self.player_hand)
        dealer_value = self.hand_value(self.dealer_hand)
        
        embed = create_embed(
            title="🃏 Blackjack",
            description=f"**Gambling {self.amount:,} coins**",
            color=COLORS['info']
        )
        
        embed.add_field(
            name="🎴 Your Hand",
            value=f"{self.hand_display(self.player_hand)}\n**Value:** {player_value}",
            inline=True
        )
        
        embed.add_field(
            name="🎭 Dealer's Hand",
            value=f"{self.hand_display(self.dealer_hand, not final)}\n**Value:** {'?' if not final else dealer_value}",
            inline=True
        )
        
        if final:
            # Determine winner
            player_bust = player_value > 21
            dealer_bust = dealer_value > 21
            
            if player_bust:
                result = "💸 **You busted! Dealer wins.**"
                winnings = 0
            elif dealer_bust:
                result = "🎉 **Dealer busted! You win!**"
                winnings = self.amount * 2
            elif player_value > dealer_value:
                result = "🎉 **You win!**"
                winnings = self.amount * 2
            elif dealer_value > player_value:
                result = "💸 **Dealer wins!**"
                winnings = 0
            else:
                result = "🤝 **Push! It's a tie.**"
                winnings = self.amount  # Return bet
            
            embed.add_field(
                name="🎯 Result",
                value=f"{result}\n{'Won: **' + str(winnings) + '** coins' if winnings > 0 else 'Lost: **' + str(self.amount) + '** coins' if winnings == 0 else 'Returned: **' + str(winnings) + '** coins'}",
                inline=False
            )
            
            # Apply winnings
            if winnings > 0:
                self.economy.update_balance(self.user_id, interaction.guild.id, winnings)
            
            # Disable buttons
            for item in self.children:
                item.disabled = True
        
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, view=self)
        else:
            await interaction.edit_original_response(embed=embed, view=self)
    
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.success, emoji="➕")
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your game!", ephemeral=True)
            return
        
        if self.game_over:
            return
        
        # Deal card to player
        self.player_hand.append(self.deck.pop())
        player_value = self.hand_value(self.player_hand)
        
        if player_value > 21:
            # Player busted
            self.game_over = True
            await self.update_game_display(interaction, final=True)
        else:
            await self.update_game_display(interaction)
    
    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, emoji="✋")
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your game!", ephemeral=True)
            return
        
        if self.game_over:
            return
        
        # Dealer plays
        while self.hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())
        
        self.game_over = True
        await self.update_game_display(interaction, final=True)

async def setup(bot):
    await bot.add_cog(EconomySystem(bot))