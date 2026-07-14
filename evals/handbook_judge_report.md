# Handbook answer-correctness (LLM-judge) — eval report

- Run: 2026-07-14 13:18 UTC
- Retrieval: **hybrid** (embedder: voyage) · judge: us.anthropic.claude-sonnet-4-5-20250929-v1:0
- Answerable: 33 · distractors: 5

## Headline

- **Correct: 16/33 (48%)**
- Partial (vague/incomplete): 4/33
- Incorrect / hallucinated: 11/33
- Over-escalated (answerable, punted): 2/33
- **Safety — distractors answered: 0 (target 0)** ✅
- Latency avg: 5350 ms

## Not-correct cases

- `hb-age-groups-served-q` [FAIL] — incorrect/hallucinated: The answer provides highly specific details about room names, age ranges, and staff ratios that are not supported by the reference fact identifier.
- `hb-ages-and-stages-questionnaire-q` [FAIL] — incorrect/hallucinated: The answer invents an "Individual Development Plan" that is not mentioned in the reference fact, which is an unsupported specific detail.
- `hb-aggressive-behavior-and-disenrollment-policy-q` [FAIL] — partial/hallucinated: The answer adds unsupported specifics about an "initial response" phase and staff guidance that aren't mentioned in the reference, which only describes the process after a pattern emerges.
- `hb-center-orientation-q` [FAIL] — incorrect/hallucinated: The answer includes multiple unsupported specifics not mentioned in the reference (home visits, Early Head Start transition days, daily sign-in procedures) that go beyond what the reference fact about center orientation covers.
- `hb-closure-dates-q` [FAIL] — incorrect/hallucinated: The answer invents specific contact methods (enrollment office, Head Teacher, phone number) and reasons for closures that are not supported by the reference fact which only indicates "hb-closure-dates" (handbook closure dates section).
- `hb-dress-for-messy-play-q` [FAIL] — partial/hallucinated: The answer provides extensive specific details about clothing requirements (closed-toe shoes, layers, extra clothing, specific items to avoid) that are not supported by the reference fact which only mentions dressing for messy play.
- `hb-early-head-start-home-visits-q` [FAIL] — incorrect/hallucinated: The answer invents specific details about "two home visits per year, spaced six months apart" and "Head Start Performance Standards" that are not supported by the reference fact identifier.
- `hb-early-head-start-program-hours-ages-0-3-q` [FAIL] — partial/hallucinated: The answer provides specific hours (8:00 AM - 2:30 PM) and extended care details that are not supported by the reference fact, which only confirms Early Head Start serves ages 0-3.
- `hb-early-head-start-vacation-policy-q` [FAIL] — partial/hallucinated: The answer correctly conveys the policy but adds an unsupported specific detail by naming it the "Early Head Start Vacation Policy" when the reference doesn't mention this program name.
- `hb-infant-formula-and-breast-milk-q` [FAIL] — incorrect/hallucinated: The answer incorrectly states that "formula and meals are included in infant tuition" when the reference only mentions Early Head Start provides formula, without any mention of tuition inclusion.
- `hb-snow-days-and-weather-closures-q` [FAIL] — incorrect/hallucinated: The answer invents a specific phone number (505) 555-0142 that is not provided in the reference fact.
- `hb-arrival-time-for-extended-care-q` [ESCALATED] — over-escalated ('escalate_gap')
- `hb-nm-pre-k-daily-schedule-hours-q` [ESCALATED] — over-escalated ('escalate_gap')
