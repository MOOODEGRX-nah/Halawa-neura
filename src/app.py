import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time
import flet as ft
from state import get_state
from monitor import get_monitor


def main(page: ft.Page):
    page.title = "Neura - System Monitor"
    page.theme_mode = "dark"
    page.bgcolor = "#101418"
    page.padding = 24

    state = get_state()
    monitor = get_monitor()

    status_dot = ft.Icon(name="circle", color="#FFC107", size=14)
    status_text = ft.Text("Starting...", size=14, color="#ECEFF1")

    cpu_bar = ft.ProgressBar(width=260, color="#42A5F5", bgcolor="#37474F", value=0)
    cpu_text = ft.Text("CPU: 0%", size=12, color="#B0BEC5", width=150)

    ram_bar = ft.ProgressBar(width=260, color="#66BB6A", bgcolor="#37474F", value=0)
    ram_text = ft.Text("RAM: 0 GB", size=12, color="#B0BEC5", width=150)

    gpu_bar = ft.ProgressBar(width=260, color="#FFA726", bgcolor="#37474F", value=0)
    gpu_text = ft.Text("GPU: 0%", size=12, color="#B0BEC5", width=150)

    vram_text = ft.Text("VRAM: 0.0 GB", size=12, color="#B0BEC5")
    tps_text = ft.Text("Tokens/s: 0.0", size=12, color="#B0BEC5")

    def refresh():
        d = state.monitor_data
        status_dot.color = {"ready": "#66BB6A", "thinking": "#FFC107",
                            "speaking": "#42A5F5"}.get(state.status, "#EF5350")
        status_text.value = state.status_msg or state.status
        cpu_bar.value = min(d.get("cpu_percent", 0) / 100.0, 1.0)
        cpu_text.value = "CPU: %.0f%%" % d.get("cpu_percent", 0)
        ram_bar.value = min(d.get("ram_percent", 0) / 100.0, 1.0)
        ram_text.value = "RAM: %.1f/%.0f GB" % (d.get("ram_used_gb", 0), d.get("ram_total_gb", 0))
        gpu_bar.value = min(d.get("gpu_percent", 0) / 100.0, 1.0)
        gpu_text.value = "GPU: %.0f%%" % d.get("gpu_percent", 0)
        vram_text.value = "VRAM: %.1f GB" % d.get("vram_used_gb", 0)
        tps_text.value = "Tokens/s: %.1f" % d.get("tokens_per_sec", 0)
        page.update()

    def loop():
        while True:
            try:
                refresh()
            except Exception:
                pass
            time.sleep(1.0)

    card = ft.Card(
        content=ft.Container(
            padding=20,
            content=ft.Column([
                ft.Text("Neura System Monitor", size=20, weight="bold", color="#ECEFF1"),
                ft.Divider(),
                ft.Row([status_dot, status_text]),
                ft.Divider(),
                ft.Row([cpu_bar, cpu_text]),
                ft.Row([ram_bar, ram_text]),
                ft.Row([gpu_bar, gpu_text]),
                ft.Row([vram_text, tps_text]),
            ], spacing=10),
        ),
        width=420,
    )
    page.add(card)

    monitor.start()
    state.update_status("ready", "System Online - Dual GPU Active")
    page.run_thread(loop)


if __name__ == "__main__":
    ft.app(target=main)
