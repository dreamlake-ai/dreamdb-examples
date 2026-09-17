"""Select bounded real input paths; never download video or expose credentials."""

import argparse
import importlib.metadata
import json
import random
from pathlib import Path

from huggingface_hub import HfApi, RepoFile, RepoFolder

REPO = "builddotai/Egocentric-100K"
REVISION = "fae604b751b25337d6fd8c4c53e595910c28f68f"


def select(api, count, seed, byte_cap):
    def tree(path):
        return list(api.list_repo_tree(REPO, path_in_repo=path, revision=REVISION,
                                       repo_type="dataset", recursive=False))

    factories = sorted(x.path for x in tree("") if isinstance(x, RepoFolder))
    if len(factories) < count:
        raise ValueError("not enough factories for the requested spread")
    indices = ([len(factories) // 2] if count == 1 else
               [i * (len(factories) - 1) // (count - 1) for i in range(count)])
    rng = random.Random(seed)
    selected = []
    total = 0
    for i in indices:
        factory = factories[i]
        workers = sorted(x.path for x in tree(factory) if isinstance(x, RepoFolder))
        if not workers:
            raise ValueError(f"no worker folders: {factory}")
        worker = rng.choice(workers)
        shards = sorted((x for x in tree(worker)
                         if isinstance(x, RepoFile) and x.path.endswith(".tar")),
                        key=lambda x: x.path)
        if not shards:
            raise ValueError(f"no TAR shards: {worker}")
        shard = rng.choice(shards)
        if not isinstance(shard.size, int) or shard.size <= 0:
            raise ValueError(f"unknown/empty shard size: {shard.path}")
        total += shard.size
        if total > byte_cap:
            raise ValueError("selected shards exceed byte cap; no download performed")
        selected.append({"factory": factory, "worker": worker,
                         "path": shard.path, "size_bytes": shard.size,
                         "blob_id": shard.blob_id,
                         "lfs_sha256": shard.lfs.sha256 if shard.lfs else None})
    return {"repo": REPO, "revision": REVISION, "seed": seed,
            "selection": "even factory spread; seeded worker and shard per factory",
            "factory_count_observed": len(factories), "shards": selected,
            "selected_bytes": total, "source_byte_cap": byte_cap,
            "huggingface_hub_version": importlib.metadata.version("huggingface_hub"),
            "downloaded_video_bytes": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--factories", type=int, default=8)
    parser.add_argument("--seed", type=int, default=400)
    args = parser.parse_args()
    if not 1 <= args.factories <= 8:
        parser.error("pilot permits 1..8 factories")
    if args.output.exists():
        parser.error("output already exists; refusing overwrite")
    result = select(HfApi(), args.factories, args.seed, 8 * 1024**3)
    with args.output.open("x") as out:
        json.dump(result, out, indent=2)
        out.write("\n")
    print(json.dumps({"manifest": str(args.output), "shards": len(result["shards"]),
                      "selected_bytes": result["selected_bytes"],
                      "downloaded_video_bytes": 0}))


if __name__ == "__main__":
    main()
