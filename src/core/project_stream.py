"""Incremental fenced-file parser; incomplete output remains a distinct draft."""
import re
import posixpath
from pathlib import PurePosixPath
from urllib.parse import urlsplit,unquote
from src.core.project_files import ProjectError, MAX_FILE, MAX_FILES, safe_path


class FileStream:
    def __init__(self, emit, *, expected_files=(), filename_hints=()):
        self.emit = emit
        self.buffer = ''
        self.total = 0
        self.files = {}
        self.current = None
        self.fence_size = 0
        self.partial = 0
        self.first_body_line = True
        self.expected_files=list(expected_files)
        self.filename_hints=list(filename_hints)
        self.resolutions={}
        for path in self.expected_files+self.filename_hints:safe_path(path)

    def _referenced_files(self):
        from src.core.project_validation import References
        result=[]
        for path,value in self.files.items():
            if not value['complete'] or PurePosixPath(path).suffix.lower() not in ('.html','.htm'):continue
            parsed=References();parsed.feed(value['content'])
            for reference in parsed.references:
                try:
                    url=urlsplit(reference)
                    if url.scheme or url.netloc or not url.path:continue
                    target=posixpath.normpath(posixpath.join(posixpath.dirname(path),unquote(url.path)))
                    safe_path(target)
                except (ValueError,ProjectError):continue
                result.append(target)
        return list(dict.fromkeys(result))

    def _filename(self,language,extensions):
        for origin,paths in [('invoice',self.expected_files),('reference',self._referenced_files()),('hint',self.filename_hints)]:
            candidates=[path for path in paths if PurePosixPath(path).suffix.lower() in extensions and path not in self.files]
            candidates=list(dict.fromkeys(candidates))
            if len(candidates)==1:return candidates[0],origin
            if len(candidates)>1:break
        raise ProjectError('اسم ملف '+language+' غير محدد أو له أكثر من مرشح؛ يجب كتابة الاسم النسبي في رأس الكتلة.')

    def feed(self, text):
        self.total += len(text.encode('utf-8'))
        if self.total > 1_000_000:
            raise ProjectError('تجاوز مخرج التوليد الحد المسموح')
        self.buffer += text
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            self._line(line.rstrip('\r'), newline=True)
        if self.current and self.buffer and not re.fullmatch(r'\s*`*\s*',self.buffer):
            end=len(self.buffer)-(1 if self.buffer.endswith('\r') else 0)
            self._append(self.buffer[self.partial:end])
            self.partial=end

    def _append(self,text):
        if not text:return
        entry=self.files[self.current]
        if len((entry['content']+text).encode())>MAX_FILE:
            raise ProjectError('الملف المولّد يتجاوز الحد')
        offset=len(entry['content'].encode('utf-8'))
        entry['content']+=text
        self.emit('file_delta',{'path':self.current,'delta':text,'offset':offset})

    def _line(self, line, *, newline):
        if self.current:
            if re.fullmatch(r'\s*`{' + str(self.fence_size) + r',}\s*', line):
                entry = self.files[self.current]
                if not entry['content'].strip():
                    raise ProjectError('ملف مولّد فارغ: ' + self.current)
                entry['complete'] = True
                self.emit('file_draft_complete', {'path': self.current})
                self.current = None
                self.partial=0
                return
            entry = self.files[self.current]
            text = line[self.partial:] + ('\n' if newline else '')
            if self.first_body_line:
                declared = re.match(r'\s*(?:#|//|<!--)\s*(?:file|filename)\s*:\s*([^\s>]+)', line, re.I)
                if declared and declared[1] != self.current:
                    raise ProjectError('اسم الملف داخل المخرج يخالف اسمه في رأس الكتلة')
            self._append(text)
            self.partial=0
            self.first_body_line=False
            return
        opening = re.fullmatch(r'\s*(`{3,})([^`]*)', line)
        if not opening:
            return
        tokens = opening[2].strip().split()
        extensions = {'python': {'.py'}, 'html': {'.html', '.htm'}, 'css': {'.css'},
                      'javascript': {'.js'}, 'js': {'.js'}, 'json': {'.json'}, 'markdown': {'.md'}}
        origin='model'
        if len(tokens)==1 and tokens[0].lower() in extensions:
            language=tokens[0];path,origin=self._filename(language,extensions[language.lower()])
        elif len(tokens)==2:language,path=tokens
        else:raise ProjectError('يجب تحديد لغة الملف واسمه النسبي في رأس الكتلة: '+line[:120])
        safe_path(path)
        if language.lower() in extensions and PurePosixPath(path).suffix.lower() not in extensions[language.lower()]:
            raise ProjectError('لغة الكتلة لا توافق امتداد الملف: ' + path)
        if path in self.files or len(self.files) >= MAX_FILES:
            raise ProjectError('اسم ملف مكرر أو عدد الملفات يتجاوز الحد: ' + path)
        self.current, self.fence_size = path, len(opening[1])
        self.first_body_line=True
        self.partial=0
        self.files[path] = {'content': '', 'complete': False}
        self.resolutions[path]=origin
        self.emit('file_started', {'path': path, 'language': language,'filename_origin':origin})

    def finish(self):
        if self.buffer:
            self._line(self.buffer.rstrip('\r'), newline=False)
            self.buffer = ''
        if self.current:
            raise ProjectError('توقف التوليد قبل إكمال الملف: ' + self.current)
        if not self.files:
            raise ProjectError('لم يُنتج النموذج أي ملف مسمى')
        return {path: value['content'] for path, value in self.files.items()}
