# billx eval: synthetic-seed-1

- Date: 2026-10-15
- Engine version: 0.1.0
- Set: synthetic; synthetic bills with known values, not a measure of real-bill accuracy
- Cloud model allowed: yes; budget per bill: 1.00 USD
- Cases: 90 (bills 32, non-bills 10, planted 48)
- Silent errors: 0 in 13 passed bills (true rate below 0.2308 with 95% confidence)
- False refusals: 2; correct refusals: 10; non-bills read as bills: 0
- Planted misreads: 48 caught, 0 missed

## Per layout, input kind and route

| layout | input kind | route | n | bills | passed | coverage | silent errors | bound 3/n | correct refusals | false refusals | non-bills read as bills | needs review | declined | errors | formula coverage | planted caught / missed | cost USD median / p95 | seconds median / p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| avvnl-ht-synth-v1 | digital_pdf | template | 22 | 2 | 2 | 1.0000 | 0 | 1.5000 | 0 | 0 | 0 | 0 | 0 | 0 | 0.6429 | 20 / 0 | 0.0000 / 0.0000 | 24.121 / 24.695 |
| avvnl-ht-synth-v1 | photo_jpeg | cloud_model | 10 | 10 | 2 | 0.2000 | 0 | 1.5000 | 0 | 0 | 0 | 8 | 0 | 0 | 0.5811 | 0 / 0 | 0.0962 / 0.1228 | 64.883 / 86.735 |
| avvnl-ht-synth-v1 | scan_pdf | cloud_model | 2 | 2 | 2 | 1.0000 | 0 | 1.5000 | 0 | 0 | 0 | 0 | 0 | 0 | 0.6429 | 0 / 0 | 0.0935 / 0.0939 | 53.895 / 58.136 |
| gas-citygas-synth-v1 | digital_pdf | template | 5 | 1 | 1 | 1.0000 | 0 | 3.0000 | 0 | 0 | 0 | 0 | 0 | 0 | 0.5000 | 4 / 0 | 0.0000 / 0.0000 | 11.721 / 11.785 |
| gas-citygas-synth-v1 | photo_jpeg | cloud_model | 1 | 1 | 0 | 0.0000 | 0 | - | 0 | 0 | 0 | 1 | 0 | 0 | 0.3750 | 0 / 0 | 0.0578 / 0.0578 | 14.015 / 14.015 |
| gas-gridsales-synth-v1 | digital_pdf | template | 5 | 1 | 1 | 1.0000 | 0 | 3.0000 | 0 | 0 | 0 | 0 | 0 | 0 | 0.5000 | 4 / 0 | 0.0000 / 0.0000 | 11.975 / 12.113 |
| gas-gridsales-synth-v1 | photo_jpeg | cloud_model | 1 | 1 | 1 | 1.0000 | 0 | 3.0000 | 0 | 0 | 0 | 0 | 0 | 0 | 0.5000 | 0 / 0 | 0.0560 / 0.0560 | 15.573 / 15.573 |
| invoice-supplies-synth-v1 | digital_pdf | none | 1 | 0 | 0 | - | 0 | - | 1 | 0 | 0 | 0 | 0 | 0 | - | 0 / 0 | 0.0000 / 0.0000 | 10.566 / 10.566 |
| invoice-supplies-synth-v1 | photo_jpeg | none | 1 | 0 | 0 | - | 0 | - | 1 | 0 | 0 | 0 | 0 | 0 | - | 0 / 0 | 0.0000 / 0.0000 | 2.756 / 2.756 |
| letter-synth-v1 | digital_pdf | none | 1 | 0 | 0 | - | 0 | - | 1 | 0 | 0 | 0 | 0 | 0 | - | 0 / 0 | 0.0000 / 0.0000 | 0.049 / 0.049 |
| letter-synth-v1 | photo_jpeg | none | 1 | 0 | 0 | - | 0 | - | 1 | 0 | 0 | 0 | 0 | 0 | - | 0 / 0 | 0.0000 / 0.0000 | 8.662 / 8.662 |
| pvvnl-hv2-synth-v1 | digital_pdf | template | 22 | 2 | 1 | 0.5000 | 0 | 3.0000 | 0 | 0 | 0 | 1 | 0 | 0 | 0.6667 | 20 / 0 | 0.0000 / 0.0000 | 21.199 / 21.415 |
| pvvnl-hv2-synth-v1 | photo_jpeg | cloud_model | 8 | 8 | 2 | 0.2500 | 0 | 1.5000 | 0 | 0 | 0 | 6 | 0 | 0 | 0.6909 | 0 / 0 | 0.0884 / 0.0994 | 52.277 / 62.636 |
| pvvnl-hv2-synth-v1 | photo_jpeg | none | 2 | 2 | 0 | 0.0000 | 0 | - | 0 | 2 | 0 | 0 | 0 | 0 | - | 0 / 0 | 0.0000 / 0.0000 | 10.282 / 10.517 |
| pvvnl-hv2-synth-v1 | scan_pdf | cloud_model | 2 | 2 | 1 | 0.5000 | 0 | 3.0000 | 0 | 0 | 0 | 1 | 0 | 0 | 0.6667 | 0 / 0 | 0.0820 / 0.0822 | 49.517 / 50.413 |
| receipt-store-synth-v1 | digital_pdf | none | 1 | 0 | 0 | - | 0 | - | 1 | 0 | 0 | 0 | 0 | 0 | - | 0 / 0 | 0.0000 / 0.0000 | 7.659 / 7.659 |
| receipt-store-synth-v1 | photo_jpeg | none | 1 | 0 | 0 | - | 0 | - | 1 | 0 | 0 | 0 | 0 | 0 | - | 0 / 0 | 0.0000 / 0.0000 | 6.334 / 6.334 |
| telecom-fictional-synth-v1 | digital_pdf | none | 1 | 0 | 0 | - | 0 | - | 1 | 0 | 0 | 0 | 0 | 0 | - | 0 / 0 | 0.0000 / 0.0000 | 11.085 / 11.085 |
| telecom-fictional-synth-v1 | photo_jpeg | none | 1 | 0 | 0 | - | 0 | - | 1 | 0 | 0 | 0 | 0 | 0 | - | 0 / 0 | 0.0000 / 0.0000 | 7.872 / 7.872 |
| water-municipal-synth-v1 | digital_pdf | none | 1 | 0 | 0 | - | 0 | - | 1 | 0 | 0 | 0 | 0 | 0 | - | 0 / 0 | 0.0000 / 0.0000 | 0.034 / 0.034 |
| water-municipal-synth-v1 | photo_jpeg | none | 1 | 0 | 0 | - | 0 | - | 1 | 0 | 0 | 0 | 0 | 0 | - | 0 / 0 | 0.0000 / 0.0000 | 5.142 / 5.142 |
| all | all | all | 90 | 32 | 13 | 0.4063 | 0 | 0.2308 | 10 | 2 | 0 | 17 | 0 | 0 | 0.6247 | 48 / 0 | 0.0000 / 0.0996 | 21.343 / 66.421 |

## Accuracy over attempted, per field, on passed bills

### avvnl-ht-synth-v1 / digital_pdf / template (passed 2)

| field | correct | attempted | accuracy |
| --- | --- | --- | --- |
| charges.demand | 2 | 2 | 1.0000 |
| charges.energy | 2 | 2 | 1.0000 |
| connection.tariff_category | 2 | 2 | 1.0000 |
| consumer.account_number | 2 | 2 | 1.0000 |
| consumer.name | 2 | 2 | 1.0000 |
| demand.contract_kva | 2 | 2 | 1.0000 |
| demand.max_kva | 2 | 2 | 1.0000 |
| energy.kvah | 2 | 2 | 1.0000 |
| energy.kwh | 2 | 2 | 1.0000 |
| period.bill_date | 2 | 2 | 1.0000 |
| period.bill_month | 2 | 2 | 1.0000 |
| period.due_date | 2 | 2 | 1.0000 |
| period.from | 2 | 2 | 1.0000 |
| period.to | 2 | 2 | 1.0000 |
| tariff.category | 2 | 2 | 1.0000 |
| totals.arrears | 2 | 2 | 1.0000 |
| totals.current_charges | 2 | 2 | 1.0000 |
| totals.net_payable | 2 | 2 | 1.0000 |
| utility.name | 2 | 2 | 1.0000 |

### avvnl-ht-synth-v1 / photo_jpeg / cloud_model (passed 2)

| field | correct | attempted | accuracy |
| --- | --- | --- | --- |
| charges.demand | 2 | 2 | 1.0000 |
| charges.energy | 2 | 2 | 1.0000 |
| connection.tariff_category | 2 | 2 | 1.0000 |
| consumer.account_number | 2 | 2 | 1.0000 |
| consumer.name | 2 | 2 | 1.0000 |
| demand.contract_kva | 2 | 2 | 1.0000 |
| demand.max_kva | 2 | 2 | 1.0000 |
| energy.kvah | 2 | 2 | 1.0000 |
| energy.kwh | 2 | 2 | 1.0000 |
| period.bill_date | 2 | 2 | 1.0000 |
| period.bill_month | 2 | 2 | 1.0000 |
| period.due_date | 2 | 2 | 1.0000 |
| period.from | 2 | 2 | 1.0000 |
| period.to | 2 | 2 | 1.0000 |
| tariff.category | 2 | 2 | 1.0000 |
| totals.arrears | 2 | 2 | 1.0000 |
| totals.current_charges | 2 | 2 | 1.0000 |
| totals.net_payable | 2 | 2 | 1.0000 |
| utility.name | 2 | 2 | 1.0000 |

### avvnl-ht-synth-v1 / scan_pdf / cloud_model (passed 2)

| field | correct | attempted | accuracy |
| --- | --- | --- | --- |
| charges.demand | 2 | 2 | 1.0000 |
| charges.energy | 2 | 2 | 1.0000 |
| connection.tariff_category | 2 | 2 | 1.0000 |
| consumer.account_number | 2 | 2 | 1.0000 |
| consumer.name | 2 | 2 | 1.0000 |
| demand.contract_kva | 2 | 2 | 1.0000 |
| demand.max_kva | 2 | 2 | 1.0000 |
| energy.kvah | 2 | 2 | 1.0000 |
| energy.kwh | 2 | 2 | 1.0000 |
| period.bill_date | 2 | 2 | 1.0000 |
| period.bill_month | 2 | 2 | 1.0000 |
| period.due_date | 2 | 2 | 1.0000 |
| period.from | 2 | 2 | 1.0000 |
| period.to | 2 | 2 | 1.0000 |
| tariff.category | 2 | 2 | 1.0000 |
| totals.arrears | 2 | 2 | 1.0000 |
| totals.current_charges | 2 | 2 | 1.0000 |
| totals.net_payable | 2 | 2 | 1.0000 |
| utility.name | 2 | 2 | 1.0000 |

### gas-citygas-synth-v1 / digital_pdf / template (passed 1)

| field | correct | attempted | accuracy |
| --- | --- | --- | --- |
| consumer.customer_id | 1 | 1 | 1.0000 |
| energy.mmbtu | 1 | 1 | 1.0000 |
| gas.gcv_kcal_per_scm | 1 | 1 | 1.0000 |
| period.from | 1 | 1 | 1.0000 |
| period.to | 1 | 1 | 1.0000 |
| readings.current | 1 | 1 | 1.0000 |
| readings.previous | 1 | 1 | 1.0000 |
| totals.amount | 1 | 1 | 1.0000 |
| volume.scm | 1 | 1 | 1.0000 |

### gas-gridsales-synth-v1 / digital_pdf / template (passed 1)

| field | correct | attempted | accuracy |
| --- | --- | --- | --- |
| consumer.customer_id | 1 | 1 | 1.0000 |
| energy.mmbtu | 1 | 1 | 1.0000 |
| gas.gcv_kcal_per_scm | 1 | 1 | 1.0000 |
| period.from | 1 | 1 | 1.0000 |
| period.to | 1 | 1 | 1.0000 |
| readings.current | 1 | 1 | 1.0000 |
| readings.previous | 1 | 1 | 1.0000 |
| totals.amount | 1 | 1 | 1.0000 |
| volume.scm | 1 | 1 | 1.0000 |

### gas-gridsales-synth-v1 / photo_jpeg / cloud_model (passed 1)

| field | correct | attempted | accuracy |
| --- | --- | --- | --- |
| consumer.customer_id | 1 | 1 | 1.0000 |
| energy.mmbtu | 1 | 1 | 1.0000 |
| gas.gcv_kcal_per_scm | 1 | 1 | 1.0000 |
| period.from | 1 | 1 | 1.0000 |
| period.to | 1 | 1 | 1.0000 |
| readings.current | 1 | 1 | 1.0000 |
| readings.previous | 1 | 1 | 1.0000 |
| totals.amount | 1 | 1 | 1.0000 |
| utility.name | 1 | 1 | 1.0000 |
| volume.scm | 1 | 1 | 1.0000 |

### pvvnl-hv2-synth-v1 / digital_pdf / template (passed 1)

| field | correct | attempted | accuracy |
| --- | --- | --- | --- |
| charges.demand | 1 | 1 | 1.0000 |
| charges.energy | 1 | 1 | 1.0000 |
| connection.tariff_category | 1 | 1 | 1.0000 |
| consumer.account_number | 1 | 1 | 1.0000 |
| consumer.name | 1 | 1 | 1.0000 |
| demand.contract_kva | 1 | 1 | 1.0000 |
| demand.max_kva | 1 | 1 | 1.0000 |
| energy.kvah | 1 | 1 | 1.0000 |
| energy.kwh | 1 | 1 | 1.0000 |
| meter.number | 1 | 1 | 1.0000 |
| period.bill_date | 1 | 1 | 1.0000 |
| period.bill_month | 1 | 1 | 1.0000 |
| period.due_date | 1 | 1 | 1.0000 |
| period.from | 1 | 1 | 1.0000 |
| period.to | 1 | 1 | 1.0000 |
| tariff.category | 1 | 1 | 1.0000 |
| totals.arrears | 1 | 1 | 1.0000 |
| totals.current_charges | 1 | 1 | 1.0000 |
| totals.net_payable | 1 | 1 | 1.0000 |
| utility.name | 1 | 1 | 1.0000 |

### pvvnl-hv2-synth-v1 / photo_jpeg / cloud_model (passed 2)

| field | correct | attempted | accuracy |
| --- | --- | --- | --- |
| charges.demand | 2 | 2 | 1.0000 |
| charges.energy | 2 | 2 | 1.0000 |
| connection.tariff_category | 2 | 2 | 1.0000 |
| consumer.account_number | 2 | 2 | 1.0000 |
| consumer.name | 2 | 2 | 1.0000 |
| demand.contract_kva | 2 | 2 | 1.0000 |
| demand.max_kva | 2 | 2 | 1.0000 |
| energy.kvah | 2 | 2 | 1.0000 |
| energy.kwh | 2 | 2 | 1.0000 |
| meter.number | 2 | 2 | 1.0000 |
| period.bill_date | 2 | 2 | 1.0000 |
| period.bill_month | 2 | 2 | 1.0000 |
| period.due_date | 2 | 2 | 1.0000 |
| period.from | 2 | 2 | 1.0000 |
| period.to | 2 | 2 | 1.0000 |
| tariff.category | 2 | 2 | 1.0000 |
| totals.arrears | 2 | 2 | 1.0000 |
| totals.current_charges | 2 | 2 | 1.0000 |
| totals.net_payable | 2 | 2 | 1.0000 |
| utility.name | 2 | 2 | 1.0000 |

### pvvnl-hv2-synth-v1 / scan_pdf / cloud_model (passed 1)

| field | correct | attempted | accuracy |
| --- | --- | --- | --- |
| charges.demand | 1 | 1 | 1.0000 |
| charges.energy | 1 | 1 | 1.0000 |
| connection.tariff_category | 1 | 1 | 1.0000 |
| consumer.account_number | 1 | 1 | 1.0000 |
| consumer.name | 1 | 1 | 1.0000 |
| demand.contract_kva | 1 | 1 | 1.0000 |
| demand.max_kva | 1 | 1 | 1.0000 |
| energy.kvah | 1 | 1 | 1.0000 |
| energy.kwh | 1 | 1 | 1.0000 |
| meter.number | 1 | 1 | 1.0000 |
| period.bill_date | 1 | 1 | 1.0000 |
| period.bill_month | 1 | 1 | 1.0000 |
| period.due_date | 1 | 1 | 1.0000 |
| period.from | 1 | 1 | 1.0000 |
| period.to | 1 | 1 | 1.0000 |
| tariff.category | 1 | 1 | 1.0000 |
| totals.arrears | 1 | 1 | 1.0000 |
| totals.current_charges | 1 | 1 | 1.0000 |
| totals.net_payable | 1 | 1 | 1.0000 |
| utility.name | 1 | 1 | 1.0000 |

### all / all / all (passed 13)

| field | correct | attempted | accuracy |
| --- | --- | --- | --- |
| charges.demand | 10 | 10 | 1.0000 |
| charges.energy | 10 | 10 | 1.0000 |
| connection.tariff_category | 10 | 10 | 1.0000 |
| consumer.account_number | 10 | 10 | 1.0000 |
| consumer.customer_id | 3 | 3 | 1.0000 |
| consumer.name | 10 | 10 | 1.0000 |
| demand.contract_kva | 10 | 10 | 1.0000 |
| demand.max_kva | 10 | 10 | 1.0000 |
| energy.kvah | 10 | 10 | 1.0000 |
| energy.kwh | 10 | 10 | 1.0000 |
| energy.mmbtu | 3 | 3 | 1.0000 |
| gas.gcv_kcal_per_scm | 3 | 3 | 1.0000 |
| meter.number | 4 | 4 | 1.0000 |
| period.bill_date | 10 | 10 | 1.0000 |
| period.bill_month | 10 | 10 | 1.0000 |
| period.due_date | 10 | 10 | 1.0000 |
| period.from | 13 | 13 | 1.0000 |
| period.to | 13 | 13 | 1.0000 |
| readings.current | 3 | 3 | 1.0000 |
| readings.previous | 3 | 3 | 1.0000 |
| tariff.category | 10 | 10 | 1.0000 |
| totals.amount | 3 | 3 | 1.0000 |
| totals.arrears | 10 | 10 | 1.0000 |
| totals.current_charges | 10 | 10 | 1.0000 |
| totals.net_payable | 10 | 10 | 1.0000 |
| utility.name | 11 | 11 | 1.0000 |
| volume.scm | 3 | 3 | 1.0000 |

## Findings

- Silent errors (case, field): none
- False refusals (case):
  - pvvnl-hv2-synth-v1_01.photo-lowres.jpg
  - pvvnl-hv2-synth-v1_02.photo-lowres.jpg

- Non-bills read as bills (case): none
- Planted misreads missed (case, check): none
- Engine errors (case, class): none
