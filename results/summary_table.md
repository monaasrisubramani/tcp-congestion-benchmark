# TCP Congestion Control Benchmark — Results

| Scenario | Algorithm | Avg Throughput Mbps | End Throughput Mbps | Total Bytes Mb | Retransmissions | Jfi |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | bbr | 9.5418 | 9.5420 | 71.5653 | 0 | — |
| baseline | cubic | 9.7686 | 9.7690 | 73.2692 | 118 | — |
| baseline | reno | 15.5120 | 10.0835 | 75.6285 | 526 | — |
| loss_1 | bbr | 9.5249 | 9.5245 | 71.4342 | 506 | — |
| loss_1 | cubic | 4.6277 | 4.4738 | 33.5544 | 227 | — |
| loss_1 | reno | 4.6310 | 4.6311 | 34.7341 | 241 | — |
| loss_5 | bbr | 9.3495 | 9.3496 | 70.1235 | 2639 | — |
| loss_5 | cubic | 1.9416 | 1.7475 | 13.1072 | 393 | — |
| loss_5 | reno | 1.5909 | 1.5379 | 11.5343 | 422 | — |
| high_rtt | bbr | 18.1420 | 9.9787 | 74.8421 | 513 | — |
| high_rtt | cubic | 13.2350 | 9.9262 | 74.4489 | 414 | — |
| high_rtt | reno | 13.2962 | 9.7515 | 73.1382 | 341 | — |
| small_buffer | bbr | 9.4370 | 9.4369 | 70.7789 | 2404 | — |
| small_buffer | cubic | 7.9515 | 7.9689 | 59.7688 | 146 | — |
| small_buffer | reno | 7.1475 | 7.1475 | 53.6084 | 158 | — |
| fairness | bbr | 5.3530 | 3.3903 | 25.4280 | 58 | 0.9851 |
| fairness | cubic | 6.8516 | 6.6233 | 49.6763 | 79 | 0.9851 |
| fairness | cubic+bbr | 5.0068 | — | — | 0 | 0.9056 |
