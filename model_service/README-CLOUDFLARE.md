# RiceGrade Model Service — Cloudflare Containers

The current migration procedure is located at [`../docs/deployment/cloudflare-containers-migration.md`](../docs/deployment/cloudflare-containers-migration.md).

Use the **private Pages service binding** `RICEGRADE_MODEL`, not the old tunnel origin. The model Worker is `ricegrade-model` and remains reachable internally through Pages Functions only.

**Required:** The exactly matching file `models/final_ricegrade/efficientnet_b0.pth` must be present locally and pass `python check_bundle.py` before deployment. A checkpoint from a different training run will not work with the frozen model manifest.

Original local-tunnel documentation is retained for historical debugging, not for production deployment.
