"""Neura GPU Full Check - model IDs, driver status, problem codes, VRAM, Vulkan."""
import subprocess, sys, json, re

KNOWN_IDS = {
    ("1002", "67DF"): "Polaris 10 - RX 470/480/570/580",
    ("1002", "6FDF"): "Polaris 20/30 - RX 580 2048SP / RX 590",
    ("1002", "7590"): "RDNA 4 (Navi 4x) - your card: RX 9060 XT",
    ("1002", "7550"): "RDNA 4 (Navi 4x) - RX 9000 family",
}

PROBLEMS = {
    0:  "OK - working",
    10: "Code 10 - cannot start (no compatible driver)",
    22: "Code 22 - disabled",
    28: "Code 28 - driver not installed",
    43: "Code 43 - stopped",
}

def ps(cmd):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, timeout=60)
    return r.stdout.strip()

def get_json(cmd):
    out = ps(cmd)
    if not out:
        return []
    d = json.loads(out)
    return d if isinstance(d, list) else [d]

def decode_id(pnpid):
    m = re.search(r"VEN_([0-9A-F]{4})&DEV_([0-9A-F]{4})", pnpid or "", re.I)
    if not m:
        return None, None, "unknown"
    ven, dev = m.group(1).upper(), m.group(2).upper()
    return ven, dev, KNOWN_IDS.get((ven, dev), "uncatalogued ID")

def vram_text(gpu):
    ram = gpu.get("AdapterRAM") or 0
    if ram == 0:
        return "unknown"
    gb = ram / 1024 ** 3
    if ram >= 4 * 1024 ** 3 - 1024 ** 2:
        return "%.1f GB (32-bit API cap - real size larger)" % gb
    return "%.1f GB" % gb

def vulkan_lines():
    try:
        r = subprocess.run([sys.executable, "-c",
                            "from llama_cpp import llama_cpp; llama_cpp.llama_backend_init()"],
                           capture_output=True, text=True, timeout=120)
        return [l.strip() for l in r.stderr.splitlines() if "vulkan" in l.lower()]
    except Exception as e:
        return ["error: %s" % e]

def main():
    print("=" * 70)
    print("Neura GPU Full Check")
    print("=" * 70)
    controllers = get_json("Get-CimInstance Win32_VideoController | ConvertTo-Json -Compress")
    pnp = get_json("Get-CimInstance Win32_PnPEntity | Where-Object PNPClass -eq 'Display' | "
                   "Select-Object Name, ConfigManagerErrorCode, PNPDeviceID | ConvertTo-Json -Compress")
    pnp_map = {(p.get("PNPDeviceID") or "").upper(): p for p in pnp}

    for i, gpu in enumerate(controllers):
        name = gpu.get("Name", "?")
        pnpid = gpu.get("PNPDeviceID", "")
        ven, dev, fam = decode_id(pnpid)
        code = (pnp_map.get(pnpid.upper()) or {}).get("ConfigManagerErrorCode")
        print("")
        print("--- [%d] %s ---" % (i, name))
        if ven:
            print("  Model (PCI ID):   VEN_%s & DEV_%s" % (ven, dev))
        print("  Family:           %s" % fam)
        print("  Full ID:          %s" % pnpid)
        print("  Windows status:   %s" % gpu.get("Status", "?"))
        if code is not None:
            print("  Problem code:     %s -> %s" % (code, PROBLEMS.get(code, "unknown")))
        print("  Driver version:   %s" % (gpu.get("DriverVersion") or "none"))
        print("  Driver date:      %s" % (gpu.get("DriverDate") or "none"))
        print("  VRAM:             %s" % vram_text(gpu))
        print("  GPU processor:    %s" % (gpu.get("VideoProcessor") or "?"))
        print("  Resolution:       %sx%s" % (gpu.get("CurrentHorizontalResolution"),
                                             gpu.get("CurrentVerticalResolution")))

    print("")
    print("=" * 70)
    print("Vulkan devices seen by Neura engine (llama.cpp)")
    print("=" * 70)
    for l in vulkan_lines():
        print("  " + l)

    print("")
    print("=" * 70)
    print("Final verdict")
    print("=" * 70)
    for gpu in controllers:
        name = gpu.get("Name", "?")
        drv = gpu.get("DriverVersion") or ""
        status = gpu.get("Status", "")
        if status == "OK" and drv and not drv.startswith("10.0."):
            verdict = "AI-READY (AMD driver + Vulkan)"
        elif "Basic" in name:
            verdict = "NO AMD DRIVER - display only, no compute"
        else:
            verdict = "manual check needed"
        print("  %s: %s" % (name, verdict))
    print("")

if __name__ == "__main__":
    main()
