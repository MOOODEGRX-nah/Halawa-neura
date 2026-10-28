"""Reviewed desktop adapter. GIO parses trusted desktop entries; never a shell."""
import configparser
import hashlib
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from src.core.project_files import SafeTree, ProjectError
from src.desktop.paths import DesktopSettings

TEXT = {'.txt','.md','.json','.csv','.py','.js','.css','.html','.htm','.sh','.toml','.yaml','.yml','.xml','.sql','.ini','.log'}
DOCUMENTS = {'.pdf','.png','.jpg','.jpeg','.gif','.webp','.bmp'}


class DesktopUnavailable(ProjectError):
    status = 503


class DesktopAdapter:
    def __init__(self, store, settings=None, *, runner=subprocess.run, roots=None):
        self.store = store
        self.settings = settings
        self.runner = runner
        self.roots = [Path(x) for x in (roots or ['/usr/share/applications','/usr/local/share/applications'])]

    def configuration(self):
        return self.settings or DesktopSettings().values

    def catalog(self):
        apps = {}
        for root in self.roots:
            if not root.is_dir() or root.is_symlink():
                continue
            for path in sorted(root.glob('*.desktop')):
                try:
                    info = path.lstat()
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                        continue
                    parser = configparser.ConfigParser(interpolation=None, strict=False)
                    parser.read(path, encoding='utf-8')
                    entry = parser['Desktop Entry']
                    if entry.get('Type') != 'Application' or entry.get('Hidden','false') == 'true' or entry.get('NoDisplay','false') == 'true' or entry.get('Terminal','false') == 'true':
                        continue
                    if not entry.get('Exec') and entry.get('DBusActivatable','false') != 'true':
                        continue
                    apps[path.name] = {'id':path.name, 'name':entry.get('Name[ar]',entry.get('Name',path.stem)), 'entry':str(path)}
                except (OSError, KeyError, configparser.Error):
                    continue
        return apps

    def status(self):
        session = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')) and bool(os.environ.get('DBUS_SESSION_BUS_ADDRESS'))
        gio = shutil.which('gio')
        browser = self.configuration().get('brave_desktop_id','brave-browser.desktop')
        catalog = self.catalog()
        return {'desktop_available': bool(session and gio), 'brave_available': browser in catalog,
                'text_viewer_available':any(key in catalog for key in ('org.kde.kate.desktop','org.gnome.TextEditor.desktop','org.gnome.gedit.desktop')),
                'folder_viewer_available':any(key in catalog for key in ('org.kde.dolphin.desktop','org.gnome.Nautilus.desktop')),
                'reason': '' if session and gio else 'جلسة سطح المكتب أو GIO غير متاحة.',
                'applications': [{'id':a['id'],'name':a['name']} for a in list(catalog.values())[:500]],
                'locations': [{'id':key,'name':Path(value['path']).name,'kind':value['kind']}
                              for key,value in self.configuration().get('approved_locations',{}).items()]}

    def launch(self, app_id, uris=()):
        if not self.status()['desktop_available']:
            raise DesktopUnavailable('جلسة سطح المكتب غير متاحة؛ افتح Neura من قائمة التطبيقات.')
        entry = self.catalog().get(app_id)
        if not entry:
            raise DesktopUnavailable('التطبيق المحدد غير مثبت أو ليس في السجل الموثوق.')
        command = [shutil.which('gio'), 'launch', entry['entry'], *uris]
        try:
            # GUI children may inherit GIO's output handles. DEVNULL lets us wait
            # for the launch request itself, rather than for the GUI to close.
            result = self.runner(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, shell=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DesktopUnavailable('تعذر إرسال طلب فتح التطبيق أو انتهت مهلته.') from exc
        if result.returncode:
            raise DesktopUnavailable('لم يقبل سطح المكتب طلب الفتح. تحقق من التطبيق والجلسة.')
        return {'status':'launched','application_id':app_id,'application_name':entry['name'],
                'message':'أُرسل طلب الفتح إلى سطح المكتب؛ لا يثبت ذلك اكتمال تحميل الصفحة أو التطبيق.'}

    def browser(self, url):
        app_id = self.configuration().get('brave_desktop_id','brave-browser.desktop')
        if app_id not in self.catalog():
            raise DesktopUnavailable('Brave غير مثبت أو لم يُضبط. اختر تطبيق Brave من إعدادات Neura.')
        return self.launch(app_id, [url])

    def resolve_location(self, args, *, folder=False):
        if args.get('project_id'):
            root = self.store.directory(args['project_id'])
            if folder:
                return root, None
            with SafeTree(root) as tree:
                data = tree.read(args['path'])
            return root / args['path'], data
        location = self.configuration().get('approved_locations',{}).get(args.get('selection_id'))
        if not location or location['kind'] != ('folder' if folder else 'file'):
            raise ProjectError('اختر ملفًا أو مجلدًا من إعدادات Neura أولًا؛ لا يُقبل مسار حر.')
        path = Path(location['path'])
        if not path.is_absolute():
            raise ProjectError('المكان المعتمد غير صالح')
        # Walk every selected path component without following a changed link.
        with SafeTree(Path('/')) as tree:
            if folder:
                parent, name = tree.parent(str(path).lstrip('/') + '/sentinel', internal=True)
                os.close(parent)
                return path, None
            data = tree.read(str(path).lstrip('/'), internal=True, limit=5_000_000)
        return path, data

    def open_folder(self, args):
        path, _ = self.resolve_location(args, folder=True)
        catalog=self.catalog()
        app=next((key for key in ('org.kde.dolphin.desktop','org.gnome.Nautilus.desktop') if key in catalog),None)
        if not app:raise DesktopUnavailable('مدير الملفات الموثوق غير متاح على هذا الجهاز.')
        return self.launch(app, [path.as_uri()])

    def open_file(self, args):
        path, data = self.resolve_location(args)
        suffix = path.suffix.lower()
        if suffix not in TEXT | DOCUMENTS or data.startswith((b'\x7fELF',b'MZ')):
            raise ProjectError('هذا النوع لا يُفتح بهذه المهارة؛ البرامج وملفات desktop التنفيذية غير مسموحة.')
        if suffix in TEXT:
            try: data.decode('utf-8')
            except UnicodeError as exc: raise ProjectError('الملف ليس نص UTF-8 صالحًا للعرض') from exc
        # View an immutable private copy, so a race cannot replace the selected file
        # with an executable between validation and the desktop launch request.
        cache = self.store.root / 'view-cache'
        cache.mkdir(mode=0o700, exist_ok=True)
        if cache.is_symlink():
            raise ProjectError('مجلد العرض غير صالح')
        name = hashlib.sha256(data).hexdigest() + suffix
        with SafeTree(cache) as tree:
            tree.write(name, data, internal=True)
            copies=[]
            for filename in os.listdir(tree.fd):
                if re.fullmatch(r'[a-f0-9]{64}\.[a-z0-9]+',filename):
                    info=tree.info(filename);copies.append((info['mtime_ns'],filename,info['size']))
            size=sum(item[2] for item in copies)
            for _,old,amount in sorted(copies):
                if len(copies)<=40 and size<=100_000_000:break
                if old!=name:tree.remove(old);size-=amount;copies=[item for item in copies if item[1]!=old]
        target = (cache/name).as_uri()
        if suffix in TEXT:
            catalog=self.catalog()
            editor=next((key for key in ('org.kde.kate.desktop','org.gnome.TextEditor.desktop','org.gnome.gedit.desktop') if key in catalog),None)
            if not editor:raise DesktopUnavailable('محرر النصوص الموثوق غير متاح؛ لم يُنفّذ الملف.')
            result = self.launch(editor, [target])
            result['message'] = 'أُرسل الملف إلى محرر النصوص للعرض؛ لم يُنفّذ الكود.'
        else:
            if not self.status()['desktop_available']:
                raise DesktopUnavailable('جلسة سطح المكتب غير متاحة.')
            try:response = self.runner([shutil.which('gio'),'open',target],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8,check=False,shell=False)
            except (OSError,subprocess.TimeoutExpired) as exc:raise DesktopUnavailable('تعذر إرسال طلب عرض الملف أو انتهت مهلته.') from exc
            if response.returncode:
                raise DesktopUnavailable('لم يقبل عارض الملفات طلب الفتح.')
            result = {'status':'launched','message':'أُرسل طلب عرض الملف إلى التطبيق الافتراضي.'}
        return result
