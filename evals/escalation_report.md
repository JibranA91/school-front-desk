# Escalation classifier — eval report

- Run: 2026-07-14 03:15 UTC
- Target: `app.escalation.classify_sensitive` (deterministic, no LLM)
- Cases: 29

## Headline

- **False negatives — missed a sensitive topic: 0 (target 0)** ✅
- **False positives — escalated a benign question: 0 (target 0)** ✅
- Passed: **29/29**
- Sensitive (right category): 18/18
- Substring traps (stay None): 7/7
- Benign (stay None): 4/4

## All cases

| ✓ | id | kind | text | expected | got | note |
|---|----|------|------|----------|-----|------|
| ✅ | sens-fever | sensitive | My child has a fever, can she come in? | health | health |  |
| ✅ | sens-feverish | sensitive | She feels feverish this morning | health | health |  |
| ✅ | sens-ill | sensitive | My son is ill today | health | health |  |
| ✅ | sens-illness | sensitive | She's had an illness all week | health | health |  |
| ✅ | sens-cough | sensitive | He keeps coughing, is that okay? | health | health |  |
| ✅ | sens-vomit | sensitive | My daughter threw up last night | health | health |  |
| ✅ | sens-medication | sensitive | Can you give my child medication during the day? | medication | medication |  |
| ✅ | sens-tylenol | sensitive | What is your tylenol dosage policy? | medication | medication |  |
| ✅ | sens-allergy | sensitive | My child has a peanut allergy | allergy | allergy |  |
| ✅ | sens-allergies | sensitive | She has several food allergies | allergy | allergy |  |
| ✅ | sens-anaphylaxis | sensitive | He is at risk of anaphylaxis | allergy | allergy |  |
| ✅ | sens-fell | sensitive | My child fell and hit their head | safety | safety |  |
| ✅ | sens-fall | sensitive | She took a bad fall on the playground | safety | safety |  |
| ✅ | sens-injury | sensitive | There was an injury, she's bleeding | safety | safety |  |
| ✅ | sens-billing | sensitive | I want to dispute a charge on my invoice | billing_dispute | billing_dispute |  |
| ✅ | sens-overcharge | sensitive | You overcharged me last month | billing_dispute | billing_dispute |  |
| ✅ | sens-custody | sensitive | My ex is not allowed to pick up my child | custody | custody |  |
| ✅ | sens-courtorder | sensitive | There is a court order about custody | custody | custody |  |
| ✅ | trap-will | trap | what will be for lunch tomorrow? | None | None | 'will' contains 'ill' |
| ✅ | trap-licensed | trap | Is the daycare licensed? | None | None | 'licensed' contains 'lice' |
| ✅ | trap-fellow | trap | My fellow parents recommended you | None | None | 'fellow' contains 'fell' |
| ✅ | trap-refill | trap | Can I get a refill on the water bottle? | None | None | 'refill' contains 'ill' |
| ✅ | trap-still | trap | Do you offer a still-life art class? | None | None | 'still' contains 'ill' |
| ✅ | trap-skills | trap | What skills will my child develop here? | None | None | 'skills'/'will' both contain 'ill' |
| ✅ | trap-influence | trap | Do the older kids influence the younger ones? | None | None | 'influence' contains 'flu' |
| ✅ | ben-hours | benign | What are your hours? | None | None |  |
| ✅ | ben-tuition | benign | How much is infant tuition? | None | None |  |
| ✅ | ben-tour | benign | Can I book a tour for next Tuesday? | None | None |  |
| ✅ | ben-lunch | benign | What's for lunch today? | None | None |  |
