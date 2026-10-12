# RiceGrade model integration: merge plan

There are two ZIPs:

- **RiceGrade_Model_Frontend_Patch.zip** — migration `0002_screening_trials.sql`, complete Cloudflare Pages `/api/[[path]]` handler (including the working 100,000-iteration registration fix), and React model-preview UI. Merge these onto the current `main`; leave `frontend/wrangler.toml` and all secrets unchanged.
- **RiceGrade_Model_Cloudflare_Container.zip** — runnable Python model service using the already-trained frozen model weights, private Cloudflare Worker gateway, Dockerfile, tests, and deployment instructions.

Read `model_service/README-CLOUDFLARE.md` inside the second ZIP for the exact deployment sequence and limitations. These files are **not deployed** to your account by this package. Production D1 migration needs to be applied before the Pages API patch is pushed. Workers Paid must be approved by the group's billing manager before a Cloudflare Container can be deployed. No cost has been incurred by preparing these files.

Production inference is a **research preview only** until the automatic OpenCV isolation pipeline is validated on local rice photos. No fake DSS outputs or official mass-based grades are generated.
