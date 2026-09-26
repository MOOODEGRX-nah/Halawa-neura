import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time
from llama_cpp import Llama
from memory import SemanticMemory
from state import get_state

CHAT_MODEL = 'models/Qwen2.5-7B-Instruct-Q4_K_M.gguf'


class NeuraCore:
    """Main AI engine: chat model on RX 9060 XT + semantic memory on RX 580."""

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

    def chat(self, user_message, max_tokens=200):
        """Generate response with memory context."""
        self.state.update_status('thinking', 'Searching memory...')

        # Search memory for relevant context
        memories = self.memory.search(user_message, top_k=2)
        memory_context = ''
        if memories:
            mem_texts = [text for score, text in memories if score > 0.5]
            if mem_texts:
                memory_context = '\n\nRelevant memories:\n' + '\n'.join(f'- {t}' for t in mem_texts)

        # Build prompt with memory context
        system_prompt = "You are Neura, a helpful AI assistant."
        if memory_context:
            system_prompt += memory_context

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message}
        ]

        self.state.update_status('thinking', 'Generating response...')
        t0 = time.perf_counter()
        response = self.llm.create_chat_completion(messages=messages, max_tokens=max_tokens)
        dt = time.perf_counter() - t0

        assistant_message = response['choices'][0]['message']['content']
        tokens = response['usage']['completion_tokens']
        speed = tokens / dt if dt > 0 else 0

        # Save to memory
        self.memory.add(f"User: {user_message}")
        self.memory.add(f"Assistant: {assistant_message}")

        self.state.update_status('ready', 'Response complete')
        self.state.update_monitor(tokens_per_sec=speed)

        return {
            'message': assistant_message,
            'tokens': tokens,
            'time': dt,
            'speed': speed,
            'memory_hits': len(memories)
        }


def demo():
    print('='*70)
    print('T-0307: NeuraCore with Semantic Memory')
    print('='*70)

    core = NeuraCore()

    questions = [
        'Which GPU do you use for chat?',
        'What language should you respond in?',
        'Did you try speculative decoding?'
    ]

    for q in questions:
        print(f'\nUser: {q}')
        result = core.chat(q, max_tokens=100)
        print(f'Neura: {result["message"][:150]}...')
        print(f'  [{result["tokens"]} tok in {result["time"]:.2f}s = {result["speed"]:.1f} tok/s | memory hits: {result["memory_hits"]}]')

    print(f'\n[Core] Total memory entries: {len(core.memory.entries)}')


if __name__ == '__main__':
    demo()
