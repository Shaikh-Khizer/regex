#!/usr/bin/env python3

"""
regex_scanner.py — Advanced Regex Pattern Scanner
Features:
  - Confidence scoring (YAML-defined + entropy + length + regex specificity)
  - Priority-ranked output (CRITICAL → HIGH → MEDIUM → LOW)
  - Terminal (colored), JSON, and CSV output
  - Token deduplication (skip same token twice in a file scan)
  - Encoding-safe file reading
  - Clean separation of scan logic and display
  - Silent invalid-regex handling (PCRE inline-flag fallback then skip)
  - All rules loaded per-file — no cross-file regex deduplication
"""

import os
import re
try:
    import regex  # full PCRE support (pip install regex)
    _re = regex
except ImportError:
    _re = re      # fallback to stdlib re if regex not installed
import sys
import csv
import math
import json
import glob
import logging
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

# =============================================================
# Logging
# =============================================================
logging.basicConfig(format="%(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_RULES_DIR = "/opt/regex/list"

# Confidence level ordering (higher index = higher priority)
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
CONFIDENCE_COLORS = {
    "critical": "\033[35m",  # Magenta
    "high":     "\033[31m",  # Red
    "medium":   "\033[33m",  # Yellow
    "low":      "\033[36m",  # Cyan
}

# =============================================================
# Color System
# =============================================================
class Color:
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    CYAN    = "\033[36m"
    MAGENTA = "\033[35m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RESET   = "\033[0m"

    _enabled = sys.stdout.isatty()

    @classmethod
    def disable(cls):
        cls._enabled = False

    @classmethod
    def wrap(cls, text: str, color: str) -> str:
        if not cls._enabled:
            return text
        return f"{color}{text}{cls.RESET}"

    @classmethod
    def confidence(cls, level: str) -> str:
        color = CONFIDENCE_COLORS.get(level, cls.CYAN)
        return cls.wrap(level.upper(), color)


# =============================================================
# Data Models
# =============================================================
@dataclass
class Rule:
    name: str
    regex: re.Pattern
    pattern_str: str                  # raw regex string (for specificity scoring)
    confidence: str = "low"          # from YAML: low / medium / high / critical
    source_file: str = ""


@dataclass
class MatchResult:
    rule_name: str
    confidence: str                   # yaml-defined level
    entropy_score: float              # Shannon entropy of token
    length_score: int                 # token length
    composite_score: float            # final priority score
    source_file: str


@dataclass
class TokenReport:
    token: str
    matches: list[MatchResult] = field(default_factory=list)

    @property
    def top_confidence(self) -> str:
        if not self.matches:
            return "none"
        return max(self.matches, key=lambda m: m.composite_score).confidence

    @property
    def total_score(self) -> float:
        return sum(m.composite_score for m in self.matches)


# =============================================================
# Entropy & Scoring
# =============================================================
def shannon_entropy(text: str) -> float:
    """Calculate Shannon entropy of a string (0.0 – 8.0 scale)."""
    if not text:
        return 0.0
    freq = defaultdict(int)
    for ch in text:
        freq[ch] += 1
    length = len(text)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in freq.values()
    )


def regex_specificity(pattern: str) -> float:
    """
    Estimate how specific/precise a regex is.
    More specific patterns (longer, more anchors, more char classes) score higher.
    This differentiates rules that share the same YAML confidence level.

    Scoring:
      - Each literal character   : +0.05
      - Each character class []  : +0.5
      - Each quantifier {n,m}    : +1.0
      - Start/end anchors ^ $    : +2.0 each
      - Each named group (?P<>)  : +1.5
      - Length of pattern        : +0.02 per char (capped at 100)
    """
    score = 0.0
    score += len(re.findall(r'\[[^\]]+\]', pattern)) * 0.5
    score += len(re.findall(r'\{\d+(?:,\d*)?\}', pattern)) * 1.0
    score += pattern.count('^') * 2.0
    score += pattern.count('$') * 2.0
    score += len(re.findall(r'\(\?P<', pattern)) * 1.5
    score += min(len(pattern), 100) * 0.02
    return round(score, 2)


def compute_composite_score(token: str, yaml_confidence: str, pattern_str: str = "") -> float:
    """
    Composite score formula:
      - YAML confidence base   : low=1, medium=2, high=3, critical=4  (×10)
      - Shannon entropy bonus  : 0.0–8.0 scale                         (×5)
      - Length bonus           : capped at 64 chars                    (×0.1)
      - Regex specificity      : how precise the matching rule is       (×1)

    Higher score = more likely a real secret / more specific match.
    """
    base        = (CONFIDENCE_ORDER.get(yaml_confidence, 0) + 1) * 10
    entropy     = shannon_entropy(token) * 5
    length      = min(len(token), 64) * 0.1
    specificity = regex_specificity(pattern_str) if pattern_str else 0.0
    return round(base + entropy + length + specificity, 2)


# =============================================================
# Rule Loader
# =============================================================
# Patterns that strip unsupported PCRE inline flags Python can't handle.
# Python's re does not support (?-i), (?-s) etc. inline flag toggling.
_INLINE_FLAG_RE = _re.compile(r'\(\?[-a-zA-Z]+\)')

def _try_compile(regex_str: str) -> re.Pattern | None:
    """
    Compile using the `regex` library (full PCRE inline flag support).
    Falls back to stdlib `re` if `regex` is not installed.
    Returns None silently on failure — no error spam.
    """
    try:
        return _re.compile(regex_str, _re.IGNORECASE)
    except Exception:
        pass

    # If regex lib is available but still failed, nothing more to try.
    # If using stdlib re, attempt stripping unsupported inline flags and retry.
    if _re is re:
        cleaned = _INLINE_FLAG_RE.sub('', regex_str).strip()
        if cleaned and cleaned != regex_str:
            try:
                return re.compile(cleaned, re.IGNORECASE)
            except re.error:
                pass

    return None  # silently skip


def load_rules(rules_dir: str) -> tuple[list[Rule], int]:
    rules: list[Rule] = []
    path = Path(rules_dir)

    if not path.exists():
        logger.error(Color.wrap(f"[!] Rules directory not found: {rules_dir}", Color.RED))
        return rules, 0

    files = list(path.glob("*.yaml")) + list(path.glob("*.yml"))

    if not files:
        logger.warning(Color.wrap(f"[!] No YAML files found in {rules_dir}", Color.YELLOW))
        return rules, 0

    # Dedup only within the SAME file (same name+regex in same file = skip)
    # Cross-file duplicates are KEPT — same rule in different files is intentional
    for file in files:
        try:
            import yaml
            with open(file, "r", encoding="utf-8", errors="replace") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            logger.warning(Color.wrap(f"[!] Failed to load {file.name}: {e}", Color.YELLOW))
            continue

        if not data or not isinstance(data.get("patterns"), list):
            continue

        seen_in_file: set[str] = set()  # dedup within this file only

        for item in data["patterns"]:
            pattern_obj = item.get("pattern", {})
            if not isinstance(pattern_obj, dict):
                continue

            name       = pattern_obj.get("name", "unknown").strip()
            regex_str  = pattern_obj.get("regex", "").strip()
            confidence = pattern_obj.get("confidence", "low").strip().lower()

            if not regex_str:
                continue

            # Skip exact duplicates within the same file
            dedup_key = f"{name}::{regex_str}"
            if dedup_key in seen_in_file:
                continue
            seen_in_file.add(dedup_key)

            if confidence not in CONFIDENCE_ORDER:
                confidence = "low"

            compiled = _try_compile(regex_str)
            if compiled is None:
                continue  # silently skip broken patterns

            rules.append(Rule(
                name        = name,
                regex       = compiled,
                pattern_str = regex_str,
                confidence  = confidence,
                source_file = file.name,
            ))

    return rules, len(rules)


# =============================================================
# Core Scanner  (pure logic — no printing)
# =============================================================
def scan_token(token: str, rules: list[Rule]) -> TokenReport:
    report = TokenReport(token=token)

    for rule in rules:
        if rule.regex.search(token):
            score = compute_composite_score(token, rule.confidence, rule.pattern_str)
            report.matches.append(MatchResult(
                rule_name       = rule.name,
                confidence      = rule.confidence,
                entropy_score   = round(shannon_entropy(token), 3),
                length_score    = len(token),
                composite_score = score,
                source_file     = rule.source_file,
            ))

    # Deduplicate by rule_name — keep highest scoring match, merge source files
    deduped: dict[str, MatchResult] = {}
    sources: dict[str, list[str]] = {}

    for match in report.matches:
        key = match.rule_name.lower().strip()
        if key not in deduped or match.composite_score > deduped[key].composite_score:
            deduped[key] = match
            sources[key] = [match.source_file]
        elif match.source_file not in sources[key]:
            sources[key].append(match.source_file)

    # Write merged source files back into each match
    for key, match in deduped.items():
        match.source_file = ", ".join(sorted(sources[key]))

    # Sort matches: highest composite score first
    report.matches = sorted(deduped.values(), key=lambda m: m.composite_score, reverse=True)
    return report


def scan_tokens(tokens: list[str], rules: list[Rule], deduplicate: bool = True) -> list[TokenReport]:
    reports: list[TokenReport] = []
    seen: set[str] = set()

    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if deduplicate:
            if token in seen:
                continue
            seen.add(token)
        reports.append(scan_token(token, rules))

    return reports


def tokens_from_file(path: str) -> list[str]:
    file = Path(path)
    if not file.exists():
        logger.error(Color.wrap(f"[!] Input file not found: {path}", Color.RED))
        return []
    with open(file, "r", encoding="utf-8", errors="replace") as f:
        return [line.strip() for line in f if line.strip()]


# =============================================================
# Terminal Output
# =============================================================
DIVIDER = "=" * 65

def print_token_report(report: TokenReport, index: int):
    print(f"\n{DIVIDER}")
    print(
        Color.wrap(f"  TOKEN #{index}", Color.BOLD) + "  " +
        Color.wrap(report.token, Color.YELLOW)
    )
    print(f"  Entropy : {Color.wrap(str(round(shannon_entropy(report.token), 3)), Color.CYAN)}"
          f"  |  Length : {Color.wrap(str(len(report.token)), Color.CYAN)}")

    if not report.matches:
        print(Color.wrap("  [-] No matches found", Color.RED))
        return

    print(Color.wrap(f"  [+] {len(report.matches)} match(es) found — "
                     f"top score: {report.matches[0].composite_score}", Color.GREEN))

    prev_conf = None
    for match in report.matches:
        # Print confidence group header when it changes
        if match.confidence != prev_conf:
            print(f"\n  {Color.wrap('── ' + match.confidence.upper(), CONFIDENCE_COLORS.get(match.confidence, Color.CYAN))}")
            prev_conf = match.confidence

        print(
            f"    • {Color.wrap(match.rule_name, Color.BOLD)}"
            f"  [{Color.wrap(match.source_file, Color.DIM)}]"
            f"  score={Color.wrap(str(match.composite_score), Color.GREEN)}"
        )


def print_summary(reports: list[TokenReport]):
    total_tokens  = len(reports)
    matched       = sum(1 for r in reports if r.matches)
    total_matches = sum(len(r.matches) for r in reports)
    clean         = total_tokens - matched

    print(f"\n{DIVIDER}")
    print(Color.wrap("  SCAN SUMMARY", Color.BOLD))
    print(f"  Tokens scanned : {Color.wrap(str(total_tokens), Color.CYAN)}")
    print(f"  Matched        : {Color.wrap(str(matched), Color.RED)}")
    print(f"  Clean          : {Color.wrap(str(clean), Color.GREEN)}")
    print(f"  Total matches  : {Color.wrap(str(total_matches), Color.YELLOW)}")

    if matched:
        print(f"\n  {Color.wrap('Top Hits (by score):', Color.BOLD)}")
        all_matches = [
            (r.token, m)
            for r in reports
            for m in r.matches
        ]
        all_matches.sort(key=lambda x: x[1].composite_score, reverse=True)
        for token, match in all_matches[:5]:
            short_token = token[:40] + "…" if len(token) > 40 else token
            print(
                f"    {Color.wrap(str(match.composite_score), Color.YELLOW):>8}  "
                f"{Color.wrap(match.rule_name, Color.BOLD):35}  "
                f"{Color.wrap(short_token, Color.CYAN)}"
            )
    print(DIVIDER)


# =============================================================
# JSON Output
# =============================================================
def reports_to_json(reports: list[TokenReport], output_path: str):
    data = {
        "scan_time": datetime.utcnow().isoformat() + "Z",
        "total_tokens": len(reports),
        "results": []
    }
    for report in reports:
        data["results"].append({
            "token": report.token,
            "matched": bool(report.matches),
            "top_confidence": report.top_confidence,
            "total_score": report.total_score,
            "entropy": round(shannon_entropy(report.token), 3),
            "matches": [
                {
                    "rule": m.rule_name,
                    "confidence": m.confidence,
                    "composite_score": m.composite_score,
                    "entropy": m.entropy_score,
                    "source_file": m.source_file,
                }
                for m in report.matches
            ]
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info(Color.wrap(f"[+] JSON report saved → {output_path}", Color.GREEN))


# =============================================================
# CSV Output
# =============================================================
def reports_to_csv(reports: list[TokenReport], output_path: str):
    headers = [
        "token", "rule_name", "confidence",
        "composite_score", "entropy", "token_length", "source_file"
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for report in reports:
            if not report.matches:
                writer.writerow({
                    "token": report.token,
                    "rule_name": "",
                    "confidence": "none",
                    "composite_score": 0,
                    "entropy": round(shannon_entropy(report.token), 3),
                    "token_length": len(report.token),
                    "source_file": "",
                })
            else:
                for match in report.matches:
                    writer.writerow({
                        "token": report.token,
                        "rule_name": match.rule_name,
                        "confidence": match.confidence,
                        "composite_score": match.composite_score,
                        "entropy": match.entropy_score,
                        "token_length": match.length_score,
                        "source_file": match.source_file,
                    })

    logger.info(Color.wrap(f"[+] CSV report saved → {output_path}", Color.GREEN))


# =============================================================
# CLI
# =============================================================
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Regex Pattern Scanner — Priority & Entropy Aware",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("-t", "--token",
        help="Scan a single token")
    parser.add_argument("-f", "--file",
        help="Scan tokens from a file (one per line)")
    parser.add_argument("-d", "--directory",
        default=DEFAULT_RULES_DIR,
        help=f"Rules directory (default: {DEFAULT_RULES_DIR})")
    parser.add_argument("--json",
        metavar="FILE",
        help="Save results as JSON to FILE")
    parser.add_argument("--csv",
        metavar="FILE",
        help="Save results as CSV to FILE")
    parser.add_argument("--min-score",
        type=float,
        default=0.0,
        metavar="N",
        help="Only show matches with composite score >= N (default: 0)")
    parser.add_argument("--no-color",
        action="store_true",
        help="Disable colored terminal output")
    parser.add_argument("--no-dedup",
        action="store_true",
        help="Disable deduplication (scan duplicate tokens too)")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.no_color:
        Color.disable()

    if not args.token and not args.file:
        parser.print_help()
        sys.exit(1)

    # ── Load rules ──────────────────────────────────────────
    logger.info(Color.wrap("[*] Loading rules...", Color.CYAN))
    rules, total_rules = load_rules(args.directory)

    if total_rules == 0:
        logger.error(Color.wrap("[!] No valid rules loaded. Exiting.", Color.RED))
        sys.exit(1)

    logger.info(Color.wrap(f"[+] Loaded {total_rules} unique regex patterns\n", Color.GREEN))

    # ── Build token list ────────────────────────────────────
    tokens: list[str] = []
    if args.token:
        tokens = [args.token]
    elif args.file:
        tokens = tokens_from_file(args.file)
        if not tokens:
            logger.error(Color.wrap("[!] No tokens found in file.", Color.RED))
            sys.exit(1)

    # ── Scan ────────────────────────────────────────────────
    deduplicate = not args.no_dedup
    reports = scan_tokens(tokens, rules, deduplicate=deduplicate)

    # Apply min-score filter to matches (not to reports themselves)
    if args.min_score > 0:
        for report in reports:
            report.matches = [m for m in report.matches if m.composite_score >= args.min_score]

    # ── Terminal output ─────────────────────────────────────
    for i, report in enumerate(reports, start=1):
        print_token_report(report, i)

    print_summary(reports)

    # ── File outputs ────────────────────────────────────────
    if args.json:
        reports_to_json(reports, args.json)

    if args.csv:
        reports_to_csv(reports, args.csv)


if __name__ == "__main__":
    main()
