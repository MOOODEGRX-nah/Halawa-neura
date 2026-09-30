        elif intent == 'browser_login':
            # تسجيل دخول تفاعلي - متصفح مرئي، Neura لا يرى كلمة المرور
            from agent.session_vault import SessionVault
            vault = SessionVault()
            url = params.get('url', '')
            session_name = params.get('session_name', 'default')
            if url and not url.startswith('http'):
                url = 'https://' + url
            if not url:
                return False

            assistant_widget, assistant_header, assistant_body = make_message_widget("assistant")
            chat_list.controls.append(assistant_widget)
            assistant_header.value = "Neura [Session]"
            assistant_body.value = f'🔐 سأفتح متصفحاً لتسجيل الدخول في:\n{url}\n\nSession name: {session_name}\n\nأكمل الدخول بنفسك ثم أغلق النافذة.'
            page.update()

            def do_login():
                try:
                    # متصفح مرئي (headed) - المستخدم يدخل بنفسه
                    with browser_actions.SafeBrowser(headless=False, session_name=session_name) as br:
                        result = br.login_interactive(url)
                    if result['ok']:
                        assistant_body.value = f'✅ تم حفظ الجلسة الدائمة: {session_name}\n\nالآن يمكنك استخدام "{session_name}" للوصول التلقائي.'
                    else:
                        assistant_body.value = f'❌ فشل: {result["error"]}'
                    page.update()
                except Exception as e:
                    assistant_body.value = f'❌ خطأ: {str(e)}'
                    page.update()

            threading.Thread(target=do_login, daemon=True).start()
            return True

        elif intent == 'session_list':
            from agent.session_vault import SessionVault
            vault = SessionVault()
            sessions = vault.list_persistent()
            assistant_widget, assistant_header, assistant_body = make_message_widget("assistant")
            chat_list.controls.append(assistant_widget)
            assistant_header.value = "Neura [Sessions]"
            if sessions:
                text = f'🔐 لديك {len(sessions)} جلسة دائمة:\n\n'
                for s in sessions:
                    text += f'  • {s["name"]} ({s["modified"]})\n'
                assistant_body.value = text
            else:
                assistant_body.value = 'لا توجد جلسات محفوظة.'
            page.update()
            return True

