import sys, os, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from monitor import get_monitor
from llama_cpp import Llama

m = get_monitor()
m.start()
time.sleep(2)

peaks = {'gpu': 0.0, 'vram': 0.0}
def sampler():
    while True:
        d = m.state.monitor_data
        peaks['gpu'] = max(peaks['gpu'], d['gpu_percent'])
        peaks['vram'] = max(peaks['vram'], d['vram_used_gb'])
        time.sleep(0.5)
threading.Thread(target=sampler, daemon=True).start()

print('Loading model on RX 9060 XT ...')
llm = Llama(model_path='models/Qwen2.5-7B-Instruct-Q4_K_M.gguf',
            n_ctx=1024, n_gpu_layers=-1, main_gpu=0,
            tensor_split=[1.0, 0.0], verbose=False)

print('Generating 3 rounds while monitoring ...')
for i in range(1, 4):
    llm('Tell me a detailed story about space exploration.', max_tokens=300)
    d = m.state.monitor_data
    print('  After round %d: GPU %.0f%% | VRAM %.2f GB' % (i, d['gpu_percent'], d['vram_used_gb']))

m.stop()
print()
print('PEAK DURING LOAD: GPU %.0f%% | VRAM %.2f GB' % (peaks['gpu'], peaks['vram']))
if peaks['gpu'] > 50 and peaks['vram'] > 2.0:
    print('PASS: monitor sees GPU load correctly')
else:
    print('FAIL: monitor blind to GPU load - counter path needs debugging')
