# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
import pytest

from open_formal_cdc.infer import (Candidate, FormalAnswer, Literal, MiningResult, Signal,
                                   blocking_steps, design_signals, formal_filters, implication_map,
                                   implies, mine, mine_trace, sample_trace, unique)

A = Literal("a")
B = Literal("b")
C = Literal("c")
SIGNALS = [Signal("ack", "output", "a"), Signal("req", "input", "a"),
           Signal("go", "input", "a")]


def always(c):
    return Candidate("always", (), c)


def imp(a, c):
    return Candidate("implies", (a,), c)


def nxt(a, c):
    return Candidate("next", (a,), c)


def both(a, b, c):
    return Candidate("and", (a, b), c)


def both_next(a, b, c):
    return Candidate("and_next", (a, b), c)


def mixed(a, b, c):
    return Candidate("mixed_next", (a, b), c)


def test_mine_common_protocol_assumption():
    traces = [
        [{"ack": 0, "req": 0, "go": 0}, {"ack": 0, "req": 1, "go": 1},
         {"ack": 1, "req": 1, "go": 0}],
        [{"ack": 0, "req": 0, "go": 0}, {"ack": 0, "req": 0, "go": 0},
         {"ack": 0, "req": 1, "go": 0}, {"ack": 1, "req": 1, "go": 0}],
    ]
    result = mine(traces, SIGNALS)
    expected = both_next(Literal("ack", False), Literal("req", False), Literal("req", False))
    assert expected in result.candidates
    assert str(expected) == "always (!ack && !req) -> next !req"
    assert always(Literal("go", False)) not in result.candidates
    assert always(Literal("go", False)) in result.rejected["common_cause"]
    assert always(Literal("ack")) in result.rejected["input"]
    relaxed = mine(traces, SIGNALS, common_threshold=0.5)
    assert always(Literal("go", False)) in relaxed.candidates


def test_uniqueness_orders_outputs_before_inputs():
    signals = {s.name: s for s in SIGNALS}
    ack, req = Literal("ack"), Literal("req")
    assert unique(imp(ack, Literal("req", False)), signals)
    assert not unique(imp(req, Literal("ack", False)), signals)
    assert not unique(both(ack, req, Literal("go")), signals)
    assert unique(both(ack, Literal("go"), req), signals)


def test_unknown_values_do_not_create_literals():
    rows = [{"ack": 0, "req": 0, "go": 0}, {"ack": 0, "req": 2, "go": 1}]
    found = mine_trace(rows, SIGNALS)
    assert not any(c.consequent.signal == "req" and c.template == "next" for c in found)


def test_all_appendix_e_implications():
    pairs = [
        (always(A), imp(A.negate(), B)),
        (always(B), imp(A, B)),
        (always(A), nxt(A.negate(), B)),
        (always(B), nxt(A, B)),
        (always(A), both(A.negate(), B, C)),
        (always(B), both(A, B.negate(), C)),
        (always(C), both(A, B, C)),
        (always(A), both_next(A.negate(), B, C)),
        (always(B), both_next(A, B.negate(), C)),
        (always(C), both_next(A, B, C)),
        (always(A), mixed(A.negate(), B, C)),
        (always(B), mixed(A, B.negate(), C)),
        (always(C), mixed(A, B, C)),
        (imp(A, B), both(A, B.negate(), C)),
        (imp(A, C), both(A, B, C)),
        (imp(B, C), both(A, B, C)),
        (imp(A, B), both_next(A, B.negate(), C)),
        (imp(B, C), mixed(A, B, C)),
        (nxt(A, C), both_next(A, B, C)),
        (nxt(B, C), both_next(A, B, C)),
        (nxt(A, C), mixed(A, B, C)),
        (nxt(A, B), mixed(A, B.negate(), C)),
    ]
    assert len(pairs) == 22
    assert all(implies(strong, weak) for strong, weak in pairs)
    result = implication_map([pairs[0][0], pairs[0][1], always(C)])
    assert result == {pairs[0][0]: [pairs[0][1]]}


def test_implication_rejects_invalid_time_shifts():
    assert not implies(imp(A, B), nxt(A, B))
    assert not implies(nxt(A, B), imp(A, B))
    assert not implies(always(A), always(B))
    assert not implies(both(A, B, C), imp(A, C))
    assert not implies(imp(A, B), mixed(A, B.negate(), C))


def test_mining_input_validation():
    with pytest.raises(ValueError, match="antecedents"):
        Candidate("implies", (), A)
    with pytest.raises(ValueError, match="common_threshold"):
        mine([[{"a": 0}]], [Signal("a", "input", "a")], common_threshold=0)
    assert mine([], SIGNALS).candidates == []


def test_candidate_params_roundtrip():
    candidate = both_next(Literal("ack", False), Literal("req", False), Literal("req", False))
    params = candidate.params("a")
    assert Candidate.from_params(params) == candidate
    assert params["verify"] is False and params["source"] == "inferred"
    assert params["consequent"] == {"signal": "req", "positive": False}


TRACE_VCD = """$scope module ofcdc_top $end
$var wire 1 i ofcdc_init_done $end
$var wire 1 a ofcdc_edge_a $end
$var wire 1 b ofcdc_edge_b $end
$var wire 1 g ofcdc_in_go $end
$var wire 1 n ofcdc_in_async_in $end
$var wire 2 q ofcdc_out_q $end
$upscope $end
$enddefinitions $end
#0
0i
0a
0b
0g
0n
b00 q
#1
b1 i
b1 a
b01 q
#2
b0 a
b1 b
b1 n
b10 q
#3
b1 a
b0 b
b1 g
b11 q
#4
b0 a
b1 b
"""


def test_domain_trace_sampling_and_blocking(tmp_path):
    from types import SimpleNamespace
    from open_formal_cdc.config import Input
    from open_formal_cdc.netlist import Netlist
    data = {"modules": {"top": {
        "ports": {"clk_a": {"direction": "input", "bits": [1]},
                  "rst_n": {"direction": "input", "bits": [2]},
                  "go": {"direction": "input", "bits": [3]},
                  "async_in": {"direction": "input", "bits": [4]},
                  "q": {"direction": "output", "bits": [5, 6]}},
        "netnames": {}}}}
    nl = Netlist(data, "top")
    cfg = SimpleNamespace(clocks=[SimpleNamespace(port="clk_a")],
                          resets=[SimpleNamespace(port="rst_n")],
                          inputs=[Input("go", "a"), Input("async_in", None)], outputs={"q": "b"})
    signals = design_signals(cfg, nl)
    assert [s.name for s in signals] == ["go", "q[0]", "q[1]"]
    all_signals = design_signals(cfg, nl, include_async=True)
    assert "async_in" in [s.name for s in all_signals]
    trace = tmp_path / "trace.vcd"
    trace.write_text(TRACE_VCD)
    assert sample_trace(trace, signals, "a") == [{"go": 0}, {"go": 1}]
    assert sample_trace(trace, signals, "b") == [{"q[0]": 0, "q[1]": 1},
                                                   {"q[0]": 1, "q[1]": 1}]
    assert blocking_steps(trace, all_signals) == [
        {"go": 0, "async_in": 0}, {"go": 0, "async_in": 1}, {"go": 1, "async_in": 1},
        {"go": 1, "async_in": 1}]


def test_formal_filters_propagate_triviality_downward():
    strong, weak = always(A), imp(A.negate(), B)
    calls = []

    def evaluate(candidate, stage):
        calls.append((candidate, stage))
        return FormalAnswer("trivial")

    result = formal_filters(MiningResult([strong, weak], {strong: [weak]}), evaluate)
    assert [r.reason for r in result] == ["triviality", "triviality"]
    assert calls == [(strong, "triviality")]


def test_formal_filters_propagate_results_upward():
    strong, weak = always(A), imp(A.negate(), B)
    calls = []

    def evaluate(candidate, stage):
        calls.append((candidate, stage))
        if stage == "triviality":
            return FormalAnswer("nontrivial")
        if stage == "consistency":
            return FormalAnswer("consistent")
        if stage == "vacuity":
            return FormalAnswer("nonvacuous")
        return FormalAnswer("proven")

    result = formal_filters(MiningResult([weak, strong], {strong: [weak]}), evaluate)
    assert [r.quality for r in result] == [1.0, 1.0]
    assert (strong, "triviality") not in calls
    assert (strong, "assertion") not in calls
    assert (strong, "consistency") in calls and (strong, "vacuity") in calls


def test_formal_filters_reject_vacuous_and_report_quality():
    strong, weak = always(A), imp(A.negate(), B)

    def vacuous(candidate, stage):
        return FormalAnswer({"triviality": "nontrivial", "consistency": "consistent",
                             "vacuity": "vacuous"}[stage])

    result = formal_filters(MiningResult([weak, strong], {strong: [weak]}), vacuous)
    assert all(r.status == "rejected" and r.reason == "vacuity" for r in result)

    def counterexample(candidate, stage):
        values = {"triviality": "nontrivial", "consistency": "consistent", "vacuity": "nonvacuous",
                  "assertion": "cex"}
        return FormalAnswer(values[stage], quality=0.25 if stage == "assertion" else None)

    result = formal_filters(MiningResult([weak], {}), counterexample)
    assert result[0].status == "candidate" and result[0].quality == 0.25


def test_formal_filter_batches_keep_implication_savings():
    strong, weak, independent = always(A), imp(A.negate(), B), always(C)
    batches = []

    def evaluate_many(candidates, stage):
        batches.append((stage, candidates))
        return {c: FormalAnswer("trivial") for c in candidates}

    def unexpected(candidate, stage):
        raise AssertionError("fallback must not be used")

    result = formal_filters(MiningResult([strong, weak, independent], {strong: [weak]}),
                            unexpected, evaluate_many)
    assert batches == [("triviality", [strong, independent])]
    assert all(r.reason == "triviality" for r in result)
