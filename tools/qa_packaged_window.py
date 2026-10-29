"""Opt-in QA window with real packaged backend/model/desktop; no UI injection.

The real Qt window runs offscreen when QT_QPA_PLATFORM=offscreen is supplied.
Use the published local URL through CUA for visible composer interactions.
Never writes production user data; --data must be a dedicated QA directory.
"""
import argparse
import json
import os
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--data',type=Path,required=True)
p.add_argument('--info',type=Path,required=True)
p.add_argument('--stop',type=Path,required=True)
args=p.parse_args();root=args.data.resolve();args.stop=args.stop.resolve();args.info=args.info.resolve()
os.environ.update(NEURA_SETTINGS_DIR=str(root/'config'),NEURA_DATA_DIR=str(root/'data'),
                  NEURA_STATE_DIR=str(root/'state'),NEURA_TIMEOUT_S='900')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from src.desktop.paths import DesktopSettings,VERSION
from src.desktop.app import MainWindow
from src.runtime import ROOT

app=QApplication(['neura-packaged-qa']);settings=DesktopSettings()
settings.values.update(models_dir='/opt/neura-ai/models',n_gpu_layers=0,n_ctx=4096,
                       dedicated_coder=True,check_updates=False)
settings.save();window=MainWindow(settings);window.setWindowTitle('Neura AI — QA '+VERSION);window.show()
args.stop.unlink(missing_ok=True)
def tick():
    if args.stop.exists():
        window.close_checked=True;window.close();return
    if window.loaded and window.stack.currentIndex()==1 and not args.info.exists():
        args.info.parent.mkdir(parents=True,exist_ok=True)
        args.info.write_text(json.dumps({'url':window.service.url,'instance_id':window.service.instance,
            'qt_pid':os.getpid(),'backend_pid':window.service.process.pid,'version':VERSION,
            'application_root':str(ROOT),'qa_profile':str(root),'n_ctx':4096,'device':'explicit CPU',
            'model':'Qwen2.5-Coder-14B-Q4_K_M.gguf','model_adapter':'actual llama.cpp',
            'desktop_adapter':'actual trusted GIO; launch acceptance is not window observation',
            'qt_surface':os.environ.get('QT_QPA_PLATFORM','default'),
            'visible_ui':'same packaged frontend through CUA browser; native window interaction not automated'},ensure_ascii=False,indent=2))
        print('QA ready:',window.service.url,flush=True)
timer=QTimer();timer.timeout.connect(tick);timer.start(200)
try:app.exec()
finally:window.service.stop()
