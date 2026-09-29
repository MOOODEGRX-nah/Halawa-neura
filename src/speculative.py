"""
Neura Speculative Decoding Engine (T-0414)
Custom n-gram prompt-lookup draft (works with any llama-cpp-python version).
"""
import time
import numpy as np
from llama_cpp import Llama

TARGET_MODEL = 'models/Qwen2.5-7B-Instruct-Q4_K_M.gguf'


class PromptLookupDraft:
    """Duck-typed draft model: proposes tokens by n-gram lookup in context."""

    def __init__(self, ngram_size=2, n_draft=6):
        self.ngram_size = ngram_size
        self.n_draft = n_draft
        self.calls = 0
        self.hits = 0

    def __call__(self, input_ids, *args, **kwargs):
        self.calls += 1
        ids = list(input_ids)
        n = self.ngram_size
        if len(ids) < n + 2:
            return np.array([], dtype=np.int32)
        needle = ids[-n:]
        last = len(ids) - n
        for i in range(0, last):
            if ids[i:i + n] == needle:
                draft = ids[i + n:i + n + self.n_draft]
                if draft:
                    self.hits += 1
                    return np.array(draft, dtype=np.int32)
        return np.array([], dtype=np.int32)


def make_llama(draft=None):
    return Llama(
        model_path=TARGET_MODEL,
        n_ctx=1024,
        n_batch=512,
        n_gpu_layers=-1,
        main_gpu=0,
        tensor_split=[1.0, 0.0],
        verbose=False,
        draft_model=draft,
    )


def run_rounds(llm, prompt, rounds=4, tokens=80):
    total_tok = 0
    total_t = 0.0
    for i in range(1, rounds + 1):
        t0 = time.perf_counter()
        out = llm(prompt, max_tokens=tokens, temperature=0.7)
        dt = time.perf_counter() - t0
        tok = out['usage']['completion_tokens']
        total_tok += tok
        total_t += dt
        print('  Round %d: %d tok in %.2fs = %.2f tok/s' % (i, tok, dt, tok / dt))
    return total_tok / total_t if total_t else 0.0


def main():
    prompt = 'Explain the theory of general relativity in detail.'
    print('=' * 70)
    print('T-0414: Speculative Decoding Benchmark (custom prompt lookup)')
    print('=' * 70)

    print('[1/2] Baseline (no draft) on RX 9060 XT ...')
    base_llm = make_llama(draft=None)
    base_speed = run_rounds(base_llm, prompt)
    del base_llm

    print('[2/2] With prompt-lookup draft on RX 9060 XT ...')
    draft = PromptLookupDraft(ngram_size=2, n_draft=6)
    spec_llm = make_llama(draft=draft)
    spec_speed = run_rounds(spec_llm, prompt)
    hit_rate = 100.0 * draft.hits / draft.calls if draft.calls else 0.0
    del spec_llm

    print()
    print('=' * 70)
    print('RESULTS')
    print('=' * 70)
    print('  Baseline speed : %.2f tok/s' % base_speed)
    print('  Speculative    : %.2f tok/s' % spec_speed)
    print('  Speedup        : %.2fx' % (spec_speed / base_speed if base_speed else 0))
    print('  Draft hit rate : %.1f%% (%d/%d)' % (hit_rate, draft.hits, draft.calls))
    print('=' * 70)


if __name__ == '__main__':
    main()
