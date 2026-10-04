"""Build a public research package without fetching sources or calling AI/services."""
import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def digest(data):
    return hashlib.sha256(data).hexdigest()


def review_fingerprint(data, target):
    """Bind a review to its target and underlying evidence, not an unrelated edit."""
    claims = {c['id']: c for c in data['claims']}
    sources = {s['id']: s for s in data['sources']}
    kind, ident = target['kind'], target['id']
    if kind == 'claim':
        selected, selected_sources = {}, {}
        def collect(key):
            if key in selected:
                return
            selected[key] = claims[key]
            for edge in claims[key].get('evidence', []):
                selected_sources[edge['source']] = sources[edge['source']]
            for parent in claims[key].get('depends_on', []):
                collect(parent)
        collect(ident)
        value = {'claims': selected, 'sources': selected_sources, 'method': data['method']}
    elif kind == 'source':
        value = sources[ident]
    elif kind == 'method' and ident == 'method':
        value = {'question': data['question'], 'method': data['method']}
    else:
        raise ValueError('Unknown review target')
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())


def review_state(data, review):
    if review_fingerprint(data, review['target']) != review['reviewed_target_sha256']:
        return 'needs_reassessment'
    return review['resolution']['status']


def verification_text(review):
    record = review.get('verification')
    if record is None:
        return 'Tarkastuksen syvyys: ei kirjattu'
    labels = {'report': 'raportin luku', 'source_check': 'lähdekohtien tarkistus',
              'rerun': 'laskennan tai kokeen toisto'}
    return (f"Tarkastuksen syvyys: {labels[record['level']]} · "
            f"Laajuus: {record['scope']} · Rajat: {record['limitations']}")


def assessment_state(data, record):
    return ('needs_reassessment' if review_fingerprint(data, record['target']) !=
            record['reviewed_target_sha256'] else 'current')


def assessment_lines(data):
    lines = []
    if data.get('reviews'):
        lines = ['', '## Kirjatut arvioinnit',
                 'Huomautusten puuttuminen rajatussa tarkastuksessa ei todista väitettä oikeaksi.']
    labels = {'no_findings': 'Ei huomautuksia tarkastetussa laajuudessa',
              'findings': 'Huomautuksia', 'inconclusive': 'Tarkastus jäi avoimeksi'}
    for r in data.get('reviews', []):
        lines += ['', f"### {r['id']} · {r['target']['id']} · {assessment_state(data, r)}",
                  labels[r['outcome']], r['summary'], verification_text(r),
                  f"Arvioija: {r['author']['name']} · Malli: {r['author'].get('model') or 'ei kirjattu'}",
                  f"Päivä: {r['date']} · Versio: {r['reviewed_version']} · Commit: {r['reviewed_commit']}",
                  f"Huomautukset: {', '.join(r['criticisms']) or 'ei kirjattuja'}"]
    return lines


def review_lines(data, audit=False):
    reviews = data.get('criticisms', [])
    if not reviews:
        return []
    lines = ['', '## Kritiikki ja vastaukset']
    for r in sorted(reviews, key=lambda r: (r['priority'], r['id'])):
        lines += ['', f"### {r['id']} · {r['target']['id']} · {review_state(data, r)}",
                  r['text'], f"Perustelu: {r['basis']}", verification_text(r)]
        if audit:
            lines += [f"Tyyppi: {r['type']} · Prioriteetti: {r['priority']}",
                      f"Tekijä: {r['author']['name']} ({r['author']['kind']}) · Malli: {r['author'].get('model') or 'ei'}",
                      f"Arvioitu tutkimusversio: {r['reviewed_version']}",
                      f"Vastaus: {r['response'] or 'Ei vielä vastausta'}",
                      f"Kirjattu ratkaisu: {r['resolution']['status']} — {r['resolution']['rationale'] or 'avoin'}",
                      f"Vaikutukset: {r['resolution']['changes'] or 'Ei kirjattuja muutoksia'}",
                      f"Lähteet: {', '.join(r['sources']) or 'Tarkistuskysymys, ei lähteistetty vastanäyttö'}"]
        else:
            lines += [f"Vastaus: {r['response'] or 'Avoin tarkistuskysymys.'}"]
    return lines


def validate(data):
    for key in ("id", "version", "title", "date", "question", "method"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"Missing text: {key}")
    if data.get("schema_version") != "0.1":
        raise ValueError("Unsupported schema version")
    ids = set()
    for group in ("sources", "claims", "stamps"):
        if not isinstance(data.get(group), list):
            raise ValueError(f"Missing list: {group}")
        for item in data[group]:
            ident = item.get("id", "")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", ident) or ident in ids:
                raise ValueError(f"Invalid/duplicate ID: {ident}")
            ids.add(ident)
    sources = {s["id"]: s for s in data["sources"]}
    claims = {c["id"]: c for c in data["claims"]}
    for source in sources.values():
        if source.get("access") != "public":
            raise ValueError("Public renderer refuses restricted source metadata")
        for key in ("title", "locator", "quote", "criticism"):
            if not isinstance(source.get(key), str):
                raise ValueError(f"Invalid source field: {key}")
        url = urlsplit(source.get("url", ""))
        if url.scheme != "https" or not url.netloc or url.username or url.password:
            raise ValueError("Sources require an HTTPS URL without credentials")
        sha = source.get("capture_sha256")
        if sha is not None and not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("Invalid capture SHA-256")
    for claim in claims.values():
        if claim.get("status") not in ("supported", "interpretation", "disputed", "open"):
            raise ValueError("Invalid claim status")
        if not claim.get("text") or not isinstance(claim.get("uncertainty"), str):
            raise ValueError("Claim needs text and explicit uncertainty")
        for parent in claim.get("depends_on", []):
            if parent not in claims:
                raise ValueError(f"Unknown dependency: {parent}")
        for edge in claim.get("evidence", []):
            if edge.get("source") not in sources or edge.get("relation") not in ("FOR", "AGAINST", "CONTEXT") or not edge.get("rationale"):
                raise ValueError("Invalid evidence edge")
        if claim["status"] == "supported" and not any(e["relation"] == "FOR" for e in claim.get("evidence", [])):
            raise ValueError("Supported claim needs supporting evidence")
    def visit(ident, stack, done):
        if ident in stack:
            raise ValueError("Cyclic claim dependencies")
        if ident in done:
            return
        for parent in claims[ident].get("depends_on", []):
            visit(parent, stack | {ident}, done)
        done.add(ident)
    done = set()
    for ident in claims:
        visit(ident, set(), done)
    for stamp in data["stamps"]:
        if stamp.get("source") not in sources or not stamp.get("claim_text"):
            raise ValueError("Stamp needs its original claim and source")
        if urlsplit(stamp.get("url", "")).scheme != "https":
            raise ValueError("Invalid stamp URL")
        if stamp.get("network") == "irys-devnet" and stamp.get("permanent") is not False:
            raise ValueError("Devnet is not permanent")
    for scene in data.get("game", {}).get("scenes", []):
        for choice in scene.get("choices", []):
            if choice.get("claim") not in claims or not choice.get("assumption"):
                raise ValueError("Game rule requires a claim and explicit assumption")
    reviews = data.get('criticisms', [])
    if not isinstance(reviews, list):
        raise ValueError('criticisms must be a list')
    for r in reviews:
        ident = r.get('id', '')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', ident) or ident in ids:
            raise ValueError('Invalid criticism ID')
        ids.add(ident)
        if r.get('type') not in ('source_error', 'reasoning', 'missing_evidence', 'alternative', 'sensitivity'):
            raise ValueError('Invalid criticism type')
        if type(r.get('priority')) is not int or r['priority'] not in (1, 2, 3):
            raise ValueError('Priority must be 1, 2 or 3')
        for key in ('text', 'basis', 'reviewed_version'):
            if not isinstance(r.get(key), str) or not r[key].strip():
                raise ValueError('Criticism needs text, basis and reviewed version')
        author = r.get('author', {})
        if not author.get('name') or author.get('kind') not in ('human', 'agent') or (author['kind'] == 'agent' and not author.get('model')):
            raise ValueError('Criticism needs an identified author/model')
        if not isinstance(r.get('response'), str):
            raise ValueError('Response must be a string, possibly empty')
        if 'verification' in r:
            verification = r['verification']
            if not isinstance(verification, dict) or verification.get('level') not in ('report', 'source_check', 'rerun'):
                raise ValueError('Invalid verification level')
            for key in ('scope', 'limitations'):
                if not isinstance(verification.get(key), str) or not verification[key].strip():
                    raise ValueError('Verification needs explicit scope and limitations')
        resolution = r.get('resolution', {})
        if resolution.get('status') not in ('open', 'accepted', 'partly_accepted', 'rejected'):
            raise ValueError('Invalid resolution status')
        if not isinstance(resolution.get('rationale'), str) or not isinstance(resolution.get('changes'), str):
            raise ValueError('Resolution needs rationale and changes fields')
        if resolution['status'] != 'open' and (not resolution['rationale'].strip() or not r['response'].strip()):
            raise ValueError('Resolved criticism needs response and rationale')
        if not isinstance(r.get('sources'), list) or any(s not in sources for s in r['sources']):
            raise ValueError('Unknown criticism source')
        if not re.fullmatch(r'[0-9a-f]{64}', r.get('reviewed_target_sha256', '')):
            raise ValueError('Criticism needs reviewed target hash')
        try:
            review_fingerprint(data, r['target'])
        except (KeyError, TypeError) as e:
            raise ValueError('Unknown criticism target') from e


    assessments = data.get('reviews', [])
    if not isinstance(assessments, list):
        raise ValueError('reviews must be a list')
    criticism_map = {r['id']: r for r in reviews}
    for r in assessments:
        ident = r.get('id', '')
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', ident) or ident in ids:
            raise ValueError('Invalid review ID')
        ids.add(ident)
        for key in ('summary', 'reviewed_version'):
            if not isinstance(r.get(key), str) or not r[key].strip():
                raise ValueError('Review needs summary and version')
        if not isinstance(r.get('reviewed_commit'), str) or not re.fullmatch(r'[0-9a-f]{40}', r['reviewed_commit']):
            raise ValueError('Review needs a full Git commit SHA')
        if not isinstance(r.get('date'), str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', r['date']):
            raise ValueError('Review needs ISO date')
        try:
            from datetime import date
            date.fromisoformat(r['date'])
            review_fingerprint(data, r['target'])
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError('Invalid review date or target') from e
        if not isinstance(r.get('reviewed_target_sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', r['reviewed_target_sha256']):
            raise ValueError('Review needs target hash')
        author = r.get('author')
        if not isinstance(author, dict) or not isinstance(author.get('name'), str) or not author['name'].strip() or author.get('kind') not in ('human', 'agent'):
            raise ValueError('Review needs author')
        if author['kind'] == 'agent' and (not isinstance(author.get('model'), str) or not author['model'].strip()):
            raise ValueError('Review needs model or explicit unknown')
        verification = r.get('verification')
        if not isinstance(verification, dict) or verification.get('level') not in ('report', 'source_check', 'rerun') or any(not isinstance(verification.get(k), str) or not verification[k].strip() for k in ('scope', 'limitations')):
            raise ValueError('Review needs verification scope and limitations')
        links = r.get('criticisms')
        if not isinstance(links, list) or any(not isinstance(k, str) or k not in criticism_map for k in links):
            raise ValueError('Unknown review criticism')
        if len(set(links)) != len(links) or any(criticism_map[k]['target'] != r['target'] for k in links):
            raise ValueError('Review criticism must match target and be unique')
        if r.get('outcome') not in ('no_findings', 'findings', 'inconclusive') or (r['outcome'] == 'no_findings' and links) or (r['outcome'] == 'findings' and not links):
            raise ValueError('Review outcome conflicts with criticism links')
    validate_activities(data, ids)


def validate_activities(data, existing):
    actors, activities = data.get('actors', []), data.get('activities', [])
    if not isinstance(actors, list) or not isinstance(activities, list):
        raise ValueError('actors and activities must be lists')
    ids = set(existing)
    if any(i.startswith('tool-') for i in ids):
        raise ValueError('tool- prefix is reserved')
    for item in actors + activities:
        ident = item.get('id', '')
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', ident) or ident in ids or ident.startswith('tool-'):
            raise ValueError('Invalid/duplicate provenance ID')
        ids.add(ident)
    actor_map = {a['id']: a for a in actors}
    for actor in actors:
        if actor.get('kind') not in ('human', 'agent') or not isinstance(actor.get('name'), str) or not actor['name'].strip():
            raise ValueError('Actor needs name and kind')
        for key in ('model', 'version'):
            if actor.get(key) is not None and not isinstance(actor[key], str):
                raise ValueError('Actor model/version must be text or null')
    artifacts = set(existing) | {'research.json'}
    from datetime import date
    for a in activities:
        if a.get('kind') not in ('research', 'human_decision') or a.get('actor') not in actor_map:
            raise ValueError('Activity needs known actor and kind')
        if a['kind'] == 'human_decision' and actor_map[a['actor']]['kind'] != 'human':
            raise ValueError('Human decision requires human actor')
        for key in ('date', 'description', 'rationale'):
            if not isinstance(a.get(key), str) or not a[key].strip():
                raise ValueError('Activity needs date, description and rationale')
        try:
            date.fromisoformat(a['date'])
        except ValueError as e:
            raise ValueError('Activity date must be ISO date') from e
        for key in ('inputs', 'outputs'):
            if not isinstance(a.get(key), list) or any(not isinstance(ref, str) or ref not in artifacts for ref in a[key]):
                raise ValueError('Unknown activity input/output')
        tool = a.get('tool')
        if tool is not None and (not isinstance(tool, dict) or not isinstance(tool.get('name'), str) or not tool['name'].strip() or (tool.get('version') is not None and not isinstance(tool['version'], str))):
            raise ValueError('Tool needs name and optional version')


def activity_lines(data):
    if not data.get('activities'):
        return []
    actors = {a['id']: a for a in data['actors']}
    lines = ['', '## Työvaiheet ja ihmisen päätökset']
    for a in data['activities']:
        actor, tool = actors[a['actor']], a.get('tool') or {}
        lines += ['', f"### {a['id']} · {a['date']} · {a['kind']}", a['description'],
                  f"Perustelu: {a['rationale']}",
                  f"Tekijä: {actor['name']} · Malli: {actor.get('model') or 'ei kirjattu'} · Versio: {actor.get('version') or 'ei kirjattu'}",
                  f"Työkalu: {tool.get('name') or 'ei kirjattu'} · Versio: {tool.get('version') or 'ei kirjattu'}",
                  f"Syötteet: {', '.join(a['inputs']) or 'ei kirjattu'}",
                  f"Tulokset: {', '.join(a['outputs']) or 'ei kirjattu'}"]
    return lines


def text_view(data, audit=False):
    lines = [f"# {data['title']}", f"Versio {data['version']} · {data['date']}",
             "", f"Tutkimuskysymys: {data['question']}", "", data["method"]]
    for claim in data["claims"]:
        lines += ["", f"## {claim['id']}: {claim['text']}",
                  f"Tila: {claim['status']}", f"Epävarmuus: {claim['uncertainty']}"]
        for edge in claim.get("evidence", []):
            source = next(s for s in data["sources"] if s["id"] == edge["source"])
            lines += [f"- {edge['relation']}: {source['title']}, {source['locator']} ({source['url']})",
                      f"  Perustelu: {edge['rationale']}"]
            if audit:
                lines += [f"  Lainaus: {source['quote']}", f"  Lähdekritiikki: {source['criticism']}"]
        if audit:
            lines += [f"Riippuvuudet: {', '.join(claim.get('depends_on', [])) or 'ei'}"]
    if audit:
        lines += ["", "## Leima-tietueet"]
        for stamp in data["stamps"]:
            lines += [f"- {stamp['id']}: {stamp['claim_text']} — {stamp['assessment']}",
                      f"  {stamp['url']} · {stamp['network']} · {stamp['confirmation']}", f"  {stamp['note']}"]
        lines += ["", "## Työmäärä ja kustannukset", "Kirjatut tapahtumat: " + str(len(data.get('work_log', []))),
                  "Tyhjä loki tarkoittaa puuttuvaa mittausta, ei nollakustannusta."]
    lines += review_lines(data, audit)
    lines += assessment_lines(data)
    if audit:
        lines += activity_lines(data)
    return "\n".join(lines) + "\n"


def web_view(data):
    esc = html.escape
    cards = []
    for claim in data["claims"]:
        evidence = []
        for edge in claim.get("evidence", []):
            s = next(s for s in data["sources"] if s["id"] == edge["source"])
            evidence.append(f'<p><b>{esc(edge["relation"])}</b> — {esc(edge["rationale"])}</p><blockquote>{esc(s["quote"])}</blockquote><p><a href="{esc(s["url"], quote=True)}">{esc(s["title"])}</a> · {esc(s["locator"])}</p><p>{esc(s["criticism"])}</p>')
        cards.append(f'<article id="{claim["id"]}"><small>{claim["id"]} · {esc(claim["status"])}</small><h2>{esc(claim["text"])}</h2><p>{esc(claim["uncertainty"])}</p><details><summary>Avaa perustelut ja lähteet</summary>{"".join(evidence)}</details></article>')
    activities_html = '<section id="activities"><h2>Työvaiheet ja ihmisen päätökset</h2><pre>' + esc('\n'.join(activity_lines(data))) + '</pre></section>' if data.get('activities') else ''
    activities_html += '<section id="reviews"><pre>' + esc('\n'.join(assessment_lines(data))) + '</pre></section>' if data.get('reviews') else ''
    scenes = []
    for scene in data.get("game", {}).get("scenes", []):
        choices = ''.join(f'<details><summary>{esc(c["label"])}</summary><p>{esc(c["consequence"])}</p><p>Oletus: {esc(c["assumption"])}</p><a href="#{c["claim"]}">Tutkimusperusta: {c["claim"]}</a></details>' for c in scene["choices"])
        scenes.append(f'<article><h3>{esc(scene["text"])}</h3>{choices}</article>')
    reviews = []
    for r in sorted(data.get('criticisms', []), key=lambda r: (r['priority'], r['id'])):
        target = r['target']['id']
        reviews.append(f'<article id="{r["id"]}"><small>{r["id"]} · {esc(target)} · {review_state(data,r)}</small><h3>{esc(r["text"])}</h3><p>{esc(r["basis"])}</p><p>{esc(verification_text(r))}</p><details><summary>Vastaus ja ratkaisuhistoria</summary><p>Tekijä: {esc(r["author"]["name"])} · {esc(r["author"].get("model", ""))}</p><p>Arvioitu versio: {esc(r["reviewed_version"])}</p><p>Vastaus: {esc(r["response"] or "Ei vielä vastausta")}</p><p>Kirjattu ratkaisu: {esc(r["resolution"]["status"])} · {esc(r["resolution"]["rationale"])}</p><p>Vaikutukset: {esc(r["resolution"]["changes"] or "Ei kirjattuja muutoksia")}</p></details></article>')
    return f'''<!doctype html><html lang="fi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(data['title'])}</title>
<style>body{{font:18px/1.65 system-ui;background:#f3f0e8;color:#183329;max-width:900px;margin:auto;padding:32px}}h1{{font-size:2.3em;line-height:1.15}}article{{background:white;padding:25px;margin:20px 0;border-radius:16px}}summary,a{{cursor:pointer;color:#215f4a}}blockquote{{border-left:3px solid #b88842;padding-left:18px}}small{{color:#64736b}}nav a{{margin-right:20px}}</style>
<header><small>LEIMA RESEARCH · {esc(data['version'])}</small><h1>{esc(data['title'])}</h1><p>{esc(data['question'])}</p><p>{esc(data['method'])}</p></header>
<nav><a href="#research">Tutkimus</a><a href="#game">Pelattava tulkinta</a><a href="audit.md">Tarkastajan näkymä</a><a href="ro-crate-metadata.json">RO-Crate</a></nav>
<main id="research">{''.join(cards)}{activities_html}<section id="criticism"><h2>Vahvimmat vastaväitteet ja avoimet tarkistukset</h2>{''.join(reviews) or '<p>Ei kirjattuja kritiikkejä. Tämä ei tarkoita, että tutkimus olisi tarkastettu.</p>'}</section><section id="game"><h2>Pelattava tulkinta</h2><p>{esc(data.get('game',{}).get('disclaimer','Ei pelimallia.'))}</p>{''.join(scenes)}</section></main></html>'''


def build(input_path, output):
    # Git may check out CRLF on Windows. Publish the same LF bytes on every host.
    raw = input_path.read_bytes().replace(b'\r\n', b'\n')
    data = json.loads(raw)
    validate(data)
    if output.resolve() == input_path.parent.resolve() or output.resolve() in input_path.resolve().parents:
        raise ValueError("Output must be separate from the authored input")
    output.mkdir(parents=True, exist_ok=True)
    files = {"research.json": raw, "article.md": text_view(data).encode(),
             "audit.md": text_view(data, True).encode(), "index.html": web_view(data).encode()}
    graph = [
        {"@id": "ro-crate-metadata.json", "@type": "CreativeWork", "about": {"@id": "./"}, "conformsTo": {"@id": "https://w3id.org/ro/crate/1.3"}},
        {"@id": "./", "@type": "Dataset", "name": data["title"], "description": data["method"], "datePublished": data["date"], "version": data["version"],
         "hasPart": [{"@id": name} for name in files], "mentions": [{"@id": "#" + c["id"]} for c in data["claims"] + data["sources"]]},
    ]
    for name, content in files.items():
        graph.append({"@id": name, "@type": "File", "name": name, "encodingFormat": "text/html" if name.endswith('.html') else "application/json" if name.endswith('.json') else "text/markdown",
                      "sha256": digest(content), "isBasedOn": {"@id": "research.json"}} if name != "research.json" else
                     {"@id": name, "@type": "File", "name": name, "encodingFormat": "application/json", "sha256": digest(content)})
    for source in data["sources"]:
        graph.append({"@id": "#" + source["id"], "@type": "CreativeWork", "name": source["title"], "url": source["url"], "description": source["locator"] + ": " + source["quote"]})
    for claim in data["claims"]:
        graph.append({"@id": "#" + claim["id"], "@type": "CreativeWork", "text": claim["text"], "description": claim["status"] + ": " + claim["uncertainty"], "citation": [{"@id": "#" + e["source"]} for e in claim.get("evidence", [])], "isPartOf": {"@id": "research.json"}})
    for stamp in data['stamps']:
        graph.append({'@id': '#' + stamp['id'], '@type': 'CreativeWork', 'name': stamp['claim_text'], 'url': stamp['url'], 'isBasedOn': {'@id': '#' + stamp['source']}})
    for r in data.get('criticisms', []):
        graph[1]['mentions'].append({'@id': '#' + r['id']})
        graph.append({'@id': '#' + r['id'], '@type': 'Comment', 'text': r['text'],
                      'about': {'@id': 'research.json' if r['target']['kind'] == 'method' else '#' + r['target']['id']},
                      'description': review_state(data, r) + ': ' + r['basis'] + '\n' + verification_text(r), 'isPartOf': {'@id': 'research.json'}})
    for r in data.get('reviews', []):
        graph[1]['mentions'].append({'@id': '#' + r['id']})
        graph.append({'@id': '#' + r['id'], '@type': 'CreativeWork', 'name': 'Arviointi ' + r['id'],
                      'text': r['summary'], 'dateCreated': r['date'],
                      'about': {'@id': 'research.json' if r['target']['kind'] == 'method' else '#' + r['target']['id']},
                      'description': '\n'.join(assessment_lines(dict(data, reviews=[r]))),
                      'citation': [{'@id': '#' + k} for k in r['criticisms']],
                      'isPartOf': {'@id': 'research.json'}})
    def ref(ident):
        return {'@id': ident if ident == 'research.json' else '#' + ident}
    for actor in data.get('actors', []):
        entity = {'@id': '#' + actor['id'], '@type': 'Person' if actor['kind'] == 'human' else 'SoftwareApplication', 'name': actor['name']}
        if actor.get('version'):
            entity['softwareVersion' if actor['kind'] == 'agent' else 'description'] = actor['version']
        if actor.get('model'):
            entity['description'] = 'Model: ' + actor['model']
        graph.append(entity)
        graph[1]['mentions'].append(ref(actor['id']))
    for a in data.get('activities', []):
        entity = {'@id': '#' + a['id'], '@type': 'ChooseAction' if a['kind'] == 'human_decision' else 'CreateAction',
                  'name': a['description'], 'description': a['rationale'], 'dateCreated': a['date'],
                  'agent': ref(a['actor']), 'object': [ref(i) for i in a['inputs']],
                  'result': [ref(i) for i in a['outputs']], 'actionStatus': {'@id': 'http://schema.org/CompletedActionStatus'}}
        if a.get('tool'):
            tool_id = '#tool-' + a['id']
            tool = {'@id': tool_id, '@type': 'SoftwareApplication', 'name': a['tool']['name']}
            if a['tool'].get('version'):
                tool['softwareVersion'] = a['tool']['version']
            graph.append(tool)
            entity['instrument'] = {'@id': tool_id}
        graph.append(entity)
        graph[1]['mentions'].append(ref(a['id']))
    files["ro-crate-metadata.json"] = (json.dumps({"@context": "https://w3id.org/ro/crate/1.3/context", "@graph": graph}, ensure_ascii=False, indent=2) + '\n').encode()
    # This external envelope avoids hashing a manifest containing its own hash or stamp.
    files["release-manifest.json"] = (json.dumps({"schema_version": "0.1", "research_version": data["version"], "files": {name: digest(content) for name, content in files.items()}}, indent=2) + '\n').encode()
    for name, content in files.items():
        (output / name).write_bytes(content)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    build(args.input, args.out)
    print(f"Validated and built: {args.out}")


if __name__ == "__main__":
    main()
