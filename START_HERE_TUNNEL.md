# RiceGrade: Free development tunnel for the trained hybrid model

This bundle is a **local model service**, not the Cloudflare Pages UI patch. It runs the existing frozen PyTorch EfficientNet-B0 + OpenCV 16-feature + XGBoost classifier in a Python process on your PC, and allows the authenticated Cloudflare Pages API to send an R2-stored image to it through a temporary Cloudflare Tunnel URL. Nothing here changes D1, R2, or your deployed Pages frontend.

**Important:** Before using the website Analyze button, you must have merged `RiceGrade_Model_Frontend_Patch.zip`, applied migration `0002_screening_trials.sql` to the **remote** D1 database, and pushed the patch to your Pages `main` branch. Verify your already-working registration is still working. If you already did all these, do not repeat the migration.

## One-time setup on Windows 10/11

1. Download the ZIP, extract it, open PowerShell, and `cd` into the **`model_service`** folder. Install **Python 3.11 (64-bit)** if needed, then create a private virtual environment:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --upgrade pip
   .\.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.7.1 torchvision==0.22.1
   .\.venv\Scripts\python.exe -m pip install -r requirements-server.txt
   .\.venv\Scripts\python.exe check_bundle.py
   ```

   The first install may download large PyTorch CPU wheels. `check_bundle.py` must print `PASS` before you proceed. Install a current `cloudflared` binary from <https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/>; verify `cloudflared --version` works in a fresh PowerShell terminal. You do not need Docker or Workers Paid for this mode.

2. Generate a **new** random secret once, on your PC:

   ```powershell
   .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
   ```

   Store it securely. Do **not** commit it to GitHub, share it in chat/screenshots, place it in frontend `VITE_*` variables, or include it in a URL. Under `Workers & Pages → ricegrade → Settings → Variables and Secrets → Production`, add **encrypted secret** `RICEGRADE_ML_TOKEN` with that value. This is **not** a D1/R2 binding. Do not touch the existing `DB` and `IMAGES` bindings.

3. Start the model server, in **Terminal 1**:

   ```powershell
   .\.venv\Scripts\python.exe start_local_model.py
   ```

   Paste the same private token at the hidden prompt. The server intentionally listens only on `127.0.0.1:8080`. Wait until the pretrained model loads. In a browser on this PC, visit `http://127.0.0.1:8080/health` and confirm `{"status":"ok","model":"loaded"}`. If Windows Firewall asks, do not expose it to public networks: the outbound tunnel handles the remote connection.

4. Start a **Quick Tunnel**, in **Terminal 2**:

   ```powershell
   cloudflared tunnel --url http://127.0.0.1:8080
   ```

   Cloudflare will print a random HTTPS hostname like `https://random-words.trycloudflare.com`. Keep this terminal running. Quick Tunnels are meant for development and **not** stable production hosting. The URL changes when the tunnel restarts. If you have an existing cloudflared `config.yaml` file interfering with Quick Tunnels, follow the Cloudflare Quick Tunnel documentation.

5. Open **Cloudflare Dashboard → Workers & Pages → ricegrade → Settings → Variables and Secrets → Production**. Add **plaintext server-side environment variable** `RICEGRADE_ML_ORIGIN` with the full Tunnel HTTPS **origin only**, for example:

   ```text
   https://random-words.trycloudflare.com
   ```

   No trailing slash, path `/predict/image`, query string, or embedded credentials. Redeploy your Pages project after setting or changing the variable so the Pages Function receives it. The model token goes in the **encrypted** secret field; the origin URL does not need to be a secret.

6. Sign in to <https://ricegrade.pages.dev/>. Navigate to an assessment **you own** that has a private R2 image. Click **Run experimental grain screening**. The Pages Function should retrieve the R2 image, call the Tunnel service with the private header, verify the response, and save **four-class grain-count** research preview results in D1.

## When you finish testing

- Stop Terminal 2 (`Ctrl+C`) to remove the temporary public Tunnel address; stop Terminal 1 (`Ctrl+C`) to shut down your local model.
- Your **Pages UI, D1 accounts, and R2 images stay online**; AI requests will not work while the PC is off. Previously saved previews in D1 remain available.
- To stop new online screening requests explicitly, remove the Production `RICEGRADE_ML_ORIGIN` variable and redeploy. Alternatively, keep the site in supervised testing mode.
- On the next tunnel session, a *new* Quick Tunnel URL is normally issued. Update `RICEGRADE_ML_ORIGIN` and redeploy Pages before testing again. Reuse the same private token unless you suspect compromise, in which case rotate it in both places.

## Common problems

| Symptom | Explanation / Fix |
|---|---|
| `/health` locally fails | Python dependencies not installed, server not started, or model bundle checksum mismatch |
| Public Tunnel `/health` fails | Tunnel stopped, wrong local port, antivirus/firewall/proxy issue, or expired random hostname |
| RiceGrade says model is not configured (503) | `RICEGRADE_ML_ORIGIN` and/or encrypted `RICEGRADE_ML_TOKEN` missing from Pages Production environment or Pages not redeployed |
| RiceGrade says model unavailable / timed out (502) | Model/tunnel is offline, initial inference exceeds timeout, wrong origin, or token mismatched |
| Server says unauthorized (401) | Token in local model process and Pages Production secret differ |
| 422 image not suitable | Provisional OpenCV segmentation cannot isolate valid grains in this photo. Try a controlled photo with separated grains on a dark matte background; do not claim operational reliability yet |
| No new result after re-opening | D1 caches completed research previews; analysis does **not** run again on every page view |

## Cost and limits

- Cloudflare Workers/Pages Functions Free currently includes **100,000 requests/day**, resetting at **midnight UTC (08:00 Philippine time)**. On Free, requests beyond the limit can error until reset. D1, R2, and Cloudflare Tunnel are separate resources/quotas. You must check the Cloudflare dashboard for current plan allowances and usage.
- A Quick Tunnel does **not** incur Cloudflare Container usage fees. The PC runs the CPU inference. It must be switched on, with both terminals running.
- On later moving to Cloudflare Containers or any hosted service, measure memory/CPU and costs, then approve paid hosting through the group's billing owner.

## Research integrity

Automatic grain isolation is **experimental** and has **not** been validated on local test-mill masks. Reported classifier performance from annotated grains is not end-to-end performance on uploaded photos. Class percentages are by **grain count**, not weight. Do not show official PNS/BAFS grades or unvalidated DSS output from these data.
