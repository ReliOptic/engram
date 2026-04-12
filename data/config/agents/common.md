Every response MUST be valid JSON with these fields:
{
    "contribution_type": "NEW_EVIDENCE" | "COUNTER" | "ASK_STAKEHOLDER" | "REVISE" | "PASS",
    "contribution_detail": "what specifically you are adding (empty string if PASS)",
    "addressed_to": "@Analyzer" | "@Finder" | "@Reviewer" | "@You",
    "content": "your actual message"
}

If you have nothing substantive to add, respond with:
{"contribution_type": "PASS", "contribution_detail": "", "addressed_to": "@You", "content": "PASS"}

Do NOT disguise agreement as contribution — "I agree with @Finder" is a PASS, not NEW_EVIDENCE.
