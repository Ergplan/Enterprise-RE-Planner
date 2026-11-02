You are transcribing an Indian utility bill ({{BILL_KIND}}) from its page images, so that a
person can confirm each value against the same images.

Rules:
- Transcribe only. Copy each value exactly as it is printed on the bill: the same digits,
  digit grouping, decimal places, sign, date format and spelling.
- Never calculate, add, convert, round or infer a value. If a value is not printed, give null.
- Do not include units or currency symbols unless they are part of an identifier.
- Every value is a JSON string or null. Never a JSON number.

Fields (path: type, unit):
{{FIELDS}}

Answer with one JSON object and nothing else. Its keys are exactly the field paths above;
each value is the printed text as a string, or null when the bill does not print it.
