"""Command-line interface for PA-LCP-Tool.

Commands
--------
* ``palcp build``    -- build the Excel workbook from assumptions + items.
* ``palcp validate`` -- run the Daubert pre-flight checks and print findings.
* ``palcp init``     -- copy blank input templates into a directory.
* ``palcp sample``   -- write the bundled sample inputs and build a demo workbook.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import build_plan, load_assumptions, load_items
from .economics import project
from .pricing import apply_pricing, load_pricing
from .validate import validate_plan
from .workbook import save_workbook

try:  # Python 3.9+: importlib.resources.files
    from importlib.resources import files as _resource_files
except ImportError:  # pragma: no cover
    _resource_files = None


def _data_path(name: str) -> Path:
    """Resolve a bundled data file shipped under ``palcp/data``."""
    if _resource_files is not None:
        return Path(str(_resource_files("palcp") / "data" / name))
    return Path(__file__).parent / "data" / name  # pragma: no cover


def _print_validation(report) -> None:
    print(f"Validation: {report.summary()}")
    for f in report.sorted():
        print(f"  {f}")


def _load_pricing_arg(path_args: list[str] | None):
    if not path_args:
        return None
    from .pricing import PRESETS, PricingTable

    table = PricingTable()
    for spec in path_args:
        # Allow "path" or "path:preset". A trailing ":token" is only treated as
        # a preset when token is a known preset key, so Windows drive-letter
        # paths (e.g. C:/fees.xlsx) and URL-like paths are not mis-split.
        path, preset = spec, None
        if ":" in spec:
            candidate_path, candidate_preset = spec.rsplit(":", 1)
            if candidate_preset in PRESETS:
                path, preset = candidate_path, candidate_preset
        table.extend(load_pricing(path, preset=preset).records)
    return table


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_build(args: argparse.Namespace) -> int:
    config = load_assumptions(args.assumptions)
    items = load_items(args.items, sheet=args.items_sheet)
    plan = build_plan(config, items)

    pricing = _load_pricing_arg(args.pricing)
    if pricing is not None:
        resolutions = apply_pricing(plan.items, pricing)
        unresolved = [r for r in resolutions if r.method == "unresolved"]
        if unresolved:
            print(f"Note: {len(unresolved)} item(s) had no price match; "
                  f"they keep any directly-entered unit_cost.", file=sys.stderr)

    report = validate_plan(plan)
    _print_validation(report)
    if report.errors and not args.force:
        print("\nERRORS present. Fix them or re-run with --force to build anyway.",
              file=sys.stderr)
        return 2

    result = project(plan)
    generated_on = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_workbook(result, report, args.out, version=__version__,
                  generated_on=generated_on)
    print(f"\nWrote {args.out}")
    print(f"  Lifetime current (undiscounted): ${result.grand_total_current:,.2f}")
    print(f"  Lifetime future (nominal):       ${result.grand_total_nominal:,.2f}")
    print(f"  Lifetime PRESENT VALUE:          ${result.grand_total_present_value:,.2f}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    config = load_assumptions(args.assumptions)
    items = load_items(args.items, sheet=args.items_sheet)
    plan = build_plan(config, items)
    if args.pricing:
        apply_pricing(plan.items, _load_pricing_arg(args.pricing))
    report = validate_plan(plan)
    _print_validation(report)
    return 0 if report.ok else 2


def cmd_init(args: argparse.Namespace) -> int:
    out = Path(args.dir)
    out.mkdir(parents=True, exist_ok=True)
    templates = [
        ("templates/assumptions.template.yaml", "assumptions.yaml"),
        ("templates/plan_items.template.csv", "plan_items.csv"),
        ("templates/pricing.template.csv", "pricing.csv"),
        ("templates/life_table.template.csv", "life_table.csv"),
    ]
    for src, dst in templates:
        target = out / dst
        target.write_text(_data_path(src).read_text(encoding="utf-8"),
                          encoding="utf-8")
        print(f"  wrote {target}")
    print(f"\nTemplates written to {out}/. Edit them, then run:\n"
          f"  palcp build --assumptions {out}/assumptions.yaml "
          f"--items {out}/plan_items.csv --out report.xlsx")
    return 0


def cmd_sample(args: argparse.Namespace) -> int:
    config = load_assumptions(_data_path("sample_assumptions.yaml"))
    items = load_items(_data_path("sample_plan_items.csv"))
    plan = build_plan(config, items)
    pricing = load_pricing(_data_path("sample_pricing.csv"))
    apply_pricing(plan.items, pricing)
    report = validate_plan(plan)
    _print_validation(report)
    result = project(plan)
    generated_on = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_workbook(result, report, args.out, version=__version__,
                  generated_on=generated_on)
    print(f"\nWrote sample workbook to {args.out}")
    print(f"  Lifetime PRESENT VALUE: ${result.grand_total_present_value:,.2f}")
    return 0


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="palcp",
        description="Life Care Plan cost-projection engine and Excel report "
                    "generator (Daubert / FRE 702 oriented).",
    )
    p.add_argument("--version", action="version", version=f"palcp {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="Build the Excel workbook.")
    b.add_argument("--assumptions", required=True, help="Path to assumptions YAML.")
    b.add_argument("--items", required=True, help="Path to plan-items CSV/XLSX.")
    b.add_argument("--items-sheet", default=None, help="Worksheet name if XLSX.")
    b.add_argument("--pricing", nargs="*", default=None,
                   help="Optional pricing file(s); use path or path:preset.")
    b.add_argument("--out", default="life_care_plan.xlsx", help="Output .xlsx path.")
    b.add_argument("--force", action="store_true",
                   help="Build even if validation reports errors.")
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("validate", help="Run Daubert pre-flight validation only.")
    v.add_argument("--assumptions", required=True)
    v.add_argument("--items", required=True)
    v.add_argument("--items-sheet", default=None)
    v.add_argument("--pricing", nargs="*", default=None)
    v.set_defaults(func=cmd_validate)

    i = sub.add_parser("init", help="Write blank input templates to a directory.")
    i.add_argument("--dir", default="lcp_inputs", help="Target directory.")
    i.set_defaults(func=cmd_init)

    s = sub.add_parser("sample", help="Build a demo workbook from bundled samples.")
    s.add_argument("--out", default="sample_life_care_plan.xlsx")
    s.set_defaults(func=cmd_sample)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
