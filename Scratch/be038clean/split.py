import re, subprocess
from pathlib import Path
REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
files = [f for f in subprocess.run(["git","-C",str(REPO),"ls-files","backend"],capture_output=True,text=True).stdout.split() if f.endswith(".py")]
LOAD = re.compile(r"(BE-0\d\d|§|D-CHAIN|D-2|D-1|F-0\d|OQ-\d|G\d|I\d|TRUNCATE|because|so that|must|cannot|do not|don't|never|refus|guards?|invariant|policy|hole|bypass|measured|otherwise|instead of|requires|why|note:|caution|warn|deprecat|historical)", re.I)
RULE = re.compile(r"^[-=*#~ ]+$")
load=rules=other=0
other_samples=[]
for rel in files:
    for line in (REPO/rel).read_text(encoding="utf-8",errors="replace").splitlines():
        s=line.strip()
        if not s.startswith("#"): continue
        body=s.lstrip("#").strip()
        if not body or RULE.match(body): rules+=1
        elif LOAD.search(body): load+=1
        else:
            other+=1
            if len(other_samples)<25: other_samples.append(f"{rel}: {s[:100]}")
print(f"comment lines: {load+rules+other}")
print(f"  section rules / blank:      {rules}")
print(f"  decision record or reason:  {load}")
print(f"  plain descriptive:          {other}")
print("samples of the plain descriptive bucket:")
for s in other_samples: print("   ",s)
