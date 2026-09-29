"""
Neura Agent App
واجهة دردشة مع Agent Mode — يفهم نواياك ويستدعي الأدوات تلقائياً.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
import threading
import re
import flet as ft
from state import get_state
from monitor import get_monitor
from neura_core import NeuraCore
from stt import SpeechToText
from agent.router import IntentRouter
from agent import media_actions, file_actions, git_actions
from agent import browser_actions


def main(page: ft.Page):
    page.title = "Neura Agent - Smart Assistant"
    page.theme_mode = "dark"
    page.bgcolor = "#101418"
    page.padding = 20

    state = get_state()
    monitor = get_monitor()

    print('[App] Loading NeuraCore ...')
    core = NeuraCore()

    print('[App] Loading Whisper STT ...')
    stt = SpeechToText(model_name='base', device='cpu')

    print('[App] Initializing Intent Router ...')
    router = IntentRouter()

    state.update_status('ready', 'Agent Mode Active')

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
        hint_text="اكتب أمراً أو سؤالاً...",
        multiline=False,
        expand=True,
        bgcolor="#1E1E1E",
        color="#ECEFF1",
        border_color="#42A5F5",
    )
    send_btn = ft.IconButton(icon="send", icon_color="#42A5F5")
    mic_btn = ft.IconButton(icon="mic", icon_color="#FF5252", icon_size=28)

    def make_message_widget(role, speed=None):
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

    def execute_agent_action(user_msg):
        """ينفذ أداة Agent بناءً على النية."""
        intent = router.detect_intent(user_msg)
        params = router.extract_params(user_msg, intent)

        print(f'[Agent] Intent: {intent}, Params: {params}')

        if intent == 'media_search':
            # بحث YouTube
            query = params.get('query', user_msg)
            assistant_widget, assistant_header, assistant_body = make_message_widget("assistant")
            chat_list.controls.append(assistant_widget)
            assistant_header.value = "Neura [Media]"
            assistant_body.value = f'🔍 بحث YouTube عن: {query}'
            page.update()

            def do_search():
                try:
                    results = media_actions.search_videos(query, count=5)
                    text = f'📹 وجدت {len(results)} نتائج:\n\n'
                    for i, r in enumerate(results, 1):
                        text += f'{i}. {r["title"]}\n'
                        text += f'   👤 {r["channel"]} | ⏱️ {r["duration"]} | 👁️ {r["views"]}\n'
                        text += f'   🔗 {r["url"]}\n\n'
                    assistant_body.value = text
                    page.update()
                except Exception as e:
                    assistant_body.value = f'❌ خطأ: {str(e)}'
                    page.update()

            threading.Thread(target=do_search, daemon=True).start()
            return True

        elif intent in ('file_move', 'file_copy', 'file_delete'):
            # عمليات الملفات (تحتاج Safety Gate في console)
            assistant_widget, assistant_header, assistant_body = make_message_widget("assistant")
            chat_list.controls.append(assistant_widget)
            assistant_header.value = "Neura [File]"
            assistant_body.value = f'⚙️ عملية: {intent}\nسأطلب موافقتك في Terminal...'
            page.update()

            def do_file_action():
                try:
                    if intent == 'file_move':
                        result = file_actions.safe_move(
                            params.get('src', ''),
                            params.get('dst', '')
                        )
                    elif intent == 'file_copy':
                        result = file_actions.safe_copy(
                            params.get('src', ''),
                            params.get('dst', '')
                        )
                    elif intent == 'file_delete':
                        result = file_actions.safe_delete(params.get('src', ''))

                    if result.get('ok'):
                        assistant_body.value = f'✅ نجحت العملية!'
                    else:
                        assistant_body.value = f'❌ فشلت: {result.get("error", "unknown")}'
                    page.update()
                except Exception as e:
                    assistant_body.value = f'❌ خطأ: {str(e)}'
                    page.update()

            threading.Thread(target=do_file_action, daemon=True).start()
            return True

        elif intent in ('git_push', 'git_commit'):
            # Git operations
            assistant_widget, assistant_header, assistant_body = make_message_widget("assistant")
            chat_list.controls.append(assistant_widget)
            assistant_header.value = "Neura [Git]"
            assistant_body.value = f'⚙️ عملية Git: {intent}\nسأطلب موافقتك في Terminal...'
            page.update()

            def do_git_action():
                try:
                    if intent == 'git_push':
                        result = git_actions.safe_commit_and_push(
                            message=input(f'رسالة الكوميت: ')
                        )
                    else:
                        result = git_actions.safe_commit(
                            message=input(f'رسالة الكوميت: ')
                        )

                    if result.get('ok'):
                        assistant_body.value = f'✅ نجحت عملية Git!'
                    else:
                        assistant_body.value = f'❌ فشلت: {result.get("error", "unknown")}'
                    page.update()
                except Exception as e:
                    assistant_body.value = f'❌ خطأ: {str(e)}'
                    page.update()

            threading.Thread(target=do_git_action, daemon=True).start()
            return True

        elif intent == 'browser_read':
            m = re.search(r'(?:موقع|site)\s+(\S+)', user_msg)
            url = m.group(1) if m else ''
            if url and not url.startswith('http'):
                url = 'https://' + url
            if not url:
                return False

            assistant_widget, assistant_header, assistant_body = make_message_widget("assistant")
            chat_list.controls.append(assistant_widget)
            assistant_header.value = "Neura [Browser]"
            assistant_body.value = '🌐 قراءة: ' + url
            page.update()

            def do_read():
                try:
                    with browser_actions.SafeBrowser(headless=True) as br:
                        result = br.read_page(url)
                    if result['ok']:
                        assistant_body.value = '📄 ' + result['title'] + '\n\n' + result['content'][:2000]
                    else:
                        assistant_body.value = '❌ فشل: ' + str(result['error'])
                    page.update()
                except Exception as e:
                    assistant_body.value = '❌ خطأ: ' + str(e)
                    page.update()

            threading.Thread(target=do_read, daemon=True).start()
            return True

        elif intent == 'browser_headlines':
            m = re.search(r'(?:موقع|site)\s+(\S+)', user_msg)
            url = m.group(1) if m else ''
            if url and not url.startswith('http'):
                url = 'https://' + url
            if not url:
                return False

            assistant_widget, assistant_header, assistant_body = make_message_widget("assistant")
            chat_list.controls.append(assistant_widget)
            assistant_header.value = "Neura [Browser]"
            assistant_body.value = '📰 استخراج عناوين: ' + url
            page.update()

            def do_headlines():
                try:
                    with browser_actions.SafeBrowser(headless=True) as br:
                        result = br.extract_headlines(url)
                    if result['ok']:
                        text = '📰 ' + result['title'] + '\n\n'
                        for i, h in enumerate(result['headlines'][:15], 1):
                            text += '%d. %s\n' % (i, h)
                        assistant_body.value = text
                    else:
                        assistant_body.value = '❌ فشل: ' + str(result['error'])
                    page.update()
                except Exception as e:
                    assistant_body.value = '❌ خطأ: ' + str(e)
                    page.update()

            threading.Thread(target=do_headlines, daemon=True).start()
            return True

        return False  # لم يتم تنفيذ أداة

    def stream_response(user_msg):
        """محادثة عادية مع streaming."""
        assistant_widget, assistant_header, assistant_body = make_message_widget("assistant")
        chat_list.controls.append(assistant_widget)
        page.update()

        try:
            final_speed = 0.0
            for chunk in core.chat_stream(user_msg, max_tokens=200):
                if chunk['type'] == 'token':
                    assistant_body.value += chunk['text']
                    page.update()
                elif chunk['type'] == 'done':
                    final_speed = chunk['speed']
                    assistant_header.value = "Neura [%.1f tok/s]" % final_speed
                    page.update()
        except Exception as ex:
            assistant_body.value = "Error: %s" % str(ex)
            page.update()
        finally:
            input_field.disabled = False
            send_btn.disabled = False
            mic_btn.disabled = False
            mic_btn.icon = "mic"
            mic_btn.icon_color = "#FF5252"
            page.update()

    def process_input(user_msg):
        """يحدد: أداة Agent أو محادثة عادية."""
        if execute_agent_action(user_msg):
            # تم تنفيذ أداة
            input_field.disabled = False
            send_btn.disabled = False
            page.update()
        else:
            # محادثة عادية
            stream_response(user_msg)

    def send_text(e):
        user_msg = input_field.value.strip()
        if not user_msg:
            return

        input_field.disabled = True
        send_btn.disabled = True
        mic_btn.disabled = True
        input_field.value = ""

        user_widget, _, user_body = make_message_widget("user")
        user_body.value = user_msg
        chat_list.controls.append(user_widget)
        page.update()

        threading.Thread(target=process_input, args=(user_msg,), daemon=True).start()

    def record_voice(e):
        input_field.disabled = True
        send_btn.disabled = True
        mic_btn.disabled = True
        mic_btn.icon = "stop"
        mic_btn.icon_color = "#FFA726"
        state.update_status('speaking', 'Recording ...')
        page.update()

        def do_record():
            try:
                text, dt, lang = stt.record_and_transcribe(duration=6.0)
                if text:
                    user_widget, user_header, user_body = make_message_widget("user")
                    user_header.value = "You [voice, %s]" % lang
                    user_body.value = text
                    chat_list.controls.append(user_widget)
                    page.update()
                    process_input(text)
                else:
                    note_widget, _, note_body = make_message_widget("assistant")
                    note_body.value = "(No voice detected)"
                    chat_list.controls.append(note_widget)
                    input_field.disabled = False
                    send_btn.disabled = False
                    mic_btn.disabled = False
                    mic_btn.icon = "mic"
                    mic_btn.icon_color = "#FF5252"
                    state.update_status('ready', 'Ready')
                    page.update()
            except Exception as ex:
                print('[STT Error]', ex)
                input_field.disabled = False
                send_btn.disabled = False
                mic_btn.disabled = False
                mic_btn.icon = "mic"
                mic_btn.icon_color = "#FF5252"
                state.update_status('ready', 'Ready')
                page.update()

        threading.Thread(target=do_record, daemon=True).start()

    send_btn.on_click = send_text
    mic_btn.on_click = record_voice

    def refresh_monitor():
        while True:
            try:
                d = state.monitor_data
                cpu_bar.value = min(d.get("cpu_percent", 0) / 100.0, 1.0)
                cpu_text.value = "CPU: %.0f%%" % d.get("cpu_percent", 0)
                ram_bar.value = min(d.get("ram_percent", 0) / 100.0, 1.0)
                ram_text.value = "RAM: %.1fGB" % d.get("ram_used_gb", 0)
                gpu_bar.value = min(d.get("gpu_percent", 0) / 100.0, 1.0)
                gpu_text.value = "GPU: %.0f%%" % d.get("gpu_percent", 0)
                vram_text.value = "VRAM: %.1fGB | %.0f tok/s" % (d.get("vram_used_gb", 0), d.get("tokens_per_sec", 0))
                status_dot.color = {"ready": "#66BB6A", "thinking": "#FFC107", "speaking": "#FF5252"}.get(state.status, "#EF5350")
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
                ft.Row([input_field, send_btn, mic_btn], spacing=10),
            ], expand=True),
        ),
        expand=True,
    )

    page.add(monitor_card, chat_card)

    monitor.start()
    page.run_thread(refresh_monitor)

    welcome_widget, _, welcome_body = make_message_widget("assistant")
    welcome_body.value = "مرحباً! أنا Neura Agent. يمكنني:\n• البحث عن فيديوهات YouTube\n• نقل/نسخ/حذف ملفات بأمان\n• رفع مشاريعك لـ GitHub\n• أو مجرد الدردشة معك!"
    chat_list.controls.append(welcome_widget)
    page.update()


if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER)
