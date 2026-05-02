"""Metrics template code injected into generated Modal container scripts.

The FUNCTIONS string is a raw string containing Python code that will be
inserted into generated scripts via str.replace(). Raw string ensures
escape sequences like \\n and \\t remain as literal two-character sequences,
which is exactly what we need in the generated Python files.
"""

FUNCTIONS = r'''
def _print_metrics():
    import subprocess as _sp, os as _os
    print()
    print("=" * 65)
    print("  CONTAINER HARDWARE METRICS")
    print("=" * 65)
    try:
        r = _sp.run(["nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,"
            "utilization.memory,temperature.gpu,power.draw,power.limit,driver_version",
            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            for i, line in enumerate(r.stdout.strip().split("\n")):
                p = [x.strip() for x in line.split(",")]
                if len(p) >= 10:
                    print(f"  GPU {i}: {p[0]}")
                    print(f"    Driver:       {p[9]}")
                    print(f"    VRAM:         {p[2]} / {p[1]} MiB  (free: {p[3]} MiB)")
                    print(f"    GPU Util:     {p[4]}%")
                    print(f"    Mem Util:     {p[5]}%")
                    print(f"    Temperature:  {p[6]} C")
                    print(f"    Power:        {p[7]} / {p[8]} W")
    except Exception as e:
        print(f"  [GPU] error: {e}")
    try:
        with open("/proc/cpuinfo") as _f:
            _ci = _f.read()
        _cores = _ci.count("processor\t:")
        _mn = ""
        for _ln in _ci.split("\n"):
            if _ln.startswith("model name"):
                _mn = _ln.split(":", 1)[1].strip()
                break
        print(f"  CPU: {_mn}  ({_cores} cores)")
    except:
        pass
    try:
        with open("/proc/meminfo") as _f:
            _mi = {}
            for _ln in _f:
                if ":" in _ln:
                    _k, _v = _ln.split(":", 1)
                    _mi[_k.strip()] = _v.strip()
        _t = int(_mi.get("MemTotal", "0 kB").split()[0])
        _a = int(_mi.get("MemAvailable", "0 kB").split()[0])
        _u = _t - _a
        print(f"  Memory: {_u / 1048576:.1f} / {_t / 1048576:.1f} GB  ({_u * 100 // _t}% used)")
    except:
        pass
    try:
        _st = _os.statvfs("/")
        _td = _st.f_blocks * _st.f_frsize
        _fd = _st.f_bavail * _st.f_frsize
        _ud = _td - _fd
        print(f"  Disk:   {_ud / (1024**3):.1f} / {_td / (1024**3):.1f} GB  (free: {_fd / (1024**3):.1f} GB)")
    except:
        pass
    print("=" * 65)
    print()

def _monitor_metrics(interval=30):
    import subprocess as _sp, time as _time, threading as _th
    def _loop():
        while True:
            _time.sleep(interval)
            try:
                r = _sp.run(["nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                    "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        p = [x.strip() for x in line.split(",")]
                        if len(p) >= 5:
                            print(f"[METRICS] GPU {p[0]}% | VRAM {p[1]}/{p[2]} MiB | {p[3]}C | {p[4]}W", flush=True)
            except:
                pass
            try:
                with open("/proc/loadavg") as _f:
                    _la = _f.read().split()[:3]
                print(f"[METRICS] CPU load {_la[0]} {_la[1]} {_la[2]}", flush=True)
            except:
                pass
    _th.Thread(target=_loop, daemon=True).start()
'''
