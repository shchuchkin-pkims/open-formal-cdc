# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
from open_formal_cdc.results import TaskResult, combine, overall, parse_task, ModelResult

LOG_FAIL = """SBY 1:00:00 [job_ticks_prove] engine_0: Status returned by engine: FAIL
SBY 1:00:00 [job_ticks_prove] summary: Elapsed clock time [H:MM:SS (secs)]: 0:00:03 (3)
SBY 1:00:00 [job_ticks_prove] summary: counterexample trace: job_ticks_prove/engine_0/trace.vcd
SBY 1:00:00 [job_ticks_prove] summary:   failed assertion ofcdc_top.chk_g.p_gray at ofcdc_gray.v:20.7-20.51 step 6
"""
LOG_COVER = """SBY 1:00:00 [job_ticks_cover] summary:   reached cover statement ofcdc_top.chk_g.c_change at x.v:1 step 4
SBY 1:00:00 [job_ticks_cover] summary:   unreached cover statement ofcdc_top.chk_g.c_other
SBY 1:00:00 [job_ticks_cover] summary: unreached cover statements:
SBY 1:00:00 [job_ticks_cover] summary:   ofcdc_top.chk_g.c_last at x.v:2
SBY 1:00:00 [job_ticks_cover] DONE (FAIL, rc=2)
"""


def write(d, status, log):
    d.mkdir(parents=True)
    (d / "status").write_text(status)
    (d / "logfile.txt").write_text(log)
    return d


def test_parse_fail(tmp_path):
    r = parse_task(write(tmp_path / "job_ticks_prove", "FAIL 0 1\n", LOG_FAIL))
    assert r.status == "FAIL"
    assert r.failed == [("ofcdc_top.chk_g.p_gray", 6)]
    assert r.seconds == 3
    assert r.traces[0].endswith("job_ticks_prove/engine_0/trace.vcd")


def test_parse_cover(tmp_path):
    r = parse_task(write(tmp_path / "c", "FAIL 0 1\n", LOG_COVER))
    assert r.reached == [("ofcdc_top.chk_g.c_change", 4)]
    assert r.unreached == ["ofcdc_top.chk_g.c_last", "ofcdc_top.chk_g.c_other"]


def test_missing(tmp_path):
    assert parse_task(tmp_path / "none").status == "MISSING"


def test_combine():
    ok = TaskResult("PASS")
    assert combine("ticks", ok, ok).status == "proven"
    assert combine("ticks", TaskResult("FAIL", failed=[("p", 5)]), ok).status == "cex"
    assert combine("ticks", TaskResult("FAIL", failed=[("p", 5)]), ok).step == 5
    bounded = combine("ticks", ok, TaskResult("FAIL", unreached=["c"]))
    assert bounded.status == "unknown" and "bounded search" in bounded.detail
    assert combine("ticks", ok, TaskResult("TIMEOUT", unreached=["c"])).status == "unknown"
    assert combine("ticks", TaskResult("UNKNOWN"), ok).status == "unknown"
    assert combine("ticks", TaskResult("ERROR", error="boom"), ok).status == "error"


def test_overall():
    assert overall([ModelResult("ticks", "proven"), ModelResult("clk2ff", "proven")]) == "proven"
    assert overall([ModelResult("ticks", "proven"), ModelResult("clk2ff", "cex")]) == "model_mismatch"


def test_fail_without_trace(tmp_path):
    log = ("SBY 1:00:00 [j] summary: engine_0 (abc pdr) returned FAIL\n"
           "SBY 1:00:00 [j] ERROR: engine_0: Could not determine aigsmt status.\n")
    r = parse_task(write(tmp_path / "j", "ERROR 16\n", log))
    assert r.status == "FAIL" and "without trace" in r.error
    assert combine("ticks", r, TaskResult("PASS")).status == "cex"
