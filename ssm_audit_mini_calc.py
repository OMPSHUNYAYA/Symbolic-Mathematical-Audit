#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSM-Audit Mini Calculator (CLI)

Canonicals (ASCII):
  phi((m,a)) = m
  Clamp: a := clamp(a, -1+eps_a, +1-eps_a)
  Band thresholds: A++: a>=0.75; A+: a>=0.50; A0: a>=0.25; A-: a>=0.10; else A--
  Hysteresis: promote if delta_a >= +promote; demote if delta_a <= demote
  Rapidity fuse: a_out := tanh( (SUM w*atanh(a)) / max(SUM w, eps_w) )
  SDI (portfolio): a_sdi := tanh( (SUM atanh(a_i)) / n )
"""

import argparse, csv, json, hashlib, math, os, sys
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Tuple

# ---------- helpers ----------
def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x

SCORE = {"A--":1,"A-":2,"A0":3,"A+":4,"A++":5}

def band_from_a(a: float) -> str:
    if a >= 0.75: return "A++"
    elif a >= 0.50: return "A+"
    elif a >= 0.25: return "A0"
    elif a >= 0.10: return "A-"
    else: return "A--"

def canonical_json(d: Dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"))

def sha256_ascii(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def knobs_hash_from(knobs: Dict) -> str:
    return sha256_ascii(canonical_json(knobs))

def parse_iso(ts: str) -> datetime:
    if not ts:
        # UTC, date-only
        return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    if "T" in ts:
        return datetime.fromisoformat(ts.replace("Z","+00:00")).replace(tzinfo=None)
    try:
        return datetime.strptime(ts, "%Y-%m-%d")
    except Exception:
        return datetime.fromisoformat(ts)

# ---------- compute-a mappers ----------
def compute_a_from_mapper(row: Dict, eps_a: float) -> Tuple[float, str]:
    mapper = (row.get("mapper","") or "").strip().lower()
    try:
        if mapper == "coverage":
            q = float(row.get("q",""))
            a = 2.0*q - 1.0
            return (clamp(a, -1+eps_a, 1-eps_a), "coverage")
        elif mapper == "agreement":
            m1 = float(row.get("m1","")); m2 = float(row.get("m2","")); b = float(row.get("b",""))
            if b <= 0: return (None, "agreement:b<=0")
            d = abs(m1 - m2)
            a = math.tanh(1.0 - d/b)
            return (clamp(a, -1+eps_a, 1-eps_a), "agreement")
        elif mapper == "residual":
            actual = float(row.get("actual","")); forecast = float(row.get("forecast","")); s = float(row.get("s",""))
            if s <= 0: return (None, "residual:s<=0")
            k = float(row.get("k","1.0") or 1.0)
            r = actual - forecast
            a = math.tanh(k*(1.0 - abs(r)/s))
            return (clamp(a, -1+eps_a, 1-eps_a), "residual")
        else:
            return (None, "no-mapper")
    except Exception as e:
        return (None, f"mapper-error:{mapper}:{e}")

# ---------- hysteresis ----------
def next_band(prev_band: str, a_prev: float, a_now: float, promote: float, demote: float) -> str:
    raw = band_from_a(a_now)
    d = a_now - (a_prev if a_prev is not None else a_now)
    if SCORE[raw] > SCORE.get(prev_band, SCORE[raw]) and d >= promote: return raw
    if SCORE[raw] < SCORE.get(prev_band, SCORE[raw]) and d <= demote:  return raw
    return prev_band or raw

# ---------- alerts ----------
def compute_alerts(rows_sorted: List[Dict], slope_7d: float=-0.02) -> List[Dict]:
    alerts, win = [], deque(maxlen=3)
    for r in rows_sorted:
        win.append(SCORE[r["band_hyst"]])
        if len(win) == 3:
            drops = (win[2] < win[1]) + (win[1] < win[0]) + (win[2] < win[0])
            if drops >= 2:
                alerts.append({"time": r["time"], "kpi": r["kpi"], "rule":"degrade_2of3"})
    if len(rows_sorted) >= 8:
        a0, a7 = rows_sorted[-8]["a"], rows_sorted[-1]["a"]
        slope = (a7 - a0) / 7.0
        if slope <= slope_7d:
            alerts.append({"time": rows_sorted[-1]["time"], "kpi": rows_sorted[-1]["kpi"],
                           "rule":"slope_7d", "value": round(slope,4)})
    return alerts

# ---------- plotting ----------
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAVE_PLOT = True
except Exception:
    HAVE_PLOT = False

def plot_kpi(rows_sorted: List[Dict], kpi: str, out_dir: str,
             color_m: str="tab:blue", color_a: str="tab:orange",
             tag: str=None, keep_plain: bool=False) -> str:
    if not HAVE_PLOT:
        print("[plot] matplotlib not available; skipping.")
        return None

    ts = [parse_iso(r["time"]) for r in rows_sorted]
    m  = [float(r["m"]) for r in rows_sorted]
    a  = [float(r["a"]) for r in rows_sorted]

    fig, ax1 = plt.subplots(figsize=(12,4))
    ax1.plot(ts, m, label=f"m (classical: {kpi})", linewidth=2, color=color_m, zorder=3)
    ax1.set_xlabel("time"); ax1.set_ylabel("m")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))

    ax2 = ax1.twinx()
    ax2.plot(ts, a, label="a (lane)", linewidth=2, linestyle="--", color=color_a, zorder=3)
    ax2.set_ylabel("a in (-1,+1)"); ax2.set_ylim(-1.0, 1.0)

    for th in [0.10, 0.25, 0.50, 0.75]:
        ax2.axhline(th, linestyle="--", linewidth=1, alpha=0.35, label="_nolegend_", zorder=1)

    lines = [l for l in (ax1.get_lines() + ax2.get_lines())
             if l.get_label() and not l.get_label().startswith("_")]
    labels = [l.get_label() for l in lines]
    leg = ax1.legend(lines, labels, loc="upper left",
                     frameon=True, framealpha=1.0, facecolor="white", edgecolor="0.8")
    leg.set_zorder(10)

    ax1.grid(True, linestyle="--", alpha=0.35, zorder=0)
    fig.tight_layout()

    os.makedirs(out_dir, exist_ok=True)
    base = f"{kpi}.png"
    tagged = f"{kpi}_{tag}.png" if tag else base
    path_tagged = os.path.join(out_dir, tagged)
    fig.savefig(path_tagged, dpi=150)
    if keep_plain and tagged != base:
        fig.savefig(os.path.join(out_dir, base), dpi=150)
    plt.close(fig)
    return path_tagged

# ---------- SDI helper (native) ----------
# a_sdi := tanh( (SUM atanh(a_i)) / n )
def append_sdi_rows_from_csv(output_csv_path: str, eps_a: float, sdi_kpis: str,
                             sdi_csv: str, do_plot: bool, plots_dir: str):
    def _clamp(a, eps):
        if a > 1.0 - eps: return 1.0 - eps
        if a < -1.0 + eps: return -1.0 + eps
        return a
    def _norm(name: str) -> str:
        return (name or "").strip().strip('"').strip("'")

    # read & purge existing SDI rows
    header, base_rows = None, []
    with open(output_csv_path, "r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        header = rdr.fieldnames or ["time","kpi","m","a","band","band_hyst","knobs_hash","build_id","stamp"]
        for r in rdr:
            if (r.get("kpi","") or "") == "SDI":
                continue
            base_rows.append(r)

    # robust filter: strip quotes/spaces around tokens
    filt = set(_norm(s) for s in (sdi_kpis or "").split(",") if _norm(s))

    # collect a-values per day after optional KPI filter
    per_day = defaultdict(list)
    for r in base_rows:
        kpi = _norm(r.get("kpi",""))
        if filt and kpi not in filt:
            continue
        t = r.get("time","")
        if not t:
            continue
        try:
            a_val = float(r.get("a",""))
        except Exception:
            continue
        per_day[t].append(a_val)

    # compute SDI rows
    sdi_rows = []
    for t in sorted(per_day.keys()):
        a_list = per_day[t]
        if not a_list:
            continue
        u_sum = 0.0
        for ai in a_list:
            u_sum += math.atanh(_clamp(ai, eps_a))
        a_sdi = math.tanh(u_sum / max(len(a_list), 1))
        sdi_rows.append({
            "time": t, "kpi": "SDI", "m": "0.0", "a": f"{a_sdi:.10f}",
            "band": band_from_a(a_sdi), "band_hyst": band_from_a(a_sdi),
            "knobs_hash": "", "build_id": "", "stamp": ""
        })

    # write purged + SDI
    with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in base_rows:
            w.writerow(r)
        for r in sdi_rows:
            w.writerow(r)

    # optional SDI-only CSV
    if sdi_csv:
        with open(sdi_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["time","kpi","m","a","band","band_hyst","knobs_hash","build_id","stamp"])
            w.writeheader()
            for r in sdi_rows:
                w.writerow(r)

    # optional SDI plot
    if do_plot and HAVE_PLOT and sdi_rows:
        try:
            xs = [r["time"] for r in sdi_rows]
            ys = [float(r["a"]) for r in sdi_rows]
            fig, ax = plt.subplots(figsize=(10,3.5))
            ax.plot(xs, ys, marker="o")
            ax.set_title("SDI (tanh-mean of lanes)")
            ax.set_xlabel("time"); ax.set_ylabel("a_sdi")
            ax.grid(True, linestyle="--", alpha=0.35)
            fig.tight_layout()
            os.makedirs(plots_dir, exist_ok=True)
            out_path = os.path.join(plots_dir, "SDI.png")
            fig.savefig(out_path, dpi=150)
            plt.close(fig)
            print(f"[OK] SDI plot: {out_path}")
        except Exception as e:
            print(f"[WARN] SDI plot skipped: {e}")

    print(f"[OK] SDI appended: {len(sdi_rows)} rows")

# ---------- DEMO generator ----------
def demo_rows(start_iso: str, days: int, eps_a: float) -> List[Dict]:
    start = parse_iso(start_iso) if start_iso else \
            datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    out = []
    k, s  = 1.2, 50_000.0
    b     = 0.005
    q0    = 0.88

    for i in range(days):
        t = (start + timedelta(days=i)).strftime("%Y-%m-%d")

        # Revenue_actual (smooth ramp; one mid-curve miss)
        forecast = 1_000_000 + 30_000*i
        actual   = forecast + (20_000 if i==6 else (-10_000 if i<3 else 5_000))
        r = actual - forecast
        a_res = math.tanh(k*(1 - abs(r)/s))
        out.append({"time":t,"kpi":"Revenue_actual","m":float(actual),
                    "a": clamp(a_res, -1+eps_a, 1-eps_a)})

        # AR_collected_issued (coverage easing then recovering)
        q = q0 + 0.01*i if i<3 else q0 + 0.03 - 0.008*(i-3)
        q = max(0.0, min(1.0, q))
        a_cov = 2*q - 1
        out.append({"time":t,"kpi":"AR_collected_issued","m":0.96,
                    "a": clamp(a_cov, -1+eps_a, 1-eps_a)})

        # Refunds_agreement (drift then re-align)
        m_platform = 0.021 + 0.0002*i
        m_bank     = 0.020 + (0.0004*i if i<5 else 0.00005*i)
        d = abs(m_platform - m_bank)
        a_agree = math.tanh(1 - d/b)
        out.append({"time":t,"kpi":"Refunds_agreement","m":m_platform,
                    "a": clamp(a_agree, -1+eps_a, 1-eps_a)})
    return out

# ---------- main ----------
def main():
    p = argparse.ArgumentParser(description="SSM-Audit Mini Calculator (values unchanged: phi((m,a)) = m)")

    # positional (optional in demo mode)
    p.add_argument("input_csv", nargs="?", default=None)
    p.add_argument("output_csv", nargs="?", default=None)

    # knobs
    p.add_argument("--build_id", default="demo")
    p.add_argument("--eps_a", type=float, default=1e-6)
    p.add_argument("--eps_w", type=float, default=1e-12)
    p.add_argument("--gamma", type=float, default=1.0)
    p.add_argument("--promote", type=float, default=0.05)
    p.add_argument("--demote",  type=float, default=-0.05)

    # alerts / plotting
    p.add_argument("--alerts_csv")
    p.add_argument("--slope_7d", type=float, default=-0.02)
    p.add_argument("--plot_kpi")
    p.add_argument("--plots_dir", default="Plots")
    p.add_argument("--color_m", default="tab:blue")
    p.add_argument("--color_a", default="tab:orange")
    p.add_argument("--plot_tag", default="", help="suffix for plot filename; defaults to DEMO/CSV by mode")
    p.add_argument("--plot_keep_plain", action="store_true", help="also write plain <kpi>.png")

    # SDI (portfolio roll-up)
    p.add_argument("--sdi", action="store_true", help="compute portfolio SDI across KPIs per day")
    p.add_argument("--sdi_kpis", default="", help="comma-separated KPI filter for SDI (default: all KPIs)")
    p.add_argument("--sdi_csv", default="", help="optional SDI-only CSV output")
    p.add_argument("--sdi_plot", action="store_true", help="also plot SDI")

    # demo controls
    p.add_argument("--demo", action="store_true", help="run built-in sample without CSV")
    p.add_argument("--demo_days", type=int, default=10)
    p.add_argument("--demo_start", default="", help="YYYY-MM-DD (optional)")

    # CSV mapper control
    p.add_argument("--compute_a", default="auto", choices=["auto","on","off"],
                   help="build 'a' from mapper columns (coverage/agreement/residual)")

    args = p.parse_args()

    # knobs hash (deterministic fingerprint)
    knobs = {
        "eps_a": args.eps_a, "eps_w": args.eps_w, "gamma": args.gamma,
        "division_policy": "strict",
        "bands": {"A++":0.75, "A+":0.50, "A0":0.25, "A-":0.10, "A--":-float("inf")},
        "hysteresis": {"promote": args.promote, "demote": args.demote},
        "mappings": "mini_calc"
    }
    khash = knobs_hash_from(knobs)

    # --- Build rows: DEMO or CSV ---
    rows: List[Dict] = []

    if args.demo:
        rows = demo_rows(args.demo_start, args.demo_days, args.eps_a)
        if not args.output_csv:
            args.output_csv = "mini_calc_output.csv"
    else:
        if not args.input_csv or not args.output_csv:
            print("[ERR] Provide input_csv and output_csv, or use --demo")
            sys.exit(2)
        with open(args.input_csv, newline="", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            header = [h.strip() for h in (rdr.fieldnames or [])]
            have_mapper = "mapper" in [h.lower() for h in header]
            compute_flag = (args.compute_a == "on") or (args.compute_a == "auto" and have_mapper)
            for r in rdr:
                r = {k: (r.get(k,"") or "").strip() for k in r.keys()}
                # fill a if needed
                a_value = r.get("a","")
                a_float = None
                if compute_flag and (a_value == "" or a_value.lower() == "na"):
                    a_float, _reason = compute_a_from_mapper(r, args.eps_a)
                else:
                    try:
                        a_float = float(a_value)
                    except Exception:
                        a_float = 0.0
                r["a"] = clamp(a_float if a_float is not None else 0.0, -1+args.eps_a, 1-args.eps_a)

                # default m if residual mapper present
                if r.get("m","") == "" and (r.get("mapper","") or "").lower() == "residual":
                    try:
                        r["m"] = float(r.get("actual","0") or 0.0)
                    except Exception:
                        r["m"] = 0.0
                rows.append(r)

    # --- Group by (time,kpi); fuse a if multiple rows share the key ---
    grouped: Dict[Tuple[str,str], List[Dict]] = defaultdict(list)
    for r in rows:
        key = (r.get("time",""), r.get("kpi",""))
        grouped[key].append(r)

    fused_rows: List[Dict] = []
    for (t,k), lst in grouped.items():
        lst_sorted = sorted(lst, key=lambda z: canonical_json(z))
        # classical m: prefer explicit m if present; else 0.0
        m_num = None
        for mv in [z.get("m","") for z in lst_sorted]:
            try:
                m_num = float(mv); break
            except Exception:
                continue
        if m_num is None: m_num = 0.0

        # fuse a in rapidity space with optional weights
        num, den = 0.0, 0.0
        for z in lst_sorted:
            a_i = float(z.get("a",0) or 0)
            w_i = float(z.get("weight",1) or 1)
            a_i = clamp(a_i, -1+args.eps_a, 1-args.eps_a)
            num += w_i * math.atanh(a_i)
            den += w_i
        a_out = math.tanh(num / max(den, args.eps_w))

        fused_rows.append({
            "time": t or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "kpi": k, "m": m_num, "a": a_out
        })

    # --- Per-KPI time sort, hysteresis, hash/build tags ---
    by_kpi: Dict[str, List[Dict]] = defaultdict(list)
    for r in fused_rows:
        r["band"] = band_from_a(r["a"])
        by_kpi[r["kpi"]].append(r)

    latest = {}
    for kpi, lst in by_kpi.items():
        lst.sort(key=lambda z: parse_iso(z["time"]))
        prev_band, prev_a = None, None
        for r in lst:
            r["band_hyst"] = next_band(prev_band, prev_a, r["a"], args.promote, args.demote)
            r["knobs_hash"] = khash
            r["build_id"] = args.build_id
            prev_band, prev_a = r["band_hyst"], r["a"]
        latest[kpi] = lst[-1]

    # --- Write output CSV ---
    fieldnames = ["time","kpi","m","a","band","band_hyst","knobs_hash","build_id","stamp"]
    with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames); w.writeheader()
        for kpi in sorted(by_kpi.keys()):
            for r in by_kpi[kpi]:
                out = {k: r.get(k,"") for k in fieldnames}
                out["a"] = f"{float(out['a']):.4f}"
                w.writerow(out)

    # --- Alerts (optional) ---
    if args.alerts_csv:
        all_alerts = []
        for kpi, lst in by_kpi.items():
            all_alerts.extend(compute_alerts(lst, args.slope_7d))
        with open(args.alerts_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["time","kpi","rule","value"])
            w.writeheader()
            for ar in all_alerts: w.writerow(ar)
        print(f"Alerts written to: {args.alerts_csv}")

    # --- Plot KPI (optional) ---
    if args.plot_kpi and args.plot_kpi in by_kpi:
        tag = args.plot_tag or ("DEMO" if args.demo else "CSV")
        path = plot_kpi(by_kpi[args.plot_kpi], args.plot_kpi, args.plots_dir,
                        color_m=args.color_m, color_a=args.color_a,
                        tag=tag, keep_plain=args.plot_keep_plain)
        if path: print(f"Plot saved: {path}")

    # --- SDI (native; purge+append) ---
    if args.sdi:
        append_sdi_rows_from_csv(
            output_csv_path=args.output_csv,
            eps_a=args.eps_a,
            sdi_kpis=args.sdi_kpis,
            sdi_csv=args.sdi_csv,
            do_plot=args.sdi_plot,
            plots_dir=args.plots_dir
        )

    # --- Console summary ---
    print("=== Mini Calculator Summary (latest by KPI) ===")
    for kpi, r in latest.items():
        print(f"{kpi}: m={r['m']}, a={float(r['a']):.4f}, band={r['band']}, band_hyst={r['band_hyst']}")
    if args.sdi:
        try:
            last_sdi = None
            with open(args.output_csv, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("kpi") == "SDI":
                        last_sdi = row
            if last_sdi:
                print(f"\nSDI: m={last_sdi.get('m','0.0')}, a={float(last_sdi['a']):.4f}, "
                      f"band={last_sdi.get('band')}, band_hyst={last_sdi.get('band_hyst')}")
        except Exception:
            pass

    print(f"\nOutput written to: {args.output_csv}")
    print(f"knobs_hash: {knobs_hash_from(knobs)}")

if __name__ == "__main__":
    main()
