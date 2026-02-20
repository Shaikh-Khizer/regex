#!/usr/bin/env python3

import os
import re
import sys
import yaml
import glob
import argparse
from collections import defaultdict

DEFAULT_RULES_DIR = "/opt/regex/list"


# ==========================================================
# Color System (Auto disables if not TTY)
# ==========================================================
class Color:
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    enabled = sys.stdout.isatty()

    @classmethod
    def disable(cls):
        cls.enabled = False

    @classmethod
    def wrap(cls, text, color):
        if not cls.enabled:
            return text
        return f"{color}{text}{cls.RESET}"


# ==========================================================
# Rule Loader
# ==========================================================
def load_rules(rules_dir):
    rules = defaultdict(list)
    total_rules = 0

    pattern = os.path.join(rules_dir, "*.y*ml")
    files = glob.glob(pattern)

    if not files:
        print(Color.wrap(f"[!] No YAML files found in {rules_dir}", Color.RED))
        return rules, total_rules

    for file in files:
        try:
            with open(file, "r") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            print(Color.wrap(f"[!] Failed to load {file}: {e}", Color.RED))
            continue

        if not data or "patterns" not in data:
            continue

        for item in data["patterns"]:
            pattern_obj = item.get("pattern", {})
            name = pattern_obj.get("name", "unknown")
            regex = pattern_obj.get("regex")

            if not regex:
                continue

            try:
                compiled = re.compile(regex)
                rules[file].append((name, compiled))
                total_rules += 1
            except re.error:
                continue

    return rules, total_rules


# ==========================================================
# Scanner
# ==========================================================
def scan_token(token, rules):
    found = False
    total_matches = 0

    for file, file_rules in rules.items():
        matches = []

        for name, regex in file_rules:
            if regex.search(token):
                matches.append(name)
                total_matches += 1

        if matches:
            found = True
            print(Color.wrap(f"\n[+] Match in {os.path.basename(file)}", Color.GREEN))
            for m in matches:
                print("   -", Color.wrap(m, Color.YELLOW))

    if not found:
        print(Color.wrap("\n[-] No matches found", Color.RED))

    return total_matches


def scan_file(path, rules):
    if not os.path.exists(path):
        print(Color.wrap("[!] Input file not found", Color.RED))
        return

    tokens_scanned = 0
    total_matches = 0

    with open(path, "r") as f:
        for line in f:
            token = line.strip()
            if not token:
                continue

            tokens_scanned += 1
            print("\n" + "=" * 60)
            print(Color.wrap("Token:", Color.BOLD),
                  Color.wrap(token, Color.YELLOW))

            total_matches += scan_token(token, rules)

    print_summary(tokens_scanned, total_matches)


# ==========================================================
# Summary
# ==========================================================
def print_summary(tokens, matches):
    print("\n" + "=" * 60)
    print(Color.wrap("SCAN COMPLETE", Color.BOLD))
    print(Color.wrap(f"Tokens scanned : {tokens}", Color.CYAN))
    print(Color.wrap(f"Total matches  : {matches}", Color.GREEN))


# ==========================================================
# Main CLI
# ==========================================================
def main():
    parser = argparse.ArgumentParser(
        description="Regex Pattern Scanner",
        epilog="""
Examples:
  regex -t "example@email.com"
  regex -f tokens.txt
  regex -d /custom/rules -t AKIAIOSFODNN7EXAMPLE
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("-t", "--token", help="Scan a single token")
    parser.add_argument("-f", "--file", help="Scan tokens from file")
    parser.add_argument(
        "-d",
        "--directory",
        default=DEFAULT_RULES_DIR,
        help=f"Rules directory (default: {DEFAULT_RULES_DIR})"
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )

    args = parser.parse_args()

    if args.no_color:
        Color.disable()

    if not args.token and not args.file:
        parser.print_help()
        sys.exit(1)

    print(Color.wrap("[*] Loading rules...", Color.CYAN))
    rules, total_rules = load_rules(args.directory)

    if total_rules == 0:
        print(Color.wrap("[!] No valid rules loaded", Color.RED))
        sys.exit(1)

    print(Color.wrap(f"[+] Loaded {total_rules} regex patterns\n", Color.GREEN))

    if args.token:
        print(Color.wrap("Token:", Color.BOLD),
            Color.wrap(args.token, Color.YELLOW))
        matches = scan_token(args.token, rules)
        print_summary(1, matches)


    elif args.file:
        scan_file(args.file, rules)


if __name__ == "__main__":
    main()
