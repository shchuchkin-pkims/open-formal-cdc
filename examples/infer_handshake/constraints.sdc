# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
create_clock -name a -period 10 [get_ports clk]
set_input_delay 0 -clock a [get_ports req]
set_output_delay 0 -clock a [get_ports ack]
