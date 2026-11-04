---
name: ux-research
description: Run lightweight, decision-driven UX research—usability tests, interviews, surveys, and analytics review—with unbiased scripts and actionable synthesis.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: low
---

# UX Research

## 1. Purpose

Reduce uncertainty about users before and during product work. Research is valuable when it answers a specific decision ("should onboarding be one screen or three?") with evidence, not when it produces a long report of opinions. This skill covers choosing a method, writing unbiased scripts, recruiting the right participants, running sessions, and synthesizing findings into decisions.

**Scope:** research with informed consent. Recording, storing, or sharing participant data requires consent, anonymization, and compliance with privacy rules; never publish identifiable participant material.

## 2. Activation Conditions

- A design decision is contested or based on internal opinion.
- Usability problems are suspected but unverified.
- Onboarding, checkout, or a critical flow is underperforming.
- Need to size a problem (how many users hit an error).
- Keywords: UX research, usability test, user interview, survey, usability, task success, think-aloud, personas, journey map, analytics, discovery.

## 3. When Not to Use

- The question is answerable from existing data (analytics, support tickets, session recordings) — check those first.
- A/B testing a live hypothesis is better suited (quantitative, behavioral).
- The decision is already made and irreversible—research after the fact breeds cynicism.

## 4. Required Context

1. The decision to be informed and who owns it.
2. What is already known (analytics, tickets, prior studies).
3. Target user segments and how to reach them.
4. Timeline and budget (a 5-day study vs. 2-hour guerrilla test).
5. Legal/consent requirements for recording.

## 5. Operating Procedure

1. **Write the research brief**: decision, questions (3–5 max), method, participants, timeline, and what "we will do differently" means.
2. **Choose the method**:
   - Generative/discovery: interviews, diary studies.
   - Evaluative: moderated usability tests (5–8 participants per segment), unmoderated tests at scale.
   - Quantitative: surveys (with validated scales), analytics, A/B tests.
   - Mixed: analytics to size, interviews to explain.
3. **Recruit representative participants** — not colleagues. Screen for the behavior that matters (e.g. "has booked travel online in the last 6 months"), and include edge cases (assistive tech users, low connectivity).
4. **Write the script**: warm-up, context questions, task prompts framed neutrally ("Show me how you would find your last invoice"), no leading questions, and probes ("What did you expect to happen there?").
5. **Run sessions**: think-aloud, observer notes in a template, no coaching, silence is fine, and note timestamps of friction.
6. **Capture evidence**: recordings (with consent), task success/failure, time on task, error counts, and key quotes anonymized.
7. **Synthesize with an affinity map**: cluster observations, count how many participants hit each issue, and separate observation from interpretation.
8. **Prioritize** by frequency × severity × confidence; connect each finding to the decision.
9. **Deliver** a short report: top findings, evidence, recommended actions, and what remains unknown.
10. **Follow up**: track which recommendations were implemented and whether the metric moved.

## 6. Tools and Technologies

| Purpose | Options |
|---|---|
| Moderated testing | Zoom/Meet + recording, Lookback, UserTesting |
| Unmoderated | Maze, UserZoom, PlaybookUX |
| Surveys | Typeform, Google Forms, Qualtrics |
| Analytics | Amplitude, PostHog, GA4, SQL over event data |
| Session replay | PostHog, FullStory, Hotjar |
| Synthesis | Dovetail, Notion, Miro affinity boards |
| Recruitment | Internal panels, Respondent, user testing platforms |

## 7. Practical Implementation

**Usability test script (moderated, 30 min):**

```markdown
## Intro (3 min)
- Thank you; we're testing the product, not you.
- We'll record with your permission; you can stop anytime.
- Please think aloud — share what you're looking at and expecting.

## Context (5 min)
- Tell me about the last time you had to [task context].
- What tools did you use? What was frustrating?

## Tasks (18 min)
Task 1: "You received an invoice by email and want to check whether it was paid.
         Starting from this screen, show me how you'd do that."
  Success criteria: reaches invoice detail with payment status within 3 min.
  Probes: "What are you looking for?" / "What did you expect there?"
Task 2: "Now add a second user to your account."
  Success criteria: invite sent with the correct role.

## Wrap-up (4 min)
- What was the most confusing moment?
- If you could change one thing, what would it be?
```

**Neutral phrasing rules:**

```text
BAD:  "Was it easy to find the export button?"
GOOD: "How did you go about exporting?"
BAD:  "Don't you think this step is unnecessary?"
GOOD: "Walk me through what you did here."
BAD:  "Would you use a feature that..."
GOOD: "Tell me about the last time you needed to..."
```

**Session notes template:**

```markdown
Participant: P03 (segment: small-business accountant)
Task 1: success, 48 s, no errors
- Expectation mismatch at "Invoice status": looked for a badge in the list, not a detail page.
- Quote: "I'd expect the status right here next to the amount."
Task 2: failure (5 min timeout)
- Failed to find "Team" under Settings; searched the top nav twice.
Severity: high (blocks a core admin task)
```

**Survey question with a validated scale:**

```text
How confident are you that you can find any past invoice within one minute?
(1 = not at all confident, 7 = extremely confident)   [single-select]

Avoid: double-barreled ("fast and easy"), leading, or absolute phrasing.
```

**Severity scoring:**

```text
severity = frequency (participants affected / total) × impact (1–3)
  3 = blocks task completion, 2 = causes significant rework/confusion, 1 = cosmetic delay
Report: e.g. 6/8 participants × 3 = 18 (critical)
```

**Analytics funnel query (SQL):**

```sql
WITH steps AS (
  SELECT user_id,
         MIN(ts) FILTER (WHERE event = 'checkout_started') AS started,
         MIN(ts) FILTER (WHERE event = 'payment_submitted') AS submitted,
         MIN(ts) FILTER (WHERE event = 'order_confirmed') AS confirmed
  FROM events WHERE ts >= now() - interval '30 days'
  GROUP BY user_id
)
SELECT count(*) AS started_users,
       count(submitted) AS submitted_users,
       count(confirmed) AS confirmed_users,
       round(100.0 * count(submitted) / count(*), 1) AS start_to_submit_pct
FROM steps;
```

**Synthesis into decisions:**

```markdown
Finding F1: Status is not visible in the invoice list (6/8 participants).
Evidence: P01, P03, P05 quotes; task 1 median time 2.4 min where successful.
Impact: delays the core "is it paid?" question; drives support contacts.
Recommendation: surface a status badge in the list row; re-test with 5 users.
Decision owner: @design-lead. Status: accepted for next sprint.
```

## 8. Quality Standards

- Every study has a written decision and questions before recruitment.
- Scripts avoid leading questions; tasks are framed around goals, not UI.
- Participants are real users meeting screening criteria; sample size justified.
- Observations and interpretations are recorded separately.
- Findings include frequency and severity, not just anecdotes.
- Quotes are anonymized; consent for recording is documented.
- Recommendations name an owner and a follow-up measurement.

## 9. Verification and Testing

- Pilot the script with one internal participant; fix ambiguous tasks.
- Check that tasks are completable and time-boxed.
- Verify recruitment screening (ask a qualifying question, not self-description).
- After the study, confirm the top three findings are corroborated by at least two participants or by analytics.
- Track whether implemented changes moved the target metric.

## 10. Security Considerations

- Obtain informed consent for recording and data use; state retention and who sees the data.
- Anonymize participants in reports (use P01, P02) and remove faces/names from screenshots.
- Do not record screens containing real customer data; use test accounts.
- Incentives and personal data (emails, payment details for gift cards) must be handled under privacy policy.
- Session recordings can capture credentials if participants log in—blur or pause recording during authentication.
- Guard against research bias and social engineering: participants may demonstrate workarounds that reveal internal systems; do not collect confidential business data.

## 11. Failure Handling

- **Participants cannot complete any task:** tasks are mis-specified—clarify wording, don't coach.
- **Everything "works fine":** the sample is too familiar with the product; recruit new users.
- **Stakeholders dismiss findings:** involve them as observers and tie findings to a business metric.
- **Recruiting is slow:** use a shorter unmoderated study or intercepts; document the sample limitation.
- **Conflicting findings:** segment the data (by role/experience) instead of averaging.
- **Research requested after launch:** redirect to analytics and support-ticket analysis to measure the impact.

## 12. Expected Deliverables

1. Research brief with decision and questions.
2. Screener and recruitment criteria.
3. Test script or interview guide.
4. Session notes with timestamps and anonymized quotes.
5. Severity-ranked findings with evidence.
6. Recommendations with owners and follow-up metrics.
7. Limitations section.

## 13. References

- Nielsen Norman Group — usability testing 101 — https://www.nngroup.com/articles/usability-testing-101/
- "Rocket Surgery Made Easy" (Steve Krug).
- "Just Enough Research" (Erika Hall).
- GOV.UK Service Manual — user research — https://www.gov.uk/service-manual/user-research
- "Measuring the User Experience" (Albert & Tullis).
- System Usability Scale (SUS) — https://www.usability.gov/how-to-and-tools/methods/system-usability-scale.html
