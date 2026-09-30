        elif intent == 'browser_open_visible':
            m = re.search(r'(?:موقع|site)\s+(\S+)', user_msg)
            url = m.group(1) if m else ''
            if url and not url.startswith('http'):
                url = 'https://' + url
            if not url:
                return False

            from agent.session_vault import SessionVault as _SV2
            _dom = url.split('//')[-1].split('/')[0]
            _sn, _ss = _SV2().get_state_for_domain(_dom)

            assistant_widget, assistant_header, assistant_body = make_message_widget("assistant")
            chat_list.controls.append(assistant_widget)
            assistant_header.value = "Neura [Browser]"
            sess_note = f' (بجلسة: {_sn})' if _sn else ''
            assistant_body.value = f'🖥️ سأفتح نافذة متصفح حقيقية{sess_note}:\n{url}\nأغلق النافذة عند الانتهاء.'
            page.update()

            def do_open():
                try:
                    with browser_actions.SafeBrowser(headless=False, session_state=_ss) as br:
                        br.open_visible(url)
                    assistant_body.value = '🖥️ أُغلقت نافذة المتصفح.'
                    page.update()
                except Exception as e:
                    assistant_body.value = f'❌ خطأ: {str(e)}'
                    page.update()

            threading.Thread(target=do_open, daemon=True).start()
            return True
