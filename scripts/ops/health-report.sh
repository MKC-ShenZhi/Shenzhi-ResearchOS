#!/usr/bin/env bash
# Linux host health report + Feishu custom bot (plan A: shell + cron).
set -euo pipefail

MODE="${1:-}"
if [[ "$MODE" != "daily" && "$MODE" != "probe" ]]; then
  echo "usage: $0 daily|probe" >&2
  exit 2
fi

OPS_LARK_WEBHOOK_URL="${OPS_LARK_WEBHOOK_URL:-}"
OPS_LARK_SIGN_SECRET="${OPS_LARK_SIGN_SECRET:-}"
OPS_COMPOSE_FILE="${OPS_COMPOSE_FILE:-}"
OPS_HTTP_URL="${OPS_HTTP_URL:-http://127.0.0.1/}"
OPS_STATE_FILE="${OPS_STATE_FILE:-/var/lib/shenzhi/ops-alert-state.json}"
OPS_ALERT_MEM_AVAIL_PCT="${OPS_ALERT_MEM_AVAIL_PCT:-10}"
OPS_ALERT_DISK_USE_PCT="${OPS_ALERT_DISK_USE_PCT:-90}"
OPS_ALERT_LOAD_FACTOR="${OPS_ALERT_LOAD_FACTOR:-2}"
OPS_ALERT_COOLDOWN_SEC="${OPS_ALERT_COOLDOWN_SEC:-1800}"
OPS_HOST_LABEL="${OPS_HOST_LABEL:-$(hostname -s 2>/dev/null || echo host)}"
OPS_SOURCE_SERVICE="${OPS_SOURCE_SERVICE:-monitoring}"
OPS_SOURCE_COMPONENT="${OPS_SOURCE_COMPONENT:-host-probe}"

log() {
  echo "[$(date -Iseconds)] $*" >&2
}

cpu_usage_pct() {
  local a b idle1 idle2 total1 total2
  read -r _ user1 nice1 sys1 idle1 iow1 irq1 sirq1 steal1 _ < /proc/stat
  total1=$((user1 + nice1 + sys1 + idle1 + iow1 + irq1 + sirq1 + steal1))
  idle_t1=$idle1
  sleep 1
  read -r _ user2 nice2 sys2 idle2 iow2 irq2 sirq2 steal2 _ < /proc/stat
  total2=$((user2 + nice2 + sys2 + idle2 + iow2 + irq2 + sirq2 + steal2))
  idle_t2=$idle2
  local dt=$((total2 - total1))
  local di=$((idle_t2 - idle_t1))
  if (( dt <= 0 )); then
  echo 0
  return
  fi
  echo $(( (100 * (dt - di)) / dt ))
}

mem_stats() {
  local total avail swap_total swap_free
  total=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
  avail=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
  swap_total=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
  swap_free=$(awk '/^SwapFree:/ {print $2}' /proc/meminfo)
  local used_pct=0 avail_pct=0 swap_used_pct=0
  if (( total > 0 )); then
    used_pct=$(( (100 * (total - avail)) / total ))
    avail_pct=$(( (100 * avail) / total ))
  fi
  if (( swap_total > 0 )); then
    swap_used_pct=$(( (100 * (swap_total - swap_free)) / swap_total ))
  fi
  echo "$used_pct $avail_pct $swap_used_pct"
}

disk_root_use_pct() {
  df -P / | awk 'NR==2 {gsub(/%/,""); print $5}'
}

load_1min() {
  awk '{print $1}' /proc/loadavg
}

cpu_cores() {
  nproc 2>/dev/null || echo 1
}

http_code() {
  curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "$OPS_HTTP_URL" 2>/dev/null || echo "000"
}

docker_ps_summary() {
  if [[ ! -f "$OPS_COMPOSE_FILE" ]] || ! command -v docker >/dev/null 2>&1; then
  echo "(docker compose unavailable)"
  return
  fi
  docker compose -f "$OPS_COMPOSE_FILE" ps --format 'table {{.Name}}\t{{.Status}}' 2>/dev/null || echo "(compose ps failed)"
}

web_running() {
  if [[ ! -f "$OPS_COMPOSE_FILE" ]] || ! command -v docker >/dev/null 2>&1; then
  return 0
  fi
  local line
  line=$(docker compose -f "$OPS_COMPOSE_FILE" ps web --status running -q 2>/dev/null | head -n1)
  [[ -n "$line" ]]
}

send_feishu_text() {
  local text="$1"
  if [[ -z "$OPS_LARK_WEBHOOK_URL" ]]; then
  log "OPS_LARK_WEBHOOK_URL not set; skip send"
  return 1
  fi
  local payload
  if [[ -n "$OPS_LARK_SIGN_SECRET" ]]; then
    local ts sign
    ts=$(date +%s)
    sign=$(printf '%s' "${ts}"$'\n'"${OPS_LARK_SIGN_SECRET}" | openssl dgst -sha256 -hmac "$OPS_LARK_SIGN_SECRET" -binary | base64)
    payload=$(TEXT="$text" TS="$ts" SIGN="$sign" python3 - <<'PY'
import json, os
print(json.dumps({
  "timestamp": os.environ["TS"],
  "sign": os.environ["SIGN"],
  "msg_type": "text",
  "content": {"text": os.environ["TEXT"]},
}, ensure_ascii=False))
PY
)
  else
    payload=$(TEXT="$text" python3 - <<'PY'
import json, os
print(json.dumps({
  "msg_type": "text",
  "content": {"text": os.environ["TEXT"]},
}, ensure_ascii=False))
PY
)
  fi
  curl -sS -X POST "$OPS_LARK_WEBHOOK_URL" \
    -H 'Content-Type: application/json; charset=utf-8' \
    -d "$payload" >/dev/null
}

cooldown_active() {
  local key="$1"
  local now last
  now=$(date +%s)
  if [[ ! -f "$OPS_STATE_FILE" ]]; then
  return 1
  fi
  last=$(python3 - "$OPS_STATE_FILE" "$key" <<'PY' 2>/dev/null || echo 0
import json, sys
path, key = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    print(0)
else:
    print(int(data.get(key, 0)))
PY
)
  if (( now - last < OPS_ALERT_COOLDOWN_SEC )); then
  return 0
  fi
  return 1
}

record_event_ts() {
  local key="$1"
  local now
  now=$(date +%s)
  mkdir -p "$(dirname "$OPS_STATE_FILE")"
  python3 - "$OPS_STATE_FILE" "$key" "$now" <<'PY'
import json, os, sys
path, key, ts = sys.argv[1], sys.argv[2], int(sys.argv[3])
data = {}
if os.path.isfile(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        data = {}
data[key] = ts
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f)
PY
}

read_active_alerts() {
  if [[ ! -f "$OPS_STATE_FILE" ]]; then
  return
  fi
  python3 - "$OPS_STATE_FILE" <<'PY'
import json, sys
path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {}
active = data.get("active")
if isinstance(active, list):
    for item in active:
        if isinstance(item, str) and item:
            print(item)
PY
}

write_active_alerts() {
  local -n keys_ref=$1
  mkdir -p "$(dirname "$OPS_STATE_FILE")"
  local joined
  joined=$(printf '%s\n' "${keys_ref[@]}")
  ACTIVE_LIST="$joined" python3 - "$OPS_STATE_FILE" <<'PY'
import json, os, sys
path = sys.argv[1]
raw = os.environ.get("ACTIVE_LIST", "")
active = [line.strip() for line in raw.splitlines() if line.strip()]
data = {}
if os.path.isfile(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        data = {}
data["active"] = active
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
PY
}

build_report() {
  local cpu pct mem_used mem_avail swap_used disk load cores code dkr
  cpu=$(cpu_usage_pct)
  read -r pct mem_used mem_avail swap_used < <(mem_stats)
  disk=$(disk_root_use_pct)
  load=$(load_1min)
  cores=$(cpu_cores)
  code=$(http_code)
  dkr=$(docker_ps_summary)

  cat <<EOF
【深知·运维】模式=${MODE} 来源=${OPS_SOURCE_SERVICE}/${OPS_SOURCE_COMPONENT} 主机=${OPS_HOST_LABEL}
CPU: ${cpu}%  内存已用: ${mem_used}%  可用: ${mem_avail}%  Swap已用: ${swap_used}%
磁盘(/): ${disk}%  负载(1m): ${load}  CPU核: ${cores}
HTTP ${OPS_HTTP_URL}: ${code}
---
${dkr}
EOF
}

collect_alerts() {
  local alerts=()
  local cpu pct mem_used mem_avail swap_used disk load cores code
  cpu=$(cpu_usage_pct)
  read -r pct mem_used mem_avail swap_used < <(mem_stats)
  disk=$(disk_root_use_pct)
  load=$(load_1min)
  cores=$(cpu_cores)
  code=$(http_code)

  if (( mem_avail < OPS_ALERT_MEM_AVAIL_PCT )); then
    alerts+=("mem_avail")
  fi
  if (( swap_used >= 95 )); then
    alerts+=("swap")
  fi
  if (( disk >= OPS_ALERT_DISK_USE_PCT )); then
    alerts+=("disk")
  fi
  load_int=${load%.*}
  if [[ -z "$load_int" ]]; then load_int=0; fi
  if (( load_int > cores * OPS_ALERT_LOAD_FACTOR )); then
    alerts+=("load")
  fi
  if [[ "$code" != "200" && "$code" != "301" && "$code" != "302" && "$code" != "304" ]]; then
    alerts+=("http")
  fi
  if ! web_running; then
    alerts+=("web_down")
  fi
  if ((${#alerts[@]} == 0)); then
  echo ""
  else
  printf '%s\n' "${alerts[@]}"
  fi
}

main() {
  local body
  body=$(build_report)

  if [[ "$MODE" == "daily" ]]; then
    log "daily report"
    send_feishu_text "$body"
    exit 0
  fi

  local alert_lines key sent=0
  mapfile -t curr_alerts < <(collect_alerts | sed '/^$/d')
  mapfile -t prev_alerts < <(read_active_alerts | sed '/^$/d')

  local prev key found
  for key in "${prev_alerts[@]}"; do
    [[ -z "$key" ]] && continue
    found=0
    for k in "${curr_alerts[@]}"; do
      [[ "$k" == "$key" ]] && found=1 && break
    done
  if (( found == 0 )); then
    local rkey="recovery:${key}"
    if cooldown_active "$rkey"; then
      log "cooldown skip $rkey"
    else
      send_feishu_text "[恢复] 告警项 ${key} 已恢复正常
${body}"
      record_event_ts "$rkey"
      sent=1
      log "recovery sent $key"
    fi
  fi
  done

  for key in "${curr_alerts[@]}"; do
    [[ -z "$key" ]] && continue
    found=0
    for k in "${prev_alerts[@]}"; do
      [[ "$k" == "$key" ]] && found=1 && break
    done
    if (( found == 0 )); then
      send_feishu_text "[告警·新] ${key}
${body}"
      record_event_ts "alert:${key}"
      sent=1
      log "alert sent (new) $key"
      continue
    fi
    if cooldown_active "alert:${key}"; then
      log "cooldown skip alert:${key}"
      continue
    fi
    send_feishu_text "[告警·持续] ${key}
${body}"
    record_event_ts "alert:${key}"
    sent=1
    log "alert sent (ongoing) $key"
  done

  write_active_alerts curr_alerts

  if ((${#curr_alerts[@]} == 0)); then
    log "probe ok"
  elif (( sent == 0 )); then
    log "probe alerts muted by cooldown"
  fi
}

main