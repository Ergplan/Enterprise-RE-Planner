# Survey of the unconfirmed set

2026-10-16, engine 0.1.0. Counts only: no value,
name or file name appears here. Statuses are the engine's (contract 1.1); the
`needs_review` reasons and failed checks are codes. Nothing here is an accuracy
figure (**unmeasured**).

| Discom / kind | files | statuses | reasons | failed checks | discom matched | required fields found (verified) | median s | median pages | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| APCPDCL / digital_pdf | 3 | needs_review 3 | check_failed 6, insufficient_arithmetic 3, required_field_not_printed 9, unverified 79 | G01 3, G02 3, G03 1, G07 1, G08 3, G09 1, G20 3 | apcpdcl 3 | account_number 3 (3), kwh 1 (1), from 1 (1), to 1 (1), net_payable 3 (3) | 56.316 | 2 | - |
| AVVNL / digital_pdf | 4 | needs_review 4 | disputed 1, insufficient_arithmetic 4, required_field_not_printed 16 | G01 4 | avvnl 4 | account_number 4 (4), net_payable 4 (4) | 56.652 | 1 | - |
| AVVNL / pdf_unopened | 2 | - | - | - | - | - | - | - | UnsupportedType 2 |
| AVVNL / scan_pdf | 6 | needs_review 6 | check_failed 7, disputed 25, insufficient_arithmetic 6, required_field_not_printed 23, unverified 25 | G01 5, G05 6, G20 1 | avvnl 6 | account_number 6 (6), bill_month 6 (6), net_payable 1 (1) | 59.146 | 1 | - |
| DVVNL / digital_pdf | 1 | needs_review 1 | check_failed 3, disputed 4, insufficient_arithmetic 1, required_field_not_printed 4, unverified 14 | G01 1, G05 1, G07 1, G09 1 | dvvnl 1 | bill_month 1 (1), net_payable 1 (1) | 74.905 | 5 | - |
| GESCOM / digital_pdf | 1 | needs_review 1 | check_failed 3, disputed 1, insufficient_arithmetic 1, required_field_not_printed 2, unverified 23 | G05 1, G06 1, G07 1, G09 1 | gescom 1 | account_number 1 (1), kwh 1 (0), bill_month 1 (1), net_payable 1 (1) | 56.155 | 1 | - |
| GESCOM / scan_pdf | 3 | needs_review 3 | check_failed 6, disputed 1, insufficient_arithmetic 3, required_field_not_printed 6, unverified 25 | G07 1, G08 2, G20 3 | gescom 3 | account_number 3 (3), kwh 3 (3), bill_month 3 (3), net_payable 3 (3) | 38.138 | 1 | - |
| MSEDCL / digital_pdf | 6 | needs_review 6 | check_failed 8, disputed 12, insufficient_arithmetic 6, required_field_not_printed 30, unverified 14 | G01 6, G05 6, G08 2, G20 6 | msedcl 6 | bill_month 6 (6) | 61.478 | 7 | - |
| MVVNL / image | 8 | needs_review 8 | check_failed 26, disputed 13, insufficient_arithmetic 6, required_field_not_printed 15, unverified 354 | G01 7, G02 4, G03 5, G05 1, G07 8, G09 2, G15 1, G20 6 | mvvnl 5, none 3 | account_number 8 (8), kwh 7 (4), bill_month 1 (1), from 4 (3), to 4 (3), net_payable 8 (7) | 58.19 | 1 | - |
| MVVNL / scan_pdf | 8 | needs_review 8 | check_failed 39, disputed 28, insufficient_arithmetic 7, required_field_not_printed 7, unverified 407 | G01 4, G02 5, G03 6, G05 7, G06 1, G07 7, G09 7, G15 4, G16 1, G20 5 | mvvnl 6, none 2 | account_number 7 (7), kwh 7 (6), bill_month 5 (2), from 7 (7), to 7 (7), net_payable 8 (7) | 50.072 | 2 | - |
| NPCL / digital_pdf | 2 | needs_review 2 | check_failed 6, unverified 84 | G05 2, G07 2, G20 2 | npcl 2 | account_number 2 (2), kwh 2 (2), bill_month 2 (2), from 2 (2), to 2 (2), net_payable 2 (2) | 103.898 | 4 | - |
| NPCL / scan_pdf | 1 | needs_review 1 | check_failed 3, disputed 3, insufficient_arithmetic 1, required_field_not_printed 3, unverified 48 | G03 1, G07 1, G20 1 | npcl 1 | account_number 1 (1), bill_month 1 (1), net_payable 1 (1) | 58.642 | 1 | - |
| PSPCL / digital_pdf | 3 | needs_review 3 | check_failed 4, insufficient_arithmetic 2, required_field_not_printed 9, unverified 9 | G01 3, G02 1, G03 1, G05 3, G07 3, G09 2, G20 2 | pspcl 3 | kwh 3 (3), bill_month 3 (3), net_payable 3 (3) | 59.365 | 3 | - |
| PVVNL / digital_pdf | 4 | needs_review 4 | check_failed 9, disputed 4, insufficient_arithmetic 4, required_field_not_printed 21, unverified 93 | G01 4, G02 1, G03 1, G05 3, G07 1, G09 1, G15 1, G20 1 | none 3, pvvnl 1 | kwh 1 (0), bill_month 1 (1), net_payable 1 (1) | 91.823 | 3 | - |
| PVVNL / image | 1 | needs_review 1 | check_failed 4, disputed 2, insufficient_arithmetic 1, required_field_not_printed 1, unverified 27 | G01 1, G05 1, G06 1, G07 1, G20 1 | pvvnl 1 | account_number 1 (1), from 1 (1), to 1 (1), net_payable 1 (1) | 46.92 | 1 | - |
| PVVNL / scan_pdf | 11 | needs_review 11 | check_failed 25, disputed 24, insufficient_arithmetic 10, required_field_not_printed 55, unverified 148 | G01 11, G02 4, G03 2, G05 8, G06 1, G07 1, G20 1 | none 9, pvvnl 2 | account_number 2 (2), kwh 1 (0), bill_month 2 (1), from 1 (1), to 1 (1), net_payable 4 (1) | 66.466 | 2 | - |
| TANGEDCO / digital_pdf | 2 | needs_review 2 | check_failed 4, insufficient_arithmetic 2, required_field_not_printed 4, unverified 32 | G06 2, G07 2, G20 2 | tangedco 2 | account_number 2 (2), kwh 2 (2), bill_month 2 (2), net_payable 2 (2) | 55.425 | 5 | - |
| TGSPDCL / digital_pdf | 1 | needs_review 1 | check_failed 2, disputed 1, insufficient_arithmetic 1, required_field_not_printed 5, unverified 23 | G01 1, G05 1 | none 1 | net_payable 1 (0) | 380.248 | 1 | - |
| unsorted / image | 1 | needs_review 1 | check_failed 1, disputed 2, insufficient_arithmetic 1, required_field_not_printed 5, unverified 3 | G01 1, G05 1 | pvvnl 1 | account_number 1 (1) | 378.346 | 1 | - |
| unsorted / scan_pdf | 3 | needs_review 3 | check_failed 6, disputed 5, insufficient_arithmetic 2, required_field_not_printed 12, unverified 39 | G01 3, G02 1, G03 1, G05 1, G06 1, G07 1 | none 2, pvvnl 1 | account_number 1 (1), kwh 1 (0), from 1 (1), to 1 (1), net_payable 2 (1) | 383.726 | 2 | - |
| **all** | 71 | needs_review 69 | check_failed 162, disputed 126, insufficient_arithmetic 61, required_field_not_printed 227, unverified 1447 | G01 54, G02 19, G03 18, G05 42, G06 7, G07 31, G08 7, G09 15, G15 6, G16 1, G20 34 |  |  | 58.642 |  | UnsupportedType 2 |
