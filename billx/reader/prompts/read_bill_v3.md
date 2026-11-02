You are transcribing an Indian utility bill ({{BILL_KIND}}) from its page images. Your
transcription will be compared, value by value, with independent readings of the same pages,
so it must be what is printed and nothing else.

Rules:
- Transcribe only. Copy each value exactly as printed: the same digits, digit grouping,
  decimal places, sign, date format and spelling. "2,43,58,156.60" stays "2,43,58,156.60".
- Never calculate, add, convert, round, correct or infer a value. If a value is not printed,
  give null. If a figure is printed twice in different forms, give the one next to its label.
- Do not add units or currency symbols unless they are part of an identifier.
- Every value is a JSON string or null. Never a JSON number, never a boolean.
- Where a value is printed in two scripts (Hindi and English), give the English one.

Layout notes for this bill's layout, from its profile (they say where a field is printed or
which of two similar identifiers is meant; they never give a value):
{{HINTS}}

Answer with one JSON object and nothing else, with exactly these four keys:

1. "fields": an object whose keys are exactly the field paths below and whose values are the
   printed text as a string, or null when the bill does not print it.

   Fields (path: type, unit):
{{FIELDS}}

2. "meters": a list with one object per row of the meter-reading table (one per register and
   time-of-day slot), in printed order, each with the keys
   "register" (the quantity the row measures as printed: kWh, kVAh, kVA, kW, kVArh or other),
   "tod_slot" (the slot label as printed, or null when the row is not a slot),
   "present", "past", "difference", "multiplying_factor", "consumption"
   (each the printed figure as a string, or null when that column is not printed).
   An empty list when the bill prints no meter table.

3. "lines": a list with one object for every printed line that carries an amount, in printed
   order, from every section of the bill (charges, rebates, surcharges, duties, taxes,
   arrears, adjustments, subtotals, totals), each with the keys
   "group" (the heading of the section or table the line is printed under, as printed, or null),
   "label" (the line's text exactly as printed, including any sign or currency marker in it
   such as "(-)", "(Rs)" or "(₹)": a line printed as "Rebate (₹)(-)" keeps "(-)", because
   the marker is what says the amount is subtracted),
   "kind" ("item" for a charge, rebate or credit; "subtotal" for a printed sum of other lines,
   including grand totals; "info" for a figure printed for information that is not added to
   anything, such as a previous bill's amount, a security deposit, a payment made, or a
   rebate or surcharge that applies only if the bill is paid by or after a date),
   "stage" ("current" for the current period's charges, "arrear" for arrears of earlier
   periods, "adjustment" for adjustments, credits or refunds of earlier bills),
   "quantity", "rate", "unit", "amount" (each the printed text as a string, or null;
   "amount" is the money figure on that line, and a line without one is not listed),
   "detail_of" (when the line itemises or repeats another line printed elsewhere on the bill,
   the label of that other line exactly as printed; otherwise null. Bills often print a
   summary table and, elsewhere, a calculation or details table that breaks a summary line
   down: the time-of-day lines of the energy charge, the lines of "Misc. Charges", or the
   demand charge again with its quantity and rate. List those lines too, with "detail_of"
   set and "kind" "info", so nothing is added twice).
   A negative or credit amount keeps its printed sign or marker ("-1,234.00", "1,234.00 CR").

4. "extraction_notes": a list of short strings naming anything that made a value hard to
   read (faint print, a stamp over a figure, a torn edge, two figures under one label), or an
   empty list. Never put a value in a note.
