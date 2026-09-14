"""
واجهة Neura الرئيسية — تصميم داكن عصري بأسلوب halawa-hub
"""
import threading

import flet as ft

from config import Config, APP_NAME, APP_VERSION
from database import JarvisDatabase
from neura_core import JarvisCore
from voice import JarvisVoice
from vision import JarvisVision
from github_bridge import GitHubBridge
import downloader

# ألوان داكنة بأسلوب GitHub / halawa-hub
BG = "#0D1117"
PANEL = "#161B22"
BORDER = "#30363D"
ACCENT = "#58A6FF"
GREEN = "#238636"
RED = "#DA3633"
TEXT = "#E6EDF3"
MUTED = "#8B949E"
USER_BUBBLE = "#1F6FEB"
BOT_BUBBLE = "#21262D"


def main(page: ft.Page):
    # ===== الإعدادات الأساسية =====
    page.title = f"{APP_NAME} — المساعد الذكي"
    try:
        page.window.width = 1050
        page.window.height = 700
    except Exception:
        page.window_width = 1050
        page.window_height = 700
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG
    page.padding = 15

    # ===== النواة =====
    config = Config()
    db = JarvisDatabase(config.data_dir / "neura_memory.db")
    core = JarvisCore(config, db)
    voice = JarvisVoice(config.get("language", "ar-SA"))
    vision = JarvisVision(config)
    gh = GitHubBridge()

    # ===== أدوات مساعدة =====
    def toast(msg, color=GREEN):
        page.snack_bar = ft.SnackBar(ft.Text(msg, color="white"), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    def bubble(text, is_user=False):
        if is_user:
            radius = ft.border_radius.only(top_left=12, top_right=12, bottom_left=12, bottom_right=2)
            content = ft.Text(text, color="white", selectable=True, size=14)
        else:
            radius = ft.border_radius.only(top_left=2, top_right=12, bottom_left=12, bottom_right=12)
            content = ft.Row(
                [ft.Icon(ft.icons.SMART_TOY, size=18, color=ACCENT),
                 ft.Text(text, color=TEXT, selectable=True, size=14)],
                spacing=8, vertical_alignment=ft.CrossAxisAlignment.START)
        return ft.Container(
            content=content,
            bgcolor=USER_BUBBLE if is_user else BOT_BUBBLE,
            border_radius=radius,
            padding=12,
            border=ft.border.all(1, BORDER) if not is_user else None)

    def add_message(text, is_user=False):
        row = ft.Row([bubble(text, is_user)],
                     alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START)
        chat_list.controls.append(row)
        page.update()

    typing_row = ft.Container(
        content=ft.Row([ft.ProgressRing(width=16, height=16, stroke_width=2),
                        ft.Text("Neura يفكر...", color=MUTED, size=13)], spacing=8))

    def show_typing(show=True):
        if show:
            chat_list.controls.append(typing_row)
        else:
            try:
                chat_list.controls.remove(typing_row)
            except ValueError:
                pass
        page.update()

    # ===== الإرسال =====
    def handle_send(e=None):
        text = input_field.value.strip()
        if not text:
            return
        input_field.value = ""
        page.update()
        add_message(text, True)
        show_typing(True)

        def worker():
            result = core.process(text)
            reply = result["reply"]
            db.save_conversation(text, reply)
            show_typing(False)
            add_message(reply, False)
            if config.get("voice_enabled"):
                voice.speak(reply)

        threading.Thread(target=worker, daemon=True).start()

    def handle_mic(e):
        if not voice.stt_ok:
            toast("التعرف الصوتي غير متوفر (ثبّت مكتبات الصوت)", RED)
            return
        toast("🎤 أستمع إليك...")

        def worker():
            heard = voice.listen(timeout=6)
            if heard:
                input_field.value = heard
                page.update()
                handle_send()
            else:
                toast("لم أسمعك، حاول مرة أخرى", RED)

        threading.Thread(target=worker, daemon=True).start()

    # ===== عرض المحادثة =====
    chat_list = ft.ListView(expand=True, spacing=8, padding=10, auto_scroll=True)
    input_field = ft.TextField(
        hint_text="اكتب رسالتك هنا...", expand=True, border_radius=10,
        bgcolor=PANEL, color=TEXT, border_color=BORDER,
        focused_border_color=ACCENT, content_padding=14, on_submit=handle_send)

    chat_view = ft.Column([
        ft.Container(expand=True, content=chat_list, bgcolor=BG,
                     border_radius=10, border=ft.border.all(1, BORDER)),
        ft.Container(
            padding=10, bgcolor=PANEL, border_radius=10,
            content=ft.Row([
                input_field,
                ft.IconButton(ft.icons.MIC, icon_color="white", bgcolor=RED,
                              tooltip="التحدث", on_click=handle_mic),
                ft.IconButton(ft.icons.SEND, icon_color="white", bgcolor=GREEN,
                              tooltip="إرسال", on_click=handle_send),
            ], spacing=8))
    ], spacing=10, expand=True)

    # ===== عرض المهام =====
    tasks_list = ft.ListView(expand=True, spacing=6)
    task_field = ft.TextField(hint_text="مهمة جديدة...", expand=True, bgcolor=PANEL,
                              color=TEXT, border_color=BORDER, border_radius=10)

    def refresh_tasks():
        tasks_list.controls.clear()
        for tid, title, done in db.list_tasks():
            tasks_list.controls.append(ft.Container(
                padding=8, bgcolor=PANEL, border_radius=8,
                content=ft.Row([
                    ft.Checkbox(value=bool(done),
                                on_change=lambda e, tid=tid: toggle_task(tid, e.control.value)),
                    ft.Text(title, color=TEXT, expand=True),
                ])))
        page.update()

    def toggle_task(tid, val):
        db.set_task_done(tid, val)
        refresh_tasks()

    def add_task(e):
        t = task_field.value.strip()
        if not t:
            return
        db.add_task(t)
        task_field.value = ""
        refresh_tasks()
        toast("أُضيفت المهمة ✓")

    tasks_view = ft.Column([
        ft.Row([task_field,
                ft.ElevatedButton("إضافة", bgcolor=GREEN, color="white", on_click=add_task)],
               spacing=8),
        ft.Container(expand=True, content=tasks_list, border_radius=10,
                     border=ft.border.all(1, BORDER), padding=10),
    ], spacing=10, expand=True)

    # ===== عرض الرؤية =====
    vision_field = ft.TextField(hint_text="اسأل عن شاشتك... مثال: ماذا أفعل لأغير الصوت؟",
                                expand=True, bgcolor=PANEL, color=TEXT,
                                border_color=BORDER, border_radius=10)
    vision_status = ft.Text("", color=MUTED, size=12)
    vision_answer = ft.Text("", color=TEXT, selectable=True, size=14)

    def ask_vision(e):
        q = vision_field.value.strip() or "اشرح لي ما الذي يظهر على الشاشة وماذا أفعل؟"
        vision_status.value = "⏳ ألتقط الشاشة وأحللها..."
        vision_answer.value = ""
        page.update()

        def worker():
            if vision.status != "ready":
                vision.load()
            if vision.status != "ready":
                vision_status.value = f"⚠️ {vision.status_msg}"
                page.update()
                return
            answer, img_path = vision.ask(q)
            vision_answer.value = answer
            vision_status.value = f"💾 حُفظت اللقطة في: {img_path}" if img_path else ""
            page.update()

        threading.Thread(target=worker, daemon=True).start()

    vision_view = ft.Column([
        ft.Row([vision_field,
                ft.ElevatedButton("👁️ اسأل الشاشة", bgcolor=ACCENT, color="white",
                                  on_click=ask_vision)], spacing=8),
        vision_status,
        ft.Container(expand=True, content=ft.ListView([vision_answer], padding=10),
                     bgcolor=PANEL, border_radius=10, border=ft.border.all(1, BORDER)),
    ], spacing=10, expand=True)

    # ===== الإعدادات =====
    def open_settings(e):
        gaming_sw = ft.Switch(label="وضع اللعب (موارد محدودة)", value=bool(config.get("gaming_mode")))
        voice_sw = ft.Switch(label="تفعيل الصوت", value=bool(config.get("voice_enabled")))
        lang_dd = ft.Dropdown(value=config.get("language"), width=220, options=[
            ft.dropdown.Option("ar-SA", "العربية"),
            ft.dropdown.Option("en-US", "English"),
        ])
        gh_text = ft.Text(f"GitHub: {'متصل (' + gh.whoami() + ')' if gh.available else 'غير متصل (عيّن GITHUB_TOKEN)'}",
                          color=MUTED, size=12)

        def save(_):
            config.set("gaming_mode", gaming_sw.value)
            config.set("voice_enabled", voice_sw.value)
            config.set("language", lang_dd.value)
            config.save()
            page.dialog.open = False
            update_status_bar()
            toast("حُفظت الإعدادات ✓ (أعد التشغيل لتطبيق نموذج الذكاء)")

        dlg = ft.AlertDialog(
            modal=True, bgcolor=PANEL,
            title=ft.Text("⚙️ الإعدادات", color=TEXT),
            content=ft.Container(width=420, content=ft.Column([
                gaming_sw, voice_sw,
                ft.Text("لغة الصوت:", color=TEXT), lang_dd,
                ft.Divider(color=BORDER), gh_text,
            ], tight=True, spacing=10)),
            actions=[
                ft.TextButton("إلغاء", on_click=lambda _: close_dialog()),
                ft.ElevatedButton("حفظ", bgcolor=GREEN, color="white", on_click=save),
                ft.ElevatedButton("⬇️ تحميل النموذج", bgcolor=ACCENT, color="white",
                                  on_click=lambda _: open_download()),
            ])
        page.dialog = dlg
        dlg.open = True
        page.update()

    def close_dialog():
        if page.dialog:
            page.dialog.open = False
        page.update()

    # ===== تحميل النماذج =====
    def open_download():
        bar = ft.ProgressBar(width=340)
        status = ft.Text("اختر النموذج الذي تريد تحميله", color=MUTED, size=12)

        def start(keys):
            def work():
                for key in keys:
                    status.value = f"⏳ {downloader.MODELS[key]['desc']}"
                    page.update()

                    def cb(d, t, k=key):
                        if t:
                            bar.value = d / t
                        status.value = f"{downloader.MODELS[k]['desc']} — {d // 1_000_000} / {t // 1_000_000} MB"
                        page.update()

                    try:
                        downloader.download_model(key, config.models_dir, cb)
                    except Exception as ex:
                        status.value = f"❌ فشل التحميل: {ex}"
                        page.update()
                        return
                status.value = "✅ اكتمل التحميل! أعد تشغيل البرنامج لتحميل النموذج"
                page.update()

            threading.Thread(target=work, daemon=True).start()

        dlg = ft.AlertDialog(
            modal=True, bgcolor=PANEL,
            title=ft.Text("⬇️ تحميل نماذج الذكاء", color=TEXT),
            content=ft.Container(width=420, content=ft.Column([
                ft.Text("نموذج المحادثة: مطلوب للذكاء الكامل", color=TEXT, size=13),
                ft.ElevatedButton("تحميل نموذج المحادثة (~4.7GB)", bgcolor=GREEN, color="white",
                                  on_click=lambda _: start(["chat"])),
                ft.Divider(color=BORDER),
                ft.Text("نموذج الرؤية: اختياري لميزة تحليل الشاشة", color=TEXT, size=13),
                ft.ElevatedButton("تحميل نموذج الرؤية (~4.9GB)", bgcolor=ACCENT, color="white",
                                  on_click=lambda _: start(["vision", "vision_mmproj"])),
                ft.Divider(color=BORDER),
                bar, status,
            ], tight=True, spacing=8)),
            actions=[ft.TextButton("إغلاق", on_click=lambda _: close_dialog())])
        page.dialog = dlg
        dlg.open = True
        page.update()

    # ===== عن البرنامج =====
    def open_about(e):
        s = db.stats()
        dlg = ft.AlertDialog(
            modal=True, bgcolor=PANEL,
            title=ft.Text(f"🤖 عن {APP_NAME}", color=TEXT),
            content=ft.Container(width=360, content=ft.Column([
                ft.Text(f"الإصدار: {APP_VERSION} (Alpha)", color=TEXT),
                ft.Text(f"المحادثات المحفوظة: {s['conversations']}", color=MUTED),
                ft.Text(f"الذكريات: {s['memories']}", color=MUTED),
                ft.Text(f"المهام: {s['tasks']}", color=MUTED),
                ft.Text(f"المسار: {config.base_path}", color=MUTED, size=11),
            ], tight=True, spacing=6)),
            actions=[ft.ElevatedButton("حسناً", bgcolor=GREEN, color="white",
                                       on_click=lambda _: close_dialog())])
        page.dialog = dlg
        dlg.open = True
        page.update()

    # ===== شريط الحالة =====
    status_text = ft.Text("", color=MUTED, size=12)

    def update_status_bar():
        mode = "🎮 وضع اللعب" if config.get("gaming_mode") else "💼 وضع عادي"
        st = {"ready": "🟢 النموذج محمّل", "basic": "🟡 وضع أساسي",
              "loading": "⏳ جاري التحميل", "error": "🔴 خطأ",
              "not_loaded": "⚪ غير محمّل"}.get(core.status, core.status)
        status_text.value = f"{mode}  |  {st}  |  v{APP_VERSION}"
        page.update()

    # ===== التنقل بين العروض =====
    content_area = ft.Container(expand=True)

    def set_view(name):
        if name == "chat":
            content_area.content = chat_view
        elif name == "tasks":
            refresh_tasks()
            content_area.content = tasks_view
        elif name == "vision":
            content_area.content = vision_view
        page.update()

    def nav(icon, label, view):
        return ft.Container(
            margin=ft.margin.only(bottom=8),
            content=ft.ElevatedButton(
                label, icon=icon, width=180, height=44,
                style=ft.ButtonStyle(bgcolor=PANEL, color=TEXT,
                                     shape=ft.RoundedRectangleBorder(radius=8)),
                on_click=lambda _: set_view(view)))

    sidebar = ft.Container(
        width=210, bgcolor=PANEL, border_radius=10, padding=15,
        content=ft.Column([
            ft.Container(padding=ft.padding.only(bottom=20), content=ft.Row([
                ft.Icon(ft.icons.SMART_TOY, size=28, color=ACCENT),
                ft.Text("Neura", size=20, weight=ft.FontWeight.BOLD, color=ACCENT)])),
            nav(ft.icons.CHAT, "المحادثة", "chat"),
            nav(ft.icons.VISIBILITY, "الرؤية", "vision"),
            nav(ft.icons.CHECKLIST, "المهام", "tasks"),
            nav(ft.icons.SETTINGS, "الإعدادات", None) if False else ft.Container(
                margin=ft.margin.only(bottom=8),
                content=ft.ElevatedButton("الإعدادات", icon=ft.icons.SETTINGS, width=180, height=44,
                                          style=ft.ButtonStyle(bgcolor=PANEL, color=TEXT,
                                                               shape=ft.RoundedRectangleBorder(radius=8)),
                                          on_click=open_settings)),
            ft.Container(expand=True),
            ft.Container(
                content=ft.ElevatedButton("ℹ️ عن البرنامج", icon=ft.icons.INFO, width=180, height=44,
                                          style=ft.ButtonStyle(bgcolor="#30363D", color=TEXT,
                                                               shape=ft.RoundedRectangleBorder(radius=8)),
                                          on_click=open_about)),
        ]))

    # ===== التجميع النهائي =====
    title_bar = ft.Container(
        bgcolor=PANEL, border_radius=10, padding=12,
        content=ft.Row([
            ft.Icon(ft.icons.SMART_TOY, size=26, color=ACCENT),
            ft.Text("المساعد الذكي", size=17, weight=ft.FontWeight.BOLD, color=TEXT),
            ft.Container(expand=True),
            status_text,
        ]))

    page.add(ft.Column([
        title_bar,
        ft.Row([sidebar, content_area], spacing=12, expand=True),
    ], spacing=12, expand=True))

    set_view("chat")
    add_message(f"مرحباً! أنا {APP_NAME}، مساعدك الذكي 🚀\nجرّب: مساعدة، افتح يوتيوب، كم الساعة؟")
    update_status_bar()

    # ===== بدء التشغيل: تحميل النموذج في الخلفية =====
    def startup():
        core.load_model()
        if config.get("vision_enabled"):
            vision.load()
        update_status_bar()
        if core.status == "basic":
            add_message(f"💡 {core.status_msg}\nمن الإعدادات ⚙️ يمكنك تحميل النموذج")

    threading.Thread(target=startup, daemon=True).start()
