# Collections-call summary review data

This pack contains **20 synthetic transcript–summary pairs** and the rules used to produce the summaries. All calls are fictional; no real customer records are used.

## Files

- `candidate-calls.json`: machine-readable list of calls.
- `candidate-calls.md`: the same calls in a readable format.
- `summary-rules.txt`: the original supplied summary-generation rules.

## Review scope

Your review service should help a user identify:

- Summary claims that contradict the transcript.
- Claims that the transcript does not support.
- Information the summary rules require but the summary omits.
- Breaches of the summary rules, even when the underlying fact is correct.

Some summaries are accurate. Do not assume that every call contains an error. Use transcript turn IDs as evidence, and distinguish uncertainty from a definite error. A missing category is not automatically an omission: it must have been discussed and required by the rules.

## Data conventions

Each record contains `id`, `call_date`, `estimated_duration`, `transcript` and `summary`. Turn IDs are local to each call. Use the call ID and turn ID together when citing evidence.

The call date supplies context for relative dates such as “tomorrow”. Timestamps are illustrative. Calls are designed to represent approximately three to four minutes of speech and short pauses; there are no audio recordings. Secure card and bank identifiers are excluded. Occasional transcription imperfections are intentional.

For DPA, apply the explicit instruction requiring “no DPA stated with agent” when full verification or confirmed pre-call security is absent. Treat that specific instruction as an exception to the general omission rule. Retain named advice bodies such as Citizens Advice and StepChange, because the rules expressly require reporting those referrals; redact identifying employers, garages and other private entities.

This pack provides data and review scope; it does not prescribe implementation choices or replace the hiring challenge's wider delivery requirements.
