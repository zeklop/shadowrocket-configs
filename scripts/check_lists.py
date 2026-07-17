#!/usr/bin/env python3
"""Проверка конфигов и списков правил.

Запуск локально перед push:   python3 scripts/check_lists.py
Пропустить проверку DNS:      python3 scripts/check_lists.py --no-dns

Падает, если найдено то, что сломает маршрутизацию у пользователей.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULE_TYPES = {
    "DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6",
    "GEOIP", "URL-REGEX", "USER-AGENT", "PROCESS-NAME", "AND", "OR", "NOT",
    "DST-PORT", "SRC-IP", "PROTOCOL", "RULE-SET", "FINAL",
}
errors, warnings = [], []


def fail(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def rules_of(path):
    """[(номер строки, тип, значение)] — без комментариев и пустых строк."""
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split(",")
        out.append((n, parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""))
    return out


def configs():
    return sorted(ROOT.glob("*.conf"))


def connected_lists(conf):
    """Списки, подключённые к конфигу, в порядке приоритета."""
    out = []
    for line in conf.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("#") or not s.startswith("RULE-SET"):
            continue
        m = re.search(r"/([A-Za-z0-9_-]+\.list)", s)
        if m:
            out.append(m.group(1))
    return out


# --- 1. RULE-SET ссылается на существующий файл ---------------------------
for conf in configs():
    for name in connected_lists(conf):
        if not (ROOT / name).exists():
            fail(f"{conf.name}: RULE-SET ссылается на {name}, а файла в репозитории нет")

# --- 2. update-url указывает сам на себя ---------------------------------
for conf in configs():
    text = conf.read_text(encoding="utf-8")
    m = re.search(r"update-url\s*=\s*\S*/([A-Za-z0-9_-]+\.conf)", text)
    if not m:
        warn(f"{conf.name}: не найден update-url")
    elif m.group(1) != conf.name:
        fail(f"{conf.name}: update-url указывает на {m.group(1)} — конфиг перезапишет себя чужим")

# --- 3. синтаксис правил -------------------------------------------------
for path in sorted(ROOT.glob("*.list")):
    for n, rtype, value in rules_of(path):
        if rtype not in RULE_TYPES:
            fail(f"{path.name}:{n}: неизвестный тип правила «{rtype}»")
        elif not value:
            fail(f"{path.name}:{n}: правило {rtype} без значения")
    raw = path.read_text(encoding="utf-8")
    for n, line in enumerate(raw.splitlines(), 1):
        if not line.strip().startswith("#") and re.search(r",\s+|\s+,", line):
            fail(f"{path.name}:{n}: пробел рядом с запятой — «{line.strip()}»")

# --- 4. дубли внутри файла -----------------------------------------------
for path in sorted(ROOT.glob("*.list")):
    seen = {}
    for n, rtype, value in rules_of(path):
        key = (rtype, value)
        if key in seen:
            fail(f"{path.name}:{n}: дубль строки {seen[key]} — {rtype},{value}")
        else:
            seen[key] = n

# --- 5. коллизии между списками одного конфига ---------------------------
for conf in configs():
    order = connected_lists(conf)
    owner = {}
    for name in order:
        p = ROOT / name
        if not p.exists():
            continue
        for _, rtype, value in rules_of(p):
            key = (rtype, value)
            if key in owner and owner[key] != name:
                fail(f"{conf.name}: «{rtype},{value}» есть и в {owner[key]}, и в {name}; "
                     f"выигрывает {owner[key]} — правило в {name} мёртвое")
            owner.setdefault(key, name)

# --- 6. AI.list отсортирован ---------------------------------------------
ai = ROOT / "AI.list"
if ai.exists():
    suffixes = [v for _, t, v in rules_of(ai) if t == "DOMAIN-SUFFIX"]
    if suffixes != sorted(suffixes):
        fail("AI.list: DOMAIN-SUFFIX не отсортированы по алфавиту")

# --- 7. домены существуют ------------------------------------------------
if "--no-dns" not in sys.argv:
    try:
        import dns.resolver
    except ImportError:
        warn("dnspython не установлен — проверка DNS пропущена (pip install dnspython)")
    else:
        # Резолверы задаются явно, а не берутся системные: если на машине поднят
        # прокси с fake-IP DNS, он отвечает выдуманным адресом на любой домен,
        # включая несуществующий, и проверка молча становится бесполезной.
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = ["9.9.9.9", "1.1.1.1", "8.8.8.8"]
        resolver.timeout, resolver.lifetime = 5, 10

        checked = set()
        for path in sorted(ROOT.glob("*.list")):
            for n, rtype, value in rules_of(path):
                if rtype not in ("DOMAIN", "DOMAIN-SUFFIX") or value in checked:
                    continue
                checked.add(value)
                try:
                    resolver.resolve(value, "A")
                except dns.resolver.NXDOMAIN:
                    fail(f"{path.name}:{n}: домена {value} не существует (NXDOMAIN)")
                except dns.resolver.NoAnswer:
                    pass  # домен есть, A-записи на апексе нет — норма для CDN
                except Exception:
                    pass  # таймаут или сбой сети — не повод падать

# --- итог ----------------------------------------------------------------
for w in warnings:
    print(f"ПРЕДУПРЕЖДЕНИЕ: {w}")
for e in errors:
    print(f"ОШИБКА: {e}")

if errors:
    print(f"\nПровалено: {len(errors)}")
    sys.exit(1)
print(f"Проверки пройдены{', предупреждений: %d' % len(warnings) if warnings else ''}")
