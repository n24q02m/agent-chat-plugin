import time
from pathlib import Path
from chat import message_files, _seq_from_name

def old_max_seq(chan: Path) -> int:
    files = message_files(chan)
    return _seq_from_name(files[-1].name) if files else 0

def new_max_seq(chan: Path) -> int:
    mx = 0
    for p in chan.glob("*.md"):
        # Inline the fast seq parsing logic since this is a hot loop for polling and stats
        name = p.name
        dash_idx = name.find("-")
        if dash_idx != -1:
            try:
                seq = int(name[:dash_idx])
                if seq > mx:
                    mx = seq
            except ValueError:
                pass
    return mx

def benchmark():
    root = Path("mock_corpus")
    d = root / "channel_0"

    t0 = time.time()
    for _ in range(50):
        old_max_seq(d)
    t1 = time.time()
    old_time = (t1 - t0) * 1000 / 50
    print(f"Old max_seq: {old_time:.3f} ms per run")

    t0 = time.time()
    for _ in range(50):
        new_max_seq(d)
    t1 = time.time()
    new_time = (t1 - t0) * 1000 / 50
    print(f"New max_seq: {new_time:.3f} ms per run")

    print(f"Improvement: {old_time / new_time:.2f}x")

if __name__ == "__main__":
    benchmark()
