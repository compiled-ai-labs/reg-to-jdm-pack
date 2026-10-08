# Readback

Every row of `rules.jdm.json` in plain English, under the sentence it was compiled from, then every rule of `rules.dmn` in the same words. Rendered by code from the decision models and the receipts; no model call.

## JDM (`rules.jdm.json`)

### sources/reg-z-1026-2-a-6.txt

#### 1026.2(a)(6)

> Business day means a day on which the creditor's offices are open to the public for carrying on substantially all of its business functions.

State: NOT_A_RULE.


#### 1026.2(a)(6).s2

> However, for purposes of rescission under §§ 1026.15 and 1026.23, and for purposes of §§ 1026.19(a)(1)(ii), 1026.19(a)(2), 1026.19(e)(1)(iii)(B), 1026.19(e)(1)(iv), 1026.19(e)(2)(i)(A), 1026.19(e)(4)(ii), 1026.19(f)(1)(ii), 1026.19(f)(1)(iii), 1026.20(e)(5), 1026.31, and 1026.46(d)(4), the term means all calendar days except Sundays and the legal public holidays specified in 5 U.S.C. 6103(a), such as New Year's Day, the Birthday of Martin Luther King, Jr., Washington's Birthday, Memorial Day, Independence Day, Labor Day, Columbus Day, Veterans Day, Thanksgiving Day, and Christmas Day.

State: RULE.

- `1026.2(a)(6).s2/d1` (node `derive-1`, field `derived.business_days`): A day counts as one of the business days when the day is not a Sunday and the day is not in the legal public holidays (5 U.S.C. 6103(a)) as observed, supplied with the loan file.
  Quote: "the term means all calendar days except Sundays and the legal public holidays specified in 5 U.S.C. 6103(a)"

### sources/trid-1026-19f.txt

#### 1026.19(f)(1)(i) Scope

> In a transaction subject to paragraph (e)(1)(i) of this section, the creditor shall provide the consumer with the disclosures required under § 1026.38 reflecting the actual terms of the transaction.

State: LINK.

- Link (external) to 1026.19(e)(1)(i), cited as "paragraph (e)(1)(i)".
- Link (external) to 1026.38, cited as "§ 1026.38".

#### 1026.19(f)(1)(ii)(A) In general

> Except as provided in paragraphs (f)(1)(ii)(B), (f)(2)(i), (f)(2)(iii), (f)(2)(iv), and (f)(2)(v) of this section, the creditor shall ensure that the consumer receives the disclosures required under paragraph (f)(1)(i) of this section no later than three business days before consummation.

State: RULE.

- Row `1026.19(f)(1)(ii)(A)/r1/pass`: When it is not the case that the transaction is secured by a consumer's interest in a timeshare plan, and the number of business days where the day is on or after the date the consumer received, or is considered to have received, the Closing Disclosure and the day is before the date of consummation is at least 3, the result is **pass**.
- Row `1026.19(f)(1)(ii)(A)/r1/fail`: When it is not the case that the transaction is secured by a consumer's interest in a timeshare plan, and it is not the case that the number of business days where the day is on or after the date the consumer received, or is considered to have received, the Closing Disclosure and the day is before the date of consummation is at least 3, the result is **fail**.
  Quote: "Except as provided in paragraphs (f)(1)(ii)(B), (f)(2)(i), (f)(2)(iii), (f)(2)(iv), and (f)(2)(v) of this section, the creditor shall ensure that the consumer receives the disclosures required under paragraph (f)(1)(i) of this section no later than three business days before consummation"
- Link (exception) to 1026.19(f)(1)(ii)(B), cited as "(f)(1)(ii)(B)".
- Link (external) to 1026.19(f)(2)(i), cited as "(f)(2)(i)".
- Link (external) to 1026.19(f)(2)(iii), cited as "(f)(2)(iii)".
- Link (external) to 1026.19(f)(2)(iv), cited as "(f)(2)(iv)".
- Link (external) to 1026.19(f)(2)(v), cited as "(f)(2)(v)".
- Link (reference) to 1026.19(f)(1)(i), cited as "paragraph (f)(1)(i)".

#### 1026.19(f)(1)(ii)(B) Timeshares

> For transactions secured by a consumer's interest in a timeshare plan described in 11 U.S.C. 101(53D), the creditor shall ensure that the consumer receives the disclosures required under paragraph (f)(1)(i) of this section no later than consummation.

State: RULE.

- Row `1026.19(f)(1)(ii)(B)/r1/pass`: When the transaction is secured by a consumer's interest in a timeshare plan, and the date the consumer received, or is considered to have received, the Closing Disclosure is on or before the date of consummation, the result is **pass**.
- Row `1026.19(f)(1)(ii)(B)/r1/fail`: When the transaction is secured by a consumer's interest in a timeshare plan, and it is not the case that the date the consumer received, or is considered to have received, the Closing Disclosure is on or before the date of consummation, the result is **fail**.
  Quote: "For transactions secured by a consumer's interest in a timeshare plan described in 11 U.S.C. 101(53D), the creditor shall ensure that the consumer receives the disclosures required under paragraph (f)(1)(i) of this section no later than consummation"
- Link (reference) to 1026.19(f)(1)(i), cited as "paragraph (f)(1)(i)".
- Link (external) to 11 U.S.C. 101(53D), cited as "11 U.S.C. 101(53D)".

#### 1026.19(f)(1)(iii) Receipt of disclosures

> If any disclosures required under paragraph (f)(1)(i) of this section are not provided to the consumer in person, the consumer is considered to have received the disclosures three business days after they are delivered or placed in the mail.

State: RULE.

- `1026.19(f)(1)(iii)/d1` (node `derive-2`, field `derived.cd_receipt_date`): The date the consumer received, or is considered to have received, the Closing Disclosure: if how the Closing Disclosure was provided is "in_person" (handed to the consumer in person): the date the consumer received the Closing Disclosure, as recorded in the loan file; otherwise the third of business days where the day is after the date the Closing Disclosure was delivered other than in person, or placed in the mail.
  Quote: "If any disclosures required under paragraph (f)(1)(i) of this section are not provided to the consumer in person, the consumer is considered to have received the disclosures three business days after they are delivered or placed in the mail"
- Link (reference) to 1026.19(f)(1)(i), cited as "paragraph (f)(1)(i)".

## DMN (`rules.dmn`)

The same rules as decisions of the DMN model. Rule ids are the DMN `id` of each rule; the rule id of the receipts is its `rule_id` output and its description.

### 1026.2(a)(6).s2

- `1026.2(a)(6).s2/d1` (decision `derived_business_days`): A day counts as one of the business days when the day is not a Sunday and the day is not in the legal public holidays (5 U.S.C. 6103(a)) as observed, supplied with the loan file.

### 1026.19(f)(1)(ii)(A)

- Rule `rule_1026_19_f_1_ii_A_r1_pass` (decision `s1026_19_f_1_ii_A`): When it is not the case that the transaction is secured by a consumer's interest in a timeshare plan, and the number of business days where the day is on or after the date the consumer received, or is considered to have received, the Closing Disclosure and the day is before the date of consummation is at least 3, the result is **pass**.
- Rule `rule_1026_19_f_1_ii_A_r1_fail` (decision `s1026_19_f_1_ii_A`): When it is not the case that the transaction is secured by a consumer's interest in a timeshare plan, and it is not the case that the number of business days where the day is on or after the date the consumer received, or is considered to have received, the Closing Disclosure and the day is before the date of consummation is at least 3, the result is **fail**.

### 1026.19(f)(1)(ii)(B)

- Rule `rule_1026_19_f_1_ii_B_r1_pass` (decision `s1026_19_f_1_ii_B`): When the transaction is secured by a consumer's interest in a timeshare plan, and the date the consumer received, or is considered to have received, the Closing Disclosure is on or before the date of consummation, the result is **pass**.
- Rule `rule_1026_19_f_1_ii_B_r1_fail` (decision `s1026_19_f_1_ii_B`): When the transaction is secured by a consumer's interest in a timeshare plan, and it is not the case that the date the consumer received, or is considered to have received, the Closing Disclosure is on or before the date of consummation, the result is **fail**.

### 1026.19(f)(1)(iii)

- `1026.19(f)(1)(iii)/d1` (decision `derived_cd_receipt_date`): The date the consumer received, or is considered to have received, the Closing Disclosure: if how the Closing Disclosure was provided is "in_person" (handed to the consumer in person): the date the consumer received the Closing Disclosure, as recorded in the loan file; otherwise the third of business days where the day is after the date the Closing Disclosure was delivered other than in person, or placed in the mail.
