"""Log evidence -> units. Six line syntaxes, one event grammar:

    {"syntax", "ts", "level", "service", "trace_id", "event", "fields"}

bracket  TS [LEVEL] [service] [trace] event: k="v" ...
pipe     TS | LEVEL | service | trace | event | k="v" ...
logfmt   TS [LEVEL] k=v ... (service=, trace_id=, event= among the pairs)
json     TS {"severity":..,"service":..,"trace_id":..,"event":..}
syslog   TS <pri>1 node service trace - - k="v" ...
cloud    TS requestId=trace level=.. function=service message="k=\"v\" ..."

A unit is one trace (lines sharing trace_id; a line without one stands
alone). *_started carries the identifier, *_completed the resource_id and
state; each distinct resource_id in a trace becomes one unit that shares the
trace's identifiers.
"""
import json
import re

from . import parse_common as pc

KV = re.compile(r'([A-Za-z_][\w.]*)=("(?:[^"\\]|\\.)*"|\S+)')
TS = re.compile(r"(\d{4}-\d\d-\d\dT[\d:.]+Z?)\s+(.*)")
BRACKET = re.compile(r"\[(\w+)\] \[([^\]]+)\] \[([^\]]+)\] (\w+):\s*(.*)")
SYSLOG = re.compile(r"<\d+>\d+ (\S+) (\S+) (\S+) \S+ \S+ ?(.*)")

# Event-name prefix -> category (event semantics, not the emitting service).
EVENT_CATEGORIES = [
    ("profile_lookup", "USER_PROFILE"),
    ("index_query", "SEARCH_INDEX_ENTRY"),
    ("audit_record", "SECURITY_AUDIT_LOG"),
    ("analytics_profile", "ANALYTICS_PROFILE"),
    ("analytics_identity", "ANALYTICS_PROFILE"),
    ("support_ticket", "SUPPORT_MESSAGE"),
    ("message_", "SUPPORT_MESSAGE"),
    ("attachment_", "SUPPORT_ATTACHMENT"),
    ("thumbnail_", "SUPPORT_ATTACHMENT"),
    ("connector_", "DATA_FLOW"),
    ("restore_", "BACKUP_ARCHIVE"),
    ("export_metadata", "USER_EXPORT"),
    ("export_download", "USER_EXPORT"),
    ("retained_order", "LEGAL_HOLD_RECORD"),
]


def _kvs(text):
    out = {}
    for k, v in KV.findall(text):
        if v.startswith('"') and v.endswith('"') and len(v) >= 2:
            v = v[1:-1].replace('\\"', '"')
        out[k] = v
    return out


def parse_line(line):
    """One log line -> event dict, or None for blank / unparseable lines."""
    line = line.rstrip("\r\n")
    m = TS.match(line)
    if not m:
        return None
    ts, rest = m.groups()
    ev = {"ts": ts, "level": "", "service": "", "trace_id": "", "event": "", "fields": {}}
    if rest.startswith("{"):
        try:
            fields = {k: ("" if v is None else str(v)) for k, v in json.loads(rest).items()}
        except ValueError:
            return None
        ev.update(syntax="json", level=fields.pop("severity", ""))
        fields.pop("logger", None)
    elif rest.startswith("["):
        b = BRACKET.match(rest)
        if not b:
            return None
        lv, svc, tr, name, tail = b.groups()
        fields = _kvs(tail)
        ev.update(syntax="bracket", level=lv, service=svc, trace_id=tr, event=name)
    elif rest.startswith("|"):
        parts = [p.strip() for p in rest.split("|", 5)]
        if len(parts) < 6:
            return None
        _, lv, svc, tr, name, tail = parts
        fields = _kvs(tail)
        ev.update(syntax="pipe", level=lv, service=svc, trace_id=tr, event=name)
    elif rest.startswith("<"):
        s = SYSLOG.match(rest)
        if not s:
            return None
        _node, svc, tr, tail = s.groups()
        fields = _kvs(tail)
        ev.update(syntax="syslog", service=svc, trace_id=tr)
    elif rest.startswith("requestId="):
        top = _kvs(rest)
        fields = _kvs(top.pop("message", ""))
        ev.update(syntax="cloud", trace_id=top.pop("requestId", ""),
                  service=top.pop("function", ""), level=top.pop("level", ""))
        fields.update({k: v for k, v in top.items() if k not in fields})
    else:
        lead = re.match(r"([A-Z]+)\s+(.*)", rest)
        if lead:
            ev["level"], rest = lead.groups()
        fields = _kvs(rest)
        ev["syntax"] = "logfmt"
    ev["level"] = fields.pop("level", ev["level"])
    ev["service"] = fields.pop("service", ev["service"])
    ev["trace_id"] = fields.pop("trace_id", ev["trace_id"])
    ev["event"] = fields.pop("event", ev["event"])
    ev["fields"] = fields
    ev["line"] = line
    return ev


def event_category(ev):
    name, f = ev["event"], ev["fields"]
    if name == "record_lookup":
        return f.get("record_type", "") if f.get("record_type") in pc.CATEGORIES else ""
    if name.startswith("contact_lookup") and pc.truthy(f.get("email_opt_in", "")):
        return "MARKETING_PROFILE"
    for prefix, cat in EVENT_CATEGORIES:
        if name.startswith(prefix):
            return cat
    return ""


def _copy(events):
    for ev in events:
        pool = ev["fields"].get("pool", "")
        if pool.endswith("_replica"):
            return "replica"
        if pool.endswith("_primary"):
            return "primary"
    if any("replica" in ev["service"] for ev in events):
        return "replica"
    return "unknown"


def _trace_units(events):
    text = "\n".join(ev["line"] for ev in events)
    rids = []
    for ev in events:
        rid = ev["fields"].get("resource_id", "")
        if rid and rid not in rids:
            rids.append(rid)
    identifiers = pc.extract_identifiers(text)
    if not rids and not any(identifiers.values()):
        return []
    copy = _copy(events)
    trace_cat = next((c for c in map(event_category, events) if c), "")
    units = []
    for rid in rids or [""]:
        own = [ev for ev in events if ev["fields"].get("resource_id", "") == rid] if rid else events
        merged = {}
        for ev in own:
            merged.update(ev["fields"])
        cat = next((c for c in map(event_category, own) if c), trace_cat)
        last = own[-1]
        system = merged.get("system") or pc.system_for(rid, last["service"])
        state = pc.infer_state(merged, cat) if rid else ""
        units.append(pc.make_unit(system_id=system, resource_id=rid, category_hint=cat,
                                  state=state, text=text, copy=copy, event_time=last["ts"],
                                  raw=last["line"]))
    units += pc.reference_units(text, rids, copy=copy, event_time=events[-1]["ts"])
    return units


def parse_lines(lines):
    traces, order = {}, []
    for i, line in enumerate(lines):
        ev = parse_line(line)
        if ev is None:
            continue
        key = ev["trace_id"] or f"__line{i}"
        if key not in traces:
            traces[key] = []
            order.append(key)
        traces[key].append(ev)
    units = []
    for key in order:
        units += _trace_units(traces[key])
    return units


def parse_log(path):
    return parse_lines(path.read_text(encoding="utf-8").splitlines())
