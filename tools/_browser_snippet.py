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
