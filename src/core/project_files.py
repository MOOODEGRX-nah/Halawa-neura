"""Bounded project file IO using directory descriptors, never followed links."""
import os
import secrets
import stat
from pathlib import PurePosixPath

MAX_FILES = 48
MAX_FILE = 300_000
MAX_TOTAL = 2_000_000
BINARY_ASSETS = {'.png','.jpg','.jpeg','.gif','.webp','.ico','.woff','.woff2','.pdf'}


class ProjectError(ValueError):
    status = 400


class Conflict(ProjectError):
    status = 409


def safe_path(value, *, internal=False):
    if not isinstance(value, str) or not value or len(value) > 240:
        raise ProjectError('مسار الملف غير صالح')
    if any(c in value for c in ('\\', '\x00', ':', '%')) or any(ord(c) < 32 for c in value):
        raise ProjectError('رموز غير مسموحة في المسار')
    parts = value.split('/')
    if PurePosixPath(value).is_absolute() or any(not p or p in ('.', '..') or len(p) > 96 or len(p.encode('utf-8'))>240 for p in parts):
        raise ProjectError('يجب أن يكون المسار نسبيًا داخل المشروع')
    if not internal and any(p.startswith('.') or p.upper().split('.')[0] in ('CON', 'PRN', 'AUX', 'NUL') for p in parts):
        raise ProjectError('ملفات البيانات الداخلية والمسارات المحجوزة غير مسموحة')
    return parts


class SafeTree:
    def __init__(self, root):
        self.root = root
        from pathlib import Path
        self.fd=None
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for part in Path(os.path.abspath(root)).parts[1:]:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=child
            self.fd=fd
        except OSError as exc:
            os.close(fd)
            raise ProjectError('جذر الملفات أو أحد آبائه يحتوي رابطًا أو ليس مجلدًا آمنًا') from exc

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def parent(self, value, *, create=False, internal=False):
        parts = safe_path(value, internal=internal)
        fd = os.dup(self.fd)
        try:
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd, parts[-1]
        except BaseException:
            os.close(fd)
            raise ProjectError('المسار غير متاح أو يحتوي رابطًا غير مسموح')

    def read(self, value, *, internal=False, limit=MAX_FILE):
        parent, name = self.parent(value, internal=internal)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size > limit:
                    raise ProjectError('الملف غير عادي أو يتجاوز حد الحجم')
                with os.fdopen(fd, 'rb', closefd=False) as stream:
                    result = stream.read(limit + 1)
                if len(result) > limit:
                    raise ProjectError('الملف يتجاوز حد الحجم')
                return result
            finally:
                os.close(fd)
        except OSError as exc:
            raise ProjectError('تعذر قراءة الملف؛ الروابط غير مسموحة') from exc
        finally:
            os.close(parent)

    def write(self, value, data, *, internal=False):
        if isinstance(data, str):
            data = data.encode('utf-8')
        limit = MAX_TOTAL * 3 if internal else MAX_FILE
        if len(data) > limit:
            raise ProjectError('الملف يتجاوز حد الحجم')
        parent, name = self.parent(value, create=True, internal=internal)
        temporary = '.write-' + secrets.token_hex(12)
        try:
            try:
                existing = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISREG(existing.st_mode) or existing.st_nlink!=1:
                    raise ProjectError('لا يمكن استبدال رابط أو ملف غير عادي')
            except FileNotFoundError:
                pass
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
            os.close(parent)

    def remove(self, value, *, internal=False):
        parent, name = self.parent(value, internal=internal)
        try:
            os.unlink(name, dir_fd=parent)
            os.fsync(parent)
        except FileNotFoundError:
            pass
        finally:
            os.close(parent)

    def info(self, value):
        parent, name = self.parent(value)
        try:
            metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink!=1:
                raise ProjectError('الملف النهائي غير عادي')
            return {'size': metadata.st_size, 'mtime_ns': metadata.st_mtime_ns}
        finally:
            os.close(parent)

    def inventory(self):
        result = {}

        def walk(fd, prefix='', depth=0):
            if depth > 12:
                raise ProjectError('تداخل المجلدات يتجاوز الحد')
            for name in sorted(os.listdir(fd)):
                if name == '.neura' and not prefix:
                    continue
                path = prefix + name
                safe_path(path)
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        walk(child, path + '/', depth + 1)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    if info.st_nlink!=1:raise ProjectError('الروابط الصلبة غير مسموحة داخل المشروع')
                    result[path] = {'size': info.st_size, 'mtime_ns': info.st_mtime_ns}
                    if len(result) > MAX_FILES or info.st_size > MAX_FILE:
                        raise ProjectError('عدد الملفات أو حجمها يتجاوز الحد')
                else:
                    raise ProjectError('المشروع يحتوي رابطًا أو ملفًا غير عادي')
            if sum(x['size'] for x in result.values()) > MAX_TOTAL:
                raise ProjectError('حجم المشروع يتجاوز الحد')

        try:
            walk(self.fd)
        except OSError as exc:
            raise ProjectError('تغير المسار أثناء القراءة أو يحتوي رابطًا') from exc
        return result


def bounded_files(files):
    if not files or len(files) > MAX_FILES:
        raise ProjectError('يجب أن يحتوي المشروع ملفًا واحدًا على الأقل ضمن الحد المسموح')
    size = 0
    for path, text in files.items():
        safe_path(path)
        if not isinstance(text,(str,bytes)):
            raise ProjectError('نوع محتوى الملف غير صالح')
        data=text.encode() if isinstance(text,str) else text
        if isinstance(text,bytes) and PurePosixPath(path).suffix.lower() not in BINARY_ASSETS:
            raise ProjectError('ملف مصدر غير نصي: '+path)
        if isinstance(text,str) and PurePosixPath(path).suffix.lower() in BINARY_ASSETS:
            raise ProjectError('هذا الأصل الثنائي يحتاج بيانات فعلية؛ استخدم SVG للنصوص المولّدة: '+path)
        if not data.strip() or len(data) > MAX_FILE:
            raise ProjectError('ملف فارغ أو يتجاوز حد الحجم: ' + path)
        size += len(data)
    if size > MAX_TOTAL:
        raise ProjectError('حجم المشروع يتجاوز الحد')
