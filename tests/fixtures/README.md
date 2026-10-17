These fixtures are **synthetic**: invented values in the shape of the real API
responses. This repository is public. **Never commit real responses.** They
contain health data and account or device IDs.

To update the shape after an API change:

1. Run `diarystats dry-run --date D --dump DIR` on the server. Keep DIR outside
   the repo.
2. Copy only the keys that `diarystats/metrics.py` reads, plus enough structure
   around them.
3. Invent the values. Do not copy IDs, names, timestamps or measurements.
