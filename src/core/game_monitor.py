"""
Game Mode Monitor for Neura (Milestone 11).
Monitors system for gaming processes and manages VRAM accordingly.
"""
import logging
import psutil
import time
import platform
from typing import Set, Optional

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

KNOWN_GAMES = {
    "linux": ["steam", "lutris", "heroic", "dolphin-emu", "pcsx2", "rpcs3", "yuzu", "ryujinx"],
    "windows": ["steam.exe", "epicgameslauncher.exe", "origin.exe", "battle.net.exe"]
}

class GameMonitor:
    def __init__(self, check_interval: float = 5.0):
        self.check_interval = check_interval
        self.is_gaming = False
        self.current_game: Optional[str] = None
        
    def detect_running_games(self) -> Set[str]:
        sys_os = "linux" if platform.system().lower() == "linux" else "windows"
        known = KNOWN_GAMES.get(sys_os, [])
        running_games = set()
        for proc in psutil.process_iter(['name']):
            try:
                name = proc.info['name'].lower() if proc.info['name'] else ""
                for game in known:
                    if game.lower() in name:
                        running_games.add(proc.info['name'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return running_games
    
    def check_once(self) -> bool:
        games = self.detect_running_games()
        if games:
            if not self.is_gaming:
                self.is_gaming = True
                self.current_game = list(games)[0]
                logger.info(f"🎮 Game detected: {self.current_game}")
            return True
        else:
            if self.is_gaming:
                logger.info(f"🛑 Game ended: {self.current_game}")
                self.is_gaming = False
                self.current_game = None
            return False
    
    def monitor_loop(self, on_game_start=None, on_game_end=None, stop_event=None):
        logger.info("👁️ Game Monitor started...")
        import threading
        stop_event = stop_event or threading.Event()
        while not stop_event.is_set():
            try:
                previous = self.is_gaming
                is_gaming = self.check_once()
                if is_gaming and not previous and on_game_start:
                    on_game_start(self.current_game)
                elif not is_gaming and previous and on_game_end:
                    on_game_end()
                stop_event.wait(self.check_interval)
            except KeyboardInterrupt:
                logger.info("Game Monitor stopped.")
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                stop_event.wait(self.check_interval)
