# Industry load shapes

Normative weekly 15-minute shapes used to turn monthly bills into a year of 15-minute demand when a
client has no meter data (master prompt Stage 2). They are **assumptions**, not measurements: each
file states its parameters and why, every synthesised profile records which shape it used, and the
client sees the shape as an editable chip. Replace a shape with a measured ergOS or SCADA week for
any client that has one.

Parameters (levels are percent of the week's peak):
- `base`: load outside working hours (utilities, lighting, compressors, HVAC).
- `working`: list of {days, start, end, level}; days are 0=Mon … 6=Sun.
- `dips`: short reductions inside working hours (lunch, shift change).
- `ramp_minutes`: linear ramp at each working-period edge.
