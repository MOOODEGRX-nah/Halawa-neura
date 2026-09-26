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

    status_dot = ft.Icon(name="circle", color="#66BB6A", size=12)
    status_text = ft.Text("Ready", size=12, color="#ECEFF1")

    chat_list = ft.ListView(expand=True, spacing=10, auto_scroll=True)
    input_field = ft.TextField(
        hint_text="Type your message...",
        multiline=False,
        expand=True,
        bgcolor="#1E1E1E",
        color="#ECEFF1",
        border_color="#42A5F5",
    )
    send_btn = ft.IconButton(icon="send", icon_color="#42A5F5")

    def make_message_widget(role, speed=None):
        """Create a message container that we can update live."""
        color = "#42A5F5" if role == "user" else "#66BB6A"
        prefix = "You" if role == "user" else "Neura"
        header = ft.Text(prefix, size=11, weight="bold", color=color)
        body = ft.Text("", size=13, color="#ECEFF1")
        return ft.Container(
            padding=10,
            border_radius=8,
            bgcolor="#1E1E1E" if role == "user" else "#2E2E2E",
            content=ft.Column([header, body]),
        ), header, body

    def send_message(e):
        """Send user message and stream response."""
        user_msg = input_field.value.strip()
        if not user_msg:
            return

        input_field.disabled = True
        send_btn.disabled = True
        input_field.value = ""

        # Add user message (static)
        user_widget, _, user_body = make_message_widget("user")
        user_body.value = user_msg
        chat_list.controls.append(user_widget)
        page.update()

        # Add assistant message placeholder
        assistant_widget, assistant_header, assistant_body = make_message_widget("assistant")
        chat_list.controls.append(assistant_widget)
        page.update()

        def stream_response():
            try:
                final_speed = 0.0
                for chunk in core.chat_stream(user_msg, max_tokens=200):
                    if chunk['type'] == 'token':
                        assistant_body.value += chunk['text']
                        page.update()
                    elif chunk['type'] == 'done':
                        final_speed = chunk['speed']
                        assistant_header.value = f"Neura [{final_speed:.1f} tok/s]"
                        page.update()
            except Exception as ex:
                assistant_body.value = f"Error: {ex}"
                page.update()
            finally:
                input_field.disabled = False
                send_btn.disabled = False
                page.update()

        threading.Thread(target=stream_response, daemon=True).start()

    send_btn.on_click = send_message

    def refresh_monitor():
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

    monitor.start()
    page.run_thread(refresh_monitor)

    welcome_widget, _, welcome_body = make_message_widget("assistant")
    welcome_body.value = "Hello! I'm Neura. Ask me anything — I remember our conversations!"
    chat_list.controls.append(welcome_widget)
    page.update()


if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER)
