# Explorer (internal)

A quick data browser for the team. It isn't part of the submission. It's deployed at https://spaceapps-puce.vercel.app

```bash
python3 -m flame.fetch            # from the repo root, once: puts the raw data in data/raw/
cd explorer && python3 view.py    # http://localhost:8000
python3 view.py build && vercel deploy --prod --scope alexzcoders-projects   # redeploy
```

`api/dl.py` redirects file links to temporary NASA S3 URLs. Locally it runs inside `view.py`; on Vercel it runs as a Python function.
