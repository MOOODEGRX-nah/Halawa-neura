"""
Neura Browser Actions v2
تصفح آمن: جلسات تلقائية + وضع مرئي + قراءة فقط.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from agent.session_vault import SessionVault


class SafeBrowser:
    def __init__(self, headless=True, timeout=20000,
                 session_name=None, session_state=None,
                 save_on_exit=False, domain=None):
        self.headless = headless
        self.timeout = timeout
        self.session_name = session_name
        self.session_state = session_state
        self.save_on_exit = save_on_exit
        self.domain = domain
        self.vault = SessionVault()
        self._playwright = None
        self._browser = None
        self._context = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        context_opts = {}
        state = self.session_state
        if state is None and self.session_name:
            state = self.vault.get_state(self.session_name)
        if state:
            context_opts['storage_state'] = state
            print('🔐 Session محمّلة تلقائياً')
        self._context = self._browser.new_context(**context_opts)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.save_on_exit and self.session_name and self._context:
            try:
                self.vault.save_persistent(
                    self.session_name,
                    self._context.storage_state(),
                    domain=self.domain
                )
            except Exception as e:
                print(f'⚠️ فشل حفظ الجلسة: {e}')
        for obj in (self._context, self._browser):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        if self._playwright:
            self._playwright.stop()

    def new_page(self):
        return self._context.new_page()

    def read_page(self, url, max_text=5000):
        print(f'🌐 زيارة: {url}')
        page = self.new_page()
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)
            page.wait_for_timeout(1000)
            content = page.inner_text('body')
            content = '\n'.join(l.strip() for l in content.split('\n') if l.strip())
            if len(content) > max_text:
                content = content[:max_text] + '\n... [مقطوع]'
            return {'ok': True, 'url': url, 'title': page.title(),
                    'content': content, 'length': len(content)}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        finally:
            page.close()

    def extract_headlines(self, url, selector='h1, h2, h3', limit=20):
        print(f'📰 عناوين: {url}')
        page = self.new_page()
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)
            page.wait_for_timeout(1000)
            headlines = []
            for e in page.query_selector_all(selector)[:limit]:
                text = e.inner_text().strip()
                if text and len(text) > 5:
                    headlines.append(text)
            return {'ok': True, 'url': url, 'title': page.title(),
                    'headlines': headlines}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        finally:
            page.close()

    def open_visible(self, url, timeout=600000):
        """نافذة مرئية تبقى مفتوحة حتى تغلقها بنفسك."""
        print(f'🖥️ نافذة مرئية: {url}')
        page = self.new_page()
        page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)
        try:
            page.wait_for_event('close', timeout=timeout)
        except Exception:
            pass

    def login_interactive(self, url, timeout=300000):
        print(f'🔐 متصفح الدخول: {url}')
        print('    سجّل دخولك بنفسك ثم أغلق النافذة لحفظ الجلسة')
        page = self.new_page()
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)
            page.wait_for_event('close', timeout=timeout)
            return {'ok': True, 'message': 'تم حفظ الجلسة'}
        except PlaywrightTimeout:
            return {'ok': False, 'error': 'انتهت المهلة'}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
