"""N038: a local knowledge base of the user's own documents (RAG) with cited answers.

Documents are split into overlapping chunks and embedded with a small local GGUF embedding model
on the CPU (it never competes with the chat model for the GPU). Questions retrieve the closest
chunks; the chat model answers from them only, citing [n]. Deleting a document deletes its chunks,
so it can never be retrieved again. Retrieved text is data, never instructions or permissions.
"""
import hashlib
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

MAX_DOCUMENTS = 300
MAX_DOCUMENT_CHARS = 400_000
CHUNK = 900
OVERLAP = 150
MIN_SCORE = 0.55
TEXT_SUFFIXES = {'.txt', '.md', '.markdown', '.csv', '.json', '.html', '.htm', '.py', '.js', '.ts', '.css', '.yaml', '.yml', '.toml', '.ini', '.log', '.srt', '.vtt', '.xml', '.tex', '.rst'}


class KnowledgeError(ValueError):
    status = 400


def find_embedding_model(models_dir):
    folder = Path(models_dir)
    candidates = sorted(p for p in folder.glob('*.gguf') if re.search(r'embed', p.name, re.I)) if folder.is_dir() else []
    return candidates[0] if candidates else None


class LocalEmbedder:
    """Lazily loaded CPU embedding model (nomic-embed style task prefixes)."""

    def __init__(self, model_path, threads=4):
        self.model_path, self.threads = model_path, threads
        self._model, self._lock = None, threading.Lock()

    @property
    def available(self):
        return bool(self.model_path and Path(self.model_path).is_file())

    def _load(self):
        if self._model is None:
            if not self.available:
                raise KnowledgeError('نموذج التضمين غير موجود في مجلد النماذج (مثل nomic-embed-text). أضفه ثم أعد المحاولة.')
            from llama_cpp import Llama
            self._model = Llama(model_path=str(self.model_path), embedding=True, n_gpu_layers=0, n_ctx=2048, n_threads=self.threads, verbose=False)
        return self._model

    def embed(self, texts, kind):
        prefix = 'search_query: ' if kind == 'query' else 'search_document: '
        with self._lock:
            model = self._load()
            return [list(map(float, v)) for v in model.embed([prefix + t for t in texts])]


def to_text(name, raw):
    """Plain text from a supported text file; HTML tags removed. PDFs/Office files are not parsed here."""
    suffix = Path(name).suffix.lower()
    if suffix not in TEXT_SUFFIXES:
        raise KnowledgeError('نوع الملف غير مدعوم في المعرفة (المدعوم: نصوص وMarkdown وCSV وHTML وكود). ملفات PDF وOffice غير مدعومة بعد؛ انسخ نصها في ملف .txt.')
    text = raw.decode('utf-8', errors='replace') if isinstance(raw, bytes) else str(raw)
    if suffix in ('.html', '.htm', '.xml'):
        from src.core.web_reader import extract
        text = extract(text)[1] if suffix != '.xml' else re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text).strip()
    if len(text) < 20:
        raise KnowledgeError('الملف لا يحتوي نصًا كافيًا.')
    if len(text) > MAX_DOCUMENT_CHARS:
        raise KnowledgeError('الملف أطول من ' + str(MAX_DOCUMENT_CHARS) + ' حرف؛ قسّمه إلى ملفات أصغر.')
    return text


def chunks(text):
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    out, current = [], ''
    for paragraph in paragraphs:
        while len(paragraph) > CHUNK:
            cut = max(paragraph.rfind(mark, 0, CHUNK) for mark in '.؟!?\n')
            cut = cut + 1 if cut > CHUNK // 2 else CHUNK
            piece, paragraph = paragraph[:cut], paragraph[max(0, cut - OVERLAP):]
            if current:
                out.append(current); current = ''
            out.append(piece.strip())
        if len(current) + len(paragraph) + 2 > CHUNK and current:
            out.append(current)
            current = current[-OVERLAP:] + '\n' + paragraph
        else:
            current = (current + '\n\n' + paragraph).strip()
    if current:
        out.append(current)
    return [c for c in out if len(c) >= 20]


class KnowledgeBase:
    def __init__(self, data_dir, embedder):
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = data_dir / 'knowledge.sqlite3'
        self.embedder = embedder
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, title TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE, chars INTEGER NOT NULL, chunks INTEGER NOT NULL, added REAL NOT NULL, source TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL, position INTEGER NOT NULL, text TEXT NOT NULL, vector BLOB NOT NULL)')
        self.db.execute('CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id)')
        self.db.commit()
        self.path.chmod(0o600)

    def close(self):
        with self.lock:
            self.db.close()

    def documents(self):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT id,title,chars,chunks,added,source FROM documents ORDER BY added DESC').fetchall()]

    def add(self, title, text, source='upload'):
        import numpy
        title = re.sub(r'\s+', ' ', str(title or '')).strip()[:160] or 'مستند'
        digest = hashlib.sha256(text.encode()).hexdigest()
        with self.lock:
            row = self.db.execute('SELECT id,title FROM documents WHERE sha256=?', (digest,)).fetchone()
            if row:
                return {'id': row['id'], 'title': row['title'], 'duplicate': True}
            if self.db.execute('SELECT COUNT(*) FROM documents').fetchone()[0] >= MAX_DOCUMENTS:
                raise KnowledgeError('وصلت المعرفة إلى حد ' + str(MAX_DOCUMENTS) + ' مستند؛ احذف بعضها أولًا.')
        pieces = chunks(text)
        if not pieces:
            raise KnowledgeError('لم أجد نصًا قابلًا للفهرسة في المستند.')
        vectors = []
        for start in range(0, len(pieces), 16):
            vectors += self.embedder.embed(pieces[start:start + 16], 'document')
        matrix = numpy.asarray(vectors, dtype=numpy.float32)
        matrix /= numpy.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
        document_id = 'k_' + uuid.uuid4().hex
        with self.lock:
            self.db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?)', (document_id, title, digest, len(text), len(pieces), time.time(), source))
            self.db.executemany('INSERT INTO chunks(document_id,position,text,vector) VALUES(?,?,?,?)',
                                [(document_id, i, piece, matrix[i].tobytes()) for i, piece in enumerate(pieces)])
            self.db.commit()
        return {'id': document_id, 'title': title, 'chunks': len(pieces), 'duplicate': False}

    def delete(self, document_id):
        with self.lock:
            row = self.db.execute('SELECT title FROM documents WHERE id=?', (document_id,)).fetchone()
            if not row:
                raise KeyError(document_id)
            self.db.execute('DELETE FROM chunks WHERE document_id=?', (document_id,))
            self.db.execute('DELETE FROM documents WHERE id=?', (document_id,))
            self.db.commit()
        return {'deleted': document_id, 'title': row['title']}

    def search(self, query, limit=4):
        import numpy
        with self.lock:
            rows = self.db.execute('SELECT c.text, c.position, c.vector, d.title, d.id FROM chunks c JOIN documents d ON d.id=c.document_id').fetchall()
        if not rows:
            raise KnowledgeError('المعرفة فارغة. أضف ملفاتك من صفحة «المساعد ← المعرفة» أولًا.')
        q = numpy.asarray(self.embedder.embed([query], 'query')[0], dtype=numpy.float32)
        q /= numpy.linalg.norm(q) + 1e-9
        matrix = numpy.frombuffer(b''.join(r['vector'] for r in rows), dtype=numpy.float32).reshape(len(rows), -1)
        scores = matrix @ q
        order = numpy.argsort(-scores)[:limit]
        return [{'title': rows[i]['title'], 'document_id': rows[i]['id'], 'position': rows[i]['position'], 'text': rows[i]['text'], 'score': float(scores[i])} for i in order]
