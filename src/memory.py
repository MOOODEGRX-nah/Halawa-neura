import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json
import numpy as np
from llama_cpp import Llama

EMBED_MODEL = 'models/nomic-embed-text-v1.5.Q8_0.gguf'
MEMORY_FILE = 'data/memory.json'


class SemanticMemory:
    """Long-term semantic memory on RX 580 (embeddings + cosine search)."""

    def __init__(self, model_path=EMBED_MODEL, store_path=MEMORY_FILE):
        self.store_path = store_path
        self.entries = []
        if os.path.exists(store_path):
            with open(store_path, 'r', encoding='utf-8') as f:
                self.entries = json.load(f)
        print('[Memory] Loading embedding model on RX 580 ...')
        self.embedder = Llama(
            model_path=model_path,
            embedding=True,
            n_gpu_layers=-1,
            main_gpu=1,
            tensor_split=[0.0, 1.0],
            verbose=False,
        )
        print('[Memory] Ready. Stored entries:', len(self.entries))

    def _embed(self, text):
        res = self.embedder.create_embedding(text)
        v = np.array(res['data'][0]['embedding'], dtype=np.float32)
        return v / (np.linalg.norm(v) + 1e-9)

    def add(self, text, meta=None):
        vec = self._embed(text)
        self.entries.append({'text': text, 'vec': vec.tolist(), 'meta': meta or {}})
        self._save()
        return len(self.entries) - 1

    def _save(self):
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
        with open(self.store_path, 'w', encoding='utf-8') as f:
            json.dump(self.entries, f, ensure_ascii=False)

    def search(self, query, top_k=3):
        if not self.entries:
            return []
        q = self._embed(query)
        mat = np.array([e['vec'] for e in self.entries], dtype=np.float32)
        sims = mat @ q
        idx = np.argsort(sims)[::-1][:top_k]
        return [(float(sims[i]), self.entries[i]['text']) for i in idx]


if __name__ == '__main__':
    mem = SemanticMemory()
    mem.add('Neura uses RX 9060 XT for chat and RX 580 for parallel services.')
    mem.add('The user prefers Arabic responses and engineering honesty.')
    mem.add('Prompt-lookup speculative decoding was tested and rejected (0.84x speedup).')
    print()
    print('Query: Which GPU runs the chat model?')
    for score, text in mem.search('Which GPU runs the chat model?'):
        print('  %.3f  %s' % (score, text))
