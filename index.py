# FunctionGraph (Python 3.9+) handler: API Gateway -> this function -> ModelArts Studio (MaaS)
# Only the standard library is used, so there is nothing to package.
#
# Environment variables (set in the function's configuration, never in code):
#   MAAS_URL      full chat-completions URL copied from the MaaS console (OpenAI-compatible)
#   MAAS_API_KEY  API key created in the MaaS console
#   MAAS_MODEL    model name shown in the MaaS console
#   ALLOW_ORIGIN  optional, e.g. https://<your-bucket>.obs-website.<region>.myhuaweicloud.com (default "*")
import json, os, urllib.request, urllib.error

MAX_QUERY = 500


def _resp(code, payload):
    return {
        "statusCode": code,
        "isBase64Encoded": False,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": os.environ.get("ALLOW_ORIGIN", "*"),
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps(payload, ensure_ascii=False),
    }


def _num(v, lo, hi, default):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def handler(event, context):
    if (event.get("httpMethod") or "").upper() == "OPTIONS":
        return _resp(200, {})

    try:
        body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            import base64
            body = base64.b64decode(body).decode("utf-8")
        data = json.loads(body)
    except Exception:
        return _resp(400, {"error": "invalid JSON"})

    query = str(data.get("query", "")).strip()[:MAX_QUERY]
    if not query:
        return _resp(400, {"error": "empty query"})

    ctx = data.get("context") or {}
    minutes = int(_num(ctx.get("usableMin"), 0, 240, 15))
    noise = int(_num(ctx.get("noiseDb"), 0, 140, 60))
    subject = str(ctx.get("subject", "your subject"))[:80]

    # The system prompt is built here, not in the browser, so the public endpoint cannot be used as a free general-purpose LLM.
    system = (
        "You are Anya, a friendly AI tutor in CommuLearn AI for a student commuter at BulSU. "
        f"Sensed context: usable time {minutes} mins, noise {noise} dB, subject \"{subject}\". "
        "Reply in natural, helpful Taglish or English. Be succinct and encouraging. "
        "Only help with studying; politely decline unrelated requests."
    )

    payload = {
        "model": os.environ["MAAS_MODEL"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": query}],
        "max_tokens": 400,
        "temperature": 0.7,
    }
    req = urllib.request.Request(
        os.environ["MAAS_URL"],
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["MAAS_API_KEY"]},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            out = json.loads(r.read().decode("utf-8"))
        reply = out["choices"][0]["message"]["content"].strip()
        return _resp(200, {"reply": reply})
    except urllib.error.HTTPError as e:
        return _resp(502, {"error": f"MaaS HTTP {e.code}"})
    except Exception as e:
        return _resp(502, {"error": "MaaS call failed"})
