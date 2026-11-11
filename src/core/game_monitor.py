"""Compatibility facade over corroborated game identity (launchers are not games)."""
import os,threading
from src.core.resource_detection import LinuxSampler,game_processes

class GameMonitor:
    def __init__(self,check_interval=2.0,process_rules=(),exclusions=()):
        self.check_interval=check_interval;self.process_rules=list(process_rules);self.exclusions=list(exclusions);self.is_gaming=False;self.current_game=None;self.identities=[]
        self.sampler=LinuxSampler(lambda:{os.getpid()},lambda:None)
    def detect_running_games(self):
        sample=self.sampler.sample();self.identities=game_processes(sample['processes'],self.process_rules,self.exclusions,{os.getpid()})
        return {g['name'] for g in self.identities}
    def check_once(self):
        games=self.detect_running_games();self.is_gaming=bool(games);self.current_game=sorted(games)[0] if games else None;return self.is_gaming
    def monitor_loop(self,on_game_start=None,on_game_end=None,stop_event=None):
        stop_event=stop_event or threading.Event()
        while not stop_event.is_set():
            previous=self.is_gaming
            try:
                current=self.check_once()
                if current and not previous and on_game_start:on_game_start(self.current_game)
                elif previous and not current and on_game_end:on_game_end()
            except (OSError,ValueError):pass
            stop_event.wait(self.check_interval)
