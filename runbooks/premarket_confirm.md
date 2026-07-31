# Runbook: Pre-entry sentiment-shift check (~9:00 AM ET, Mon–Fri)

Read `config.yaml` and today's journal (the 8:00 AM Pre-market section, already written
by `runbooks/premarket.md`) first. All times US/Eastern. Added 2026-07-27: markets can
move meaningfully in the hour between the premarket read and the 9:45 entry check —
this phase exists to catch that shift *before* entry, not discover it live at 9:45.

## 0. Guards
- Confirm today is a US equity trading day. If closed, or if today's journal has no
  Pre-market section (the 8 AM run didn't fire or found the market closed): append a
  one-line journal note, push, stop.
- If fired before 8:45 ET or after 9:30 ET (DST drift or a delayed fire): still run —
  this phase is research-only, and a late fire is still useful right up to the open.
- If today's journal already has a "Pre-market update (9:00 ET)" section: skip
  (idempotent — prevents duplicates if the Routine fires twice).

## 1. Re-pull the same signals, compare against the 8 AM read
1. WebSearch: a fresh "premarket movers" / "futures update" check — has the macro tone
   (futures direction, any data released in the last hour) shifted from the 8 AM read?
2. `run_scan` on `scan_id` and, if `enable_puts`, `scan_id_puts` — premarket scanner
   coverage is still limited this early, but note any newly-appearing names.
3. `get_equity_quotes` on every symbol from the 8 AM candidate table (top 10), plus any
   name newly surfaced in step 1: compare current premarket price against the 8:07-ish
   price already journaled. For each candidate, classify the move since 8 AM:
   - **Strengthening** — moved further in its candidate direction (more bullish for a
     call candidate, more bearish for a put candidate).
   - **Fading** — moved back toward (or through) its prior close, weakening the thesis.
   - **Reversed** — has already crossed back through its prior close in the opposite
     direction — a strong early warning the entry-check tape confirmation is likely to
     fail (this is exactly what happened to every oil-crash put candidate on 2026-07-27,
     visible in premarket data almost an hour before entry (9:45)).
   - **Unchanged** — no material move either way.
4. Note whether any 8 AM candidate now fails its own "disqualify if" condition already
   (e.g. a put candidate that reclaimed its prior close) — flag it as likely dead before
   entry.md even runs, though entry.md's live tape check remains the authoritative gate.

## 2. Re-rank
Produce an updated candidate order (same top-10 list, re-sorted) reflecting the hour's
moves: strengthening candidates move up, fading/reversed candidates move down or get a
"likely fails at 9:45" flag. Do not add brand-new names lightly — the entry runbook's
live scanner + tape check at 9:45 is still the primary discovery mechanism; this phase
is a sentiment/confirmation check on the existing list, not a second full research pass.

## 3. Journal & handoff
- Append a **"Pre-market update (9:00 ET)"** section to today's journal: one line per
  candidate on its classification (strengthening/fading/reversed/unchanged) vs. the 8 AM
  read, the re-ranked order, and a one-sentence overall read (e.g. "oil-crash puts are
  already fading back toward their opens — expect a difficult 9:45 tape check").
- Commit ("journal: YYYY-MM-DD premarket update 9:00") and push to the working branch.
- Do not place, review, or cancel any order in this phase — research only, same as
  the 8 AM premarket run.
