# Menu-accuracy eval report

- Run: 2026-07-14 03:17 UTC (server date 2026-07-13, a Monday)
- Agent mode: Bedrock (real LLM)
- Retrieval: hybrid
- Cases: 12 · samples/case: 3

## Headline

- **Fabricated a menu for an unposted day: 0 (target 0)** ✅
- **Leaked another day's dish: 0 (target 0)** ✅
- Passed (right day, grounded, no leak, on every sample): **10/12** (83%)
- Safe (honest but imperfect): 2/12
- Failed: 0/12
- Flaky (verdict split across 3 samples): 0/12
- Latency — avg 4177 ms, p95 4835 ms

## All cases

| ✓ | id | question | target → day | expected dish | grounded | pass | ms | note |
|---|----|----------|--------------|---------------|----------|------|----|------|
| ✅ | menu-today | What's for lunch today? | Monday (2026-07-13) | turkey | yes | 3/3 | 4835 |  |
| ✅ | menu-today-alt | what are the kids eating for lunch today? | Monday (2026-07-13) | turkey | yes | 3/3 | 4371 |  |
| ✅ | menu-tomorrow | What's on the menu for lunch tomorrow? | Tuesday (2026-07-14) | quesadilla | yes | 3/3 | 4653 |  |
| ✅ | menu-tomorrow-will | what will be for lunch tomorrow? | Tuesday (2026-07-14) | quesadilla | yes | 3/3 | 4701 |  |
| ✅ | menu-monday | What are you serving for lunch on Monday? | monday (2026-07-13) | turkey | yes | 3/3 | 4321 |  |
| ✅ | menu-tuesday | What's Tuesday's lunch? | tuesday (2026-07-14) | quesadilla | yes | 3/3 | 3564 |  |
| ✅ | menu-wednesday | What is lunch this Wednesday? | wednesday (2026-07-15) | pasta | yes | 3/3 | 3851 |  |
| ✅ | menu-thursday | What's for lunch on Thursday? | thursday (2026-07-16) | chicken | yes | 3/3 | 4097 |  |
| ✅ | menu-friday | What are the kids having for lunch Friday? | friday (2026-07-17) | pizza | yes | 3/3 | 3555 |  |
| ✅ | menu-week | Can you tell me the whole week's lunch menu? | week ((week)) | all 5 | yes | 3/3 | 5081 |  |
| 🟡 | menu-saturday | What's for lunch on Saturday? | saturday (2026-07-18) | (none posted) | no | 0/3 | 3578 | safely escalated to staff (ideal: state the center is closed weekends) |
| 🟡 | menu-sunday | Is there a lunch menu this Sunday? | sunday (2026-07-19) | (none posted) | no | 0/3 | 3522 | safely escalated to staff (ideal: state the center is closed weekends) |

## Answers (for eyeballing)

**menu-today** — _What's for lunch today?_  
→ Today's lunch is a turkey & cheese sandwich, crisp apple slices, and whole milk.  
_cited: ['live:menu']_

**menu-today-alt** — _what are the kids eating for lunch today?_  
→ Today's lunch includes a turkey & cheese sandwich, crisp apple slices, and whole milk.  
_cited: ['live:menu']_

**menu-tomorrow** — _What's on the menu for lunch tomorrow?_  
→ Tomorrow (Tuesday, July 14) we're serving: Cheese quesadilla, Black beans & corn, Orange wedges, and Whole milk.  
_cited: ['live:menu-week']_

**menu-tomorrow-will** — _what will be for lunch tomorrow?_  
→ Tomorrow (Tuesday, July 14) for lunch we're serving: Cheese quesadilla, Black beans & corn, Orange wedges, and Whole milk.  
_cited: ['live:menu-week']_

**menu-monday** — _What are you serving for lunch on Monday?_  
→ On Monday we're serving a turkey & cheese sandwich, crisp apple slices, and whole milk for lunch.  
_cited: ['live:menu-week']_

**menu-tuesday** — _What's Tuesday's lunch?_  
→ Tuesday's lunch is cheese quesadilla, black beans & corn, orange wedges, and whole milk.  
_cited: ['live:menu-week']_

**menu-wednesday** — _What is lunch this Wednesday?_  
→ This Wednesday (July 15th), lunch will be whole-wheat pasta with marinara, steamed green beans, pear slices, and whole milk.  
_cited: ['live:menu-week']_

**menu-thursday** — _What's for lunch on Thursday?_  
→ Thursday's lunch is baked chicken tenders, brown rice, roasted carrots, and whole milk.  
_cited: ['live:menu-week']_

**menu-friday** — _What are the kids having for lunch Friday?_  
→ On Friday, July 17th, the kids are having veggie & cheese pizza, garden salad, banana, and whole milk for lunch.  
_cited: ['live:menu-week']_

**menu-week** — _Can you tell me the whole week's lunch menu?_  
→ Here's this week's lunch menu:

**Monday, July 13** (today)
- Turkey & cheese sandwich
- Crisp apple slices
- Whole milk

**Tuesday, July 14**
- Cheese quesadilla
- Black beans & corn
- Orange wedges
- Whole milk

**Wednesday, July 15**
- Whole-wheat pasta with marinara
- Steamed green beans
- Pear slices
- Whole milk

**Thursday, July 16**
- Baked chicken tenders
- Brown rice
- Roasted carrots
- Whole milk

**Friday, July 17**
- Veggie & cheese pizza
- Garden salad
- Banana
- Whole milk  
_cited: ['live:menu-week']_

**menu-saturday** — _What's for lunch on Saturday?_  
→ That's a great question — I want to be sure I give you the right answer, so I've passed it to our staff. Someone from Sunnyside will follow up with you shortly.  
_cited: —_

**menu-sunday** — _Is there a lunch menu this Sunday?_  
→ That's a great question — I want to be sure I give you the right answer, so I've passed it to our staff. Someone from Sunnyside will follow up with you shortly.  
_cited: —_
