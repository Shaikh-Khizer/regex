# Regex
Regex Pattern Scanner  A lightweight and efficient **Regex-based Token Scanner** written in Python.   This tool scans tokens using predefined regex rules to detect sensitive patterns such as API keys, Tokens etc based on regex, secrets, and more.

---

## 🚀 Features

- Scan a single token from terminal
- Scan multiple tokens from a file
- Custom rules directory support
- Colored output for better visibility
- Clean and minimal CLI interface
- Fast regex-based matching

---

## Options:
| Argument | Short | Type | Default | Description |
|----------|-------|------|---------|-------------|
| `--help` | `-h` | flag | — | Show help message and exit |
| `--token` | `-t` | string | — | Scan a single token |
| `--file` | `-f` | path | — | Scan tokens from a file (one per line) |
| `--directory` | `-d` | path | `/opt/regex/list` | Rules directory |
| `--json` | — | path | — | Save results as JSON to FILE |
| `--csv` | — | path | — | Save results as CSV to FILE |
| `--min-score` | — | float | `0` | Only show matches with composite score >= N |
| `--no-color` | — | flag | — | Disable colored terminal output |
| `--no-dedup` | — | flag | — | Disable deduplication (scan duplicate tokens too) |
## 🔍 Examples

### Scan a single token:
```bash
sudo apt install python3-regex
python3 regex.py -t "example@email.com"
```
### Scan tokens from file:
```bash
python3 regex.py -f tokens.txt
```
### Use custom rules directory:
```bash
python3 regex.py -d /custom/rules -t AKIAIOSFODNN7EXAMPLE
```

## 📦 Installation

### 1️⃣ Requirements

- Python 3.8+

Check Python version:

```bash
python3 --version
```
---

## 📄 License

This project is licensed under the MIT License.  
See the [LICENSE](LICENSE) file for details.

---
👨‍💻 Author

***Shaikh Khizer***<br>
Computer Science Student | Penetration Tester
