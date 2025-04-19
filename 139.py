#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
骰子游戏 Telegram Bot
一个基于Telegram平台的骰子游戏机器人
用户可以在各种骰子组合上下注，支持多种投注类型和组合
支持个人和群组游戏模式，群组模式支持连续游戏
"""

import os
import sys
import json
import time
import random
import logging
import requests
import threading
import datetime
import io
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from matplotlib.font_manager import FontProperties
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, Any, List, Tuple, Union, Optional, Set

# 设置matplotlib字体，避免中文乱码
matplotlib.use('Agg')  # 非交互式后端
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False  # 正确显示负号

# 配置日志记录
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 从环境变量获取Bot token
TOKEN = os.environ.get("BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{TOKEN}"

# 定义持久化数据文件
DATA_FILE = "data/user_data.json"

# 反水比例 (0.5%)
REBATE_RATE = 0.005

# 字体文件路径
FONT_PATH = "fonts/simhei.ttf"

# 定义管理员用户ID
ADMIN_IDS = [7089737552, 5323275063]

# 会话状态定义 (用于追踪用户的会话状态)
USER_STATES = {}

# 定义状态常量
STATE_IDLE = "IDLE"
STATE_SELECTING_BET_TYPE = "SELECTING_BET_TYPE"
STATE_SELECTING_BET_VALUE = "SELECTING_BET_VALUE"
STATE_ENTERING_BET_AMOUNT = "ENTERING_BET_AMOUNT"
STATE_CONFIRMING_BET = "CONFIRMING_BET"

# 群组游戏状态
GROUP_GAME_IDLE = "IDLE"
GROUP_GAME_BETTING = "BETTING"
GROUP_GAME_PAUSED = "PAUSED"
GROUP_GAME_SELECTING_ROLLER = "SELECTING_ROLLER"  # 选择高额投注玩家摇骰子
GROUP_GAME_ROLLING = "ROLLING"

# 群组游戏等待时间（秒）
GROUP_GAME_WAIT_TIME = 30

# 高额投注阈值（达到此金额可以摇骰子）
HIGH_ROLLER_THRESHOLD = 1000

# 管理员ID列表已在上方定义

# 被封禁的用户
BANNED_USERS = set()

# ============== 常量定义 ==============

# 定义投注类型
BET_TYPES = {
    "big": "大",
    "small": "小",
    "sum": "总和",
    "triple": "豹子",
    "double": "对子",
    "single": "单号",
    "odd": "单",
    "even": "双",
    "color": "颜色",
    "big_odd": "大单",
    "big_even": "大双",
    "small_odd": "小单",
    "small_even": "小双"
}

# 颜色映射
COLORS = {
    1: "红", 2: "红", 3: "蓝",
    4: "蓝", 5: "绿", 6: "绿"
}

# 赔率定义
PAYOUT_RATIOS = {
    "big": 1,  # 大 1:1
    "small": 1,  # 小 1:1
    "odd": 1,   # 单 1:1
    "even": 1,   # 双 1:1
    "big_odd": 2,  # 大单 2:1
    "big_even": 2,  # 大双 2:1
    "small_odd": 2,  # 小单 2:1
    "small_even": 2,  # 小双 2:1
    "sum": {
        3: 150, 18: 150,      # 特定总和
        4: 50, 17: 50,
        5: 25, 16: 25,
        6: 15, 15: 15,
        7: 10, 14: 10,
        8: 8, 13: 8,
        9: 6, 10: 6, 11: 6, 12: 6
    },
    "triple": {
        "any": 25,          # 任意豹子
        "specific": 150     # 特定豹子
    },
    "double": {
        "any": 2,           # 任意对子
        "specific": 30      # 特定对子
    },
    "single": 1,  # 单号 1:1
    "color": {
        1: 1,  # 一个颜色 1:1
        2: 2,  # 两个颜色 2:1
        3: 4   # 三个颜色 4:1
    }
}

# 欢迎消息
WELCOME_MESSAGE = """
🌟 *欢迎来到天尊快三游戏* 🌟

这是一个刺激好玩的骰子游戏，您可以在多种组合上下注！

🎮 *基本命令*:
• /play - 开始新游戏
• /rules - 查看游戏规则
• /balance - 查看您的余额
• /history - 查看您的游戏历史
• /leaderboard - 查看排行榜
• /help - 显示帮助信息

💰 *上分说明*:
请联系@tianzun1进行上分

您的用户ID: {user_id}
当前余额: {balance} 金币
"""

# 帮助文本
HELP_TEXT = """
🎲 *骰子游戏命令* 🎲

*基本命令*:
• /start - 开始使用机器人并创建新账户
• /play - 开始新一轮游戏
• /rules - 查看游戏规则
• /balance - 查看当前余额
• /vip - 查看您的VIP特权
• /addcoins [金额] - 向余额添加金币（仅限管理员）
• /help - 显示此帮助信息

*高级功能*:
• /history - 查看您的游戏历史
• /stats - 查看您的游戏统计数据
• /leaderboard - 查看排行榜

您的用户ID: {user_id}
当前余额: {balance} 金币

享受游戏，祝您好运！🍀
"""

# 游戏规则说明
GAME_RULES = """
🎲 *骰子游戏规则* 🎲

游戏使用3个骰子，每个骰子上有1-6的数字。您可以在各种结果上下注：

*投注类型和赔率*:

🔹 *大（11-18）*
   - 如果总和为11-18（不包括豹子），则赢
   - 赔率：1:1

🔹 *小（3-10）*
   - 如果总和为3-10（不包括豹子），则赢
   - 赔率：1:1

🔹 *单/双*
   - 单: 总和为单数则赢
   - 双: 总和为双数则赢
   - 赔率：1:1

🔹 *大单/大双/小单/小双*
   - 大单: 总和为11-17的奇数则赢
   - 大双: 总和为12-18的偶数则赢
   - 小单: 总和为3-9的奇数则赢
   - 小双: 总和为4-10的偶数则赢
   - 赔率：2:1

🔹 *特定总和（3-18）*
   - 如果总和等于您选择的数字，则赢
   - 赔率不同：
     • 总和3或18：150:1
     • 总和4或17：50:1
     • 总和5或16：25:1
     • 总和6或15：15:1
     • 总和7或14：10:1
     • 总和8或13：8:1
     • 总和9-12：6:1

🔹 *豹子（三同号）*
   - 任意豹子：如果三个骰子显示相同数字，则赢
     • 赔率：25:1
   - 特定豹子：如果三个骰子显示您选择的数字，则赢
     • 赔率：150:1

🔹 *对子（二同号）*
   - 任意对子：如果至少两个骰子显示相同数字，则赢
     • 赔率：2:1
   - 特定对子：如果至少两个骰子显示您选择的数字，则赢
     • 赔率：30:1

🔹 *单号*
   - 如果您选择的数字出现在任何骰子上，则赢
   - 赔率：每次出现1:1

🔹 *颜色*
   - 如果您选择的颜色在结果中出现，则赢
   - 红色: 骰子点数为1,2
   - 蓝色: 骰子点数为3,4
   - 绿色: 骰子点数为5,6
   - 赔率：根据出现次数而定

注意：当出现任何豹子时，大和小投注都会输。

您的用户ID: {user_id}
当前余额: {balance} 金币

祝您好运！🍀
"""

# VIP说明
VIP_INFO = """
👑 *VIP特权系统* 👑

通过投注和赢取金币，您可以提升自己的VIP等级，享受更多特权！

*用户ID*: {user_id}
*当前VIP等级*: {vip_level} ({vip_name})
*升级进度*: {progress}%
*总投注额*: {total_bets} 金币
*当前余额*: {balance} 金币
*下一级所需*: {next_requirement} 金币

*您的特权*:
{privileges}

*下一级特权*:
{next_privileges}

🔼 继续投注以提升您的VIP等级！
"""

# VIP等级定义
VIP_LEVELS = {
    0: {
        "name": "玩家",
        "requirement": 0,
        "privileges": ["基础投注选项"]
    },
    1: {
        "name": "铜牌会员",
        "requirement": 10000,
        "privileges": ["基础投注选项", "每日领取10金币"]
    },
    2: {
        "name": "银牌会员",
        "requirement": 50000,
        "privileges": ["基础投注选项", "每日领取50金币", "专属客服"]
    },
    3: {
        "name": "金牌会员",
        "requirement": 200000,
        "privileges": ["基础投注选项", "每日领取200金币", "专属客服", "特殊投注类型"]
    },
    4: {
        "name": "钻石会员",
        "requirement": 1000000,
        "privileges": ["基础投注选项", "每日领取500金币", "专属客服", "特殊投注类型", "赔率提升5%"]
    }
}

# 群组游戏开始消息
GROUP_GAME_START_MESSAGE = """
🎲 *骰子游戏开始* 🎲

游戏将在 {wait_time} 秒后结束，请立即下注！
投注 1000 金币以上可获得摇骰子特权！

下注格式：
- 大[金额] (例如: 大100)
- 小[金额] (例如: 小50)
- 单[金额] (例如: 单200)
- 双[金额] (例如: 双100)
- 大单[金额] (例如: 大单100)
- 大双[金额] (例如: 大双100)
- 小单[金额] (例如: 小单100)
- 小双[金额] (例如: 小双100)
- 对子[金额] (例如: 对子50)
- 豹子[金额] (例如: 豹子20)

祝大家好运！🍀
"""

# 群组游戏倒计时消息
GROUP_GAME_COUNTDOWN_MESSAGE = """
⏱ *倒计时 {remaining} 秒*

请抓紧时间下注！
"""

# 群组游戏结束消息
GROUP_GAME_END_MESSAGE = """
🎮 *游戏结果揭晓* 🎮

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  骰子1: *{dice1}*  骰子2: *{dice2}*  骰子3: *{dice3}*  ┃
┃                                 ┃
┃       🔢 总点数: *{total}*        ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

{result_desc}

🏆 *获奖情况* 🏆
{winners}

⏱ 下一轮游戏将在 5 秒后自动开始
💡 发送"ye"可查询余额
"""

# 个人游戏结果消息
GAME_RESULT_MESSAGE = """
🎲 *游戏结果* 🎲

骰子: 🎲 {dice1} 🎲 {dice2} 🎲 {dice3}
总和: {total}

您的投注: {bet_desc}
{result}

{balance_change}
当前余额: {balance} 金币

您的用户ID: {user_id}

要再玩一局吗？
"""

# 余额不足消息
INSUFFICIENT_BALANCE_MESSAGE = """
❌ *余额不足* ❌

您的当前余额为 {balance} 金币，无法下注 {amount} 金币。

请联系管理员充值。

用户ID: {user_id}
"""

# 投注确认消息
BET_CONFIRMATION_MESSAGE = """
✅ *投注确认* ✅

投注类型: {bet_type}
投注值: {bet_value}
投注金额: {bet_amount} 金币

您的用户ID: {user_id}
确认后余额: {new_balance} 金币

确认投注吗？
"""

# ============== 数据管理 ==============

class DataManager:
    """管理用户数据和游戏记录"""

    def __init__(self, data_file=DATA_FILE):
        self.data_file = data_file
        self.lock = threading.RLock()
        # 加载数据或创建新数据文件
        self.load_data()

        # 群组游戏状态
        self.group_games = {}
        
        # 反水记录
        self.rebate_records = {}
        
        # 红包信息存储
        self.hongbao = {}
        
        # 每个群组的预设骰子点数 {chat_id: [dice1, dice2, dice3], ...}
        self.group_fixed_dice = {}

        # 启动自动保存线程
        self.auto_save_thread = threading.Thread(target=self._auto_save, daemon=True)
        self.auto_save_thread.start()

    def load_data(self):
        """从文件加载数据"""
        with self.lock:
            # 确保 data 目录存在
            directory = os.path.dirname(self.data_file)
            if directory:
                os.makedirs(directory, exist_ok=True)

            # 如果文件不存在，创建默认结构
            if not os.path.exists(self.data_file):
                default_data = {
                    'users': {},
                    'game_history': [],
                    'chat_messages': [],
                    'global_stats': {
                        'total_games': 0,
                        'total_bets': 0,
                        'total_winnings': 0,
                        'biggest_win': {'user_id': None, 'amount': 0, 'date': None}
                    }
                }
                with open(self.data_file, 'w', encoding='utf-8') as f:
                    json.dump(default_data, f, ensure_ascii=False, indent=2)

            try:
                if os.path.exists(self.data_file):
                    with open(self.data_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.users = data.get('users', {})
                        self.game_history = data.get('game_history', [])
                        self.chat_messages = data.get('chat_messages', [])
                        self.global_stats = data.get('global_stats', {
                            'total_games': 0,
                            'total_bets': 0,
                            'total_winnings': 0,
                            'biggest_win': {'user_id': None, 'amount': 0, 'date': None}
                        })
                else:
                    self.users = {}
                    self.game_history = []
                    self.chat_messages = []
                    self.global_stats = {
                        'total_games': 0,
                        'total_bets': 0,
                        'total_winnings': 0,
                        'biggest_win': {'user_id': None, 'amount': 0, 'date': None}
                    }
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"加载数据错误: {e}")
                self.users = {}
                self.game_history = []
                self.chat_messages = []
                self.global_stats = {
                    'total_games': 0,
                    'total_bets': 0,
                    'total_winnings': 0,
                    'biggest_win': {'user_id': None, 'amount': 0, 'date': None}
                }

    def save_data(self):
        """保存数据到文件"""
        with self.lock:
            try:
                data = {
                    'users': self.users,
                    'game_history': self.game_history,
                    'chat_messages': self.chat_messages,
                    'global_stats': self.global_stats
                }
                with open(self.data_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info("数据已保存")
            except IOError as e:
                logger.error(f"保存数据错误: {e}")

    def _auto_save(self):
        """自动定期保存数据"""
        while True:
            time.sleep(300)  # 每5分钟保存一次
            self.save_data()

    def add_user(self, user_id: int, name: str) -> None:
        """添加新用户或更新用户名"""
        user_id_str = str(user_id)
        with self.lock:
            if user_id_str not in self.users:
                # 检查是否为管理员ID
                initial_balance = 10000 if user_id in ADMIN_IDS else 0

                self.users[user_id_str] = {
                    'name': name,
                    'balance': initial_balance,
                    'total_bets': 0,
                    'total_winnings': 0,
                    'games_played': 0,
                    'joined_date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'last_activity': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'vip_level': 0,
                    'daily_bonus_claimed': None,
                    'history': []
                }
                self.save_data()
            else:
                # 更新用户名和最后活动时间
                self.users[user_id_str]['name'] = name
                self.users[user_id_str]['last_activity'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def get_user(self, user_id: int) -> Dict[str, Any]:
        """获取用户数据，如果用户不存在返回None"""
        user_id_str = str(user_id)
        with self.lock:
            return self.users.get(user_id_str)

    def update_balance(self, user_id: int, amount: int) -> Tuple[int, bool]:
        """
        更新用户余额
        返回：(新余额, 成功标志)
        """
        user_id_str = str(user_id)
        with self.lock:
            if user_id_str not in self.users:
                return 0, False
            
            new_balance = self.users[user_id_str]['balance'] + amount
            if new_balance < 0:
                return self.users[user_id_str]['balance'], False
            
            self.users[user_id_str]['balance'] = new_balance
            
            # 如果是正数增加，记录为总赢钱；负数减少，记录为总投注
            if amount > 0:
                self.users[user_id_str]['total_winnings'] += amount
            else:
                self.users[user_id_str]['total_bets'] += abs(amount)
            
            # 检查是否需要更新VIP等级
            self._update_vip_level(user_id_str)
            
            return new_balance, True

    def _update_vip_level(self, user_id_str: str) -> None:
        """根据总投注额更新用户VIP等级"""
        total_bets = self.users[user_id_str]['total_bets']
        current_level = self.users[user_id_str]['vip_level']
        
        # 检查是否可以升级
        for level in sorted(VIP_LEVELS.keys(), reverse=True):
            if level > current_level and total_bets >= VIP_LEVELS[level]['requirement']:
                self.users[user_id_str]['vip_level'] = level
                break

    def add_game_record(self, user_id: int, game_type: str, bet_type: str, 
                       bet_value: Any, bet_amount: int, result: List[int], 
                       won: bool, winnings: int, is_group_game: bool = False, 
                       group_id: Optional[int] = None) -> None:
        """添加游戏记录"""
        user_id_str = str(user_id)
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 为群组游戏分配编号，确保真实走势
        group_game_number = None
        if is_group_game and group_id is not None:
            group_id_str = str(group_id)
            
            # 查找这个群组已有多少局游戏
            group_games_count = len([
                game for game in self.game_history 
                if game.get('is_group_game', False) and 
                   game.get('group_id', '') == group_id_str
            ])
            
            # 当前局编号 = 已有局数 + 1
            group_game_number = group_games_count + 1
        
        game_record = {
            'timestamp': timestamp,
            'game_type': game_type,
            'bet_type': bet_type,
            'bet_value': bet_value,
            'bet_amount': bet_amount,
            'result': result,
            'won': won,
            'winnings': winnings,
            'is_group_game': is_group_game,
            'group_game_number': group_game_number  # 添加群组游戏编号
        }
        
        if group_id:
            game_record['group_id'] = group_id
        
        with self.lock:
            # 添加到用户历史
            if user_id_str in self.users:
                self.users[user_id_str]['games_played'] += 1
                self.users[user_id_str]['history'].append(game_record)
                # 仅保留最近50条记录
                if len(self.users[user_id_str]['history']) > 50:
                    self.users[user_id_str]['history'] = self.users[user_id_str]['history'][-50:]
            
            # 添加到全局历史
            self.game_history.append({
                'user_id': user_id_str,
                'user_name': self.users[user_id_str]['name'] if user_id_str in self.users else "未知用户",
                **game_record
            })
            
            # 仅保留最近1000条全局记录
            if len(self.game_history) > 1000:
                self.game_history = self.game_history[-1000:]
            
            # 更新全局统计
            self.global_stats['total_games'] += 1
            self.global_stats['total_bets'] += bet_amount
            
            if won:
                self.global_stats['total_winnings'] += winnings
                # 检查是否是最大赢钱记录
                if winnings > self.global_stats['biggest_win']['amount']:
                    self.global_stats['biggest_win'] = {
                        'user_id': user_id_str,
                        'amount': winnings,
                        'date': timestamp
                    }

    def get_user_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """获取用户的游戏历史"""
        user_id_str = str(user_id)
        with self.lock:
            if user_id_str not in self.users:
                return []
            
            history = self.users[user_id_str]['history']
            # 返回最近的n条记录
            return history[-limit:][::-1]  # 倒序返回

    def get_leaderboard(self, metric: str = 'balance', limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取排行榜
        metric：'balance', 'total_winnings', 'games_played'
        """
        with self.lock:
            # 根据指定指标排序用户
            sorted_users = sorted(
                [{'user_id': k, **v} for k, v in self.users.items()],
                key=lambda x: x[metric],
                reverse=True
            )
            
            # 返回前n名
            return sorted_users[:limit]

    def get_group_game(self, chat_id: int) -> Dict[str, Any]:
        """获取群组游戏状态，如果不存在则创建"""
        chat_id_str = str(chat_id)
        with self.lock:
            if chat_id_str not in self.group_games:
                self.group_games[chat_id_str] = {
                    'state': GROUP_GAME_IDLE,
                    'bets': {},  # 格式: {user_id: [{bet_type, bet_value, amount}]}
                    'last_result': None,
                    'start_time': None,
                    'message_id': None
                }
            return self.group_games[chat_id_str]

    def update_group_game(self, chat_id: int, data: Dict[str, Any]) -> None:
        """更新群组游戏状态"""
        chat_id_str = str(chat_id)
        with self.lock:
            self.group_games[chat_id_str] = data

    def add_bet_to_group_game(self, chat_id: int, user_id: int, 
                             bet_type: str, bet_value: Any, amount: int) -> bool:
        """
        向群组游戏添加投注
        返回：是否成功
        """
        chat_id_str = str(chat_id)
        user_id_str = str(user_id)
        
        with self.lock:
            if chat_id_str not in self.group_games:
                return False
            
            if self.group_games[chat_id_str]['state'] != GROUP_GAME_BETTING:
                return False
            
            # 检查用户余额
            if user_id_str not in self.users:
                return False
            
            if self.users[user_id_str]['balance'] < amount:
                return False
            
            # 更新用户余额
            self.users[user_id_str]['balance'] -= amount
            self.users[user_id_str]['total_bets'] += amount
            
            # 添加投注
            if user_id_str not in self.group_games[chat_id_str]['bets']:
                self.group_games[chat_id_str]['bets'][user_id_str] = []
            
            self.group_games[chat_id_str]['bets'][user_id_str].append({
                'bet_type': bet_type,
                'bet_value': bet_value,
                'amount': amount
            })
            
            return True

    def reset_group_game(self, chat_id: int) -> None:
        """重置群组游戏状态"""
        chat_id_str = str(chat_id)
        with self.lock:
            if chat_id_str in self.group_games:
                self.group_games[chat_id_str] = {
                    'state': GROUP_GAME_IDLE,
                    'bets': {},
                    'last_result': None,
                    'start_time': None,
                    'message_id': None
                }
    
    def set_fixed_dice(self, chat_id: int, dice_values: List[int]) -> bool:
        """设置特定群组的固定骰子点数"""
        with self.lock:
            # 验证骰子点数是否有效
            if len(dice_values) != 3 or not all(1 <= d <= 6 for d in dice_values):
                return False
            
            self.group_fixed_dice[str(chat_id)] = dice_values
            return True
            
    def get_fixed_dice(self, chat_id: int) -> Optional[List[int]]:
        """获取特定群组的固定骰子点数"""
        with self.lock:
            return self.group_fixed_dice.get(str(chat_id))
            
    def clear_fixed_dice(self, chat_id: int) -> None:
        """清除特定群组的固定骰子点数"""
        with self.lock:
            if str(chat_id) in self.group_fixed_dice:
                del self.group_fixed_dice[str(chat_id)]
                
    def get_group_history(self, chat_id: int, limit: int = 30) -> List[Dict[str, Any]]:
        """获取指定群组的游戏历史"""
        chat_id_str = str(chat_id)
        with self.lock:
            # 筛选指定群组的游戏记录
            group_games = [game for game in self.game_history 
                           if game.get('is_group_game') and str(game.get('group_id')) == chat_id_str]
            
            # 按游戏编号排序，如果没有编号则使用时间戳，确保都是数字类型
            def sort_key(x):
                # 获取游戏编号，确保是整数
                game_num = x.get('group_game_number')
                if game_num is not None:
                    try:
                        return int(game_num)
                    except (ValueError, TypeError):
                        pass
                # 如果无法获取编号，返回0（排在最前面）
                return 0
            
            # 按游戏编号倒序排列
            group_games.sort(key=sort_key, reverse=True)
            
            return group_games[:limit]

    def is_banned(self, user_id: int) -> bool:
        """检查用户是否被封禁"""
        return user_id in BANNED_USERS

    def ban_user(self, user_id: int) -> None:
        """封禁用户"""
        BANNED_USERS.add(user_id)

    def unban_user(self, user_id: int) -> bool:
        """解除用户封禁，返回是否成功"""
        if user_id in BANNED_USERS:
            BANNED_USERS.remove(user_id)
            return True
        return False
        
    def calculate_rebate(self, user_id: int) -> int:
        """
        计算用户的反水金额
        每投注100金币，可以获得1金币的反水
        返回：应返还的金币数量
        """
        user_id_str = str(user_id)
        with self.lock:
            if user_id_str not in self.users:
                return 0
                
            # 检查用户是否已经领取过反水
            if user_id in self.rebate_records:
                last_claimed = self.rebate_records[user_id]["last_claimed"]
                last_total_bets = self.rebate_records[user_id]["total_bets"]
                
                # 获取当前投注总额
                current_total_bets = self.users[user_id_str]["total_bets"]
                
                # 计算自上次领取后新增的投注额
                new_bets = current_total_bets - last_total_bets
                
                # 每100金币返1金币
                rebate_amount = new_bets // 100
                
                return rebate_amount
            else:
                # 第一次领取，按总投注额计算
                total_bets = self.users[user_id_str]["total_bets"]
                rebate_amount = total_bets // 100
                
                return rebate_amount
                
    def claim_rebate(self, user_id: int) -> Tuple[int, bool]:
        """
        用户领取反水
        返回：(反水金额, 是否成功)
        """
        rebate_amount = self.calculate_rebate(user_id)
        
        if rebate_amount <= 0:
            return 0, False
            
        # 更新用户余额
        new_balance, success = self.update_balance(user_id, rebate_amount)
        
        if success:
            # 记录此次反水
            user_id_str = str(user_id)
            self.rebate_records[user_id] = {
                "last_claimed": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_bets": self.users[user_id_str]["total_bets"],
                "amount": rebate_amount
            }
            
        return rebate_amount, success

# ============== 游戏逻辑 ==============

class DiceGame:
    """骰子游戏逻辑"""
    
    @staticmethod
    def roll_dice(num_dice: int = 3, fixed_dice: List[int] = None) -> List[int]:
        """
        掷骰子，返回结果列表
        
        参数:
            num_dice: 骰子数量
            fixed_dice: 固定的骰子点数，如果提供，则返回这个点数
        """
        if fixed_dice and len(fixed_dice) == num_dice:
            dice_results = fixed_dice
            logger.info(f"使用固定骰子点数: {dice_results}")
        else:
            dice_results = [random.randint(1, 6) for _ in range(num_dice)]
            logger.info(f"随机骰子结果: {dice_results}")
        
        return dice_results
    
    @staticmethod
    def calculate_result(dice_result: List[int]) -> Dict[str, Any]:
        """计算骰子结果的各个指标"""
        # 确保列表长度为3
        if len(dice_result) != 3:
            raise ValueError("必须提供3个骰子结果")
        
        # 计算总和
        total = sum(dice_result)
        
        # 判断大小
        is_big = 11 <= total <= 18
        is_small = 3 <= total <= 10
        
        # 判断单双
        is_odd = total % 2 == 1
        is_even = total % 2 == 0
        
        # 判断大单、大双、小单、小双
        is_big_odd = is_big and is_odd
        is_big_even = is_big and is_even
        is_small_odd = is_small and is_odd
        is_small_even = is_small and is_even
        
        # 判断豹子（三个相同）
        is_triple = dice_result[0] == dice_result[1] == dice_result[2]
        triple_value = dice_result[0] if is_triple else None
        
        # 判断对子（至少两个相同）
        pairs = []
        for i in range(1, 7):
            count = dice_result.count(i)
            if count >= 2:
                pairs.append(i)
        is_double = len(pairs) > 0
        
        # 计算每个数字和颜色的出现次数
        counts = {}
        for i in range(1, 7):
            counts[i] = dice_result.count(i)
        
        # 颜色计数
        color_counts = {
            "红": dice_result.count(1) + dice_result.count(2),
            "蓝": dice_result.count(3) + dice_result.count(4),
            "绿": dice_result.count(5) + dice_result.count(6)
        }
        
        # 特别注意：当出现豹子时，大小都视为不中奖
        if is_triple:
            is_big = is_small = False
            is_big_odd = is_big_even = is_small_odd = is_small_even = False
        
        return {
            "dice": dice_result,
            "total": total,
            "is_big": is_big,
            "is_small": is_small,
            "is_odd": is_odd,
            "is_even": is_even,
            "is_big_odd": is_big_odd,
            "is_big_even": is_big_even,
            "is_small_odd": is_small_odd,
            "is_small_even": is_small_even,
            "is_triple": is_triple,
            "triple_value": triple_value,
            "is_double": is_double,
            "pairs": pairs,
            "counts": counts,
            "color_counts": color_counts
        }
    
    @staticmethod
    def evaluate_bet(bet_type: str, bet_value: Any, result: Dict[str, Any]) -> Tuple[bool, int]:
        """
        评估投注是否赢，以及赔率
        返回：(是否赢, 赔率)
        """
        # 处理每种投注类型
        if bet_type == "big":
            return result["is_big"], PAYOUT_RATIOS["big"]
        
        elif bet_type == "small":
            return result["is_small"], PAYOUT_RATIOS["small"]
        
        elif bet_type == "odd":
            return result["is_odd"], PAYOUT_RATIOS["odd"]
        
        elif bet_type == "even":
            return result["is_even"], PAYOUT_RATIOS["even"]
        
        elif bet_type == "big_odd":
            return result["is_big_odd"], PAYOUT_RATIOS["big_odd"]
        
        elif bet_type == "big_even":
            return result["is_big_even"], PAYOUT_RATIOS["big_even"]
        
        elif bet_type == "small_odd":
            return result["is_small_odd"], PAYOUT_RATIOS["small_odd"]
        
        elif bet_type == "small_even":
            return result["is_small_even"], PAYOUT_RATIOS["small_even"]
        
        elif bet_type == "sum":
            # 特定总和投注
            total = result["total"]
            if total == bet_value:
                return True, PAYOUT_RATIOS["sum"].get(total, 0)
            return False, 0
        
        elif bet_type == "triple":
            if bet_value == "any":
                # 任意豹子
                return result["is_triple"], PAYOUT_RATIOS["triple"]["any"]
            else:
                # 特定豹子，bet_value应该是1-6的数字
                is_specific_triple = result["is_triple"] and result["triple_value"] == bet_value
                return is_specific_triple, PAYOUT_RATIOS["triple"]["specific"]
        
        elif bet_type == "double":
            if bet_value == "any":
                # 任意对子
                return result["is_double"], PAYOUT_RATIOS["double"]["any"]
            else:
                # 特定对子，bet_value应该是1-6的数字
                is_specific_double = bet_value in result["pairs"]
                return is_specific_double, PAYOUT_RATIOS["double"]["specific"]
        
        elif bet_type == "single":
            # 单号投注，bet_value应该是1-6的数字
            # 出现几次，赔率就乘以几
            count = result["counts"].get(bet_value, 0)
            if count > 0:
                return True, PAYOUT_RATIOS["single"] * count
            return False, 0
        
        elif bet_type == "color":
            # 颜色投注，bet_value应该是"红"、"蓝"或"绿"
            count = result["color_counts"].get(bet_value, 0)
            if count > 0:
                return True, PAYOUT_RATIOS["color"].get(count, 0)
            return False, 0
        
        # 未知投注类型
        return False, 0

# ============== Telegram API 函数 ==============

def send_message(chat_id: int, text: str, parse_mode: str = "Markdown", 
                reply_markup: Dict = None, reply_to_message_id: int = None) -> Dict[str, Any]:
    """发送消息到Telegram"""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    
    try:
        response = requests.post(f"{API_URL}/sendMessage", data=payload)
        result = response.json()
        if not result.get("ok"):
            logger.error(f"发送消息失败: {result}")
        return result
    except Exception as e:
        logger.error(f"发送消息异常: {e}")
        return {}

def edit_message_text(chat_id: int, message_id: int, text: str, 
                     parse_mode: str = "Markdown", reply_markup: Dict = None) -> Dict[str, Any]:
    """编辑已发送的消息"""
    try:
        # Ensure text is not empty and contains actual content
        if not text or text.strip() == "":
            logger.warning("Attempted to edit message with empty text")
            text = "正在加载..." # Provide default text in Chinese
            
        # Remove any null characters or invalid whitespace
        text = text.strip().replace('\x00', '')
        
        # Ensure text is not too long (Telegram limit is 4096 characters)
        if len(text) > 4096:
            text = text[:4093] + "..."
        
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        
        response = requests.post(f"{API_URL}/editMessageText", data=payload)
        result = response.json()
        
        if not result.get("ok"):
            logger.error(f"编辑消息失败: {result}")
            # If message not found, try sending a new message
            if result.get("error_code") == 400:
                logger.info("尝试发送新消息而不是编辑")
                return send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        return result
    except Exception as e:
        logger.error(f"编辑消息异常: {e}")
        # Fallback to sending new message
        try:
            return send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        except:
            return {}

def answer_callback_query(callback_query_id: str, text: str = None, 
                         show_alert: bool = False) -> Dict[str, Any]:
    """回答回调查询"""
    payload = {
        "callback_query_id": callback_query_id
    }
    
    if text:
        payload["text"] = text
    
    if show_alert:
        payload["show_alert"] = "true"
    
    try:
        response = requests.post(f"{API_URL}/answerCallbackQuery", data=payload)
        result = response.json()
        if not result.get("ok"):
            logger.error(f"回答回调查询失败: {result}")
        return result
    except Exception as e:
        logger.error(f"回答回调查询异常: {e}")
        return {}

def send_dice(chat_id: int, emoji: str = "🎲", 
             reply_to_message_id: int = None) -> Dict[str, Any]:
    """发送骰子消息"""
    payload = {
        "chat_id": chat_id,
        "emoji": emoji
    }
    
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    
    try:
        response = requests.post(f"{API_URL}/sendDice", data=payload)
        result = response.json()
        if not result.get("ok"):
            logger.error(f"发送骰子失败: {result}")
        return result
    except Exception as e:
        logger.error(f"发送骰子异常: {e}")
        return {}

def get_updates(offset: int = None, timeout: int = 60) -> List[Dict[str, Any]]:
    """获取消息更新"""
    params = {
        "timeout": timeout
    }
    
    if offset:
        params["offset"] = offset
    
    try:
        response = requests.get(f"{API_URL}/getUpdates", params=params)
        result = response.json()
        if result.get("ok"):
            return result.get("result", [])
        logger.error(f"获取更新错误: {result}")
        return []
    except Exception as e:
        logger.error(f"获取更新错误: {e}")
        return []

def send_photo(chat_id: int, photo_data: bytes, caption: str = None, 
               parse_mode: str = "Markdown") -> Dict[str, Any]:
    """发送图片到Telegram"""
    files = {'photo': ('trend_chart.png', photo_data, 'image/png')}
    
    payload = {
        "chat_id": chat_id
    }
    
    if caption:
        payload["caption"] = caption
        payload["parse_mode"] = parse_mode
    
    try:
        response = requests.post(f"{API_URL}/sendPhoto", data=payload, files=files)
        result = response.json()
        if not result.get("ok"):
            logger.error(f"发送图片失败: {result}")
        return result
    except Exception as e:
        logger.error(f"发送图片异常: {e}")
        return {}

def send_animation(chat_id: int, animation_path: str, caption: str = None, 
                  parse_mode: str = "Markdown", reply_markup: Dict = None) -> Dict[str, Any]:
    """发送动画GIF到Telegram"""
    try:
        with open(animation_path, 'rb') as animation_file:
            files = {'animation': (animation_path, animation_file, 'video/mp4')}
            
            payload = {
                "chat_id": chat_id
            }
            
            if caption:
                payload["caption"] = caption
                payload["parse_mode"] = parse_mode
                
            if reply_markup:
                payload["reply_markup"] = json.dumps(reply_markup)
            
            response = requests.post(f"{API_URL}/sendAnimation", data=payload, files=files)
            result = response.json()
            if not result.get("ok"):
                logger.error(f"发送动画失败: {result}")
            return result
    except Exception as e:
        logger.error(f"发送动画异常: {e}")
        return {}

def generate_trend_chart(history: List[Dict[str, Any]], max_entries: int = 20) -> bytes:
    """生成走势图表并返回图片数据"""
    if not history:
        # 创建空白图片
        img = Image.new('RGB', (600, 300), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((250, 150), "暂无数据", fill=(0, 0, 0))
        
        # 转换为字节流
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        return img_byte_arr.getvalue()
    
    # 只使用最近的记录
    recent_history = history[-max_entries:]
    
    # 准备数据
    game_nums = []  # 局号
    totals = []     # 总点数
    results = []    # 结果代码
    
    # 收集数据
    for i, game in enumerate(recent_history):
        # 计算总和和判断类型
        dice_result = game["result"]
        total = sum(dice_result)
        totals.append(total)
        
        # 局号 - 使用游戏自己的编号，如果有的话
        if "group_game_number" in game and game["group_game_number"] is not None:
            game_nums.append(game["group_game_number"])
        else:
            # 如果没有编号则使用索引
            game_nums.append(i + 1)
        
        # 大小单双判断
        is_triple = len(set(dice_result)) == 1
        is_big = total > 10 and not is_triple
        is_small = total <= 10 or is_triple
        is_odd = total % 2 == 1
        is_even = total % 2 == 0
        
        # 设置结果代码
        if is_triple:
            result = "豹"
        elif is_big and is_odd:
            result = "DD"
        elif is_big and is_even:
            result = "DS"
        elif is_small and is_odd:
            result = "XD"
        elif is_small and is_even:
            result = "XS"
        else:
            result = "--"
            
        results.append(result)
    
    # 创建图表
    plt.figure(figsize=(10, 8))
    plt.rcParams["font.size"] = 12
    
    # 设置背景颜色
    plt.gca().set_facecolor('#f0f0f0')
    
    # 标题
    plt.title('骰子游戏走势图', fontsize=16)
    
    # 创建表格数据
    columns = ['局号', '点数', '结果']
    table_data = []
    for i in range(len(game_nums)):
        table_data.append([game_nums[i], totals[i], results[i]])
    
    # 创建表格
    table = plt.table(
        cellText=table_data,
        colLabels=columns,
        cellLoc='center',
        loc='center',
        bbox=[0.2, 0.1, 0.6, 0.8]  # 调整表格位置和大小
    )
    
    # 设置表格样式
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1, 1.5)  # 调整行高
    
    # 隐藏坐标轴
    plt.axis('off')
    
    # 转换为图片
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', dpi=100, bbox_inches='tight')
    plt.close()
    img_buf.seek(0)
    
    return img_buf.getvalue()

# ============== 命令处理函数 ==============

def handle_start_command(message: Dict[str, Any], data_manager: DataManager) -> None:
    """处理 /start 命令"""
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    user_name = message["from"]["first_name"]
    
    # 添加用户
    data_manager.add_user(user_id, user_name)
    
    # 获取用户数据
    user_data = data_manager.get_user(user_id)
    
    # 发送欢迎消息
    welcome_text = WELCOME_MESSAGE.format(
        user_id=user_id,
        balance=user_data["balance"] if user_data else 0
    )
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🎮 开始游戏", "callback_data": "play"},
                {"text": "📜 游戏规则", "callback_data": "rules"}
            ],
            [
                {"text": "💰 查看余额", "callback_data": "balance"},
                {"text": "📊 历史记录", "callback_data": "history"}
            ],
            [
                {"text": "👑 VIP特权", "callback_data": "vip"},
                {"text": "🏆 排行榜", "callback_data": "leaderboard"}
            ]
        ]
    }
    
    send_message(chat_id, welcome_text, reply_markup=keyboard)

def handle_help_command(message: Dict[str, Any], data_manager: DataManager) -> None:
    """处理 /help 命令"""
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    
    # 获取用户数据
    user_data = data_manager.get_user(user_id)
    
    # 发送帮助消息
    help_text = HELP_TEXT.format(
        user_id=user_id,
        balance=user_data["balance"] if user_data else 0
    )
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🎮 开始游戏", "callback_data": "play"},
                {"text": "📜 游戏规则", "callback_data": "rules"}
            ],
            [
                {"text": "💰 查看余额", "callback_data": "balance"},
                {"text": "📊 历史记录", "callback_data": "history"}
            ]
        ]
    }
    
    send_message(chat_id, help_text, reply_markup=keyboard)

def handle_rules_command(message: Dict[str, Any], data_manager: DataManager) -> None:
    """处理 /rules 命令"""
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    
    # 获取用户数据
    user_data = data_manager.get_user(user_id)
    
    # 发送规则消息
    rules_text = GAME_RULES.format(
        user_id=user_id,
        balance=user_data["balance"] if user_data else 0
    )
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🎮 开始游戏", "callback_data": "play"},
                {"text": "🔙 返回", "callback_data": "back_to_menu"}
            ]
        ]
    }
    
    send_message(chat_id, rules_text, reply_markup=keyboard)

def handle_balance_command(message: Dict[str, Any], data_manager: DataManager) -> None:
    """处理 /balance 命令"""
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    
    # 获取用户数据
    user_data = data_manager.get_user(user_id)
    
    if not user_data:
        send_message(chat_id, "您还没有注册，请先使用 /start 命令创建账户。")
        return
    
    balance_text = f"""
💰 *余额信息* 💰

用户ID: {user_id}
用户名: {user_data['name']}
当前余额: {user_data['balance']} 金币
总投注: {user_data['total_bets']} 金币
总赢取: {user_data['total_winnings']} 金币
游戏次数: {user_data['games_played']} 次
加入时间: {user_data['joined_date']}
VIP等级: {VIP_LEVELS[user_data['vip_level']]['name']}
    """
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🎮 开始游戏", "callback_data": "play"},
                {"text": "🔙 返回", "callback_data": "back_to_menu"}
            ]
        ]
    }
    
    send_message(chat_id, balance_text, reply_markup=keyboard)

def handle_play_command(message: Dict[str, Any], data_manager: DataManager) -> None:
    """处理 /play 命令 - 开始私人游戏"""
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    
    # 检查是否是群聊
    is_group = chat_id < 0
    
    if is_group:
        # 如果是群聊，开始群组游戏
        handle_start_group_game(message, data_manager)
        return
    
    # 私人游戏
    # 获取用户数据
    user_data = data_manager.get_user(user_id)
    
    if not user_data:
        send_message(chat_id, "您还没有注册，请先使用 /start 命令创建账户。")
        return
    
    # 设置用户状态为选择投注类型
    USER_STATES[user_id] = {
        "state": STATE_SELECTING_BET_TYPE,
        "chat_id": chat_id,
        "bet_type": None,
        "bet_value": None,
        "bet_amount": None,
        "message_id": None
    }
    
    # 创建投注类型选择键盘
    bet_type_keyboard = {
        "inline_keyboard": [
            [
                {"text": "大", "callback_data": "bet_type_big"},
                {"text": "小", "callback_data": "bet_type_small"},
                {"text": "单", "callback_data": "bet_type_odd"},
                {"text": "双", "callback_data": "bet_type_even"}
            ],
            [
                {"text": "大单", "callback_data": "bet_type_big_odd"},
                {"text": "大双", "callback_data": "bet_type_big_even"},
                {"text": "小单", "callback_data": "bet_type_small_odd"},
                {"text": "小双", "callback_data": "bet_type_small_even"}
            ],
            [
                {"text": "豹子", "callback_data": "bet_type_triple"},
                {"text": "对子", "callback_data": "bet_type_double"},
                {"text": "单号", "callback_data": "bet_type_single"},
                {"text": "颜色", "callback_data": "bet_type_color"}
            ],
            [
                {"text": "总和", "callback_data": "bet_type_sum"},
                {"text": "取消", "callback_data": "cancel_bet"}
            ]
        ]
    }
    
    message_text = f"""
🎲 *请选择投注类型* 🎲

您的余额: {user_data['balance']} 金币
用户ID: {user_id}

请从下方选择一种投注类型:
    """
    
    result = send_message(chat_id, message_text, reply_markup=bet_type_keyboard)
    
    if result.get("ok"):
        USER_STATES[user_id]["message_id"] = result["result"]["message_id"]

def handle_start_group_game(message: Dict[str, Any], data_manager: DataManager) -> None:
    """开始群组游戏"""
    chat_id = message["chat"]["id"]
    
    # 获取群组游戏状态
    group_game = data_manager.get_group_game(chat_id)
    
    # 如果已经有游戏在进行中，不要重新开始
    if group_game['state'] == GROUP_GAME_BETTING:
        return
    
    # 开始新游戏
    group_game['state'] = GROUP_GAME_BETTING
    group_game['bets'] = {}
    group_game['start_time'] = time.time()
    
    # 发送游戏开始消息
    start_message = GROUP_GAME_START_MESSAGE.format(wait_time=GROUP_GAME_WAIT_TIME)
    result = send_message(chat_id, start_message)
    
    if result.get("ok"):
        group_game['message_id'] = result["result"]["message_id"]
    
    # 更新群组游戏状态
    data_manager.update_group_game(chat_id, group_game)
    
    # 启动倒计时线程
    countdown_thread = threading.Thread(
        target=group_game_countdown,
        args=(chat_id, data_manager),
        daemon=True
    )
    countdown_thread.start()

def group_game_countdown(chat_id: int, data_manager: DataManager) -> None:
    """群组游戏倒计时"""
    group_game = data_manager.get_group_game(chat_id)
    start_time = group_game['start_time']
    message_id = group_game['message_id']
    
    # 倒计时
    for remaining in range(GROUP_GAME_WAIT_TIME - 10, 0, -10):
        # 检查游戏是否被取消
        current_game = data_manager.get_group_game(chat_id)
        if current_game['state'] != GROUP_GAME_BETTING:
            return
        
        # 计算实际剩余时间
        elapsed = time.time() - start_time
        actual_remaining = max(1, int(GROUP_GAME_WAIT_TIME - elapsed))
        
        if actual_remaining <= 0:
            break
        
        # 每10秒更新一次倒计时消息
        if actual_remaining > 10:
            # 获取已下注玩家及投注额
            bets = current_game.get('bets', {})
            player_count = len(bets)
            high_rollers_count = 0
            
            # 计算1000金币以上玩家数量
            for user_id_str, user_bets in bets.items():
                total_bet = sum(bet['amount'] for bet in user_bets)
                if total_bet >= 1000:
                    high_rollers_count += 1
            
            # 更新消息加入高额玩家可摇骰子的提示
            countdown_message = f"""
🎲 *骰子游戏进行中* 🎲

⏳ 倒计时: {actual_remaining} 秒
👥 已下注: {player_count} 人
💰 高额玩家: {high_rollers_count} 人

发送投注消息参与游戏，例如:
大单100 小双50
大100
豹子1 200

📢 投注1000金币以上可获得摇骰子机会！
            """
            
            edit_message_text(chat_id, message_id, countdown_message)
        
        time.sleep(min(10, actual_remaining - 1))
    
    # 最后10秒倒计时
    for remaining in range(10, 0, -1):
        # 检查游戏是否被取消
        current_game = data_manager.get_group_game(chat_id)
        if current_game['state'] != GROUP_GAME_BETTING:
            return
        
        countdown_message = GROUP_GAME_COUNTDOWN_MESSAGE.format(remaining=remaining)
        edit_message_text(chat_id, message_id, countdown_message)
        
        time.sleep(1)
    
    # 游戏结束，查找投注1000以上的玩家
    final_game = data_manager.get_group_game(chat_id)
    bets = final_game.get('bets', {})
    high_rollers = {}  # 存储投注1000以上的玩家
    
    for user_id_str, user_bets in bets.items():
        user_id = int(user_id_str)
        total_bet = sum(bet['amount'] for bet in user_bets)
        if total_bet >= 1000:
            high_rollers[user_id] = total_bet
    
    if high_rollers:
        # 按投注金额排序
        sorted_rollers = sorted(high_rollers.items(), key=lambda x: x[1], reverse=True)
        top_roller_id, top_bet = sorted_rollers[0]
        user_data = data_manager.get_user(top_roller_id)
        
        # 更新游戏状态
        final_game['state'] = GROUP_GAME_SELECTING_ROLLER
        final_game['selected_roller'] = top_roller_id
        final_game['roller_select_time'] = time.time()
        data_manager.update_group_game(chat_id, final_game)
        
        # 发送提示消息
        invite_text = f"""
⏱ *投注时间结束* ⏱

👑 恭喜 {user_data['name']} 成为本局摇骰子玩家！
💰 总投注: {top_bet} 金币

请在20秒内直接发送🎲表情或输入"摇"/"摇骰子"来投掷骰子

⏳ 如不摇骰子，将在20秒后自动开始...
        """
        
        edit_message_text(chat_id, message_id, invite_text)
        
        # 创建计时器，20秒后检查是否需要自动摇骰子
        threading.Timer(20, check_and_roll_dice, args=(chat_id, data_manager)).start()
    else:
        # 没有高额投注者，直接开始摇骰子
        process_group_game_result(chat_id, data_manager)

def check_and_roll_dice(chat_id: int, data_manager: DataManager) -> None:
    """检查是否有人摇骰子，如果没有则自动开始"""
    # 获取群组游戏状态
    group_game = data_manager.get_group_game(chat_id)
    
    # 如果游戏状态不是选择摇骰子玩家状态，则返回
    if group_game['state'] != GROUP_GAME_SELECTING_ROLLER:
        return
    
    # 如果已经有人摇过骰子，则返回
    if group_game.get('dice_rolled', False):
        return
    
    # 20秒时间到，标记为已摇动并更新状态
    group_game['dice_rolled'] = True
    group_game['state'] = GROUP_GAME_ROLLING
    data_manager.update_group_game(chat_id, group_game)
    
    # 发送自动摇骰子消息
    auto_roll_message = """
⏱ *时间到，自动摇骰子* ⏱

骰子将自动进行...
    """
    
    try:
        send_message(chat_id, auto_roll_message)
    except Exception as e:
        logger.error(f"发送自动摇骰子消息失败: {e}")
    
    # 处理游戏结果
    process_group_game_result(chat_id, data_manager)

def process_group_game_result(chat_id: int, data_manager: DataManager) -> None:
    """处理群组游戏结果"""
    # 获取群组游戏状态
    group_game = data_manager.get_group_game(chat_id)
    
    # 将状态设置为正在掷骰子
    group_game['state'] = GROUP_GAME_ROLLING
    data_manager.update_group_game(chat_id, group_game)
    
    # 发送正在摇骰子的消息
    bet_count = len([bet for bets in group_game.get('bets', {}).values() for bet in bets])
    player_count = len(group_game.get('bets', {}))
    total_amount = sum([bet['amount'] for bets in group_game.get('bets', {}).values() for bet in bets])
    
    # 掷骰子时不发送游戏开始提示，直接掷骰子
    
    # 检查该群组是否有设定的骰子点数
    fixed_dice = data_manager.get_fixed_dice(chat_id)
    
    # 检查是否有用户已经发送了骰子表情
    user_dice_values = group_game.get("user_dice_values", [])
    
    # 获取群组游戏状态
    is_user_roll = group_game.get('dice_rolled', False) and group_game.get('selected_roller') is not None
    
    # 如果用户已经发送了足够的骰子表情，则使用这些点数
    if is_user_roll and len(user_dice_values) >= 3:
        dice_result = user_dice_values[:3]  # 只使用前3个
        # 不需要额外发送骰子动画
    else:
        # 通过API发送真实骰子动画 (3个)
        dice_result = []
        
        for dice_num in range(1, 4):  # 1, 2, 3
            dice_response = send_dice(chat_id, emoji="🎲")
            if dice_response.get("ok"):
                # Telegram骰子API返回的值是1-6
                value = dice_response["result"]["dice"]["value"]
                dice_result.append(value)
                
                # 不再单独显示每个骰子的点数
                # 让Telegram的原生骰子动画直接展示效果
                
                time.sleep(1.0)  # 短暂延迟，使骰子动画有序显示
    
    # 检查是否要使用管理员设置的固定骰子点数（用于调试）
    if fixed_dice and len(fixed_dice) == 3:
        # 对管理员显示提示，但不会影响实际结果
        logger.info(f"群组 {chat_id} 有设置的固定骰子点数: {fixed_dice}")
        for admin_id in ADMIN_IDS:
            try:
                admin_message = f"ℹ️ 群组 {chat_id} 有设置的固定骰子点数: {fixed_dice[0]}, {fixed_dice[1]}, {fixed_dice[2]}，但使用真实骰子点数。"
                send_message(admin_id, admin_message)
            except Exception as e:
                logger.error(f"发送管理员消息失败: {e}")
        
        # 清除固定点数，避免影响下一局
        data_manager.clear_fixed_dice(chat_id)
        
    # 如果没有成功获取到骰子结果，使用随机生成
    if len(dice_result) < 3:
        missing_dice = 3 - len(dice_result)
        dice_result.extend(DiceGame.roll_dice(missing_dice))
    
    logger.info(f"群组 {chat_id} 骰子结果：{dice_result}")
    result = DiceGame.calculate_result(dice_result)
    
    # 给骰子动画一些时间显示
    time.sleep(3)
    
    # 更新最后结果
    group_game['last_result'] = result
    data_manager.update_group_game(chat_id, group_game)
    
    # 处理所有投注
    winners_text = ""
    total_winners = 0
    
    for user_id_str, bets in group_game['bets'].items():
        user_id = int(user_id_str)
        user_data = data_manager.get_user(user_id)
        
        if not user_data:
            continue
        
        user_total_win = 0
        
        for bet in bets:
            bet_type = bet['bet_type']
            bet_value = bet['bet_value']
            bet_amount = bet['amount']
            
            won, ratio = DiceGame.evaluate_bet(bet_type, bet_value, result)
            
            if won:
                winnings = bet_amount * ratio
                user_total_win += winnings
                
                # 更新用户余额
                data_manager.update_balance(user_id, winnings)
                
                # 添加游戏记录
                data_manager.add_game_record(
                    user_id=user_id,
                    game_type="group",
                    bet_type=bet_type,
                    bet_value=bet_value,
                    bet_amount=bet_amount,
                    result=dice_result,
                    won=True,
                    winnings=winnings,
                    is_group_game=True,
                    group_id=chat_id
                )
            else:
                # 添加游戏记录
                data_manager.add_game_record(
                    user_id=user_id,
                    game_type="group",
                    bet_type=bet_type,
                    bet_value=bet_value,
                    bet_amount=bet_amount,
                    result=dice_result,
                    won=False,
                    winnings=0,
                    is_group_game=True,
                    group_id=chat_id
                )
        
        if user_total_win > 0:
            winners_text += f"🏆 *{user_data['name']}* 赢得 *+{user_total_win} 金币* 💰\n"
            total_winners += 1
    
    if total_winners == 0:
        winners_text = "❌ *无人中奖* ❌"
    
    # 构建结果描述
    result_desc = "📊 *结果分析*: "
    
    if result["is_triple"]:
        result_desc += f"*豹子 {result['triple_value']}* 🎯\n"
    elif result["is_double"]:
        result_desc += f"*对子 {', '.join(map(str, result['pairs']))}* 🎯\n"
    else:
        result_desc += "\n"
    
    # 添加大小单双分析
    result_desc += "   "
    if result["is_big"]:
        result_desc += "*大*"
    elif result["is_small"]:
        result_desc += "*小*"
    
    if result["is_odd"]:
        result_desc += "*单*"
    elif result["is_even"]:
        result_desc += "*双*"
    
    # 发送结果消息 - 始终作为新消息发送，不覆盖原有消息
    end_message = GROUP_GAME_END_MESSAGE.format(
        dice1=dice_result[0],
        dice2=dice_result[1],
        dice3=dice_result[2],
        total=sum(dice_result),
        result_desc=result_desc,
        winners=winners_text
    )
    
    # 直接发送新消息，不编辑原消息，确保赔付表永久保留
    send_message(chat_id, end_message)
    
    # 生成并发送走势图
    # 获取该群组的历史记录用于分析走势(最多获取30条)
    history = data_manager.get_group_history(chat_id, 30)
    
    if len(history) > 0:
        # 分析历史走势
        trend_codes = []
        result_numbers = []
        game_indices = []
        
        # 从最旧到最新收集游戏结果
        for i, game in enumerate(history):
            # 计算总和和判断类型
            dice_result = game["result"]
            total = sum(dice_result)
            result_numbers.append(total)
            
            # 获取真实的游戏编号（如果有）
            game_number = game.get('group_game_number', i+1)
            game_indices.append(game_number)
            
            # 大小单双判断
            is_triple = len(set(dice_result)) == 1
            is_big = total > 10 and not is_triple
            is_small = total <= 10 or is_triple
            is_odd = total % 2 == 1
            is_even = total % 2 == 0
            
            # 设置走势代码
            if is_triple:
                code = "豹" # 豹子
            elif is_big and is_odd:
                code = "DD" # 大单
            elif is_big and is_even:
                code = "DS" # 大双
            elif is_small and is_odd:
                code = "XD" # 小单
            elif is_small and is_even:
                code = "XS" # 小双
            else:
                code = "--" # 未知
                
            trend_codes.append(code)
        
        # 生成走势表格 (最新的数据在最下面)
        trend_table = "```\n"
        trend_table += "局号  点数  结果\n"
        trend_table += "----------------\n"
        
        # 只显示最近20条记录
        displayed_count = min(20, len(trend_codes))
        
        # 计算当前群组总游戏数
        group_total_games = len([
            game for game in data_manager.game_history 
            if game.get('is_group_game', False) and 
            str(game.get('group_id', '')) == str(chat_id)
        ])
        
        # 显示最近20条记录，使用真实游戏编号
        for i in range(max(0, len(trend_codes)-displayed_count), len(trend_codes)):
            game_number = game_indices[i]  # 使用真实的游戏编号
            trend_table += f"{game_number:3d}   {result_numbers[i]:2d}   {trend_codes[i]}\n"
        
        trend_table += "```"
        
        # 构建走势分析文本
        trend_text = f"""
📊 *游戏走势记录表* 📊

{trend_table}

第{group_total_games}局，共{group_total_games%30}/30局
说明: DD=大单, DS=大双, XD=小单, XS=小双, 豹=豹子
        """
        
        # 只有当该群组游戏次数是30的倍数时才显示统计数据
        if group_total_games % 30 == 0 and group_total_games > 0:
            # 统计数据
            result_counts = {"DD": 0, "DS": 0, "XD": 0, "XS": 0, "豹": 0}
            for code in trend_codes:
                if code in result_counts:
                    result_counts[code] += 1
            
            # 大小统计
            big_count = result_counts["DD"] + result_counts["DS"]
            small_count = result_counts["XD"] + result_counts["XS"]
            
            # 单双统计
            odd_count = result_counts["DD"] + result_counts["XD"]
            even_count = result_counts["DS"] + result_counts["XS"]
            
            trend_text += f"""
*数据统计* (最近30局):
- 大: {big_count}局 ({big_count/len(history)*100:.1f}%)
- 小: {small_count}局 ({small_count/len(history)*100:.1f}%)
- 单: {odd_count}局 ({odd_count/len(history)*100:.1f}%)
- 双: {even_count}局 ({even_count/len(history)*100:.1f}%)
- 豹子: {result_counts["豹"]}局 ({result_counts["豹"]/len(history)*100:.1f}%)

--- 数据重置，新的30局开始 ---
            """
        
        # 发送走势图
        try:
            send_message(chat_id, trend_text)
        except Exception as e:
            logger.error(f"发送走势图失败: {e}")
    
    # 5秒后开始新游戏
    time.sleep(5)
    start_new_group_game(chat_id, data_manager)

def start_new_group_game(chat_id: int, data_manager: DataManager) -> None:
    """自动开始新的群组游戏"""
    # 重置群组游戏状态
    data_manager.reset_group_game(chat_id)
    
    # 创建模拟消息
    message = {
        "chat": {"id": chat_id},
        "from": {"id": 0}  # 系统ID
    }
    
    # 开始新游戏
    handle_start_group_game(message, data_manager)

def handle_group_bet_message(message: Dict[str, Any], data_manager: DataManager) -> None:
    """处理群组中的投注消息"""
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    user_name = message["from"]["first_name"]
    text = message["text"]
    
    # 检查是否是停止游戏的命令 - 仅使用/stop命令
    if text.lower() == "/stop":
        # 检查用户是否有权限
        if user_id in ADMIN_IDS:
            has_permission = True
        else:
            # 检查用户是否是群组管理员
            try:
                chat_member = requests.get(
                    f"{API_URL}/getChatMember",
                    params={
                        "chat_id": chat_id,
                        "user_id": user_id
                    }
                ).json()
                
                if chat_member.get("ok") and chat_member.get("result"):
                    status = chat_member["result"]["status"]
                    has_permission = status in ["creator", "administrator"]
                else:
                    has_permission = False
            except Exception:
                has_permission = False
        
        if has_permission:
            # 获取群组游戏状态
            group_game = data_manager.get_group_game(chat_id)
            
            if group_game['state'] != GROUP_GAME_IDLE:
                # 设置状态为空闲
                group_game['state'] = GROUP_GAME_IDLE
                data_manager.update_group_game(chat_id, group_game)
                
                send_message(chat_id, "🛑 *游戏已停止* 🛑\n\n游戏已被管理员终止。发送 /start 重新开始游戏。")
                return
            else:
                send_message(chat_id, "❌ 当前没有正在进行的游戏。")
                return
        else:
            send_message(chat_id, "❌ 只有管理员可以停止游戏。")
            return
    
    # 检查是否是摇骰子命令
    if text.lower() in ["摇", "摇骰子", "roll", "掷骰子"]:
        # 获取群组游戏状态
        group_game = data_manager.get_group_game(chat_id)
        
        # 检查是否处于选择摇骰子玩家状态
        if group_game['state'] == GROUP_GAME_SELECTING_ROLLER:
            # 检查用户是否是被选中的玩家
            selected_roller = group_game.get('selected_roller')
            
            if user_id == selected_roller:
                # 标记骰子已摇动
                group_game['dice_rolled'] = True
                group_game['state'] = GROUP_GAME_ROLLING
                data_manager.update_group_game(chat_id, group_game)
                
                # 发送摇骰子确认
                user_data = data_manager.get_user(user_id)
                roller_message = f"""
🎲 *{user_data['name']} 正在摇骰子* 🎲

期待骰子的命运...
                """
                send_message(chat_id, roller_message, reply_to_message_id=message["message_id"])
                
                # 玩家骰子点数信息也会显示
                roller_info = f"""
👑 *高额投注者摇骰子特权* 👑
玩家 {user_data['name']} 将掷出骰子...
                """
                send_message(chat_id, roller_info)
                
                # 处理游戏结果
                process_group_game_result(chat_id, data_manager)
                return
            else:
                # 不是被选中的玩家
                send_message(chat_id, f"❌ 只有被选中的高额投注玩家才能摇骰子。", reply_to_message_id=message["message_id"])
                return
        elif group_game['state'] == GROUP_GAME_ROLLING:
            send_message(chat_id, "⏳ 骰子正在被摇动中...", reply_to_message_id=message["message_id"])
            return
        elif group_game['state'] == GROUP_GAME_BETTING:
            send_message(chat_id, "⏳ 游戏仍在投注阶段，请等待倒计时结束。", reply_to_message_id=message["message_id"])
            return
    
    # 检查用户是否被封禁
    if data_manager.is_banned(user_id):
        return
    
    # 获取群组游戏状态
    group_game = data_manager.get_group_game(chat_id)
    
    # 尝试解析投注信息，支持多投注
    bet_info_list = parse_group_bet_message(text)
    if not bet_info_list:
        return
    
    # 检查是否是查询余额命令
    if bet_info_list[0][0] == 'check_balance':
        user_data = data_manager.get_user(user_id)
        balance_message = f"""
💰 *余额查询* 💰

用户: {user_data['name']}
当前余额: *{user_data['balance']}* 金币
用户ID: {user_id}
        """
        send_message(chat_id, balance_message, reply_to_message_id=message["message_id"])
        return
    
    # 获取用户数据
    user_data = data_manager.get_user(user_id)
    
    # 如果用户不存在，创建账户
    if not user_data:
        data_manager.add_user(user_id, user_name)
        user_data = data_manager.get_user(user_id)
    
    # 计算总投注额
    total_amount = sum(amount for _, _, amount in bet_info_list)
    
    # 检查余额
    if user_data["balance"] < total_amount:
        send_message(
            chat_id, 
            INSUFFICIENT_BALANCE_MESSAGE.format(
                balance=user_data["balance"],
                amount=total_amount,
                user_id=user_id
            ),
            reply_to_message_id=message["message_id"]
        )
        return
    
    # 处理所有投注
    success_bets = []
    fail_bets = []
    
    for bet_info in bet_info_list:
        bet_type, bet_value, amount = bet_info
        # 添加投注
        success = data_manager.add_bet_to_group_game(chat_id, user_id, bet_type, bet_value, amount)
        
        if success:
            success_bets.append((bet_type, bet_value, amount))
        else:
            fail_bets.append((bet_type, bet_value, amount))
    
    if success_bets:
        # 构建成功投注的确认消息
        confirm_lines = []
        for bet_type, bet_value, amount in success_bets:
            bet_name = BET_TYPES.get(bet_type, bet_type)
            if bet_value is not None and bet_value != "any":
                bet_display = f"{bet_name} {bet_value}"
            else:
                bet_display = bet_name
            confirm_lines.append(f"- {bet_display}: {amount} 金币\n")
            
        # 获取最新余额
        updated_user_data = data_manager.get_user(user_id)
        
        confirm_text = f"""
✅ *投注成功*

用户: {user_data['name']}
投注明细:
{"".join(confirm_lines)}
总金额: {sum(amount for _, _, amount in success_bets)} 金币
余额: {updated_user_data['balance']} 金币
        """
        
        send_message(chat_id, confirm_text, reply_to_message_id=message["message_id"])
    
    if fail_bets:
        # 构建失败投注的错误消息
        fail_lines = []
        for bet_type, bet_value, amount in fail_bets:
            bet_name = BET_TYPES.get(bet_type, bet_type)
            if bet_value is not None and bet_value != "any":
                bet_display = f"{bet_name} {bet_value}"
            else:
                bet_display = bet_name
            fail_lines.append(f"- {bet_display}: {amount} 金币\n")
        
        error_text = f"""
❌ *以下投注失败*:
{"".join(fail_lines)}

请重试或调整投注。
        """
        
        send_message(chat_id, error_text, reply_to_message_id=message["message_id"])

def parse_group_bet_message(text: str) -> List[Tuple[str, Any, int]]:
    """
    解析群组投注消息文本，支持多投注
    返回: [(bet_type, bet_value, amount), ...] 或空列表
    """
    text = text.strip()
    
    # 检查是否是余额查询命令
    if text.lower() in ['ye', 'yue', '余额', '查余额']:
        return [('check_balance', None, 0)]
    
    # 大/小/单/双和组合投注
    simple_patterns = {
        "大单": "big_odd",
        "dd": "big_odd",
        "DD": "big_odd",
        "大双": "big_even",
        "ds": "big_even",
        "DS": "big_even",
        "小单": "small_odd",
        "xd": "small_odd",
        "XD": "small_odd",
        "小双": "small_even",
        "xs": "small_even",
        "XS": "small_even",
        "大": "big",
        "da": "big",
        "DA": "big",
        "小": "small",
        "x": "small",
        "X": "small",
        "单": "odd",
        "双": "even",
        "豹子": "triple",
        "对子": "double"
    }
    
    # 调试日志
    print(f"尝试解析投注消息: {text}")
    
    # 支持一次下注多个投注类型，用空格分隔，例如："大单100 小单30"
    bet_parts = text.split()
    all_bets = []
    
    # 如果只有一个部分，按旧方式处理
    if len(bet_parts) == 1:
        # 单个投注解析
        bet = _parse_single_bet(text, simple_patterns)
        if bet:
            all_bets.append(bet)
        return all_bets
    
    # 处理多个投注部分
    i = 0
    while i < len(bet_parts):
        current_part = bet_parts[i]
        
        # 检查是否匹配简单模式
        matched = False
        for pattern, bet_type in simple_patterns.items():
            if current_part.startswith(pattern):
                # 提取投注类型
                remaining = current_part[len(pattern):]
                
                # 如果数字部分为空，尝试从下一个部分获取金额
                if not remaining and i + 1 < len(bet_parts):
                    try:
                        amount = int(bet_parts[i+1])
                        bet_value = "any" if bet_type in ["triple", "double"] else None
                        all_bets.append((bet_type, bet_value, amount))
                        print(f"匹配到投注类型: {pattern}, 金额: {amount}")
                        matched = True
                        i += 2  # 跳过已处理的两个部分
                        break
                    except ValueError:
                        pass
                
                # 如果当前部分自身包含数字
                if not matched and remaining:
                    try:
                        amount = int(remaining)
                        bet_value = "any" if bet_type in ["triple", "double"] else None
                        all_bets.append((bet_type, bet_value, amount))
                        print(f"匹配到投注类型: {pattern}, 金额: {amount}")
                        matched = True
                        i += 1  # 处理下一个部分
                        break
                    except ValueError:
                        pass
        
        # 如果没有匹配，尝试一些特殊模式
        if not matched:
            # 特定总和、豹子、对子等
            special_bet = _parse_special_bet(current_part, bet_parts[i+1] if i+1 < len(bet_parts) else "")
            if special_bet:
                all_bets.append(special_bet)
                # 根据特殊投注使用的部分数量前进
                i += 2 if i+1 < len(bet_parts) and not special_bet[2] else 1
            else:
                # 没有匹配任何模式，跳过
                i += 1
                
    return all_bets

def _parse_single_bet(text: str, simple_patterns: Dict[str, str]) -> Optional[Tuple[str, Any, int]]:
    """解析单个投注，返回 (bet_type, bet_value, amount) 或 None"""
    # 处理简单模式
    for pattern, bet_type in simple_patterns.items():
        if text.startswith(pattern):
            # 提取金额
            try:
                amount = int(text[len(pattern):].strip())
                
                # 输出调试信息
                print(f"匹配到投注类型: {pattern}, 金额: {amount}")
                
                # 豹子和对子使用 "any" 作为默认值
                bet_value = "any" if bet_type in ["triple", "double"] else None
                
                return bet_type, bet_value, amount
            except ValueError:
                print(f"投注金额解析失败: {text[len(pattern):]}")
                return None
    
    # 处理特殊投注类型
    return _parse_special_bet(text, "")

def _parse_special_bet(text: str, next_part: str) -> Optional[Tuple[str, Any, int]]:
    """解析特殊投注类型，返回 (bet_type, bet_value, amount) 或 None"""
    # 特定总和: 总和X [金额]
    if text.startswith("总和"):
        # 两种情况: "总和X 金额" 或 "总和X金额"
        remaining = text[2:].strip()
        
        if remaining:
            # 尝试从当前部分解析
            try:
                parts = remaining.split()
                if len(parts) == 2:
                    sum_value = int(parts[0])
                    amount = int(parts[1])
                    
                    if 3 <= sum_value <= 18:
                        return "sum", sum_value, amount
            except ValueError:
                pass
            
            # 尝试作为单个数字解析
            try:
                sum_value = int(remaining)
                
                # 如果有下一部分，尝试从下一部分获取金额
                if next_part:
                    try:
                        amount = int(next_part)
                        if 3 <= sum_value <= 18:
                            return "sum", sum_value, amount
                    except ValueError:
                        pass
            except ValueError:
                pass
    
    # 特定豹子: 豹子X [金额]
    if text.startswith("豹子"):
        remaining = text[2:].strip()
        
        # 如果有下一个数字部分
        if remaining and remaining[0] in "123456":
            try:
                value = int(remaining[0])
                amount_str = remaining[1:].strip()
                
                if amount_str:
                    # 当前部分包含金额
                    try:
                        amount = int(amount_str)
                        return "triple", value, amount
                    except ValueError:
                        pass
                elif next_part:
                    # 尝试从下一部分获取金额
                    try:
                        amount = int(next_part)
                        return "triple", value, amount
                    except ValueError:
                        pass
            except ValueError:
                pass
    
    # 特定对子: 对子X [金额]
    if text.startswith("对子"):
        remaining = text[2:].strip()
        
        # 如果有下一个数字部分
        if remaining and remaining[0] in "123456":
            try:
                value = int(remaining[0])
                amount_str = remaining[1:].strip()
                
                if amount_str:
                    # 当前部分包含金额
                    try:
                        amount = int(amount_str)
                        return "double", value, amount
                    except ValueError:
                        pass
                elif next_part:
                    # 尝试从下一部分获取金额
                    try:
                        amount = int(next_part)
                        return "double", value, amount
                    except ValueError:
                        pass
            except ValueError:
                pass
    
    # 单号: [1-6][金额]
    if len(text) > 0 and text[0] in "123456":
        try:
            value = int(text[0])
            amount_str = text[1:].strip()
            
            if amount_str:
                # 当前部分包含金额
                try:
                    amount = int(amount_str)
                    return "single", value, amount
                except ValueError:
                    pass
            elif next_part:
                # 尝试从下一部分获取金额
                try:
                    amount = int(next_part)
                    return "single", value, amount
                except ValueError:
                    pass
        except ValueError:
            pass
    
    # 颜色: [红/蓝/绿][金额]
    colors = {"红": "红", "蓝": "蓝", "绿": "绿"}
    for color in colors:
        if text.startswith(color):
            remaining = text[len(color):].strip()
            
            if remaining:
                # 当前部分包含金额
                try:
                    amount = int(remaining)
                    return "color", color, amount
                except ValueError:
                    pass
            elif next_part:
                # 尝试从下一部分获取金额
                try:
                    amount = int(next_part)
                    return "color", color, amount
                except ValueError:
                    pass
    
    return None

def handle_dice_message(message: Dict[str, Any], data_manager: DataManager) -> None:
    """处理用户发送的骰子消息"""
    if "chat" not in message or message["chat"]["id"] >= 0:  # 非群组聊天
        return
    
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    
    # 获取群组游戏状态
    group_game = data_manager.get_group_game(chat_id)
    
    # 检查是否处于选择摇骰子玩家状态
    if group_game['state'] == GROUP_GAME_SELECTING_ROLLER:
        # 检查用户是否是被选中的玩家
        selected_roller = group_game.get('selected_roller')
        
        if user_id == selected_roller:
            # 获取用户数据和骰子值
            user_data = data_manager.get_user(user_id)
            dice_value = message["dice"]["value"]
            
            # 收集骰子结果
            if "user_dice_values" not in group_game:
                group_game["user_dice_values"] = []
            
            # 添加骰子值
            group_game["user_dice_values"].append(dice_value)
            
            # 在掷够3个骰子前保持SELECTING_ROLLER状态，这样才能继续接收骰子
            # 只有当收集够3个骰子时才标记为已摇动，并改变状态
            if len(group_game["user_dice_values"]) >= 3:
                group_game['dice_rolled'] = True
                group_game['state'] = GROUP_GAME_ROLLING
            
            data_manager.update_group_game(chat_id, group_game)
            
            # 发送骰子点数消息
            dice_message = f"""
🎲 *骰子 {len(group_game['user_dice_values'])}/3* 🎲

{user_data['name']} 掷出了: {dice_value}
            """
            send_message(chat_id, dice_message, reply_to_message_id=message["message_id"])
            
            # 如果已经掷了3个骰子，处理游戏结果
            if len(group_game["user_dice_values"]) >= 3:
                # 使用玩家掷出的骰子值
                process_group_game_result(chat_id, data_manager)
            else:
                # 继续等待玩家掷剩余的骰子
                next_dice_message = f"请继续发送🎲表情掷出第{len(group_game['user_dice_values'])+1}/3个骰子"
                send_message(chat_id, next_dice_message)

def handle_callback_query(callback_query: Dict[str, Any], data_manager: DataManager) -> None:
    """处理按钮回调查询"""
    user_id = callback_query["from"]["id"]
    chat_id = callback_query["message"]["chat"]["id"]
    message_id = callback_query["message"]["message_id"]
    data = callback_query["data"]
    
    # 检查用户是否被封禁
    if data_manager.is_banned(user_id):
        return
    
    # 处理私人红包回调
    if data.startswith("grab_private_hongbao:"):
        hongbao_id = data.split(":", 1)[1]
        
        # 确保hongbao属性存在
        if not hasattr(data_manager, "hongbao"):
            data_manager.hongbao = {}
            answer_callback_query(callback_query["id"], "❌ 红包已失效或已被领取", show_alert=True)
            return
        
        # 检查红包是否存在
        if hongbao_id not in data_manager.hongbao:
            answer_callback_query(callback_query["id"], "❌ 红包已失效或已被领取", show_alert=True)
            return
        
        hongbao_info = data_manager.hongbao[hongbao_id]
        
        # 检查红包是否已被领取
        if hongbao_info.get("is_claimed", False):
            answer_callback_query(callback_query["id"], "❌ 红包已被领取", show_alert=True)
            return
        
        # 检查是否是指定的接收者
        if user_id != hongbao_info["target_id"]:
            answer_callback_query(callback_query["id"], "❌ 这个红包不是发给您的", show_alert=True)
            return
        
        # 获取用户数据
        user_data = data_manager.get_user(user_id)
        if not user_data:
            # 如果用户不存在，则创建新用户
            user_name = callback_query["from"].get("first_name", "")
            if "last_name" in callback_query["from"]:
                user_name += f" {callback_query['from']['last_name']}"
            data_manager.add_user(user_id, user_name)
            user_data = data_manager.get_user(user_id)
        
        # 获取红包金额
        amount = hongbao_info["amount"]
        
        # 更新用户余额
        new_balance, success = data_manager.update_balance(user_id, amount)
        
        if success:
            # 标记红包为已领取
            hongbao_info["is_claimed"] = True
            hongbao_info["claimed_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 通知用户
            answer_callback_query(callback_query["id"], f"🎉 恭喜！您领取了 {amount} 金币", show_alert=True)
            
            # 更新红包消息
            updated_message = f"""
🧧 *红包已领取* 🧧

{hongbao_info['sender_name']} 发送给 {hongbao_info['target_name']} 的红包
金额: {amount} 金币
状态: ✅ 已领取
            """
            
            # 更新消息，移除按钮
            edit_message_text(chat_id, message_id, updated_message)
            
            # 删除红包信息以节省内存
            del data_manager.hongbao[hongbao_id]
        else:
            answer_callback_query(callback_query["id"], "❌ 领取红包失败，请稍后再试", show_alert=True)
    
    # 处理群组红包回调
    elif data.startswith("grab_hongbao:"):
        hongbao_id = data.split(":", 1)[1]
        
        # 确保hongbao属性存在
        if not hasattr(data_manager, "hongbao"):
            data_manager.hongbao = {}
            answer_callback_query(callback_query["id"], "❌ 红包已失效或已被抢完", show_alert=True)
            return
        
        # 检查红包是否存在
        if hongbao_id not in data_manager.hongbao:
            answer_callback_query(callback_query["id"], "❌ 红包已失效或已被抢完", show_alert=True)
            return
        
        hongbao_info = data_manager.hongbao[hongbao_id]
        
        # 检查红包是否已被抢完
        if hongbao_info["remaining_count"] <= 0:
            answer_callback_query(callback_query["id"], "❌ 红包已被抢完", show_alert=True)
            return
        
        # 检查用户是否已经抢过
        for receiver in hongbao_info["receivers"]:
            if receiver["user_id"] == user_id:
                answer_callback_query(callback_query["id"], "❌ 您已经抢过这个红包了", show_alert=True)
                return
        
        # 获取用户数据
        user_data = data_manager.get_user(user_id)
        if not user_data:
            # 如果用户不存在，则创建新用户
            user_name = callback_query["from"].get("first_name", "")
            if "last_name" in callback_query["from"]:
                user_name += f" {callback_query['from']['last_name']}"
            data_manager.add_user(user_id, user_name)
            user_data = data_manager.get_user(user_id)
        
        # 分配红包金额
        amount = hongbao_info["amounts"][hongbao_info["total_count"] - hongbao_info["remaining_count"]]
        
        # 更新用户余额
        new_balance, success = data_manager.update_balance(user_id, amount)
        
        if success:
            # 更新红包信息
            hongbao_info["remaining_count"] -= 1
            hongbao_info["remaining_amount"] -= amount
            
            receiver_info = {
                "user_id": user_id,
                "user_name": user_data["name"],
                "amount": amount,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            hongbao_info["receivers"].append(receiver_info)
            
            # 通知用户
            answer_callback_query(callback_query["id"], f"🎉 恭喜！您抢到了 {amount} 金币", show_alert=True)
            
            # 更新红包消息
            if hongbao_info["remaining_count"] == 0:
                # 所有红包已被抢完，更新消息
                updated_message = f"""
🧧 *红包已被抢完* 🧧

{hongbao_info['sender_name']} 发送的红包
总金额: {hongbao_info['total_amount']} 金币
状态: ✅ 已抢完
                """
                
                # 更新消息，移除按钮
                edit_message_text(chat_id, message_id, updated_message)
                
                # 删除红包信息以节省内存
                del data_manager.hongbao[hongbao_id]
            else:
                # 还有红包可以抢，更新消息
                updated_message = f"""
🧧 *红包来啦* 🧧

{hongbao_info['sender_name']} 发送的红包
总金额: {hongbao_info['total_amount']} 金币
剩余: {hongbao_info['remaining_count']}/{hongbao_info['total_count']} 个

点击下方按钮抢红包！
                """
                
                # 保留抢红包按钮
                grab_button = {
                    "inline_keyboard": [
                        [
                            {
                                "text": "🧧 抢红包 🧧",
                                "callback_data": f"grab_hongbao:{hongbao_id}"
                            }
                        ]
                    ]
                }
                
                edit_message_text(chat_id, message_id, updated_message, reply_markup=grab_button)
        else:
            answer_callback_query(callback_query["id"], "❌ 抢红包失败，请稍后再试", show_alert=True)
    
    # 处理不同的回调数据
    elif data == "play":
        # 模拟 /play 命令
        message = {
            "chat": {"id": chat_id},
            "from": {"id": user_id, "first_name": callback_query["from"]["first_name"]}
        }
        handle_play_command(message, data_manager)
        
    elif data == "rules":
        # 模拟 /rules 命令
        message = {
            "chat": {"id": chat_id},
            "from": {"id": user_id}
        }
        handle_rules_command(message, data_manager)
        
    elif data == "balance":
        # 模拟 /balance 命令
        message = {
            "chat": {"id": chat_id},
            "from": {"id": user_id}
        }
        handle_balance_command(message, data_manager)
        
    elif data == "history" or data == "history_trend" or data == "history_full":
        # 显示历史记录
        handle_history_callback(user_id, chat_id, message_id, data_manager)
        
    elif data == "vip":
        # 显示VIP信息
        handle_vip_callback(user_id, chat_id, message_id, data_manager)
        
    elif data == "leaderboard":
        # 显示排行榜
        handle_leaderboard_callback(user_id, chat_id, message_id, data_manager)
        
    elif data == "back_to_menu":
        # 返回主菜单
        # 模拟 /start 命令
        message = {
            "chat": {"id": chat_id},
            "from": {"id": user_id, "first_name": callback_query["from"]["first_name"]}
        }
        handle_start_command(message, data_manager)
        
    elif data == "cancel_bet":
        # 取消投注
        if user_id in USER_STATES:
            del USER_STATES[user_id]
        
        message = {
            "chat": {"id": chat_id},
            "from": {"id": user_id, "first_name": callback_query["from"]["first_name"]}
        }
        handle_start_command(message, data_manager)
        
    elif data.startswith("bet_type_"):
        # 投注类型选择
        bet_type = data[9:]  # 移除 "bet_type_" 前缀
        handle_bet_type_selection(user_id, chat_id, message_id, bet_type, data_manager)
        
    elif data.startswith("bet_value_"):
        # 投注值选择
        bet_value = data[10:]  # 移除 "bet_value_" 前缀
        handle_bet_value_selection(user_id, chat_id, message_id, bet_value, data_manager)
        
    elif data == "confirm_bet":
        # 确认投注
        handle_bet_confirmation(user_id, chat_id, message_id, data_manager)

def handle_bet_type_selection(user_id: int, chat_id: int, message_id: int, 
                              bet_type: str, data_manager: DataManager) -> None:
    """处理投注类型选择"""
    if user_id not in USER_STATES:
        return
    
    user_state = USER_STATES[user_id]
    user_state["bet_type"] = bet_type
    
    # 获取用户数据
    user_data = data_manager.get_user(user_id)
    
    if not user_data:
        return
    
    # 根据不同投注类型，提供不同的选择
    if bet_type == "sum":  # 总和
        # 创建总和选择键盘
        sum_values_keyboard = {
            "inline_keyboard": [
                [{"text": str(i), "callback_data": f"bet_value_{i}"} for i in range(3, 7)],
                [{"text": str(i), "callback_data": f"bet_value_{i}"} for i in range(7, 11)],
                [{"text": str(i), "callback_data": f"bet_value_{i}"} for i in range(11, 15)],
                [{"text": str(i), "callback_data": f"bet_value_{i}"} for i in range(15, 19)],
                [{"text": "🔙 返回", "callback_data": "play"}]
            ]
        }
        
        message_text = f"""
🎲 *选择总和值* 🎲

您的余额: {user_data['balance']} 金币
用户ID: {user_id}

请选择一个总和值(3-18):
        """
        
        edit_message_text(chat_id, message_id, message_text, reply_markup=sum_values_keyboard)
        
        user_state["state"] = STATE_SELECTING_BET_VALUE
        
    elif bet_type == "triple":  # 豹子
        # 创建豹子选择键盘
        triple_keyboard = {
            "inline_keyboard": [
                [{"text": "任意豹子", "callback_data": "bet_value_any"}],
                [
                    {"text": "1", "callback_data": "bet_value_1"},
                    {"text": "2", "callback_data": "bet_value_2"},
                    {"text": "3", "callback_data": "bet_value_3"}
                ],
                [
                    {"text": "4", "callback_data": "bet_value_4"},
                    {"text": "5", "callback_data": "bet_value_5"},
                    {"text": "6", "callback_data": "bet_value_6"}
                ],
                [{"text": "🔙 返回", "callback_data": "play"}]
            ]
        }
        
        message_text = f"""
🎲 *选择豹子类型* 🎲

您的余额: {user_data['balance']} 金币
用户ID: {user_id}

任意豹子 - 赔率 25:1
特定豹子 - 赔率 150:1

请选择:
        """
        
        edit_message_text(chat_id, message_id, message_text, reply_markup=triple_keyboard)
        
        user_state["state"] = STATE_SELECTING_BET_VALUE
        
    elif bet_type == "double":  # 对子
        # 创建对子选择键盘
        double_keyboard = {
            "inline_keyboard": [
                [{"text": "任意对子", "callback_data": "bet_value_any"}],
                [
                    {"text": "1", "callback_data": "bet_value_1"},
                    {"text": "2", "callback_data": "bet_value_2"},
                    {"text": "3", "callback_data": "bet_value_3"}
                ],
                [
                    {"text": "4", "callback_data": "bet_value_4"},
                    {"text": "5", "callback_data": "bet_value_5"},
                    {"text": "6", "callback_data": "bet_value_6"}
                ],
                [{"text": "🔙 返回", "callback_data": "play"}]
            ]
        }
        
        message_text = f"""
🎲 *选择对子类型* 🎲

您的余额: {user_data['balance']} 金币
用户ID: {user_id}

任意对子 - 赔率 2:1
特定对子 - 赔率 30:1

请选择:
        """
        
        edit_message_text(chat_id, message_id, message_text, reply_markup=double_keyboard)
        
        user_state["state"] = STATE_SELECTING_BET_VALUE
        
    elif bet_type == "single":  # 单号
        # 创建单号选择键盘
        single_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "1", "callback_data": "bet_value_1"},
                    {"text": "2", "callback_data": "bet_value_2"},
                    {"text": "3", "callback_data": "bet_value_3"}
                ],
                [
                    {"text": "4", "callback_data": "bet_value_4"},
                    {"text": "5", "callback_data": "bet_value_5"},
                    {"text": "6", "callback_data": "bet_value_6"}
                ],
                [{"text": "🔙 返回", "callback_data": "play"}]
            ]
        }
        
        message_text = f"""
🎲 *选择单号* 🎲

您的余额: {user_data['balance']} 金币
用户ID: {user_id}

单号 - 赔率 1:1 (每次出现)

请选择一个数字:
        """
        
        edit_message_text(chat_id, message_id, message_text, reply_markup=single_keyboard)
        
        user_state["state"] = STATE_SELECTING_BET_VALUE
        
    elif bet_type == "color":  # 颜色
        # 创建颜色选择键盘
        color_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "红色(1,2)", "callback_data": "bet_value_红"},
                    {"text": "蓝色(3,4)", "callback_data": "bet_value_蓝"},
                    {"text": "绿色(5,6)", "callback_data": "bet_value_绿"}
                ],
                [{"text": "🔙 返回", "callback_data": "play"}]
            ]
        }
        
        message_text = f"""
🎲 *选择颜色* 🎲

您的余额: {user_data['balance']} 金币
用户ID: {user_id}

颜色赔率:
- 出现1次: 1:1
- 出现2次: 2:1
- 出现3次: 4:1

请选择一种颜色:
        """
        
        edit_message_text(chat_id, message_id, message_text, reply_markup=color_keyboard)
        
        user_state["state"] = STATE_SELECTING_BET_VALUE
        
    else:  # 大、小、单、双等简单投注类型
        # 这些类型不需要选择投注值，直接进入投注金额输入阶段
        user_state["bet_value"] = None
        user_state["state"] = STATE_ENTERING_BET_AMOUNT
        
        message_text = f"""
🎲 *请输入投注金额* 🎲

投注类型: {BET_TYPES.get(bet_type, bet_type)}
您的余额: {user_data['balance']} 金币
用户ID: {user_id}

请回复消息输入您要投注的金额:
        """
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "🔙 返回", "callback_data": "play"}]
            ]
        }
        
        edit_message_text(chat_id, message_id, message_text, reply_markup=keyboard)

def handle_bet_value_selection(user_id: int, chat_id: int, message_id: int, 
                              bet_value: str, data_manager: DataManager) -> None:
    """处理投注值选择"""
    if user_id not in USER_STATES:
        return
    
    user_state = USER_STATES[user_id]
    bet_type = user_state["bet_type"]
    
    if bet_type is None:
        return
    
    # 处理投注值
    if bet_value == "any":
        user_state["bet_value"] = "any"
    elif bet_type == "sum":
        user_state["bet_value"] = int(bet_value)
    elif bet_type in ["triple", "double", "single"]:
        user_state["bet_value"] = int(bet_value)
    elif bet_type == "color":
        user_state["bet_value"] = bet_value
    else:
        user_state["bet_value"] = bet_value
    
    # 设置状态为输入投注金额
    user_state["state"] = STATE_ENTERING_BET_AMOUNT
    
    # 获取用户数据
    user_data = data_manager.get_user(user_id)
    
    if not user_data:
        return
    
    # 构建投注值显示文本
    bet_value_text = ""
    if bet_type == "sum":
        bet_value_text = str(user_state["bet_value"])
    elif bet_type == "triple":
        if user_state["bet_value"] == "any":
            bet_value_text = "任意豹子"
        else:
            bet_value_text = str(user_state["bet_value"])
    elif bet_type == "double":
        if user_state["bet_value"] == "any":
            bet_value_text = "任意对子"
        else:
            bet_value_text = str(user_state["bet_value"])
    elif bet_type == "single":
        bet_value_text = str(user_state["bet_value"])
    elif bet_type == "color":
        bet_value_text = user_state["bet_value"]
    
    message_text = f"""
🎲 *请输入投注金额* 🎲

投注类型: {BET_TYPES.get(bet_type, bet_type)} {bet_value_text}
您的余额: {user_data['balance']} 金币
用户ID: {user_id}

请回复消息输入您要投注的金额:
    """
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "🔙 返回", "callback_data": "play"}]
        ]
    }
    
    edit_message_text(chat_id, message_id, message_text, reply_markup=keyboard)

def handle_bet_amount_message(message: Dict[str, Any], data_manager: DataManager) -> None:
    """处理投注金额输入消息"""
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message["text"]
    
    # 检查用户状态
    if user_id not in USER_STATES:
        return
    
    user_state = USER_STATES[user_id]
    
    if user_state["state"] != STATE_ENTERING_BET_AMOUNT:
        return
    
    # 尝试解析投注金额
    try:
        bet_amount = int(text.strip())
        
        if bet_amount <= 0:
            send_message(chat_id, "❌ 投注金额必须大于0，请重新输入。")
            return
        
        # 获取用户数据
        user_data = data_manager.get_user(user_id)
        
        if not user_data:
            send_message(chat_id, "❌ 用户数据不存在，请使用 /start 命令创建账户。")
            return
        
        # 检查余额
        if user_data["balance"] < bet_amount:
            send_message(
                chat_id, 
                INSUFFICIENT_BALANCE_MESSAGE.format(
                    balance=user_data["balance"],
                    amount=bet_amount,
                    user_id=user_id
                )
            )
            return
        
        # 设置投注金额和状态
        user_state["bet_amount"] = bet_amount
        user_state["state"] = STATE_CONFIRMING_BET
        
        # 构建投注值显示文本
        bet_type = user_state["bet_type"]
        bet_value = user_state["bet_value"]
        
        bet_value_text = ""
        if bet_type == "sum":
            bet_value_text = str(bet_value)
        elif bet_type == "triple":
            if bet_value == "any":
                bet_value_text = "任意豹子"
            else:
                bet_value_text = str(bet_value)
        elif bet_type == "double":
            if bet_value == "any":
                bet_value_text = "任意对子"
            else:
                bet_value_text = str(bet_value)
        elif bet_type == "single":
            bet_value_text = str(bet_value)
        elif bet_type == "color":
            bet_value_text = bet_value
        
        # 计算确认后余额
        new_balance = user_data["balance"] - bet_amount
        
        # 发送确认消息
        confirm_message = BET_CONFIRMATION_MESSAGE.format(
            bet_type=BET_TYPES.get(bet_type, bet_type),
            bet_value=bet_value_text,
            bet_amount=bet_amount,
            user_id=user_id,
            new_balance=new_balance
        )
        
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ 确认", "callback_data": "confirm_bet"},
                    {"text": "❌ 取消", "callback_data": "cancel_bet"}
                ]
            ]
        }
        
        result = send_message(chat_id, confirm_message, reply_markup=keyboard)
        
        # 更新消息ID
        if result.get("ok"):
            user_state["message_id"] = result["result"]["message_id"]
            
    except ValueError:
        send_message(chat_id, "❌ 无效的金额，请输入一个正整数。")

def handle_bet_confirmation(user_id: int, chat_id: int, message_id: int, data_manager: DataManager) -> None:
    """处理投注确认"""
    if user_id not in USER_STATES:
        return
    
    user_state = USER_STATES[user_id]
    
    if user_state["state"] != STATE_CONFIRMING_BET:
        return
    
    # 获取投注信息
    bet_type = user_state["bet_type"]
    bet_value = user_state["bet_value"]
    bet_amount = user_state["bet_amount"]
    
    # 获取用户数据
    user_data = data_manager.get_user(user_id)
    
    if not user_data:
        return
    
    # 再次检查余额
    if user_data["balance"] < bet_amount:
        error_text = INSUFFICIENT_BALANCE_MESSAGE.format(
            balance=user_data["balance"],
            amount=bet_amount,
            user_id=user_id
        )
        edit_message_text(chat_id, message_id, error_text)
        # 重置用户状态
        del USER_STATES[user_id]
        return
    
    # 更新用户余额
    new_balance, success = data_manager.update_balance(user_id, -bet_amount)
    
    if not success:
        edit_message_text(chat_id, message_id, "❌ 更新余额失败，请重试。")
        return
    
    # 发送正在摇骰子的消息
    rolling_message = "🎲 *正在摇骰子...* 🎲"
    edit_message_text(chat_id, message_id, rolling_message)
    
    # 掷骰子
    dice_result = DiceGame.roll_dice()
    print(f"用户 {user_id} 投注 {bet_type} {bet_value}，金额：{bet_amount}，骰子结果：{dice_result}")
    result = DiceGame.calculate_result(dice_result)
    
    # 评估投注结果
    won, ratio = DiceGame.evaluate_bet(bet_type, bet_value, result)
    
    # 计算赢得的金额
    winnings = 0
    if won:
        winnings = bet_amount * ratio
        data_manager.update_balance(user_id, winnings)
    
    # 添加游戏记录
    data_manager.add_game_record(
        user_id=user_id,
        game_type="personal",
        bet_type=bet_type,
        bet_value=bet_value,
        bet_amount=bet_amount,
        result=dice_result,
        won=won,
        winnings=winnings
    )
    
    # 构建投注值显示文本
    bet_value_text = ""
    if bet_type == "sum":
        bet_value_text = str(bet_value)
    elif bet_type == "triple":
        if bet_value == "any":
            bet_value_text = "任意豹子"
        else:
            bet_value_text = str(bet_value)
    elif bet_type == "double":
        if bet_value == "any":
            bet_value_text = "任意对子"
        else:
            bet_value_text = str(bet_value)
    elif bet_type == "single":
        bet_value_text = str(bet_value)
    elif bet_type == "color":
        bet_value_text = bet_value
    elif bet_value is None:
        bet_value_text = ""
    else:
        bet_value_text = str(bet_value)
    
    # 构建结果消息
    bet_desc = f"{BET_TYPES.get(bet_type, bet_type)} {bet_value_text}"
    
    if won:
        result_text = f"✅ *恭喜！您赢了 {winnings} 金币*"
        balance_change = f"+{winnings} 金币"
    else:
        result_text = "❌ *很遗憾，您输了*"
        balance_change = f"-{bet_amount} 金币"
    
    # 更新用户数据以获取最新余额
    user_data = data_manager.get_user(user_id)
    
    game_result_message = GAME_RESULT_MESSAGE.format(
        dice1=dice_result[0],
        dice2=dice_result[1],
        dice3=dice_result[2],
        total=sum(dice_result),
        bet_desc=bet_desc,
        result=result_text,
        balance_change=balance_change,
        balance=user_data["balance"],
        user_id=user_id
    )
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🎮 再玩一局", "callback_data": "play"},
                {"text": "🔙 返回主菜单", "callback_data": "back_to_menu"}
            ]
        ]
    }
    
    # 等待1秒，模拟骰子投掷过程
    time.sleep(1)
    
    edit_message_text(chat_id, message_id, game_result_message, reply_markup=keyboard)
    
    # 重置用户状态
    del USER_STATES[user_id]

def handle_history_callback(user_id: int, chat_id: int, message_id: int, data_manager: DataManager) -> None:
    """处理查看历史记录回调"""
    # 获取用户数据
    user_data = data_manager.get_user(user_id)
    
    if not user_data:
        edit_message_text(chat_id, message_id, "❌ 用户数据不存在，请使用 /start 命令创建账户。")
        return
    
    # 获取全局历史记录用于分析走势(最多获取30条)
    history = data_manager.game_history[-30:] if len(data_manager.game_history) > 0 else []
    
    if not history:
        history_text = """
📊 *游戏走势分析* 📊

还没有任何游戏记录。
请等待游戏开始，创建游戏历史。
        """
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🎮 开始游戏", "callback_data": "play"},
                    {"text": "🔙 返回", "callback_data": "back_to_menu"}
                ]
            ]
        }
        
        try:
            edit_message_text(chat_id, message_id, history_text, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"编辑历史消息失败: {e}")
            # 如果编辑失败，尝试发送新消息
            send_message(chat_id, history_text, reply_markup=keyboard)
    else:
        # 先发送文本消息以反馈请求已收到
        try:
            edit_message_text(chat_id, message_id, "📊 *正在生成走势图表...* 📊\n\n请稍候...")
        except Exception as e:
            logger.error(f"编辑历史消息失败: {e}")
            send_message(chat_id, "📊 *正在生成走势图表...* 📊\n\n请稍候...")
        
        # 生成走势图表
        try:
            # 生成图表
            photo_data = generate_trend_chart(history)
            
            # 分析数据
            result_counts = {"big": 0, "small": 0, "odd": 0, "even": 0, "triple": 0}
            
            for game in history:
                dice_result = game["result"]
                total = sum(dice_result)
                is_triple = len(set(dice_result)) == 1
                
                if is_triple:
                    result_counts["triple"] += 1
                elif total > 10:
                    result_counts["big"] += 1
                else:
                    result_counts["small"] += 1
                
                if total % 2 == 1:
                    result_counts["odd"] += 1
                else:
                    result_counts["even"] += 1
            
            # 构建图片说明文本
            caption = f"""
📊 *游戏走势统计* 📊

历史记录: 最近{len(history)}局游戏
说明: DD=大单, DS=大双, XD=小单, XS=小双, 豹=豹子

*数据统计*:
- 大: {result_counts["big"]}局 ({result_counts["big"]/len(history)*100:.1f}%)
- 小: {result_counts["small"]}局 ({result_counts["small"]/len(history)*100:.1f}%)
- 单: {result_counts["odd"]}局 ({result_counts["odd"]/len(history)*100:.1f}%)
- 双: {result_counts["even"]}局 ({result_counts["even"]/len(history)*100:.1f}%)
- 豹子: {result_counts["triple"]}局 ({result_counts["triple"]/len(history)*100:.1f}%)
            """
            
            # 发送图片
            send_photo(chat_id, photo_data, caption=caption)
            
            # 增加操作按钮
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🎮 开始游戏", "callback_data": "play"},
                        {"text": "🔙 返回", "callback_data": "back_to_menu"}
                    ]
                ]
            }
            
            send_message(chat_id, "选择您的下一步操作:", reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"生成走势图表失败: {e}")
            # 如果生成图表失败，发送文本版走势
            trend_text = """
📈 *游戏走势分析* 📈

生成图表时出现错误，显示文本版走势。

*最近游戏结果*:
"""
            
            # 显示最近10局结果
            for i, game in enumerate(history[-10:]):
                dice_result = game["result"]
                total = sum(dice_result)
                idx = len(data_manager.game_history) - 10 + i + 1
                
                # 判断结果类型
                is_triple = len(set(dice_result)) == 1
                is_big = total > 10 and not is_triple
                is_small = total <= 10 or is_triple
                is_odd = total % 2 == 1
                is_even = total % 2 == 0
                
                result_code = ""
                if is_triple:
                    result_code = "豹子"
                elif is_big and is_odd:
                    result_code = "大单"
                elif is_big and is_even:
                    result_code = "大双"
                elif is_small and is_odd:
                    result_code = "小单"
                elif is_small and is_even:
                    result_code = "小双"
                
                trend_text += f"{idx}局: 点数={total}, 结果={result_code}\n"
            
            # 发送文本版走势
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🎮 开始游戏", "callback_data": "play"},
                        {"text": "🔙 返回", "callback_data": "back_to_menu"}
                    ]
                ]
            }
            
            send_message(chat_id, trend_text, reply_markup=keyboard)

def handle_vip_callback(user_id: int, chat_id: int, message_id: int, data_manager: DataManager) -> None:
    """处理查看VIP信息回调"""
    # 获取用户数据
    user_data = data_manager.get_user(user_id)
    
    if not user_data:
        edit_message_text(chat_id, message_id, "❌ 用户数据不存在，请使用 /start 命令创建账户。")
        return
    
    # 计算VIP等级和升级进度
    current_level = user_data["vip_level"]
    current_total_bets = user_data["total_bets"]
    
    # 获取当前等级信息
    current_level_info = VIP_LEVELS[current_level]
    current_name = current_level_info["name"]
    current_privileges = current_level_info["privileges"]
    
    # 获取下一级等级信息
    next_level = current_level + 1
    if next_level in VIP_LEVELS:
        next_level_info = VIP_LEVELS[next_level]
        next_requirement = next_level_info["requirement"]
        next_privileges = [p for p in next_level_info["privileges"] if p not in current_privileges]
        
        # 计算升级进度
        progress = min(100, (current_total_bets / next_requirement) * 100)
    else:
        next_requirement = "已达最高等级"
        next_privileges = ["已拥有所有特权"]
        progress = 100
    
    # 构建特权文本
    privileges_text = "\n".join([f"• {p}" for p in current_privileges])
    next_privileges_text = "\n".join([f"• {p}" for p in next_privileges])
    
    # 构建VIP信息文本
    vip_text = VIP_INFO.format(
        user_id=user_id,
        vip_level=current_level,
        vip_name=current_name,
        progress=int(progress),
        total_bets=current_total_bets,
        balance=user_data["balance"],
        next_requirement=next_requirement,
        privileges=privileges_text,
        next_privileges=next_privileges_text
    )
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🎮 开始游戏", "callback_data": "play"},
                {"text": "🔙 返回", "callback_data": "back_to_menu"}
            ]
        ]
    }
    
    edit_message_text(chat_id, message_id, vip_text, reply_markup=keyboard)

def handle_leaderboard_callback(user_id: int, chat_id: int, message_id: int, data_manager: DataManager) -> None:
    """处理查看排行榜回调"""
    # 获取排行榜
    leaderboard = data_manager.get_leaderboard(metric="balance")
    
    # 构建排行榜文本
    if not leaderboard:
        leaderboard_text = """
🏆 *排行榜* 🏆

暂无数据。
        """
    else:
        leaderboard_items = []
        for i, user in enumerate(leaderboard, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            leaderboard_items.append(f"{medal} {user['name']}: {user['balance']} 金币")
        
        leaderboard_items_text = "\n".join(leaderboard_items)
        leaderboard_text = f"""
🏆 *余额排行榜* 🏆

{leaderboard_items_text}
        """
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🎮 开始游戏", "callback_data": "play"},
                {"text": "🔙 返回", "callback_data": "back_to_menu"}
            ]
        ]
    }
    
    edit_message_text(chat_id, message_id, leaderboard_text, reply_markup=keyboard)

def handle_admin_command(message: Dict[str, Any], data_manager: DataManager) -> None:
    """处理管理员命令"""
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message["text"]
    
    # 检查是否是管理员
    if user_id not in ADMIN_IDS:
        send_message(chat_id, "❌ 只有管理员才能使用此命令。")
        return
    
    # 处理 /addcoins 命令
    if text.startswith("/addcoins"):
        parts = text.split()
        if len(parts) == 3:
            try:
                target_id = int(parts[1])
                amount = int(parts[2])
                
                # 获取目标用户
                user_data = data_manager.get_user(target_id)
                
                if not user_data:
                    send_message(chat_id, f"❌ 用户 {target_id} 不存在。")
                    return
                
                # 更新余额
                new_balance, success = data_manager.update_balance(target_id, amount)
                
                if success:
                    send_message(chat_id, f"✅ 已为用户 {target_id} ({user_data['name']}) 添加 {amount} 金币。\n当前余额: {new_balance} 金币。")
                else:
                    send_message(chat_id, f"❌ 更新余额失败。")
            except ValueError:
                send_message(chat_id, "❌ 用法不正确。正确格式: /addcoins [用户ID] [金额]")
        else:
            send_message(chat_id, "❌ 用法不正确。正确格式: /addcoins [用户ID] [金额]")
    
    # 处理 /ban 命令
    elif text.startswith("/ban"):
        parts = text.split()
        if len(parts) == 2:
            try:
                target_id = int(parts[1])
                
                # 获取目标用户
                user_data = data_manager.get_user(target_id)
                
                if not user_data:
                    send_message(chat_id, f"❌ 用户 {target_id} 不存在。")
                    return
                
                # 封禁用户
                data_manager.ban_user(target_id)
                send_message(chat_id, f"✅ 已封禁用户 {target_id} ({user_data['name']})。")
            except ValueError:
                send_message(chat_id, "❌ 用法不正确。正确格式: /ban [用户ID]")
        else:
            send_message(chat_id, "❌ 用法不正确。正确格式: /ban [用户ID]")
    
    # 处理 /unban 命令
    elif text.startswith("/unban"):
        parts = text.split()
        if len(parts) == 2:
            try:
                target_id = int(parts[1])
                
                # 解除封禁
                success = data_manager.unban_user(target_id)
                
                if success:
                    send_message(chat_id, f"✅ 已解除封禁用户 {target_id}。")
                else:
                    send_message(chat_id, f"❌ 用户 {target_id} 未被封禁。")
            except ValueError:
                send_message(chat_id, "❌ 用法不正确。正确格式: /unban [用户ID]")
        else:
            send_message(chat_id, "❌ 用法不正确。正确格式: /unban [用户ID]")
    
    # 处理 /setdice 命令 - 设置下一局的骰子点数
    elif text.startswith("/setdice"):
        parts = text.split()
        # 首先检查是否是私聊或群组聊天
        is_group_chat = "chat" in message and message["chat"]["id"] < 0
        
        if len(parts) == 4:
            try:
                # 解析三个骰子点数
                dice1 = int(parts[1])
                dice2 = int(parts[2])
                dice3 = int(parts[3])
                
                # 验证点数是否有效 (1-6)
                if all(1 <= d <= 6 for d in [dice1, dice2, dice3]):
                    if is_group_chat:
                        # 在群组中设置该群组的骰子点数
                        group_id = message["chat"]["id"]
                        success = data_manager.set_fixed_dice(group_id, [dice1, dice2, dice3])
                        
                        if success:
                            # 发送确认消息
                            admin_message = f"""
✅ *骰子点数设置成功*

此群组下一局将使用以下点数:
🎲 {dice1} 🎲 {dice2} 🎲 {dice3}

总点数: {dice1 + dice2 + dice3}

注意: 此设置仅对下一局游戏有效
                            """
                            send_message(chat_id, admin_message)
                    else:
                        # 管理员在私聊中设置了骰子点数
                        # 提示需要指定群组ID
                        admin_message = f"""
⚠️ *警告*: 您在私聊中设置了骰子点数，但没有指定群组ID。

请使用以下格式在私聊中设置骰子点数:
/setdice [群组ID] [骰子1] [骰子2] [骰子3]

例如:
/setdice -1001234567890 3 4 5

或直接在目标群组中使用:
/setdice [骰子1] [骰子2] [骰子3]
                        """
                        send_message(chat_id, admin_message)
                else:
                    send_message(chat_id, "❌ 骰子点数必须在 1-6 之间")
            except ValueError:
                send_message(chat_id, "❌ 用法不正确。正确格式: /setdice [骰子1] [骰子2] [骰子3]")
                
        elif len(parts) == 5 and not is_group_chat:
            # 私聊中指定群组的格式: /setdice [群组ID] [骰子1] [骰子2] [骰子3]
            try:
                # 解析群组ID和骰子点数
                group_id = int(parts[1])
                dice1 = int(parts[2])
                dice2 = int(parts[3])
                dice3 = int(parts[4])
                
                # 验证点数是否有效 (1-6)
                if all(1 <= d <= 6 for d in [dice1, dice2, dice3]):
                    success = data_manager.set_fixed_dice(group_id, [dice1, dice2, dice3])
                    
                    if success:
                        # 发送确认消息
                        admin_message = f"""
✅ *骰子点数设置成功*

群组 {group_id} 的下一局将使用以下点数:
🎲 {dice1} 🎲 {dice2} 🎲 {dice3}

总点数: {dice1 + dice2 + dice3}

注意: 此设置仅对下一局游戏有效
                        """
                        send_message(chat_id, admin_message)
                else:
                    send_message(chat_id, "❌ 骰子点数必须在 1-6 之间")
            except ValueError:
                send_message(chat_id, "❌ 用法不正确。正确格式: /setdice [群组ID] [骰子1] [骰子2] [骰子3]")
        else:
            if is_group_chat:
                send_message(chat_id, "❌ 用法不正确。正确格式: /setdice [骰子1] [骰子2] [骰子3]")
            else:
                send_message(chat_id, "❌ 用法不正确。\n群组中格式: /setdice [骰子1] [骰子2] [骰子3]\n私聊中格式: /setdice [群组ID] [骰子1] [骰子2] [骰子3]")
                        
    # 处理 /stats 命令
    elif text == "/adminstats":
        # 显示全局统计信息
        global_stats = data_manager.global_stats
        
        stats_text = f"""
📊 *全局统计信息* 📊

总游戏次数: {global_stats['total_games']}
总投注额: {global_stats['total_bets']} 金币
总赢取金额: {global_stats['total_winnings']} 金币

最大赢取记录:
用户ID: {global_stats['biggest_win']['user_id'] or '无'}
金额: {global_stats['biggest_win']['amount']} 金币
日期: {global_stats['biggest_win']['date'] or '无'}

总用户数: {len(data_manager.users)}
        """
        
        send_message(chat_id, stats_text)
    
    # 处理 /stop 命令 - 停止群组游戏
    elif text == "/stop" or text == "/stopgame":
        # 只有管理员或群组管理员可以停止游戏
        if "chat" in message and message["chat"]["id"] < 0:  # 群组ID是负数
            # 检查用户是否有权限
            if user_id in ADMIN_IDS:
                has_permission = True
            else:
                # 检查用户是否是群组管理员
                try:
                    chat_member = requests.get(
                        f"{API_URL}/getChatMember",
                        params={
                            "chat_id": chat_id,
                            "user_id": user_id
                        }
                    ).json()
                    
                    if chat_member.get("ok") and chat_member.get("result"):
                        status = chat_member["result"]["status"]
                        has_permission = status in ["creator", "administrator"]
                    else:
                        has_permission = False
                except Exception:
                    has_permission = False
            
            if has_permission:
                # 获取群组游戏状态
                group_game = data_manager.get_group_game(chat_id)
                
                if group_game['state'] != GROUP_GAME_IDLE:
                    # 设置状态为空闲
                    group_game['state'] = GROUP_GAME_IDLE
                    data_manager.update_group_game(chat_id, group_game)
                    
                    send_message(chat_id, "🛑 *游戏已停止* 🛑\n\n游戏已被管理员终止。发送 /start 重新开始游戏。")
                else:
                    send_message(chat_id, "❌ 当前没有正在进行的游戏。")
            else:
                send_message(chat_id, "❌ 只有管理员可以停止游戏。")
        else:
            send_message(chat_id, "❌ 此命令只能在群组中使用。")

# ============== 主函数 ==============

def create_gif_with_text(text: str, output_path: str) -> bool:
    """
    在GIF上添加文字
    返回：是否成功
    """
    try:
        # 检查字体文件是否存在
        if not os.path.exists(FONT_PATH):
            logger.error(f"字体文件不存在: {FONT_PATH}")
            return False

        # 创建字体对象
        font = ImageFont.truetype(FONT_PATH, 36)
        
        # 创建一个空白图片用于测量文本大小
        temp_img = Image.new('RGB', (1, 1))
        temp_draw = ImageDraw.Draw(temp_img)
        text_bbox = temp_draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        # 创建一个新的图片，大小根据文本调整
        img_width = text_width + 40  # 添加一些边距
        img_height = text_height + 40
        
        # 创建新图片并添加文字
        img = Image.new('RGBA', (img_width, img_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        
        # 计算文字位置（居中）
        x = (img_width - text_width) // 2
        y = (img_height - text_height) // 2
        
        # 绘制文字
        draw.text((x, y), text, font=font, fill=(0, 0, 0, 255))
        
        # 保存为GIF
        img.save(output_path, 'GIF')
        return True
        
    except Exception as e:
        logger.error(f"创建GIF出错: {e}")
        return False

def main():
    """主程序入口"""
    print("正在启动骰子游戏机器人...")
    
    # 创建数据管理器
    data_manager = DataManager()
    
    # 用于追踪最后处理的更新ID
    last_update_id = None
    
    try:
        # 主循环
        while True:
            try:
                # 获取更新
                updates = get_updates(offset=last_update_id)
                
                for update in updates:
                    # 更新最后处理的更新ID
                    last_update_id = update["update_id"] + 1
                    
                    # 处理消息
                    if "message" in update:
                        message = update["message"]
                        
                        # 检查是否是骰子消息
                        if "dice" in message:
                            handle_dice_message(message, data_manager)
                            continue
                        
                        # 忽略其他非文本消息
                        if "text" not in message:
                            continue
                        
                        # 获取基本信息
                        text = message["text"]
                        
                        # 处理命令
                        if text.startswith("/"):
                            if text.startswith("/start"):
                                handle_start_command(message, data_manager)
                            elif text.startswith("/help"):
                                handle_help_command(message, data_manager)
                            elif text.startswith("/rules"):
                                handle_rules_command(message, data_manager)
                            elif text.startswith("/play"):
                                handle_play_command(message, data_manager)
                            elif text.startswith("/balance"):
                                handle_balance_command(message, data_manager)
                            elif text.startswith("/history"):
                                # 处理历史记录查询
                                user_id = message["from"]["id"]
                                chat_id = message["chat"]["id"]
                                result = send_message(chat_id, "正在加载历史数据...")
                                if result.get("ok"):
                                    message_id = result["result"]["message_id"]
                                    handle_history_callback(user_id, chat_id, message_id, data_manager)
                            elif text.startswith("/addcoins") or text.startswith("/ban") or text.startswith("/unban") or text == "/adminstats" or text.startswith("/setdice"):
                                handle_admin_command(message, data_manager)
                            # 其他命令...
                        else:
                            # 处理非命令消息
                            # 检查是否在输入投注金额状态
                            user_id = message["from"]["id"]
                            text = message["text"]
                            
                            # 检查是否是"反水"请求
                            if "chat" in message and message["chat"]["id"] < 0 and text.strip() == "反水":
                                # 获取用户数据
                                user_data = data_manager.get_user(user_id)
                                chat_id = message["chat"]["id"]
                                
                                if not user_data:
                                    send_message(chat_id, "❌ 您还没有注册账户，请先使用 /start 命令创建账户", 
                                                reply_to_message_id=message["message_id"])
                                    continue
                                
                                # 计算反水金额
                                rebate_amount = data_manager.calculate_rebate(user_id)
                                
                                if rebate_amount <= 0:
                                    send_message(chat_id, "❌ 您暂时没有可领取的反水", 
                                                reply_to_message_id=message["message_id"])
                                    continue
                                
                                # 添加反水
                                new_balance, success = data_manager.update_balance(user_id, rebate_amount)
                                
                                if success:
                                    # 记录此次反水
                                    data_manager.rebate_records[user_id] = {
                                        "last_claimed": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        "total_bets": user_data["total_bets"],
                                        "amount": rebate_amount
                                    }
                                    
                                    # 发送反水成功消息
                                    rebate_message = f"""
💰 *反水成功* 💰

用户: {user_data['name']}
ID: {user_id}
反水金额: {rebate_amount} 金币
当前余额: {new_balance} 金币

投注满100金币即可获得1金币反水
祝您游戏愉快！
                                    """
                                    
                                    send_message(chat_id, rebate_message, reply_to_message_id=message["message_id"])
                                else:
                                    send_message(chat_id, "❌ 反水失败，请稍后再试", 
                                                reply_to_message_id=message["message_id"])
                            
                            # 检查是否是红包命令
                            elif "chat" in message and text.strip().startswith("hb "):
                                chat_id = message["chat"]["id"]
                                user_data = data_manager.get_user(user_id)
                                
                                if not user_data:
                                    send_message(chat_id, "❌ 您还没有注册账户，请先使用 /start 命令创建账户", 
                                                reply_to_message_id=message["message_id"])
                                    continue
                                
                                try:
                                    parts = text.strip().split()
                                    
                                    # 判断是群组红包还是私人红包
                                    is_single_target = "reply_to_message" in message
                                    
                                    if is_single_target:
                                        # 私人红包，只需要金额: hb 金额 或 hb 金额o
                                        if len(parts) != 2:
                                            send_message(chat_id, "❌ 私人红包格式错误，正确格式: hb [金额] 或 hb [金额]o", 
                                                        reply_to_message_id=message["message_id"])
                                            continue
                                        
                                        # 检查金额是否带o后缀
                                        amount_str = parts[1]
                                        
                                        if amount_str.endswith('o'):
                                            amount_str = amount_str[:-1]  # 移除o后缀
                                        
                                        try:
                                            amount = int(amount_str)
                                        except ValueError:
                                            send_message(chat_id, "❌ 红包金额必须是正整数", 
                                                        reply_to_message_id=message["message_id"])
                                            continue
                                        
                                        if amount <= 0:
                                            send_message(chat_id, "❌ 红包金额必须大于0", 
                                                        reply_to_message_id=message["message_id"])
                                            continue
                                        
                                        # 检查余额是否足够
                                        if user_data["balance"] < amount:
                                            send_message(chat_id, f"❌ 您的余额不足，当前余额: {user_data['balance']} 金币", 
                                                        reply_to_message_id=message["message_id"])
                                            continue
                                        
                                        # 扣除用户余额
                                        new_balance, success = data_manager.update_balance(user_id, -amount)
                                        
                                        if not success:
                                            send_message(chat_id, "❌ 发送红包失败，请稍后再试", 
                                                        reply_to_message_id=message["message_id"])
                                            continue
                                        
                                        try:
                                            target_user_id = message["reply_to_message"]["from"]["id"]
                                            target_name = message["reply_to_message"]["from"]["first_name"]
                                            
                                            # 确保目标用户存在
                                            target_user = data_manager.get_user(target_user_id)
                                            if not target_user:
                                                # 如果用户不存在，创建新用户
                                                data_manager.add_user(target_user_id, target_name)
                                            
                                            # 创建私人红包
                                            hongbao_id = f"{chat_id}_{int(time.time())}_private"
                                            
                                            # 初始化私人红包
                                            hongbao_info = {
                                                "sender_id": user_id,
                                                "sender_name": user_data["name"],
                                                "target_id": target_user_id,
                                                "target_name": target_name,
                                                "amount": amount,
                                                "is_claimed": False,
                                                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                            }
                                            
                                            # 保存红包信息
                                            if not hasattr(data_manager, "hongbao"):
                                                data_manager.hongbao = {}
                                            
                                            data_manager.hongbao[hongbao_id] = hongbao_info
                                            
                                            # 创建抢红包按钮
                                            grab_button = {
                                                "inline_keyboard": [
                                                    [
                                                        {
                                                            "text": "🧧 领取红包 🧧",
                                                            "callback_data": f"grab_private_hongbao:{hongbao_id}"
                                                        }
                                                    ]
                                                ]
                                            }
                                            
                                            # 发送红包提示，使用GIF动画
                                            hongbao_message = f"""
🧧 *私人红包* 🧧

{user_data['name']} 发送了一个红包给 {target_name}
金额: {amount} 金币

请点击下方按钮领取！
                                            """
                                            # 使用GIF动画发送红包
                                            result = send_animation(
                                                chat_id, 
                                                "attached_assets/GIf_hb_02.mp4", 
                                                caption=hongbao_message, 
                                                reply_markup=grab_button
                                            )
                                            
                                            # 保存消息ID，用于后续更新
                                            if result.get("ok"):
                                                message_id = result["result"]["message_id"]
                                                hongbao_info["message_id"] = message_id
                                                data_manager.hongbao[hongbao_id] = hongbao_info
                                            
                                        except Exception as e:
                                            logger.error(f"处理私人红包错误: {e}")
                                            send_message(chat_id, "❌ 发送私人红包失败，请确保回复了有效的用户消息", 
                                                        reply_to_message_id=message["message_id"])
                                            # 退还金币
                                            data_manager.update_balance(user_id, amount)
                                    else:
                                        # 群组红包，需要人数和金额: hb 人数 金额 或 hb 人数 金额o
                                        if len(parts) != 3:
                                            send_message(chat_id, "❌ 群组红包格式错误，正确格式: hb [人数] [金额] 或 hb [人数] [金额]o", 
                                                        reply_to_message_id=message["message_id"])
                                            continue
                                        
                                        people_count = int(parts[1])
                                        
                                        # 检查金额是否带o后缀
                                        amount_str = parts[2]
                                        
                                        if amount_str.endswith('o'):
                                            amount_str = amount_str[:-1]  # 移除o后缀
                                        
                                        try:
                                            amount = int(amount_str)
                                        except ValueError:
                                            send_message(chat_id, "❌ 红包金额必须是正整数", 
                                                        reply_to_message_id=message["message_id"])
                                            continue
                                        
                                        # 检查人数和金额的有效性
                                        if people_count <= 0:
                                            send_message(chat_id, "❌ 红包人数必须大于0", 
                                                        reply_to_message_id=message["message_id"])
                                            continue
                                        
                                        if amount <= 0:
                                            send_message(chat_id, "❌ 红包金额必须大于0", 
                                                        reply_to_message_id=message["message_id"])
                                            continue
                                        
                                        # 检查余额是否足够
                                        if user_data["balance"] < amount:
                                            send_message(chat_id, f"❌ 您的余额不足，当前余额: {user_data['balance']} 金币", 
                                                        reply_to_message_id=message["message_id"])
                                            continue
                                        
                                        # 扣除用户余额
                                        new_balance, success = data_manager.update_balance(user_id, -amount)
                                        
                                        if not success:
                                            send_message(chat_id, "❌ 发送红包失败，请稍后再试", 
                                                        reply_to_message_id=message["message_id"])
                                            continue
                                        
                                        # 群组红包
                                        # 保存红包信息，等待用户领取
                                        hongbao_id = f"{chat_id}_{int(time.time())}_group"
                                        
                                        # 生成随机红包金额
                                        random_amounts = []
                                        remaining = amount
                                        
                                        # 为每个人分配随机金额，最后一个人获得剩余金额
                                        for i in range(people_count - 1):
                                            # 确保每个人至少能得到1金币
                                            max_possible = remaining - (people_count - i - 1)
                                            if max_possible <= 1:
                                                # 如果剩余金额不够分，就给最低1金币
                                                coin = 1
                                            else:
                                                # 随机分配，但至少1金币
                                                coin = random.randint(1, max_possible)
                                            random_amounts.append(coin)
                                            remaining -= coin
                                        
                                        # 最后一个人获得剩余的全部金额
                                        random_amounts.append(remaining)
                                        
                                        # 打乱金额顺序，这样先抢的人不一定能得到更多
                                        random.shuffle(random_amounts)
                                        
                                        # 初始化红包信息
                                        hongbao_info = {
                                            "sender_id": user_id,
                                            "sender_name": user_data["name"],
                                            "total_amount": amount,
                                            "amounts": random_amounts,  # 随机金额列表
                                            "remaining_amount": amount,
                                            "total_count": people_count,
                                            "remaining_count": people_count,
                                            "receivers": [],
                                            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                        }
                                        
                                        # 保存红包信息
                                        if not hasattr(data_manager, "hongbao"):
                                            data_manager.hongbao = {}
                                        
                                        data_manager.hongbao[hongbao_id] = hongbao_info
                                        
                                        # 创建抢红包按钮
                                        grab_button = {
                                            "inline_keyboard": [
                                                [
                                                    {
                                                        "text": "🧧 抢红包 🧧",
                                                        "callback_data": f"grab_hongbao:{hongbao_id}"
                                                    }
                                                ]
                                            ]
                                        }
                                        
                                        # 发送红包提示，使用GIF动画
                                        hongbao_message = f"""
🧧 *红包来啦* 🧧

{user_data['name']} 发送了一个金额红包
总金额: {amount} 金币
数量: {people_count} 个

点击下方按钮抢红包！
                                        """
                                        # 使用GIF动画发送红包
                                        result = send_animation(
                                            chat_id, 
                                            "attached_assets/GIf_hb_02.mp4", 
                                            caption=hongbao_message, 
                                            reply_markup=grab_button
                                        )
                                        
                                        # 保存消息ID，用于后续更新
                                        if result.get("ok"):
                                            message_id = result["result"]["message_id"]
                                            hongbao_info["message_id"] = message_id
                                            data_manager.hongbao[hongbao_id] = hongbao_info
                                        
                                except ValueError:
                                    send_message(chat_id, "❌ 红包格式错误，请检查人数和金额是否为正整数", 
                                                reply_to_message_id=message["message_id"])
                                except Exception as e:
                                    logger.error(f"处理红包错误: {e}")
                                    send_message(chat_id, "❌ 发送红包失败，请稍后再试", 
                                                reply_to_message_id=message["message_id"])
                                    
                            # 检查是否是"抢"红包的请求（已替换为按钮形式）
                            elif "chat" in message and message["chat"]["id"] < 0 and text.strip() == "抢":
                                chat_id = message["chat"]["id"]
                                send_message(chat_id, "请点击红包下方的按钮来抢红包！", 
                                            reply_to_message_id=message["message_id"])
                                
                            # 管理员清除余额命令
                            elif "chat" in message and text.strip().startswith("清除余额") and user_id in ADMIN_IDS:
                                chat_id = message["chat"]["id"]
                                
                                # 解析命令
                                parts = text.strip().split()
                                
                                # 检查是否指定了用户ID
                                if len(parts) >= 2:
                                    try:
                                        target_user_id = int(parts[1])
                                        target_user = data_manager.get_user(target_user_id)
                                        
                                        if target_user:
                                            # 重置指定用户的余额
                                            old_balance = target_user["balance"]
                                            data_manager.users[str(target_user_id)]["balance"] = 0
                                            
                                            # 发送确认消息
                                            send_message(chat_id, f"✅ 已清除用户 {target_user['name']} (ID: {target_user_id}) 的余额\n原余额: {old_balance} 金币", 
                                                        reply_to_message_id=message["message_id"])
                                        else:
                                            send_message(chat_id, f"❌ 用户ID {target_user_id} 不存在", 
                                                        reply_to_message_id=message["message_id"])
                                    except ValueError:
                                        send_message(chat_id, "❌ 无效的用户ID，请提供正确的数字ID", 
                                                    reply_to_message_id=message["message_id"])
                                else:
                                    # 清除所有用户的余额
                                    user_count = 0
                                    for user_id_str in data_manager.users:
                                        if data_manager.users[user_id_str]["balance"] > 0:
                                            data_manager.users[user_id_str]["balance"] = 0
                                            user_count += 1
                                    
                                    # 发送确认消息
                                    send_message(chat_id, f"✅ 已清除所有用户的余额，共影响 {user_count} 个用户", 
                                                reply_to_message_id=message["message_id"])
                            
                            # 反水命令
                            elif "chat" in message and text.strip().lower() == "fs":
                                chat_id = message["chat"]["id"]
                                user_data = data_manager.get_user(user_id)
                                
                                if not user_data:
                                    send_message(chat_id, "❌ 您还没有注册账户，请先使用 /start 命令创建账户", 
                                                reply_to_message_id=message["message_id"])
                                    continue
                                
                                # 计算并领取反水
                                rebate_amount, success = data_manager.claim_rebate(user_id)
                                
                                if success:
                                    rebate_message = f"✅ 反水领取成功！\n反水金额: {rebate_amount} 金币\n当前余额: {user_data['balance']} 金币"
                                else:
                                    rebate_message = "❌ 暂无可领取的反水"
                                
                                send_message(chat_id, rebate_message, reply_to_message_id=message["message_id"])
                            
                            # 查询余额命令
                            elif "chat" in message and text.strip() == "ye":
                                chat_id = message["chat"]["id"]
                                user_data = data_manager.get_user(user_id)
                                
                                if not user_data:
                                    send_message(chat_id, "❌ 您还没有注册账户，请先使用 /start 命令创建账户", 
                                                reply_to_message_id=message["message_id"])
                                    continue
                                
                                # 发送余额信息
                                balance_message = f"""
💰 *余额查询* 💰

用户: {user_data['name']}
ID: {user_id}
当前余额: {user_data['balance']} 金币
VIP等级: {user_data['vip_level']} 级
总投注: {user_data['total_bets']} 金币
总赢取: {user_data['total_winnings']} 金币
                                """
                                send_message(chat_id, balance_message, reply_to_message_id=message["message_id"])
                            
                            # 检查是否在输入投注金额状态
                            elif user_id in USER_STATES and USER_STATES[user_id]["state"] == STATE_ENTERING_BET_AMOUNT:
                                handle_bet_amount_message(message, data_manager)
                            # 检查是否是群组投注消息
                            elif "chat" in message and message["chat"]["id"] < 0:  # 群组ID是负数
                                handle_group_bet_message(message, data_manager)
                    
                    # 处理回调查询
                    elif "callback_query" in update:
                        handle_callback_query(update["callback_query"], data_manager)
                
                # 短暂休眠避免过度轮询
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"获取更新异常: {e}")
                time.sleep(1)
    
    except KeyboardInterrupt:
        print("正在关闭骰子游戏机器人...")
        data_manager.save_data()
        print("数据已保存。再见！")

if __name__ == "__main__":
    main()