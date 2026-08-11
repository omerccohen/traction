# The Monday playbook — what to actually do when the system runs

About 30 minutes. The system runs itself every Monday and writes its files to
`briefings/`. This is what *you* do with them.

The single most important rule: **most weeks the answer is "no action," and that
is a successful outcome, not a wasted week.**

---

## Step 1 — Read the desk note. Pick ONE theme.
`briefings/desk_note_<date>.md`

It ranks where activity is unusual. Take the **top one** and ignore the rest.
Three themes a week is how you end up owning a diluted version of the market.

## Step 2 — Check the physical proxy. This is your cheapest filter.
Same file, the `physical_proxies` read.

Does the real-world commodity confirm the story? Copper up **+17%** confirmed
the construction story this week. Uranium down **−20% over 3 months**
contradicted the nuclear story.

> **If no physical proxy confirms the theme, stop here and do nothing this week.**

## Step 3 — Read the target groups. Separate VERIFIED from HYPOTHESIS.
`briefings/target_groups_<date>.md`

Only the **VERIFIED** lines are facts with a source behind them. Everything
labelled HYPOTHESIS is a story someone found plausible — including the machine.

## Step 4 — Open the price table. Hunt for the disagreement.
`briefings/price_vs_position_<date>.md`

You are looking for exactly one thing: a company where the **research says
strong** and the **price says not yet expensive** ("positioned, NOT fully
priced").

If every name in your theme reads *"priced for perfection"* — as the whole
construction group did this week — **the answer is no action.** The work already
paid for itself by telling you that.

## Step 5 — Write one sentence.
*"I believe ____, and the price does not."*

If you cannot fill in the blank, you have no reason to act. Most weeks you will
not be able to. "Company X is excellent" is **not** a valid sentence — the
backtest showed excellence is already in the price.

## Step 6 — Write the falsifier.
*"I am wrong if ____ by ____."*

Concrete and checkable: *"if IES backlog stops growing by the Q1 print"* or
*"if copper breaks below $X."* A thesis with no kill-switch is a belief, and
beliefs do not get closed — they get rationalised.

## Step 7 — Decide, and LOG IT.

```bash
python scripts/journal.py add --ticker XXX --action watch \
    --thesis "..." --falsifier "..."
```

Log the passes too (`--action pass`). The names you skipped are half your
process, and the journal scores them inverted — a good pass is one that went on
to lag.

## Step 8 — Review the open entries.

```bash
python scripts/journal.py review    # what happened since, vs SPY
python scripts/journal.py score     # your running record
```

Anything flagged **CHECK FALSIFIER** is over a month old: go look at whether the
thing you said would prove you wrong has happened. If it has, close it.

```bash
python scripts/journal.py close --id 0001 --reason "falsifier tripped"
```

---

## Why the journal is the point

Every other piece of this system describes the world. Only the journal records
what **you** decided and whether it worked — and it scores you against **SPY**,
not against zero, so a rising market cannot masquerade as skill.

You asked how you can know in advance whether this works. **You cannot.** No
backtest of mine settles it, because I can always be fooling myself with the
same data twice — this project caught itself doing exactly that. The only
honest answer is your own track record, built one logged decision at a time.

The scorecard will refuse to give you a verdict before **20 decisions**, and it
says so out loud. At smaller sizes a coin flip looks like genius.

## What the evidence supports, honestly

- **Field level — "where is something happening?"** Measured and replicated.
  This is the strongest thing here.
- **Company level — "who is exposed, and is the story real?"** True and useful;
  it is verifiable fact, not prediction.
- **"Which one will rise?"** No evidence. The naive version (buy the
  best-positioned) sorted *backwards*, and even after adding valuation the
  cheap end lost to the expensive end in this sample.

So run the loop for the first two, and let the journal — not a backtest, and
not me — tell you whether the third is ever worth acting on.
