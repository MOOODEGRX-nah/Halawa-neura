import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time
from llama_cpp import Llama
from memory import SemanticMemory
from state import get_state

CHAT_MODEL = 'models/Qwen2.5-7B-Instruct-Q4_K_M.gguf'


class NeuraCore:
    """Main AI engine: chat on RX 9060 XT + semantic memory on RX 580."""

    def __init__(self):
        self.state = get_state()
        print('[Core] Loading chat model on RX 9060 XT ...')
        t0 = time.perf_counter()
        self.llm = Llama(
            model_path=CHAT_MODEL,
            n_ctx=1024,
            n_batch=512,
            n_gpu_layers=-1,
            main_gpu=0,
            tensor_split=[1.0, 0.0],
            verbose=False,
        )
        print(f'[Core] Chat model loaded in {time.perf_counter()-t0:.1f}s')
        print('[Core] Loading semantic memory on RX 580 ...')
        self.memory = SemanticMemory()
        print(f'[Core] Memory ready with {len(self.memory.entries)} entries')

    def _build_messages(self, user_message):
        memories = self.memory.search(user_message, top_k=2)
        memory_context = ''
        if memories:
            mem_texts = [text for score, text in memories if score > 0.5]
            if mem_texts:
                memory_context = '\n\nRelevant memories:\n' + '\n'.join('- ' + t for t in mem_texts)
        system_prompt = "You are Neura, a helpful AI assistant."
        if memory_context:
            system_prompt += memory_context
        return [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message},
        ], len(memories)

    def chat(self, user_message, max_tokens=200):
        messages, hits = self._build_messages(user_message)
        self.state.update_status('thinking', 'Generating response...')
        t0 = time.perf_counter()
        response = self.llm.create_chat_completion(messages=messages, max_tokens=max_tokens)
        dt = time.perf_counter() - t0
        assistant_message = response['choices'][0]['message']['content']
        tokens = response['usage']['completion_tokens']
        speed = tokens / dt if dt > 0 else 0
        self.memory.add(f"User: {user_message}")
        self.memory.add(f"Assistant: {assistant_message}")
        self.state.update_status('ready', 'Response complete')
        self.state.update_monitor(tokens_per_sec=speed)
        return {'message': assistant_message, 'tokens': tokens, 'time': dt,
                'speed': speed, 'memory_hits': hits}

    def chat_stream(self, user_message, max_tokens=200):
        messages, hits = self._build_messages(user_message)
        self.state.update_status('thinking', 'Generating...')
        t0 = time.perf_counter()
        response_gen = self.llm.create_chat_completion(
            messages=messages, max_tokens=max_tokens, stream=True)
        tokens = 0
        full_text = ''
        for chunk in response_gen:
            delta = chunk['choices'][0].get('delta', {})
            piece = delta.get('content')
            if piece:
                full_text += piece
                tokens += 1
                yield {'type': 'token', 'text': piece}
        dt = time.perf_counter() - t0
        speed = tokens / dt if dt > 0 else 0
        self.memory.add(f"User: {user_message}")
        self.memory.add(f"Assistant: {full_text}")
        self.state.update_status('ready', 'Response complete')
        self.state.update_monitor(tokens_per_sec=speed)
        yield {'type': 'done', 'tokens': tokens, 'time': dt,
               'speed': speed, 'memory_hits': hits}


def demo():
    print('=' * 70)
    print('NeuraCore streaming demo')
    print('=' * 70)
    core = NeuraCore()
    for piece in core.chat_stream('Which GPU do you use for chat?', max_tokens=60):
        if piece['type'] == 'token':
            print(piece['text'], end='', flush=True)
        else:
            print()
            print('[done: %.1f tok/s]' % piece['speed'])


if __name__ == '__main__':
    demo()
