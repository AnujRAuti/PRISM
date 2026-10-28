import hashlib, os, sys
h = hashlib.sha256(); n = 0
for root in ("backend", "alembic"):
    for d, dirs, fs in os.walk(root):
        dirs[:] = sorted(x for x in dirs if not x.startswith(".") and x != "__pycache__")
        fs = sorted(fs)
        if any(x.startswith(".") or x == "__pycache__" for x in d.split(os.sep)):
            continue
        for f in fs:
            if f.endswith(".py"):
                p = os.path.join(d, f).replace("\\", "/")
                h.update(p.encode()); h.update(open(p, "rb").read().replace(b"\r\n", b"\n")); n += 1
print(n, h.hexdigest())
