You are transcribing a few fields from an Indian utility bill ({{BILL_KIND}}). For each page
you are given the whole page and then three overlapping horizontal bands of the same page
(its top, middle and bottom), enlarged so that small print is legible. The bands show
nothing the whole page does not; use them to read each figure exactly.

Rules:
- Transcribe only. Copy each value exactly as printed: the same digits, digit grouping,
  decimal places, sign, date format and spelling.
- Never calculate, add, convert, round, correct or infer a value. If a value is not printed,
  give null. If a figure is printed twice in different forms, give the one next to its label.
- Do not add units or currency symbols unless they are part of an identifier.
- Every value is a JSON string or null. Never a JSON number, never a boolean.
- Where a value is printed in two scripts (Hindi and English), give the English one.

Layout notes for this bill's layout, from its profile (they say where a field is printed or
which of two similar identifiers is meant; they never give a value):
{{HINTS}}

Fields (path: type, unit: what the field is; find it by its meaning, wherever the bill prints it):
{{FIELDS_DESCRIBED}}

Answer with one JSON object and nothing else. Its keys are exactly the field paths above;
each value is the printed text as a string, or null when the bill does not print it.
