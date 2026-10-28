"""Native Qt application. Opening the desktop icon starts and owns the local API."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
import copy

from PySide6.QtCore import QLockFile, QThread, QTimer, QUrl, Signal, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket, QNetworkAccessManager, QNetworkProxy, QNetworkRequest
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem,
    QTextBrowser, QToolBar, QVBoxLayout, QWidget, QListWidget)
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor, QWebEngineUrlRequestInfo
from PySide6.QtWebEngineWidgets import QWebEngineView

from src.runtime import ROOT
from src.desktop.paths import DesktopSettings, VERSION, cache_directory, config_directory, data_directory,setup_preview_environment
from src.desktop.releases import fetch_release, download_package, version_tuple
from src.desktop.service import BackendService
from src.desktop.preview_policy import navigation_allowed, request_allowed


class Task(QThread):
    succeeded = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)

    def __init__(self, function, parent):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.succeeded.emit(self.function(self))
        except Exception as error:
            self.failed.emit(str(error))


class LocalPage(QWebEnginePage):
    def __init__(self, profile, origin, parent, preview=lambda: None):
        super().__init__(profile, parent)
        self.origin = origin
        self.preview = preview
        self.permissionRequested.connect(lambda permission: permission.deny())

    def acceptNavigationRequest(self, url, navigation_type, main_frame):
        return navigation_allowed(url.toString(), self.origin(), self.preview(), main_frame)

    def createWindow(self, window_type):
        return None


class LocalRequests(QWebEngineUrlRequestInterceptor):
    def __init__(self, application, preview, parent):
        super().__init__(parent)
        self.application, self.preview = application, preview

    def interceptRequest(self, info):
        allowed = request_allowed(info.requestUrl().toString(), info.initiator().toString(),
            self.application(), self.preview(),
            info.resourceType() == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame)
        if not allowed:
            info.block(True)


class SettingsDialog(QDialog):
    def __init__(self, settings, parent):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle('إعدادات Neura')
        self.resize(760, 470)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        row = QHBoxLayout()
        self.folder = QLineEdit(settings.values['models_dir'])
        self.folder.setReadOnly(True)
        choose = QPushButton('اختيار مجلد النماذج')
        choose.clicked.connect(self.choose_folder)
        row.addWidget(self.folder); row.addWidget(choose)
        form.addRow('النماذج المحلية', row)
        self.mode = QComboBox(); self.mode.addItems(['GPU — Vulkan', 'CPU'])
        self.mode.setCurrentIndex(0 if settings.values['n_gpu_layers'] == -1 else 1)
        form.addRow('المعالجة', self.mode)
        self.gpu_device=QComboBox();self.gpu_device.addItem('تلقائي حسب الذاكرة المقاسة','auto')
        try:
            from src.backends.devices import probe_devices
            for device in probe_devices():
                self.gpu_device.addItem(device['description']+' · '+str(round(device['total_bytes']/1e9,1))+' GB',device['description'])
        except Exception:
            pass
        device_index=self.gpu_device.findData(settings.values['gpu_device'])
        if device_index<0:
            self.gpu_device.addItem('جهاز محفوظ غير متاح: '+settings.values['gpu_device'],settings.values['gpu_device'])
            device_index=self.gpu_device.count()-1
        self.gpu_device.setCurrentIndex(device_index);form.addRow('الجهاز',self.gpu_device)
        self.context = QSpinBox(); self.context.setRange(512, 32768); self.context.setSingleStep(512)
        self.context.setValue(settings.values['n_ctx']); form.addRow('حجم السياق', self.context)
        self.coder = QCheckBox('استخدام Qwen2.5 Coder بعد اكتمال ملفه والتحقق منه')
        self.coder.setChecked(settings.values['dedicated_coder']); form.addRow(self.coder)
        self.updates = QCheckBox('التحقق من تحديثات GitHub عند فتح التطبيق')
        self.updates.setChecked(settings.values['check_updates']); form.addRow(self.updates)
        self.brave=QComboBox()
        from src.desktop.actions import DesktopAdapter
        for entry in DesktopAdapter(None).catalog().values():
            if 'brave' in entry['id'].lower(): self.brave.addItem(entry['name'],entry['id'])
        if not self.brave.count():self.brave.addItem('Brave غير مثبت',settings.values['brave_desktop_id'])
        index=self.brave.findData(settings.values['brave_desktop_id'])
        self.brave.setCurrentIndex(max(index,0));form.addRow('Brave للمهارات',self.brave)
        layout.addLayout(form)
        self.locations=copy.deepcopy(settings.values['approved_locations'])
        self.locations_list=QListWidget();self.locations_list.setMaximumHeight(90);layout.addWidget(self.locations_list)
        controls=QHBoxLayout()
        for label,kind in [('اختيار ملف للعرض','file'),('اختيار مجلد للفتح','folder')]:
            action=QPushButton(label);action.clicked.connect(lambda checked=False,kind=kind:self.add_location(kind));controls.addWidget(action)
        revoke=QPushButton('إلغاء المكان المحدد');revoke.clicked.connect(self.remove_location);controls.addWidget(revoke)
        layout.addLayout(controls);self.show_locations()
        note = QLabel('الأوزان منفصلة عن التطبيق. اختر المجلد الذي يحتوي ملفات GGUF وملف mmproj للصور. لا تُنقل ملفاتك ولا تُنزّل نماذج تلقائيًا.')
        note.setWordWrap(True); layout.addWidget(note)
        self.table = QTableWidget(0, 2); self.table.setHorizontalHeaderLabels(['الملف', 'الحالة'])
        self.table.horizontalHeader().setStretchLastSection(True); layout.addWidget(self.table)
        self.refresh_files()
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def choose_folder(self):
        chosen = QFileDialog.getExistingDirectory(self, 'مجلد النماذج', self.folder.text())
        if chosen:
            self.folder.setText(chosen); self.refresh_files()

    def show_locations(self):
        self.locations_list.clear()
        for key,value in self.locations.items():self.locations_list.addItem(value['kind']+' · '+value['path'])

    def add_location(self,kind):
        if len(self.locations)>=24:return
        chosen=QFileDialog.getExistingDirectory(self,'اختيار مجلد') if kind=='folder' else QFileDialog.getOpenFileName(self,'اختيار ملف للعرض')[0]
        if chosen:
            self.locations['l_'+uuid.uuid4().hex]={'path':str(Path(chosen).resolve()),'kind':kind};self.show_locations()

    def remove_location(self):
        row=self.locations_list.currentRow()
        if row>=0:self.locations.pop(list(self.locations)[row]);self.show_locations()

    def refresh_files(self):
        import yaml
        models = yaml.safe_load((ROOT / 'configs/models.yaml').read_text())['models']
        records = [(info['file'], info) for info in models.values() if info.get('enabled') or 'coder' in info['file'].lower()]
        records.append(('mmproj-Qwen3VL-8B-Instruct-F16.gguf', {}))
        self.table.setRowCount(len(records))
        for row, (name, info) in enumerate(records):
            path = Path(self.folder.text()) / name
            if Path(str(path) + '.aria2').exists(): status = 'تنزيل غير مكتمل'
            elif not path.is_file(): status = 'غير موجود'
            elif info.get('size_bytes') and path.stat().st_size != info['size_bytes']: status = 'حجم غير مطابق'
            else: status = 'ملف متاح'
            self.table.setItem(row, 0, QTableWidgetItem(name)); self.table.setItem(row, 1, QTableWidgetItem(status))
        self.table.resizeColumnToContents(0)

    def save(self):
        if not Path(self.folder.text()).is_dir():
            QMessageBox.warning(self, 'النماذج', 'اختر مجلدًا موجودًا.'); return
        if self.coder.isChecked():
            path = Path(self.folder.text()) / 'Qwen2.5-Coder-14B-Q4_K_M.gguf'
            if not path.is_file() or Path(str(path) + '.aria2').exists():
                QMessageBox.warning(self, 'Coder', 'أكمل تنزيل Qwen Coder أولًا.'); return
        self.settings.values.update(models_dir=self.folder.text(), n_gpu_layers=-1 if self.mode.currentIndex() == 0 else 0,
                                    n_ctx=self.context.value(), dedicated_coder=self.coder.isChecked(), check_updates=self.updates.isChecked(),
                                    brave_desktop_id=self.brave.currentData(),approved_locations=self.locations,gpu_device=self.gpu_device.currentData())
        try: self.settings.save()
        except Exception as error:
            QMessageBox.warning(self, 'الإعدادات', str(error)); return
        self.accept()


class UpdateDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window; self.package = None; self.cancelled = False; self.download_task = None
        self.setWindowTitle('تحديث Neura AI'); self.resize(650, 410)
        layout = QVBoxLayout(self)
        self.status = QLabel('جارٍ التحقق من الإصدار الجديد…'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.notes = QTextBrowser(); self.notes.setOpenExternalLinks(False); layout.addWidget(self.notes)
        self.progress = QProgressBar(); self.progress.hide(); layout.addWidget(self.progress)
        self.install_button = QPushButton('تنزيل التحديث وتثبيته'); self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self.install); layout.addWidget(self.install_button)
        self.finished.connect(self.dismissed)
        window.task(lambda _: fetch_release(), self.checked, self.error)

    def dismissed(self, result):
        self.cancelled = True
        try:
            if self.download_task and self.download_task.isRunning(): self.download_task.requestInterruption()
        except RuntimeError:
            self.download_task = None
        self.window.update_dialog = None

    def checked(self, package):
        if self.cancelled: return
        self.package = package
        if version_tuple(package.version) <= version_tuple(VERSION):
            self.status.setText('أنت تستخدم أحدث إصدار: ' + VERSION)
        else:
            self.status.setText(f'الإصدار {package.version} متاح. إصدارك {VERSION}. سيطلب النظام كلمة المرور، ثم يعاد فتح التطبيق. تُحفظ الجلسات المكتملة.')
            self.install_button.setEnabled(True)
        self.notes.setPlainText(package.notes)

    def error(self, message):
        self.status.setText('تعذّر التحديث: ' + message); self.install_button.setEnabled(False)

    def install(self):
        if not self.package: return
        if not Path('/usr/lib/neura-ai/install-update').is_file() or not shutil.which('pkexec'):
            self.error('التثبيت من داخل التطبيق متاح للنسخة المثبتة بحزمة Arch.'); return
        self.install_button.setEnabled(False); self.progress.show(); self.status.setText('تنزيل الحزمة والتحقق من SHA256…')
        def download(task):
            def progress(received, total):
                if task.isInterruptionRequested(): raise RuntimeError('تم إلغاء التنزيل')
                task.progress.emit(received, total)
            return download_package(self.package, cache_directory(), progress)
        self.download_task = self.window.task(download, self.downloaded, self.error, self.progress_changed)
        self.download_task.finished.connect(lambda: setattr(self, 'download_task', None))

    def progress_changed(self, received, total):
        self.progress.setRange(0, 100); self.progress.setValue(round(received / total * 100))

    def downloaded(self, path):
        if self.cancelled: return
        self.status.setText('اكتمل التحقق. انتظر نافذة مصادقة النظام…')
        self.window.task(lambda _: self.window.service.stop(), lambda _: self.authorize(path), self.error)

    def authorize(self, path):
        if self.cancelled: return
        version = self.package.version
        self.window.task(lambda _: subprocess.run(['/usr/bin/pkexec', '/usr/lib/neura-ai/install-update', str(path), version],
            text=True, capture_output=True, timeout=300), self.installed, self.error)

    def installed(self, result):
        if result.returncode:
            self.error(result.stderr.strip()[-1000:] or 'لم يكتمل تثبيت التحديث.')
            self.window.begin_backend(); return
        QMessageBox.information(self, 'اكتمل التحديث', 'تم تثبيت التحديث. سيُعاد فتح Neura الآن.')
        subprocess.Popen(['/usr/bin/neura-ai', '--wait-for-lock'])
        self.window.close()


class MainWindow(QMainWindow):
    def __init__(self, settings, smoke_check=None):
        super().__init__()
        self.settings = settings; self.service = BackendService(settings)
        self.smoke_check = smoke_check; self.update_dialog = None
        self.tasks = set(); self.closing = False; self.stopping = False; self.loaded = False
        self.close_checked=False;self.checking_close=False
        self.setWindowTitle('Neura AI — معاينة' if os.environ.get('NEURA_PREVIEW') else 'Neura AI'); self.resize(1200, 850)
        self.setWindowIcon(QIcon(str(ROOT / 'assets/logo.png')))
        toolbar = QToolBar(); toolbar.setMovable(False); self.addToolBar(toolbar)
        toolbar.addWidget(QLabel('  Neura AI · ' + VERSION + '  '))
        settings_action = QAction('الإعدادات والنماذج', self); settings_action.triggered.connect(self.settings_dialog)
        toolbar.addAction(settings_action)
        update_action = QAction('التحديثات', self); update_action.triggered.connect(self.updates); toolbar.addAction(update_action)
        retry = QAction('إعادة الاتصال', self); retry.triggered.connect(self.restart); toolbar.addAction(retry)
        self.stack = QStackedWidget(); self.setCentralWidget(self.stack)
        splash = QWidget(); box = QVBoxLayout(splash)
        title = QLabel('NEURA AI'); title.setAlignment(Qt.AlignCenter); title.setStyleSheet('font-size:32px;color:#42a5f5')
        self.status = QLabel('جارٍ فتح Neura…'); self.status.setAlignment(Qt.AlignCenter); self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        box.addStretch(); box.addWidget(title); box.addWidget(self.status); box.addStretch()
        self.stack.addWidget(splash)
        self.preview_origin = None
        self.profile = QWebEngineProfile(self)
        self.interceptor = LocalRequests(lambda: self.service.url, lambda: self.preview_origin, self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.profile.downloadRequested.connect(self.save_export)
        self.view = QWebEngineView(); self.page = LocalPage(self.profile, lambda: self.service.url, self.view, lambda: self.preview_origin)
        self.view.setPage(self.page); self.stack.addWidget(self.view)
        self.view.loadFinished.connect(self.page_loaded)
        self.network = QNetworkAccessManager(self); self.network.setProxy(QNetworkProxy(QNetworkProxy.NoProxy))
        self.pending_health = False
        self.timer = QTimer(self); self.timer.setInterval(250); self.timer.timeout.connect(self.poll_backend)
        QTimer.singleShot(0, self.begin_backend)

    def task(self, function, success, failure=None, progress=None):
        thread = Task(function, self)
        self.tasks.add(thread)
        thread.succeeded.connect(success)
        thread.failed.connect(failure or self.show_error)
        if progress: thread.progress.connect(progress)
        thread.finished.connect(lambda: (self.tasks.discard(thread), thread.deleteLater()))
        thread.start()
        return thread

    def show_error(self, message):
        self.status.setText(message + '\nيمكنك فتح الإعدادات واختيار مجلد النماذج أو إعادة الاتصال.')
        self.stack.setCurrentIndex(0)
        if self.smoke_check:
            Path(self.smoke_check).write_text(json.dumps({'ready':False,'error':message}))
            self.close()

    def begin_backend(self):
        if self.closing: return
        self.loaded = False; self.stack.setCurrentIndex(0); self.status.setText('جارٍ فتح Neura…')
        try: self.service.start()
        except Exception as error:
            self.show_error(str(error)); return
        self.started = time.monotonic(); self.timer.start()

    def poll_backend(self):
        if self.closing: return
        if self.service.process is None or self.service.process.poll() is not None:
            self.timer.stop(); self.show_error('تعذّر بدء التطبيق. سجل التشخيص: ' + str(self.service.log_path)); return
        if self.pending_health: return
        if time.monotonic() - self.started > 30 and not self.loaded:
            self.timer.stop(); self.show_error('انتهت مهلة فتح التطبيق. سجل التشخيص: ' + str(self.service.log_path)); return
        self.pending_health = True
        request = QNetworkRequest(QUrl(self.service.url + '/health')); request.setTransferTimeout(800)
        reply = self.network.get(request)
        def received():
            self.pending_health = False
            try:
                payload = json.loads(bytes(reply.readAll()))
                if payload.get('instance_id') != self.service.instance: return
                self.preview_origin = payload.get('capabilities', {}).get('preview_origin')
                if not self.loaded:
                    self.loaded = True; self.timer.stop(); self.view.setUrl(QUrl(self.service.url + '/'))
                    if not self.smoke_check and self.settings.values['check_updates']:
                        QTimer.singleShot(3000, self.check_update_quietly)
            except (ValueError, TypeError): pass
            finally: reply.deleteLater()
        reply.finished.connect(received)

    def page_loaded(self, ok):
        if self.closing or not self.loaded: return
        if not ok: self.show_error('تعذّر فتح واجهة التطبيق.'); return
        self.stack.setCurrentIndex(1)
        if not self.smoke_check and not any((Path(self.settings.values['models_dir'])/name).is_file() for name in ['Qwen3.5-9B-Q4_K_M.gguf','gemma-4-E4B-Q4_K_M.gguf']):
            QTimer.singleShot(0, self.first_model_setup)
        if self.smoke_check:
            Path(self.smoke_check).write_text(json.dumps({'ready':True,'qt_webengine':True,'version':VERSION,'port':self.service.port}))
            QTimer.singleShot(250, self.close)

    def first_model_setup(self):
        QMessageBox.information(self, 'اختيار النماذج', 'اختر مجلد ملفات GGUF من الإعدادات لبدء المحادثة. الأوزان منفصلة عن تثبيت التطبيق.')
        self.settings_dialog()

    def save_export(self, download):
        url = download.url().toString()
        if not (url.startswith('blob:' + self.service.url + '/') or url.startswith(self.service.url + '/projects/')):
            download.cancel(); return
        target, _ = QFileDialog.getSaveFileName(self, 'حفظ نسخة المشروع', 'neura-project.zip', 'ZIP (*.zip)')
        if not target:
            download.cancel(); return
        destination = Path(target)
        download.setDownloadDirectory(str(destination.parent))
        download.setDownloadFileName(destination.name)
        download.accept()

    def restart(self):
        if self.closing: return
        if self.loaded:
            self.review_dirty('إعادة الاتصال',self._restart_backend)
        else:self._restart_backend()

    def review_dirty(self,title,continuation):
        if self.checking_close:return
        self.checking_close=True
        finished=[False]
        def received(dirty,timeout=False):
            if finished[0]:return
            finished[0]=True;self.checking_close=False
            warning='تعذر قراءة حالة المحرر؛ قد توجد تغييرات غير محفوظة.' if timeout else 'توجد تغييرات في محرر المشروع لم تُحفظ.'
            if dirty and QMessageBox.question(self,title,warning+'\nمتابعة وترك هذه التغييرات؟')!=QMessageBox.Yes:return
            continuation()
        self.page.runJavaScript('Boolean(window.NeuraWorkspace && window.NeuraWorkspace.dirty)',lambda dirty:received(bool(dirty)))
        QTimer.singleShot(1200,lambda:received(True,True))

    def _restart_backend(self):
        if self.closing:return
        self.timer.stop(); self.stack.setCurrentIndex(0); self.status.setText('جارٍ إعادة الفتح…')
        old=self.page
        self.page=LocalPage(self.profile,lambda:self.service.url,self.view,lambda:self.preview_origin)
        self.view.setPage(self.page);old.deleteLater()
        self.preview_origin=None
        self.task(lambda _: self.service.stop(), lambda _: self.begin_backend())

    def settings_dialog(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.Accepted: self.restart()

    def updates(self):
        if self.update_dialog:
            self.update_dialog.raise_(); return
        self.update_dialog = UpdateDialog(self); self.update_dialog.show()

    def check_update_quietly(self):
        if self.closing: return
        def checked(package):
            if not self.closing and version_tuple(package.version) > version_tuple(VERSION):
                self.statusBar().showMessage('تحديث جديد متاح — افتح التحديثات لتثبيته.')
        self.task(lambda _: fetch_release(), checked, lambda _: None)

    def closeEvent(self, event):
        if self.loaded and not self.close_checked and not self.smoke_check:
            event.ignore()
            def reviewed():
                self.close_checked=True;self.close()
            self.review_dirty('إغلاق Neura',reviewed)
            return
        self.closing = True; self.timer.stop()
        for task in self.tasks: task.requestInterruption()
        if not self.stopping:
            self.stopping = True
            self.view.setPage(QWebEnginePage(self.view));self.page.deleteLater();self.page=None
            self.stack.setCurrentIndex(0); self.status.setText('جارٍ إغلاق Neura…')
            self.task(lambda _: self.service.stop(), lambda _: None, lambda _: None)
        if self.tasks:
            event.ignore(); QTimer.singleShot(200, self.close); return
        if self.page:self.view.setPage(QWebEnginePage(self.view));self.page.deleteLater();self.page=None
        event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-check', help=argparse.SUPPRESS)
    parser.add_argument('--wait-for-lock', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--preview',action='store_true',help='Open a separate local review profile')
    args = parser.parse_args()
    if args.preview:setup_preview_environment()
    app = QApplication(['neura-ai']); app.setApplicationName('Neura AI'); app.setOrganizationName('Neura'); app.setDesktopFileName('neura-ai')
    app.setStyle('Fusion'); app.setStyleSheet('QWidget{background:#101418;color:#eceff1} QPushButton,QToolButton{padding:8px} QLineEdit,QSpinBox,QComboBox{padding:6px;background:#1b232a} QTableWidget{background:#161b20} QToolBar{spacing:8px;padding:5px}')
    data_directory().mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = QLockFile(str(data_directory() / '.desktop.lock')); lock.setStaleLockTime(0)
    name = 'neura-ai-' + str(os.getuid()) + '-' + hashlib.sha256(str(config_directory()).encode()).hexdigest()[:12]
    acquired = lock.tryLock(0)
    if args.wait_for_lock and not acquired:
        for _ in range(100):
            time.sleep(.1)
            if lock.tryLock(0): acquired = True; break
    if not acquired:
        socket = QLocalSocket(); socket.connectToServer(name)
        if socket.waitForConnected(500): socket.write(b'activate'); socket.flush(); socket.waitForBytesWritten(500)
        return 0
    try: settings = DesktopSettings()
    except Exception as error:
        answer = QMessageBox.question(None, 'إصلاح الإعدادات', 'تعذّر قراءة الإعدادات. هل تريد حفظ نسخة احتياطية واستعادة الإعدادات الافتراضية؟\n' + str(error))
        if answer != QMessageBox.Yes: return 1
        path = config_directory() / 'settings.json'
        try:
            if path.exists(): path.rename(path.with_name('settings-backup-' + str(int(time.time())) + '.json'))
            settings = DesktopSettings(); settings.save()
        except Exception as failure:
            QMessageBox.critical(None, 'Neura', str(failure)); return 1
    window = MainWindow(settings, args.smoke_check)
    server = QLocalServer(app); QLocalServer.removeServer(name); server.listen(name)
    def activate():
        connection = server.nextPendingConnection()
        if connection: connection.close(); connection.deleteLater()
        window.showNormal(); window.raise_(); window.activateWindow()
    server.newConnection.connect(activate)
    window.show()
    if args.smoke_check:
        QTimer.singleShot(40_000, lambda: (window.show_error('Desktop startup timeout') if not Path(args.smoke_check).exists() else None))
    try: return app.exec()
    finally: window.service.stop(); lock.unlock()
