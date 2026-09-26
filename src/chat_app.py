import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time
import threading
import flet as ft
from state import get_state
from monitor import get_monitor
from neura_core import NeuraCore


def main(page: ft.Page):
    page.title = "Neura AI Assistant"
    page.theme_mode = "dark"
    page.bgcolor = "#101418"
    page.padding = 20

    state = get_state()
    monitor = get_monitor()

    # Initialize core
    print('[App] Loading NeuraCore ...')
    core = NeuraCore()
    state.update_status('ready', 'System Online - Dual GPU Active')

    # Monitor bars
    cpu_bar = ft.ProgressBar(width=200, color="#42A5F5", bgcolor="#37474F", value=0)
    cpu_text = ft.Text("CPU: 0%", size=11, color="#B0BEC5")
    ram_bar = ft.ProgressBar(width=200, color="#66BB6A", bgcolor="#37474F", value=0)
    ram_text = ft.Text("RAM: 0GB", size=11, color="#B0BEC5")
    gpu_bar = ft.ProgressBar(width=200, color="#FFA726", bgcolor="#37474F", value=0)
    gpu_text = ft.Text("GPU: 0%", size=11, color="#B0BEC5")
    vram_text = ft.Text("VRAM: 0GB | 0 tok/s", size=11, color="#B0BEC5")

    # Status indicator
    status_dot = ft.Icon(name="circle", color="#66BB6A", size=12)
    status_text = ft.Text("Ready", size=12, color="#ECEFF1")

    # Chat area
    chat_list = ft.ListView(expand=True, spacing=10, auto_scroll=True)
    input_field = ft.TextField(
        hint_text="Type your message...",
        multiline=False,
        expand=True,
        bgcolor="#1E1E1E",
        color="#ECEFF1",
        border_color="#42A5F5",
    )
    send_btn = ft.IconButton(icon="send", icon_color="#42A5F5", on_click=lambda e: send_message())

    def add_message(role, text, speed=None):
        """Add message to chat."""
        color = "#42A5F5" if role == "user" else "#66BB6A"
        prefix = "You" if role == "user" else "Neura"
        suffix = f" [{speed:.1f} tok/s]" if speed else ""
        msg = ft.Container(
            padding=10,
            border_radius=8,
            bgcolor="#1E1E1E" if role == "user" else "#2E2E2E",
            content=ft.Column([
                ft.Text(f"{prefix}{suffix}", size=11, weight="bold", color=color),
                ft.Text(text, size=13, color="#ECEFF1"),
            ]),
        )
        chat_list.controls.append(msg)
        page.update()

    def send_message():
        """Send user message and get response."""
        user_msg = input_field.value.strip()
        if not user_msg:
            return

        # Disable input
        input_field.disabled = True
        send_btn.disabled = True
        page.update()

        # Add user message
        add_message("user", user_msg)
        input_field.value = ""

        # Generate response in background thread
        def generate():
            try:
                state.update_status('thinking', 'Generating...')
                result = core.chat(user_msg, max_tokens=200)
                add_message("assistant", result['message'], result['speed'])
            except Exception as e:
                add_message("assistant", f"Error: {str(e)}")
            finally:
                state.update_status('ready', 'Ready')
                input_field.disabled = False
                send_btn.disabled = False
                page.update()

        threading.Thread(target=generate, daemon=True).start()

    def refresh_monitor():
        """Update monitor bars every second."""
        while True:
            try:
                d = state.monitor_data
                cpu_bar.value = min(d.get("cpu_percent", 0) / 100.0, 1.0)
                cpu_text.value = f"CPU: {d.get('cpu_percent', 0):.0f}%"
                ram_bar.value = min(d.get("ram_percent", 0) / 100.0, 1.0)
                ram_text.value = f"RAM: {d.get('ram_used_gb', 0):.1f}GB"
                gpu_bar.value = min(d.get("gpu_percent", 0) / 100.0, 1.0)
                gpu_text.value = f"GPU: {d.get('gpu_percent', 0):.0f}%"
                vram_text.value = f"VRAM: {d.get('vram_used_gb', 0):.1f}GB | {d.get('tokens_per_sec', 0):.0f} tok/s"

                status_dot.color = {"ready": "#66BB6A", "thinking": "#FFC107", "speaking": "#42A5F5"}.get(state.status, "#EF5350")
                status_text.value = state.status_msg or state.status
                page.update()
            except Exception:
                pass
            time.sleep(1.0)

    # Build UI
    monitor_card = ft.Card(
        content=ft.Container(
            padding=15,
            content=ft.Column([
                ft.Row([status_dot, status_text]),
                ft.Row([cpu_bar, cpu_text], spacing=10),
                ft.Row([ram_bar, ram_text], spacing=10),
                ft.Row([gpu_bar, gpu_text], spacing=10),
                vram_text,
            ], spacing=8),
        ),
        width=450,
    )

    chat_card = ft.Card(
        content=ft.Container(
            padding=15,
            content=ft.Column([
                chat_list,
                ft.Divider(),
                ft.Row([input_field, send_btn], spacing=10),
            ], expand=True),
        ),
        expand=True,
    )

    page.add(monitor_card, chat_card)

    # Start background threads
    monitor.start()
    page.run_thread(refresh_monitor)

    # Welcome message
    add_message("assistant", "Hello! I'm Neura. Ask me anything — I remember our conversations!")


if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER)
