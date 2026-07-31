"""ClinicalTrials.gov v2 API — the BD intel engine (no key required).

  https://clinicaltrials.gov/api/v2/studies

Pulls active/recruiting trials by condition + status + geography and normalizes
them into rich Study records (sponsor + class, phase, enrollment, every site
and its PI/coordinator contact).
"""

from __future__ import annotations

import asyncio

import httpx

from ..models import Contact, Site, Study, parse_date

API = "https://clinicaltrials.gov/api/v2/studies"
UA = "StudyScout/0.1 (personal clinical-trials BD tool; respectful client)"


def _contacts(raw: list) -> list[Contact]:
    out = []
    for c in raw or []:
        if not isinstance(c, dict):
            continue
        out.append(Contact(
            name=c.get("name"), role=c.get("role"),
            email=c.get("email") or c.get("eMail"), phone=c.get("phone"),
        ))
    return out


def _study_from(record: dict) -> Study | None:
    ps = record.get("protocolSection", {})
    ident = ps.get("identificationModule", {})
    nct = ident.get("nctId", "")
    title = ident.get("briefTitle", "").strip()
    if not nct or not title:
        return None
    status_m = ps.get("statusModule", {})
    sponsor_m = ps.get("sponsorCollaboratorsModule", {})
    design = ps.get("designModule", {})
    conds = ps.get("conditionsModule", {}).get("conditions", []) or []
    cl = ps.get("contactsLocationsModule", {})
    desc = ps.get("descriptionModule", {}).get("briefSummary", "") or ""

    lead = sponsor_m.get("leadSponsor", {}) or {}
    collabs = [c.get("name", "") for c in sponsor_m.get("collaborators", []) or [] if c.get("name")]

    sites = []
    for loc in cl.get("locations", []) or []:
        sites.append(Site(
            facility=loc.get("facility", ""), city=loc.get("city", ""),
            state=loc.get("state", ""), country=loc.get("country", ""),
            status=loc.get("status", ""), contacts=_contacts(loc.get("contacts", [])),
        ))

    enroll = (design.get("enrollmentInfo", {}) or {}).get("count")
    return Study(
        nct=nct, title=title,
        status=status_m.get("overallStatus", ""),
        phases=design.get("phases", []) or [],
        conditions=conds,
        sponsor=lead.get("name", ""),
        sponsor_class=lead.get("class", ""),
        collaborators=collabs,
        enrollment=int(enroll) if isinstance(enroll, (int, float)) else None,
        study_type=design.get("studyType", ""),
        start=parse_date((status_m.get("startDateStruct") or {}).get("date")),
        sites=sites,
        central_contacts=_contacts(cl.get("centralContacts", [])),
        summary=desc,
    )


async def _query(condition: str, statuses: list[str], location: str,
                 page_size: int, client: httpx.AsyncClient) -> list[Study]:
    params = {"pageSize": min(page_size, 100), "countTotal": "false", "format": "json"}
    if condition:
        params["query.cond"] = condition
    if location:
        params["query.locn"] = location
    if statuses:
        params["filter.overallStatus"] = ",".join(statuses)
    r = await client.get(API, params=params)
    if r.status_code != 200:
        raise RuntimeError(f"ctgov HTTP {r.status_code}: {r.text[:120]}")
    out = []
    for rec in r.json().get("studies", []):
        s = _study_from(rec)
        if s:
            out.append(s)
    return out


def _agg(f: dict) -> str:
    parts = []
    if f.get("ages"):
        parts.append("ages:" + " ".join(f["ages"]))
    if f.get("phases"):
        parts.append("phase:" + " ".join(str(p) for p in f["phases"]))
    if f.get("study_type"):
        parts.append("studyType:" + str(f["study_type"]))
    if f.get("funder_types"):
        parts.append("funderType:" + " ".join(f["funder_types"]))
    return ",".join(parts)


def _keep(s: Study, excludes: list[str]) -> bool:
    if not excludes:
        return True
    hay = f"{s.title} {' '.join(s.conditions)} {s.summary}".lower()
    return not any(x.lower() in hay for x in excludes if x)


async def _paged(client: httpx.AsyncClient, base: dict, cap: int) -> list[Study]:
    out, token = [], None
    while len(out) < cap:
        params = dict(base, pageSize=min(100, cap - len(out)))
        if token:
            params["pageToken"] = token
        r = await client.get(API, params=params)
        if r.status_code != 200:
            raise RuntimeError(f"ctgov HTTP {r.status_code}: {r.text[:120]}")
        data = r.json()
        for rec in data.get("studies", []):
            s = _study_from(rec)
            if s:
                out.append(s)
        token = data.get("nextPageToken")
        if not token:
            break
    return out


async def fetch(cfg) -> tuple[list[Study], list[str]]:
    """Run the configured filters against ClinicalTrials.gov."""
    f = cfg.get("filters", {}) or {}
    base = {"format": "json", "countTotal": "false"}
    if f.get("condition"):
        base["query.cond"] = f["condition"]
    if f.get("keyword"):
        base["query.term"] = f["keyword"]
    if f.get("sponsor"):
        base["query.lead"] = f["sponsor"]
    if f.get("statuses"):
        base["filter.overallStatus"] = ",".join(f["statuses"])
    agg = _agg(f)
    if agg:
        base["aggFilters"] = agg
    country = (f.get("country") or "").strip()
    states = f.get("states") or []
    cap = int(f.get("max_results", 300))
    excludes = f.get("exclude_keywords") or []
    errors: list[str] = []

    async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=30,
                                 follow_redirects=True) as client:
        queries = []
        if states:
            for st in states:
                q = dict(base, **{"query.locn": st})
                queries.append(q)
        else:
            adv = f'AREA[LocationCountry]{country}' if country else ""
            q = dict(base)
            if adv:
                q["filter.advanced"] = adv
            queries.append(q)

        async def run(q):
            try:
                return await _paged(client, q, cap)
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
                return []
        chunks = await asyncio.gather(*(run(q) for q in queries))

    site_mode = (f.get("site_mode") or "any").lower()

    def _site_ok(s: Study) -> bool:
        if site_mode == "multi":
            return s.n_sites >= 2
        if site_mode == "single":
            return s.n_sites <= 1
        return True

    by_nct: dict[str, Study] = {}
    for chunk in chunks:
        for s in chunk:
            if s.nct not in by_nct and _keep(s, excludes) and _site_ok(s):
                by_nct[s.nct] = s
    studies = list(by_nct.values())

    sort = f.get("sort", "start")
    if sort == "enrollment":
        studies.sort(key=lambda s: (s.enrollment or 0), reverse=True)
    elif sort == "sites":
        studies.sort(key=lambda s: s.n_sites, reverse=True)
    else:  # start date, newest first
        studies.sort(key=lambda s: (s.start or parse_date("1900-01-01")), reverse=True)
    return studies[:cap], errors


async def search(conditions: list[str], statuses: list[str], locations: list[str],
                 max_studies: int = 120) -> tuple[list[Study], list[str]]:
    """Fan out over conditions × locations, dedupe by NCT."""
    conditions = conditions or [""]
    locations = locations or [""]
    per = max(20, max_studies // max(1, len(conditions) * len(locations)))
    errors: list[str] = []

    async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=25,
                                 follow_redirects=True) as client:
        async def run(cond, loc):
            try:
                return await _query(cond, statuses, loc, per, client)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{cond}/{loc}: {exc}")
                return []
        results = await asyncio.gather(
            *(run(c, l) for c in conditions for l in locations))

    by_nct: dict[str, Study] = {}
    for chunk in results:
        for s in chunk:
            by_nct.setdefault(s.nct, s)
    return list(by_nct.values())[:max_studies], errors
