"""
Test Game Mode Monitor (Milestone 11).
"""
import pathlib
import sys
import pytest
from unittest.mock import patch, MagicMock

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from core.game_monitor import GameMonitor

@pytest.fixture
def monitor():
    return GameMonitor(check_interval=0.1)

def test_no_games_running(monitor):
    with patch('psutil.process_iter') as mock_iter:
        mock_iter.return_value = []
        result = monitor.check_once()
        assert result is False
        assert monitor.is_gaming is False

def test_game_detected(monitor):
    with patch('psutil.process_iter') as mock_iter:
        mock_proc = MagicMock()
        mock_proc.info = {'name': 'steam'}
        mock_iter.return_value = [mock_proc]
        result = monitor.check_once()
        assert result is True
        assert monitor.is_gaming is True
        assert monitor.current_game == 'steam'

def test_game_ended(monitor):
    monitor.is_gaming = True
    monitor.current_game = 'steam'
    with patch('psutil.process_iter') as mock_iter:
        mock_iter.return_value = []
        result = monitor.check_once()
        assert result is False
        assert monitor.is_gaming is False
        assert monitor.current_game is None
