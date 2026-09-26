import pyaudio
import numpy as np

p = pyaudio.PyAudio()
print('=' * 60)
print('Available INPUT devices:')
print('=' * 60)
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    if info.get('maxInputChannels', 0) > 0:
        print('  [%d] %s (in channels: %d)' % (i, info['name'], info['maxInputChannels']))

default = p.get_default_input_device_info()
print()
print('Default input device: [%d] %s' % (default['index'], default['name']))
print()
print('Recording 4 seconds from DEFAULT device - SPEAK NOW ...')
stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
rms_list = []
for _ in range(int(16000 / 1024 * 4)):
    data = stream.read(1024, exception_on_overflow=False)
    s = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    rms_list.append(np.sqrt(np.mean(s ** 2)))
stream.stop_stream()
stream.close()
p.terminate()

rms_arr = np.array(rms_list)
print()
print('Level stats (int16 scale):')
print('  max RMS : %.0f' % rms_arr.max())
print('  mean RMS: %.0f' % rms_arr.mean())
print('  (float32 scale max: %.4f)' % (rms_arr.max() / 32768.0))
print()
if rms_arr.max() < 500:
    print('VERDICT: signal VERY weak or WRONG device -> check Windows sound settings')
elif rms_arr.max() < 3000:
    print('VERDICT: weak but present -> lowering thresholds will fix it')
else:
    print('VERDICT: healthy microphone signal')
