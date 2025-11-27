# Rin AI Influencer

This project automates the generation and publishing of Instagram content for the Rin persona. Posting is now handled via the Instagram Graph API, which means no browser automation is required on production runs.

## Instagram configuration

Create an Instagram Business or Creator account connected to a Facebook Page, then generate a permanent user access token that has the `instagram_basic`, `pages_show_list`, and `instagram_content_publish` permissions. Store the following keys inside your `.env` file:

```
INSTAGRAM_ACCESS_TOKEN=EAAG...
INSTAGRAM_BUSINESS_ACCOUNT_ID=1784...
```

With those credentials in place, `poster/instagram_poster.py` will upload images directly through the Graph API and publish them to the @main account that the Business ID belongs to.

## SDXL + LoRA image backend (optional)

Rin now supports a high-fidelity Stable Diffusion XL backend that uses the RinXL LoRA stored at `models/rinxl/rinxl_lora.safetensors`.
The SDXL backend is optional: if it is misconfigured or the server is offline, generation transparently falls back to the existing Gemini pipeline.

Add the following variables to `.env` to enable the SDXL client:

```
SDXL_ENDPOINT=http://localhost:8001/generate
SDXL_API_KEY= # optional bearer token
SDXL_TIMEOUT=90
```

### Starting an SDXL inference server

Run any SDXL-compatible REST service that accepts `prompt`, `negative_prompt`, `steps`, and `guidance` fields and returns a base64-encoded image payload. One lightweight option is to start a server that mounts the RinXL LoRA:

```
python -m sdxl_server \
  --model stabilityai/stable-diffusion-xl-base-1.0 \
  --lora models/rinxl/rinxl_lora.safetensors \
  --host 0.0.0.0 --port 8001
```

### Example curl request

```
curl -X POST "$SDXL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SDXL_API_KEY" \
  -d '{
    "prompt": "Rin waiting for a latte near Anfu Road, soft daylight, handheld realism",
    "negative_prompt": "text, watermarks, duplicated faces, distorted hands, extra limbs, glitch art, overexposed lighting, dramatic shadows, oversaturated colors",
    "steps": 30,
    "guidance": 7.5
  }'
```

The server should respond with JSON containing an `image` field (base64). If it returns raw image bytes, the client will also handle that response.

### How Rin uses the LoRA

When the scene subject is Rin and high fidelity is requested, the rendering router sends the shot plan to the SDXL backend. The remote server loads `models/rinxl/rinxl_lora.safetensors` so the resulting portraits stay consistent with Rin’s facial features and styling.

### Switching between backends

* **Gemini (default):** Used automatically for all non-Rin scenes or when the SDXL endpoint is missing/unreachable.
* **SDXL+LoRA:** Automatically chosen for Rin scenes marked high fidelity. Set `SDXL_ENDPOINT` to route those renders to the SDXL server; failures gracefully fall back to Gemini with no extra configuration.
