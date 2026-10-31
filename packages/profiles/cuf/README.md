# Generation shapes (CUF curves)

Normative hourly generation shapes for open-access and rooftop sources, used to settle a source before measured
or developer-supplied 15-minute generation exists. They are **assumptions**: each file states the annual capacity
utilisation factor it is scaled to and why, every settlement that uses one records it, and the client sees it as an
editable chip. Replace with the developer's P50 hourly profile for any real project.

Parameters:
- `annual_cuf_pct`: the curve is scaled so a year's energy equals capacity × 8,760 h × this factor.
- `monthly`: relative energy by calendar month (1–12).
- `hourly`: relative output by hour of day (0–23); solar is zero at night.
