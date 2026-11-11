"""Actual device counters + existing weight availability; NO model loaded."""
import argparse,json
from dataclasses import replace
from pathlib import Path
from src.runtime import Settings
from src.backends.devices import probe_devices,select_device
from src.backends.residency import ResidencyManager,gpu_memory
p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
from src.core.resource_policy import ProtectionConfig
cfg=ProtectionConfig.model_validate_json(a.profile.read_text());d=select_device(probe_devices(),cfg.protected_gpu)
s=Settings(models_dir='/opt/neura-ai/models',n_gpu_layers=-1,memory_reserve_gb=cfg.memory_reserve_gb);r=ResidencyManager(settings=s);r.bound_sysfs=d['sysfs_device']
records=[]
for mid in ('qwen3.5-9b-claude-distilled-q4','qwen2.5-coder-14b-q4'):
    # Availability is separate; record native hardware guard even if a registry
    # disabled a model. Do not load it or mutate its registry to claim success.
    records.append({'model_id':mid,'availability':r.availability(mid),'estimate_gb':r.estimate_vram_usage_gb(mid,cfg.protected_context),'selected_total_gb':d['total_bytes']/1e9,'fits_total':r.estimate_vram_usage_gb(mid,cfg.protected_context)<=d['total_bytes']/1e9,'can_load':r.can_load(mid,cfg.protected_context)})
r=ResidencyManager(settings=replace(s,models_dir=Path(cfg.protected_models_dir)));r.bound_sysfs=d['sysfs_device']
mid='qwen2.5-coder-7b-q4';records.append({'model_id':mid,'availability':r.availability(mid),'estimate_gb':r.estimate_vram_usage_gb(mid,cfg.protected_context),'can_load':r.can_load(mid,cfg.protected_context)})
a.output.write_text(json.dumps({'environment':'actual Vulkan identities/sysfs memory/existing file checks; no inference','device':{k:v for k,v in d.items() if k!='_pointer'},'memory':gpu_memory(),'records':records},indent=2));print(json.dumps(records,indent=2))
