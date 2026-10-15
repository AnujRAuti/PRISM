"""BE-032R D-CHAIN / F-04: an explicit, reviewed historical-gap baseline.

Background (the problem this solves)
------------------------------------
`verify_chain` recomputes hashes and continuity and reports *symptoms*
("sequence gap before N (expected M)", "event_hash mismatch at N", "missing
predecessor for N"). It never says whether a reported gap is *known historical*
damage — e.g. the seven ranges BE-030 §6 measured on `pofa_dev`, the residue of
two pre-enforcement test cleanups — or a *fresh* integrity event. Without that
distinction an operator cannot tell a preserved historical finding from new
tampering, and the D-CHAIN writer policy ("controlled continuation") has nothing
to anchor to.

Design contract (BE-032R §10 — non-negotiable)
----------------------------------------------
* The baseline is an **explicit, reviewed, versioned, auditable** artifact. It is
  a fixed constant of known ranges, never derived by "whatever the ledger
  happens to contain right now" — an auto-baselined current state would bless
  silent corruption.
* It distinguishes gaps only. A **hash mismatch is never blessable** as
  historical: it means surviving content changed, which is exactly the re-basing
  attack the ledger exists to catch. The same holds for a missing predecessor.
* Classification **fails closed / degrades**: with no baseline supplied every gap
  is treated as *new* (the safe default), and the presence of any non-gap failure
  or any unrecognised gap yields a `new_anomaly` status, never `clean`.
* Nothing here repairs, renumbers, deletes or reinserts ledger history. It only
  labels what `verify_chain` already observed.

Why the baseline lives in code but is NOT asserted against live `pofa_dev` in the
test suite: the classifier is exercised with synthetic gap patterns on a
disposable database. The shipped `pofa_dev` register is an *operational* artifact
an operator selects by name when verifying that specific database; tests never
open a protected database to compare against it (the §14 prohibition BE-030
recorded still holds here).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A "sequence gap before N (expected M)" means the surviving event is at N and
#: the contiguous run M..N-1 is absent. Both numbers are captured so a match must
#: agree on the exact range, not merely on a bare sequence number.
_GAP_RE = re.compile(
    r"sequence gap before (\d+) \(expected (\d+)\)"
)


@dataclass(frozen=True)
class HistoricalGapBaseline:
    """A reviewed statement that these exact gap ranges are *known* history.

    ``known_gaps`` holds ``(before_sequence, expected_sequence)`` tuples, i.e. the
    surviving event sequence and the first missing sequence of each range. Only a
    gap matching a stored tuple on *both* numbers is treated as historical; a gap
    shifted by one is a new anomaly, so a tamper that edits history and happens to
    leave the same count of holes is not blessed.
    """

    name: str
    version: int
    reviewed_by: str
    provenance: str
    known_gaps: frozenset[tuple[int, int]] = frozenset()

    def is_known(self, before_sequence: int, expected_sequence: int) -> bool:
        return (before_sequence, expected_sequence) in self.known_gaps


#: Empty baseline: the safe default. Every gap classifies as new.
EMPTY_BASELINE = HistoricalGapBaseline(
    name="none",
    version=0,
    reviewed_by="BE-032R",
    provenance="Default deny: no gap is treated as historical unless a named, "
               "reviewed baseline is supplied explicitly.",
    known_gaps=frozenset(),
)


#: The BE-030 §6 / BE-032 re-measured `pofa_dev` register: seven preserved
#: historical gap ranges (the residue of two pre-enforcement test cleanups), with
#: zero hash mismatches on the survivors. Selecting this baseline by name when
#: verifying that specific database keeps those findings *visible as known* while
#: still flagging anything else as new. It is deliberately keyed to the exact
#: (before, expected) tuples, not to a gap count.
POFA_DEV_HISTORICAL_BASELINE = HistoricalGapBaseline(
    name="pofa-dev-pre-be030-test-cleanup",
    version=1,
    reviewed_by="BE-030 §6 register; re-measured BE-032 [MEASURED 2026-10-11] and "
                "confirmed unchanged (7 gaps, 0 hash mismatch)",
    provenance="docs/BE-030 (feasibility §6) and docs/BE-032 report §7: "
               "gaps before 5350/5380/5385/5392/5397/5677/5682.",
    known_gaps=frozenset({
        (5350, 5344),
        (5380, 5374),
        (5385, 5381),
        (5392, 5386),
        (5397, 5393),
        (5677, 5671),
        (5682, 5678),
    }),
)

#: Registry an operator/config selects from by name. Keeping the set closed means
#: a baseline is always a reviewed artifact, never a runtime-invented constant.
BASELINES: dict[str, HistoricalGapBaseline] = {
    EMPTY_BASELINE.name: EMPTY_BASELINE,
    POFA_DEV_HISTORICAL_BASELINE.name: POFA_DEV_HISTORICAL_BASELINE,
}


def resolve_baseline(name_or_baseline: str | HistoricalGapBaseline | None) -> HistoricalGapBaseline:
    """Coerce a baseline reference to an artifact; ``None``/unknown -> the safe
    empty baseline (fail closed, nothing is blessed as historical)."""
    if isinstance(name_or_baseline, HistoricalGapBaseline):
        return name_or_baseline
    if not name_or_baseline:
        return EMPTY_BASELINE
    baseline = BASELINES.get(name_or_baseline)
    return baseline if baseline is not None else EMPTY_BASELINE


def classify_findings(
    failures: list[str], baseline: HistoricalGapBaseline | None = None
) -> dict:
    """Label `verify_chain`'s observed failures against a reviewed baseline.

    Returns a structured posture that never mutates the input findings and never
    hides one of them:

    * ``known_historical_gaps`` — gaps exactly matching the baseline ranges.
    * ``new_gaps`` — gaps not in the baseline (or any gap when none is supplied).
    * ``hard_anomalies`` — hash mismatches, missing predecessors, anything that is
      not a gap; these are **never** blessable and always imply ``new_anomaly``.
    * ``status`` — ``clean`` | ``known_historical_only`` | ``new_anomaly``.
    * ``degraded`` — True when hard anomalies are present (history content changed
      or is unreachable), which the writer policy must treat as fail-closed.

    The historical gaps stay *visible* in ``known_historical_gaps``; classifying a
    finding as known does not delete it or make verification pass.
    """
    baseline = resolve_baseline(baseline)
    known_historical: list[str] = []
    new_gaps: list[str] = []
    hard_anomalies: list[str] = []

    for failure in failures:
        match = _GAP_RE.search(failure)
        if match is not None:
            before_sequence = int(match.group(1))
            expected_sequence = int(match.group(2))
            if baseline.is_known(before_sequence, expected_sequence):
                known_historical.append(failure)
            else:
                new_gaps.append(failure)
        else:
            # "event_hash mismatch at N" / "missing predecessor for N" / any
            # future non-gap symptom: never historical, always a real anomaly.
            hard_anomalies.append(failure)

    new_anomaly = bool(new_gaps or hard_anomalies)
    if not failures:
        status = "clean"
    elif new_anomaly:
        status = "new_anomaly"
    else:
        status = "known_historical_only"

    return {
        "status": status,
        "degraded": bool(hard_anomalies),
        "known_historical_gaps": known_historical,
        "new_gaps": new_gaps,
        "hard_anomalies": hard_anomalies,
        "baseline_name": baseline.name,
        "baseline_version": baseline.version,
    }
