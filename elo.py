import math
import os
import sqlite3

from dataclasses import dataclass
from datetime import datetime


DB_NAME = os.environ.get("DB", "live-test.db")
K_FACTOR = 32

RESET = "\033[0m"
BOLD = "\033[1m"
YELLOW = "\033[93m"
WHITE = "\033[97m"
BLUE = "\033[94m"
GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"

class Cancelled(Exception):
    pass

def prompt(text):
    val = input(f"{BOLD}> {text}{RESET} ").strip()
    if val.lower() == 'c':
        raise Cancelled
    return val

def print_header(title):
    print(f"{BOLD}{CYAN}========== {title} =========={RESET}")

def print_success(msg):
    print(f"{GREEN}{msg}{RESET}")

def print_error(msg):
    print(f"{RED}Error: {msg}{RESET}")

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS players (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        elo REAL NOT NULL,
                        created_at DATETIME NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS games (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        yellow_score INTEGER,
                        white_score INTEGER,
                        created_at DATETIME NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS game_players (
                        game_id INTEGER,
                        player_name TEXT,
                        team TEXT,
                        FOREIGN KEY (game_id) REFERENCES games(id))''')

@dataclass
class Player:
    id: int
    name: str
    elo: float
    created_at: str

@dataclass
class Game:
    id: int
    yellow_score: int
    white_score: int
    created_at: str

@dataclass
class GamePlayer:
    game_id: int
    player_name: str
    team: str

class EloSystem:
    def __init__(self):
        init_db()

    def add_player(self, name, elo=1000):
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            try:
                c.execute("INSERT INTO players (name, elo, created_at) VALUES (?, ?, ?)", (name, elo, created_at))
                conn.commit()
                print_success("Player added.")
            except sqlite3.IntegrityError:
                print_error("Player already exists.")

    def remove_player(self, name):
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("DELETE FROM players WHERE name = ?", (name,))
            conn.commit()
            print_success("Player removed.")

    def set_player_elo(self, name, elo):
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("UPDATE players SET elo = ? WHERE name = ?", (elo, name))
            conn.commit()
            print_success("ELO updated.")

    def get_all_players(self):
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT id, name, elo, created_at FROM players ORDER BY name ASC")
            return [Player(*row) for row in c.fetchall()]

    def get_players_by_names(self, names):
        with sqlite3.connect(DB_NAME) as conn:
            q = ','.join('?' for _ in names)
            c = conn.cursor()
            c.execute(f"SELECT id, name, elo, created_at FROM players WHERE name IN ({q})", names)
            return [Player(*row) for row in c.fetchall()]

    def create_game(self, yellow_players, white_players, yellow_score, white_score):
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        yellow_objs = self.get_players_by_names(yellow_players)
        white_objs = self.get_players_by_names(white_players)

        # Calculate the average ELO of each team
        yellow_avg = sum(p.elo for p in yellow_objs) / len(yellow_objs)
        white_avg = sum(p.elo for p in white_objs) / len(white_objs)

        # Calculate expected score for each team
        expected_yellow = 1 / (1 + 10 ** ((white_avg - yellow_avg) / 400))
        expected_white = 1 - expected_yellow

        # Determine actual outcomes
        if yellow_score > white_score:
            actual_yellow, actual_white = 1, 0
        elif yellow_score < white_score:
            actual_yellow, actual_white = 0, 1
        else:
            actual_yellow = actual_white = 0.5

        # Game margin (used for scaling the Elo adjustment)
        margin = abs(yellow_score - white_score)
        multiplier = math.log(margin + 1) * (2.2 / ((abs(yellow_avg - white_avg) * 0.001) + 2.2))

        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()

            # Update ELO for Yellow team
            for p in yellow_objs:
                expected_result = 1 / (1 + 10 ** ((white_avg - p.elo) / 400))
                delta = K_FACTOR * multiplier * (actual_yellow - expected_result)
                new_elo = p.elo + delta
                delta_str = f"+{delta:.2f}" if delta > 0 else f"{delta:.2f}"
                print(f"{p.name}: {delta_str}")
                c.execute("UPDATE players SET elo = ? WHERE id = ?", (new_elo, p.id))

            # Update ELO for White team
            for p in white_objs:
                expected_result = 1 / (1 + 10 ** ((yellow_avg - p.elo) / 400))
                delta = K_FACTOR * multiplier * (actual_white - expected_result)
                new_elo = p.elo + delta
                delta_str = f"+{delta:.2f}" if delta > 0 else f"{delta:.2f}"
                print(f"{p.name}: {delta_str}")
                c.execute("UPDATE players SET elo = ? WHERE id = ?", (new_elo, p.id))

            # Insert game record
            c.execute("INSERT INTO games (yellow_score, white_score, created_at) VALUES (?, ?, ?)",
                    (yellow_score, white_score, created_at))
            game_id = c.lastrowid

            # Insert game players into the game_players table
            for name in yellow_players:
                c.execute("INSERT INTO game_players (game_id, player_name, team) VALUES (?, ?, 'yellow')",
                        (game_id, name))
            for name in white_players:
                c.execute("INSERT INTO game_players (game_id, player_name, team) VALUES (?, ?, 'white')",
                        (game_id, name))

            conn.commit()


    def auto_match(self, active_names):
        from random import shuffle
        shuffle(active_names)
        half = len(active_names) // 2
        return active_names[:half], active_names[half:]

    def get_all_games(self):
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT id, yellow_score, white_score, created_at FROM games ORDER BY created_at DESC")
            return [Game(*row) for row in c.fetchall()]

    def get_game_players(self, game_id):
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT game_id, player_name, team FROM game_players WHERE game_id = ?", (game_id,))
            return [GamePlayer(*row) for row in c.fetchall()]

    def show_all_games(self):
        games = self.get_all_games()
        for game in games:
            players = self.get_game_players(game.id)
            yellow_team = [gp.player_name for gp in players if gp.team == 'yellow']
            white_team = [gp.player_name for gp in players if gp.team == 'white']
            print(f"\n{BOLD}Game {game.id}{RESET} - {game.created_at}")
            print(f"  [{game.yellow_score}] {YELLOW}Yellow:{RESET}\t{', '.join(yellow_team)}")
            print(f"  [{game.white_score}] {WHITE}White:{RESET}\t{', '.join(white_team)}")

    def rename_player(self, old_name, new_name):
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            try:
                c.execute("UPDATE players SET name = ? WHERE name = ?", (new_name, old_name))
                c.execute("UPDATE game_players SET player_name = ? WHERE player_name = ?", (new_name, old_name))
                conn.commit()
                print_success("Player renamed.")
            except sqlite3.IntegrityError:
                print_error("New name already exists.")

class Menu:
    def __init__(self, system):
        self.system = system
        self.commands = {
            '1': ('Add Player', self.add_player),
            '2': ('Remove Player', self.remove_player),
            '3': ('Set Player ELO', self.set_player_elo),
            '4': ('Show All Players', self.show_all_players),
            '5': ('Create Game', self.create_game),
            '6': ('Auto Match Teams', self.auto_match_teams),
            '7': ('Show Game History', self.show_game_history),
            '8': ('Rename Player', self.rename_player),
            'q': ('Exit', self.exit)
        }

    def display_menu(self):
        print(f"""
{BOLD}{BLUE}=====================================
        FOOTBALL ELO MANAGEMENT
====================================={RESET}
""")
        for key, (desc, _) in self.commands.items():
            print(f" {YELLOW}{key}.{RESET} {desc}")
        print(f"{BLUE}====================================={RESET}")

    def run(self):
        while True:
            self.display_menu()
            choice = prompt("Choose option:")
            print()

            if choice in self.commands:
                try:
                    self.commands[choice][1]()
                except Exception as e:
                    print_error(f"Error: {str(e)}")
            else:
                print_error("Invalid choice.")

    def add_player(self):
        name = prompt("Player name:")
        elo = prompt("ELO (default: 1000):")
        elo = float(elo) if elo else 1000
        self.system.add_player(name, elo)

    def remove_player(self):
        name = prompt("Player name:")
        self.system.remove_player(name)

    def set_player_elo(self):
        name = prompt("Player name:")
        elo = float(prompt("New ELO:"))
        self.system.set_player_elo(name, elo)

    def show_all_players(self):
        print_header("Player List")
        for p in self.system.get_all_players():
            print(f"{BOLD}{p.name}{RESET} - {round(p.elo, 2)} (Created: {p.created_at})")
        _ = input()

    def create_game(self):
        y_team = prompt("Yellow team (comma separated):").split(',')
        w_team = prompt("White team (comma separated):").split(',')
        y_score = int(prompt("Yellow score:"))
        w_score = int(prompt("White score:"))
        self.system.create_game(y_team, w_team, y_score, w_score)

    def auto_match_teams(self):
        names = prompt("Active players (comma separated):").split(',')
        yellow, white = self.system.auto_match(names)
        print_header("Auto-match Result")
        print(f"{YELLOW}Yellow:{RESET} {', '.join(yellow)}")
        print(f"{WHITE}White:{RESET} {', '.join(white)}")

    def show_game_history(self):
        print_header("Game History")
        self.system.show_all_games()
        _ = input()

    def rename_player(self):
        old_name = prompt("Current player name:")
        new_name = prompt("New player name:")
        self.system.rename_player(old_name, new_name)

    def exit(self):
        print("Exiting the system.")
        quit()

if __name__ == '__main__':
    system = EloSystem()
    menu = Menu(system)
    menu.run()
