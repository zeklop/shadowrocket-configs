# Comss Split DNS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить Xbox DNS на Comss.one для Google/Gemini, сохранив весь DNS- и сервисный трафик внутри выбранного прокси.

**Architecture:** Широкие Google-маски в `[Host]` продолжают принудительно резолвиться локально через `https://dns.comss.one/dns-query#proxy`. Широкие Google logical rules оставляют весь последующий трафик на `PROXY`; правил `DIRECT` для Google или Comss нет. Это обязательное ограничение региона с белыми списками.

**Tech Stack:** Shadowrocket config, DoH, Git, `scripts/check_lists.py`, live API Shadowrocket.

## Global Constraints

- Изменять только `simple-dns.conf`; README не трогать.
- Глобальный основной DNS остаётся `https://safe.dot.dns.yandex.net/dns-query`.
- Instagram/Meta остаётся на NextDNS `dc5494#proxy` и политике `PROXY`.
- Перед push обязательно выполнить `python3 scripts/check_lists.py`.
- Push в `main` — только по явной просьбе пользователя.

---

### Task 1: Переключить Google/Gemini на Comss.one

**Files:**
- Modify: `simple-dns.conf`
- Test: `scripts/check_lists.py`

**Interfaces:**
- Consumes: DoH `https://dns.comss.one/dns-query`, Smart DNS gateway `45.88.174.254`.
- Produces: конфиг, где запросы к Comss DoH и весь Google-трафик идут через `PROXY`.

- [ ] **Step 1: Зафиксировать исходное состояние**

Run:

```bash
rg -c 'xbox-dns.ru/dns-query' simple-dns.conf
rg -c 'dns.comss.one/dns-query' simple-dns.conf || true
rg -c 'dns.comss.one/dns-query#proxy' simple-dns.conf || true
```

Expected: Xbox `17`, Comss через proxy `0`.

- [ ] **Step 2: Внести минимальную правку**

В `simple-dns.conf`:

```ini
fallback-dns-server = https://dns.comss.one/dns-query#proxy
```

Во всех широких Google-записях `[Host]` заменить:

```ini
server:https://xbox-dns.ru/dns-query
```

на:

```ini
server:https://dns.comss.one/dns-query#proxy
```

Обновить `# UPDATED:` и комментарий fallback. Остальные строки не менять.

- [ ] **Step 3: Проверить статический контракт**

Run:

```bash
! rg -q 'xbox-dns.ru/dns-query' simple-dns.conf
test "$(rg -c 'dns.comss.one/dns-query' simple-dns.conf)" = 17
test "$(rg -c 'dns.comss.one/dns-query#proxy' simple-dns.conf)" = 17
! rg -q '^IP-CIDR,45\.88\.174\.254/32,DIRECT,no-resolve$' simple-dns.conf
! rg -q 'dns\.comss\.one/dns-query$' simple-dns.conf
git diff --check
python3 scripts/check_lists.py
```

Expected: все команды завершаются с кодом `0`; проверка списков может вывести только известное предупреждение об отсутствующем `dnspython`.

- [ ] **Step 4: Проверить Comss DoH**

Run:

```bash
curl -sS --noproxy '*' --resolve dns.comss.one:443:195.133.25.16 \
  --doh-url https://dns.comss.one/dns-query \
  --connect-timeout 10 --max-time 20 -o /dev/null \
  -w '%{remote_ip} %{http_code}\n' \
  https://robinfrontend-pa.googleapis.com/
```

Expected: remote IP `45.88.174.254`; HTTP status может быть `404`.

- [ ] **Step 5: Подготовить отдельный коммит конфига**

Run:

```bash
git add -- simple-dns.conf
git diff --cached --check
git commit -m "switch Gemini smart DNS to Comss"
```

Expected: в коммите только `simple-dns.conf`.

### Task 2: Проверить на iPhone

**Files:**
- Modify: none
- Test: `http://192.168.1.73:1082/api/log`

**Interfaces:**
- Consumes: опубликованный `simple-dns.conf` после отдельного разрешения на push.
- Produces: подтверждение или опровержение стабильной работы Gemini.

- [ ] **Step 1: После разрешения пользователя отправить коммит в `main`**

Run:

```bash
git push origin main
```

Expected: remote `main` указывает на коммит конфига.

- [ ] **Step 2: Холодный запуск**

Пользователь обновляет конфиг с cache-busting query, переподключает Shadowrocket, полностью выгружает Gemini и запускает его заново.

- [ ] **Step 3: Проверить live-лог**

Run:

```bash
curl --max-time 10 http://192.168.1.73:1082/api/log
```

Expected:

- `robinfrontend-pa.googleapis.com` и другие перенаправленные Comss домены получают `45.88.174.254` от `https://dns.comss.one/dns-query#proxy`;
- DNS-запрос к Comss и соединение к `45.88.174.254` идут через выбранный прокси; записей `DIRECT` для Google и Comss нет;
- OAuth и обычные Google IP матчат широкие Google logical rules с `PROXY`;
- Instagram/Meta продолжает использовать NextDNS и `PROXY`;
- Gemini не показывает geo restriction после повторного холодного запуска.
