"""
Neura System Monitor (T-0306)
Real-time monitoring of CPU, GPU, RAM usage.
Updates state.monitor_data every second.
"""
import subprocess
import threading
import time
import json
import psutil
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from state import get_state


class SystemMonitor:
    """Monitors system resources in background thread."""
    
    def __init__(self):
        self.running = False
        self.thread = None
        self.state = get_state()
    
    def get_gpu_stats(self):
        """Query GPU utilization and VRAM from PowerShell."""
        ps_script = r"""
        $eng = Get-Counter '\GPU Engine(*engtype_Compute*)\Utilization Percentage' -ErrorAction SilentlyContinue
        $mem = Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage' -ErrorAction SilentlyContinue
        
        $compute_util = 0.0
        if ($eng) {
            $vals = $eng.CounterSamples | ForEach-Object { $_.CookedValue }
            $compute_util = ($vals | Measure-Object -Maximum).Maximum
        }
        
        $vram_bytes = 0
        if ($mem) {
            foreach ($s in $mem.CounterSamples) {
                $vram_bytes += $s.CookedValue
            }
        }
        $vram_mb = $vram_bytes / 1MB
        
        [pscustomobject]@{
            gpu_compute = $compute_util
            vram_mb = $vram_mb
        } | ConvertTo-Json -Compress
        """
        
        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps_script],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout.strip())
                return {
                    'gpu_percent': float(data.get('gpu_compute', 0)),
                    'vram_used_mb': float(data.get('vram_mb', 0))
                }
        except Exception as e:
            pass
        
        return {'gpu_percent': 0.0, 'vram_used_mb': 0.0}
    
    def update_once(self):
        """Collect all metrics and update state."""
        # CPU and RAM
        cpu_percent = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        ram_used_gb = ram.used / (1024**3)
        ram_total_gb = ram.total / (1024**3)
        ram_percent = ram.percent
        self.state.update_monitor(
            cpu_percent=cpu_percent,
            ram_percent=ram_percent,
            ram_used_gb=ram_used_gb,
            ram_total_gb=ram_total_gb,
        )
        
        # GPU
        gpu_stats = self.get_gpu_stats()
        gpu_percent = gpu_stats['gpu_percent']
        vram_used_mb = gpu_stats['vram_used_mb']
        vram_used_gb = vram_used_mb / 1024
        
        # Update state
        self.state.update_monitor(
            cpu_percent=cpu_percent,
            ram_percent=ram_percent,
            ram_used_gb=ram_used_gb,
            ram_total_gb=ram_total_gb,
            gpu_percent=gpu_percent,
            vram_used_gb=vram_used_gb,
            active_gpus=['RX 9060 XT', 'RX 580']
        )
    
    def _monitor_loop(self):
        """Background loop that updates every second."""
        while self.running:
            try:
                self.update_once()
            except Exception as e:
                self.state.add_error(f"Monitor error: {e}", "monitor")
            time.sleep(1.0)
    
    def start(self):
        """Start monitoring in background thread."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        print('[Monitor] Started - updating every 1s')
    
    def stop(self):
        """Stop monitoring."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        print('[Monitor] Stopped')


# Global instance
_monitor_instance = None

def get_monitor():
    """Get global monitor instance."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = SystemMonitor()
    return _monitor_instance


if __name__ == '__main__':
    print('Testing SystemMonitor for 10 seconds...')
    monitor = get_monitor()
    monitor.start()
    
    for i in range(10):
        time.sleep(1)
        state = get_state()
        data = state.monitor_data
        print(f"[{i+1}s] CPU: {data['cpu_percent']:.1f}% | "
              f"RAM: {data['ram_used_gb']:.1f}GB ({data['ram_percent']:.0f}%) | "
              f"GPU: {data['gpu_percent']:.0f}% | "
              f"VRAM: {data['vram_used_gb']:.1f}GB")
    
    monitor.stop()
    print('Done!')
