"""JSON and plain-text record evidence -> units.

JSON: any dict that carries a resource_id is one unit (nested hits inside it
stay part of that unit). Context from enclosing keys supplies the category
and system: a record_type field first, else the collection / data_store /
service-export key. An empty snapshot (records: []) becomes one unit without
a resource so the coverage it represents is not lost.

TXT: one unit per line; "ts | system | resource | record_type | result |
subject" lines are parsed, other lines only when they mention ids.
"""
import json

from . import parse_common as pc

TIME_KEYS = ("observed_at", "recorded_at", "updated_at", "created_at", "captured_at")


def _category(rec, ctx):
    rt = rec.get("record_type")
    if rt in pc.CATEGORIES:
        return rt
    for name in (ctx.get("collection"), ctx.get("kind")):
        if name in pc.CATEGORY_BY_COLLECTION:
            return pc.CATEGORY_BY_COLLECTION[name]
    return ""


def _record_unit(rec, ctx):
    text = json.dumps(rec, sort_keys=True, ensure_ascii=False)
    rid = str(rec.get("resource_id", ""))
    cat = _category(rec, ctx)
    system = rec.get("system") or pc.system_for(rid, ctx.get("system", ""))
    event_time = next((rec[k] for k in TIME_KEYS if rec.get(k)), ctx.get("time", ""))
    unit = pc.make_unit(system_id=system, resource_id=rid, category_hint=cat,
                        state=pc.infer_state(rec, cat), text=text, event_time=event_time)
    return [unit] + pc.reference_units(text, [rid], event_time=event_time)


def _walk(obj, ctx, out):
    if isinstance(obj, dict):
        if "resource_id" in obj:
            out += _record_unit(obj, ctx)
            return
        ctx = dict(ctx)
        for k in ("collection", "data_store"):
            if isinstance(obj.get(k), str):
                ctx[k] = obj[k]
        if isinstance(obj.get("data_store"), str):
            ctx["system"] = obj["data_store"]
        for k in TIME_KEYS + ("exported_at",):
            if isinstance(obj.get(k), str):
                ctx["time"] = obj[k]
                break
        if obj.get("records") == [] and ctx.get("collection"):
            out.append(pc.make_unit(
                system_id=ctx.get("system", ""), resource_id="",
                category_hint=pc.CATEGORY_BY_COLLECTION.get(ctx["collection"], ""), state="",
                text=json.dumps({k: v for k, v in obj.items() if k != "records"}, sort_keys=True),
                event_time=ctx.get("time", "")))
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                sub = dict(ctx)
                if ctx.get("_in_exports") == 1:
                    sub["system"], sub["_in_exports"] = k, 2
                elif ctx.get("_in_exports") == 2:
                    sub["kind"], sub["_in_exports"] = k, 0
                elif k == "service_exports":
                    sub["_in_exports"] = 1
                _walk(v, sub, out)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item, ctx, out)


def parse_json(path):
    out = []
    _walk(json.loads(path.read_text(encoding="utf-8")), {}, out)
    return out


def parse_txt(path):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        body = line.lstrip("- ").strip()
        parts = [p.strip() for p in body.split("|")]
        if len(parts) >= 6 and parts[2]:
            ts, system, rid, rtype, result = parts[:5]
            cat = rtype if rtype in pc.CATEGORIES else ""
            out.append(pc.make_unit(system_id=system or pc.system_for(rid), resource_id=rid,
                                    category_hint=cat, state=pc.infer_state({"result": result}, cat),
                                    text=body, event_time=ts))
            out += pc.reference_units(body, [rid], event_time=ts)
        elif pc.RESOURCE_ID.search(body) or any(pc.extract_identifiers(body).values()):
            out += pc.reference_units(body, [])
    return out
