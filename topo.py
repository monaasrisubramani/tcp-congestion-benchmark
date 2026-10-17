#!/usr/bin/env python3
"""
topo.py — Single Bottleneck Mininet Topology
=============================================
Defines a dumbbell topology with two hosts (h1, h2) connected through
one switch (s1). The link between s1 and h2 acts as the bottleneck
and is shaped with TCLink to enforce configurable:
  - Bandwidth (Mbps)
  - One-way propagation delay (ms)
  - Packet loss rate (%)
  - Queue size (packets, controls bufferbloat)

Usage (standalone test):
    sudo python3 topo.py [--bw BW] [--delay DELAY] [--loss LOSS] [--queue QUEUE]

Usage (imported by run_tests.py):
    from topo import SingleBottleneckTopo
    topo = SingleBottleneckTopo(bw=10, delay='20ms', loss=0, max_queue_size=100)
"""

import argparse
import sys

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.node import OVSBridge


# ---------------------------------------------------------------------------
# Topology definition
# ---------------------------------------------------------------------------

class SingleBottleneckTopo(Topo):
    """
    Dumbbell topology with a single bottleneck link.

    Diagram:
        h1 ──[10G lossless]──► s1 ──[bottleneck: bw/delay/loss]──► h2

    The h1–s1 link is intentionally unconstrained (high bandwidth, no delay)
    so all interesting shaping occurs only on the s1–h2 segment.
    """

    def build(self, bw=10, delay='20ms', loss=0, max_queue_size=100):
        """
        Build the topology.

        Parameters
        ----------
        bw : float
            Bottleneck bandwidth in Mbps.
        delay : str
            One-way propagation delay string, e.g. '20ms'.
        loss : float
            Packet loss percentage [0–100].
        max_queue_size : int
            Maximum queue depth in packets (netem/tbf buffer).
        """
        # Validate parameters before building
        if not isinstance(bw, (int, float)) or bw <= 0:
            raise ValueError(f"bw must be a positive number, got {bw!r}")
        if loss < 0 or loss > 100:
            raise ValueError(f"loss must be in [0, 100], got {loss!r}")
        if max_queue_size < 1:
            raise ValueError(f"max_queue_size must be >= 1, got {max_queue_size!r}")

        # ── Hosts ──────────────────────────────────────────────────────────
        h1 = self.addHost('h1', ip='10.0.0.1/24')
        h2 = self.addHost('h2', ip='10.0.0.2/24')

        # ── Switch ─────────────────────────────────────────────────────────
        s1 = self.addSwitch('s1')

        # ── Links ──────────────────────────────────────────────────────────
        # Access link: h1 → s1 (unconstrained — not the bottleneck)
        self.addLink(
            h1, s1,
            cls=TCLink,
            bw=1000,           # 1 Gbps — effectively wire speed
            delay='0ms',
            loss=0,
            max_queue_size=1000
        )

        # Bottleneck link: s1 → h2 (all shaping applied here)
        # loss=0 is handled correctly by netem (no loss module loaded)
        self.addLink(
            s1, h2,
            cls=TCLink,
            bw=bw,
            delay=delay,
            loss=loss if loss > 0 else 0,   # netem ignores 0% loss cleanly
            max_queue_size=max_queue_size
        )


# ---------------------------------------------------------------------------
# Standalone smoke-test entry point
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description='Test SingleBottleneckTopo in isolation'
    )
    parser.add_argument('--bw',    type=float, default=10,
                        help='Bottleneck bandwidth in Mbps (default: 10)')
    parser.add_argument('--delay', type=str,   default='20ms',
                        help='One-way delay string (default: 20ms)')
    parser.add_argument('--loss',  type=float, default=0,
                        help='Loss percentage [0-100] (default: 0)')
    parser.add_argument('--queue', type=int,   default=100,
                        help='Max queue size in packets (default: 100)')
    return parser.parse_args()


def main():
    setLogLevel('info')
    args = parse_args()

    info(f"*** Building topology: bw={args.bw}Mbps, delay={args.delay}, "
         f"loss={args.loss}%, queue={args.queue} pkts\n")

    topo = SingleBottleneckTopo(
        bw=args.bw,
        delay=args.delay,
        loss=args.loss,
        max_queue_size=args.queue
    )

    net = Mininet(topo=topo, link=TCLink, switch=OVSBridge, controller=None)
    net.start()

    info("*** Running connectivity test (ping h1 → h2)\n")
    result = net.pingAll()

    info("*** Running bandwidth test (iperf h1 → h2, 10 s)\n")
    net.iperf()

    info(f"*** Ping loss: {result:.1f}%\n")
    net.stop()
    info("*** Topology test complete\n")


if __name__ == '__main__':
    main()
