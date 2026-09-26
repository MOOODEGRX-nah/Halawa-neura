"""
Stress Test RX 580 - Load + Monitor simultaneously
Answers: Are we using 100% of the card?
"""
import subprocess, sys, time, threading, json

class GPUMonitor:
    def __init__(self):
        self.samples = []
        self.running = True

    def query_stats(self):
        ps = r"""
        $cpu  = (Get-Counter '\Processor(_Total)\% Processor Time' -ErrorAction SilentlyContinue).CounterSamples[0].CookedValue
        $eng  = Get-Counter '\GPU Engine(*engtype_3D*)\Utilization Percentage' -ErrorAction SilentlyContinue
        $mem  = Get-Counter '\GPU Local Adapter Memory(*adapter_luid*dedicated*)\Dedicated Usage' -ErrorAction SilentlyContinue
        $util = @()
        if ($eng) { foreach ($s in $eng.CounterSamples) { $util += [pscustomobject]@{Name=$s.InstanceName; Util=$s.CookedValue} } }
        $vram = 0
        if ($mem) { foreach ($s in $mem.CounterSamples) { $vram += $s.CookedValue } }
        [pscustomobject]@{cpu=$cpu; util=$util; vram=$vram} | ConvertTo-Json -Depth 3 -Compress
        """
        try:
            r = subprocess.run(['powershell','-NoProfile','-Command',ps],
                               capture_output=True, text=True, timeout=8)
            return json.loads(r.stdout.strip()) if r.stdout.strip() else None
        except Exception as e:
            return {'error': str(e)}

    def run(self):
        print('\n[Monitor] Sampling every 1s ...')
        while self.running:
            s = self.query_stats()
            if s and 'error' not in s:
                engines = s.get('util') or []
                max_util = max([e['Util'] for e in engines]) if engines else 0
                vram_mb = (s.get('vram') or 0) / (1024**2)
                self.samples.append({
                    't': time.perf_counter(),
                    'cpu': s.get('cpu', 0),
                    'gpu': max_util,
                    'vram_mb': vram_mb,
                })
            time.sleep(1.0)

    def stop(self):
        self.running = False

def stress_worker(result_dict):
    from llama_cpp import Llama
    model_path = 'models/Qwen2.5-7B-Instruct-Q4_K_M.gguf'
    print('[Worker] Loading model on RX 580 (device 1) ...')
    t0 = time.perf_counter()
    llm = Llama(
        model_path=model_path,
        n_ctx=1024, n_batch=512,
        n_gpu_layers=-1, main_gpu=1,
        tensor_split=[0.0, 1.0],
        verbose=False
    )
    print(f'[Worker] Model loaded in {time.perf_counter()-t0:.1f}s')

    total_tok = 0
    total_time = 0.0
    n_rounds = 0
    print('[Worker] Starting continuous generation (200 tok per round) ...')

    for rnd in range(1, 11):
        prompt = 'Explain the theory of general relativity in detail.'
        t1 = time.perf_counter()
        out = llm(prompt, max_tokens=200, temperature=0.7)
        dt = time.perf_counter() - t1
        tok = out['usage']['completion_tokens']
        speed = tok / dt if dt > 0 else 0
        total_tok += tok
        total_time += dt
        n_rounds += 1
        print(f'  [Round {rnd:2d}] {tok} tok in {dt:.2f}s  ->  {speed:6.2f} tok/s')

    avg = total_tok / total_time if total_time > 0 else 0
    result_dict['total_tok'] = total_tok
    result_dict['total_time'] = total_time
    result_dict['avg_tg'] = avg
    result_dict['rounds'] = n_rounds
    print(f'[Worker] DONE. {n_rounds} rounds, {total_tok} tokens, avg {avg:.2f} tok/s')

def main():
    print('='*70)
    print('RX 580 STRESS TEST - Simultaneous Load + Monitoring')
    print('='*70)
    print('This will run for ~1-2 minutes.')
    print('Open Task Manager > Performance > GPU 1 side by side to verify.')
    print('')

    monitor = GPUMonitor()
    result = {}

    mon_thread = threading.Thread(target=monitor.run, daemon=True)
    work_thread = threading.Thread(target=stress_worker, args=(result,), daemon=True)

    mon_thread.start()
    time.sleep(2)
    work_thread.start()
    work_thread.join()
    time.sleep(2)
    monitor.stop()
    mon_thread.join(timeout=3)

    print('')
    print('='*70)
    print('RESULTS')
    print('='*70)
    if not result:
        print('Worker failed to produce results.')
        return
    print(f'  Rounds completed : {result["rounds"]}')
    print(f'  Tokens generated : {result["total_tok"]}')
    print(f'  Total time       : {result["total_time"]:.1f} s')
    print(f'  Avg TG speed     : {result["avg_tg"]:.2f} tok/s  (RX 580, 7B Q4)')
    print('')

    if monitor.samples:
        active = [s for s in monitor.samples if s['gpu'] > 5 or s['vram_mb'] > 100]
        if active:
            gpu_vals = [s['gpu'] for s in active]
            vram_vals = [s['vram_mb'] for s in active]
            cpu_vals = [s['cpu'] for s in active]
            peak_gpu = max(gpu_vals)
            avg_gpu  = sum(gpu_vals)/len(gpu_vals)
            peak_vram = max(vram_vals)
            avg_vram  = sum(vram_vals)/len(vram_vals)
            avg_cpu   = sum(cpu_vals)/len(cpu_vals)
            print('GPU 1 (RX 580) during load:')
            print(f'  Peak 3D utilization : {peak_gpu:.0f} %')
            print(f'  Avg  3D utilization : {avg_gpu:.0f} %')
            print(f'  Peak VRAM usage     : {peak_vram:.0f} MB  ({peak_vram/1024:.2f} GB)')
            print(f'  Avg  VRAM usage     : {avg_vram:.0f} MB  ({avg_vram/1024:.2f} GB)')
            print(f'  Avg  CPU load       : {avg_cpu:.1f} %')
            print('')

            print('='*70)
            print('VERDICT')
            print('='*70)
            if peak_gpu >= 90:
                print('  [OK]  GPU hit 90%+ -> card is being fully utilized')
            elif peak_gpu >= 70:
                print('  [MED] GPU hit 70-90% -> well utilized, not saturated')
            else:
                print('  [LO]  GPU <70% -> not fully utilized (bottleneck elsewhere)')

            if peak_vram >= 4000:
                print('  [OK]  VRAM heavily used (>4 GB)')
            else:
                print('  [LO]  VRAM light usage')

            if result['avg_tg'] >= 13:
                print(f'  [OK]  TG speed {result["avg_tg"]:.1f} tok/s matches Polaris expectations')
            else:
                print(f'  [LO]  TG speed {result["avg_tg"]:.1f} tok/s lower than expected')
        else:
            print('[!] No active samples captured - monitor may have missed the load window')
    else:
        print('[!] Monitor failed to collect samples')
    print('')

if __name__ == '__main__':
    main()
