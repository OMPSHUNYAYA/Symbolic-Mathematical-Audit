SSM-Audit — Mini — Public Demo Bundle (v1.4)

Intro (brief)

This bundle ships a tiny, read-only lane calculator for finance KPIs. The value lane m is never modified; collapse parity holds: phi((m,a)) = m.
The alignment lane a is bounded and composable via rapidity (u := atanh(a), a := tanh(u)).
Streaming fuse is order-invariant by the U/W rule: U += w*atanh(a), W += w, a_out := tanh( U / max(W, eps_w) ).
Defaults: eps_a = 1e-6, eps_w = 1e-12. All formulas are plain ASCII.

What’s included (public research release)

Python CLI: ssm_audit_mini_calc.py (demo mode + CSV mode; native SDI supported).

Windows launcher: scripts\run_csv.cmd (CSV pipeline + native SDI).

Docs: GETTING_STARTED.txt, CALIBRATION.txt, Brief-SSM-Audit_ver1.4.pdf, SSM-Audit_ver1.4.pdf.

Plots folder (created at runtime).

Non-commercial evaluation and internal tooling only. Classical measurements remain unchanged; the lane is supplemental.

Repo layout (suggested)
SSM-Audit-Mini/
├─ ssm_audit_mini_calc.py
├─ README.md
├─ GETTING_STARTED.txt
├─ CALIBRATION.txt
├─ Brief-SSM-Audit_ver1.4.pdf
├─ SSM-Audit_ver1.4.pdf
├─ scripts/
│  └─ run_csv.cmd
└─ Plots/            # output images (created at runtime)

Tutorial — 2-minute walkthrough
1) Demo (no CSV)

Runs a small synthetic set so you can see lanes/bands and an SDI chart.

Windows

python ssm_audit_mini_calc.py --demo --demo_days 10 --demo_start 2025-10-01 ^
  --build_id demoW3 --alerts_csv alerts.csv --slope_7d -0.02 ^
  --plot_kpi Revenue_actual --plots_dir Plots ^
  --sdi --sdi_plot


macOS / Linux

python3 ssm_audit_mini_calc.py --demo --demo_days 10 --demo_start 2025-10-01 \
  --build_id demoW3 --alerts_csv alerts.csv --slope_7d -0.02 \
  --plot_kpi Revenue_actual --plots_dir Plots \
  --sdi --sdi_plot


Outputs: mini_calc_output.csv, optional alerts.csv, Plots\Revenue_actual_DEMO.png, Plots\SDI.png.

What to look for

phi((m,a)) = m holds: m stays the classical value.

a is inside (-1,+1) with band guides at 0.10/0.25/0.50/0.75.

SDI (portfolio) appears as rows with kpi=SDI and a separate Plots\SDI.png.

Plot naming

KPI images auto-name by mode: <kpi>_DEMO.png (demo) or <kpi>_CSV.png (CSV).

Optional switches: --plot_tag <suffix> to add a suffix, and --plot_keep_plain to also write <kpi>.png.

SDI plot writes SDI.png.

2) Use your own CSV (pilot default)

Windows (script)

scripts\run_csv.cmd pilot.csv out.csv CFO_Q4 Revenue_actual -0.02 +0.05 -0.05 Plots


Direct Python (equivalent)

python ssm_audit_mini_calc.py pilot.csv out.csv --build_id CFO_Q4 ^
  --plot_kpi Revenue_actual --alerts_csv alerts.csv ^
  --sdi --sdi_plot --plot_tag CSV --compute_a auto


Use --compute_a auto to build a end-to-end when mapper columns are present (see below).

Writes out.csv, optional alerts.csv, plots under Plots\ and SDI.png.

CSV schema (pilot-ready)

Output columns (produced by the tool)

time,kpi,m,a,band,band_hyst,knobs_hash,build_id,stamp


time: ISO YYYY-MM-DD

kpi: snake_case (e.g., Revenue_actual)

m: classical value (unchanged)

a: alignment lane in (-1,+1)

band, band_hyst: derived from a (labels: A++/A+/A0/A-/A--)

knobs_hash, build_id, stamp: reproducibility/metadata

Mapper extension (optional, for end-to-end a computation)
Add any of these columns to your input CSV (along with time,kpi):

coverage: mapper=coverage, needs q

Formula: a := 2*q - 1

agreement: mapper=agreement, needs m1,m2,b with b>0

Formula: a := tanh( 1 - |m1 - m2| / b )

residual: mapper=residual, needs actual,forecast,s with s>0 (optional k, default 1.0)

Formula: a := tanh( k*( 1 - |actual - forecast| / s ) )

If m is blank for residual, the tool uses m := actual.

CLI essentials (math & knobs)

Clamp: a := clamp(a, -1+eps_a, +1-eps_a)

Bands: A++: a>=0.75, A+: a>=0.50, A0: a>=0.25, A-: a>=0.10, else A--

Hysteresis: promote only if delta_a >= +promote; demote only if delta_a <= demote

Collapse parity: phi((m,a)) = m

Fusion (multi-child same (time,kpi)): a_out := tanh( (SUM w*atanh(a_i)) / max(SUM w, eps_w) )

Knobs fingerprint: knobs_hash := sha256( ascii(canonical_json(knobs)) )

Defaults: eps_a=1e-6, eps_w=1e-12, promote=+0.05, demote=-0.05, slope_7d=-0.02

Native SDI (portfolio index)

Formula: a_sdi := tanh( (SUM atanh(a_i)) / n )

Enable via --sdi (purges existing kpi="SDI" rows before appending).

Subset with --sdi_kpis "<csv>".

Artifacts: --sdi_csv <path> for SDI-only file; --sdi_plot writes Plots\SDI.png.

Quick verification (Windows)
find /c ",SDI," mini_calc_output.csv
dir Plots\SDI.png
python ssm_audit_mini_calc.py -h | findstr /i "sdi"

Notes for pilots

Fix knobs once for a pilot; share the knobs_hash with results.
Prefer stable windows; let the lane move, not the rule.
Start with the demo, then (optionally) mapper-based a on your CSV.

License

(c) The Authors of Shunyaya Framework and Shunyaya Symbolic Mathematics.
Released under CC BY-NC 4.0 (non-commercial, with attribution). Observation-only; non-commercial evaluation and internal tooling.
No warranty; use at your own risk. No redistribution of third-party raw data unless the licence explicitly permits it.