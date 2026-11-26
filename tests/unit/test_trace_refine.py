# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
from open_formal_cdc.trace_refine import activity, prioritize

VCD = """$scope module ofcdc_top $end
$scope module u_dut $end
$var wire 1 a dst_data_q $end
$var wire 1 b other_q $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
0a
0b
#1
1a
#2
1b
#3
0a
"""


def test_activity_prioritizes_recent_change(tmp_path):
    trace = tmp_path / "trace.vcd"
    trace.write_text(VCD)
    cuts = ["other_q", "dst_data_q", "missing_q"]
    scores = activity(trace, cuts)
    assert scores["dst_data_q"] == (1, 2)
    assert scores["other_q"] == (0, 1)
    assert scores["missing_q"] is None
    assert prioritize(trace, cuts) == ["dst_data_q", "other_q", "missing_q"]
