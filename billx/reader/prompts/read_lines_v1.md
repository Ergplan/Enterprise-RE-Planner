You are transcribing a few printed lines from an Indian utility bill. For each page you are
given the whole page and then three overlapping horizontal bands of the same page (its top,
middle and bottom), enlarged so that small print is legible.

Find each line listed below on the page by its label (and the heading of the section it is
printed under, where given) and copy the figures printed on that line.

Rules:
- Transcribe only. Copy each figure exactly as printed: the same digits, digit grouping,
  decimal places and sign. A negative or credit amount keeps its printed sign or marker.
- Never calculate, add, convert, round, correct or infer a figure. A column the line does
  not print is null. A line you cannot find on the page is reported with every figure null.
- Every value is a JSON string or null. Never a JSON number, never a boolean.

Lines (section heading | label as printed):
{{LINES}}

Answer with one JSON object and nothing else, with one key "lines": a list with one object
per line above, in the same order, each with the keys
"group" (the section heading, copied from the list above, or null),
"label" (the label, copied from the list above),
"quantity", "rate", "unit", "amount" (each the printed text as a string, or null).
