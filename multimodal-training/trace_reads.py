"""Summarize successful backend file reads between the probe's strace markers.

This counts filesystem-delivered bytes, not disk-device traffic or S3 GETs.
Raw traces stay in task scratch. Incomplete backend read records are an error.
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


def summarize(trace, backend):
    active = False
    starts = ends = 0
    pending = {}
    groups = defaultdict(lambda: dict(read_calls=0, bytes=0, opens=0, paths=set()))
    prefix = str(backend.resolve()) + "/"

    def group(path):
        relative = path.removeprefix(prefix)
        if "/track/" in relative:
            return "track"
        if "/image.png/" in relative:
            return "image"
        if "/array." in relative:
            return "array"
        return "other:" + relative.split("/")[0]

    for line in trace.read_text().splitlines():
        match = re.match(r"(\d+)\s+\d+\.\d+\s+(.*)", line)
        if not match:
            continue
        pid, event = match.groups()
        if "<unfinished ...>" in event:
            pending[pid] = event.split("<unfinished ...>")[0]
            continue
        if event.startswith("<..."):
            previous = pending.pop(pid, None)
            if previous is None:
                raise ValueError("resumed syscall without its start")
            event = previous + re.sub(r"^<\.\.\. \w+ resumed>", "", event)
        if "DDB_TRACE_START" in event:
            starts += 1
            active = True
            continue
        if "DDB_TRACE_END" in event:
            ends += 1
            active = False
            continue
        if not active:
            continue
        read = re.match(r"(?:read|pread64)\(\d+<([^>]+)>.*\)\s+=\s+(\d+)", event)
        opened = re.search(r"\)\s+=\s+\d+<([^>]+)>", event) if event.startswith("openat(") else None
        if read and read[1].startswith(prefix):
            item = groups[group(read[1])]
            item["read_calls"] += 1
            item["bytes"] += int(read[2])
            item["paths"].add(read[1])
        elif opened and opened[1].startswith(prefix):
            groups[group(opened[1])]["opens"] += 1
        elif event.startswith(("read(", "pread64(")) and prefix in event and "= -1" not in event:
            raise ValueError("unparsed backend read: " + event)
    assert starts == ends == 1 and not active
    assert not any(prefix in event for event in pending.values())
    assert groups, "no backend reads observed"
    return {name: {**{k: v for k, v in values.items() if k != "paths"},
                   "unique_read_paths": len(values["paths"])} for name, values in groups.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("backend", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.trace, args.backend), sort_keys=True))
