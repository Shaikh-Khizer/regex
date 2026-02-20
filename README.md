# regex
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
| Option                      | Description                                  |
| --------------------------- | -------------------------------------------- |
| `-h, --help`                | Show help message                            |
| `-t, --token TOKEN`         | Scan a single token                          |
| `-f, --file FILE`           | Scan tokens from file                        |
| `-d, --directory DIRECTORY` | Rules directory (default: `./list`) |
| `--no-color`                | Disable colored output                       |

## 🔍 Examples

### Scan a single token:
```bash
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
- Linux / macOS (Windows should also work with Python installed)

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

Shaikh Khizer
Computer Science Student | Penetration Tester
