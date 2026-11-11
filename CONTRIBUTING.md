# Contributing

## Reporting a problem

Open an issue with the command you ran, the owner name, and the exit code. If a
repository was reported healthy that is not, the report is more useful than a
stack trace.

## Sending a change

1. Fork and branch.
2. Every check must answer a question that **no single repository can answer
   about itself**. A check that duplicates a repository's own CI does not belong
   here — it costs API calls and tells you nothing new.
3. Keep it to the standard library. This runs in a workflow with one setup step;
   a dependency means a supply chain for a script that reads JSON.

## Adding a check

Add it to `check_repo()`, put the failure in `row["problems"]`, and update the
table in the README. If a check can produce a false alarm on a legitimately
configured repository — an archived one, a profile README — exclude that case
first. A checker that cries wolf gets ignored.