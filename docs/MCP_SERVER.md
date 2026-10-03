# MCP-palvelin (`/mcp`)

Agenttien (esim. ChatGPT) liitäntä Leiman leimausputkeen. Agentti lähettää väitteen
ja lähteen, Leima ajaa saman analyysin ja Arweave-leimauksen kuin `/api/stamp` ja
palauttaa verdict-JSONin sekä valmiin lähdeviitetekstin.

- Protokolla: `mcp_server.py` (tilaton Streamable HTTP, vain JSON-vastaukset, ei sessioita eikä SSE:tä)
- Työkalun toteutus ja reitti: `main.py`, `_stamp_citation` ja `mcp_endpoint`
- Testit: `tests/test_mcp.py`

Oma toteutus `mcp`-SDK:n sijaan, koska SDK:n streamable-HTTP-sovellus vaatii
lifespan-hallitun session managerin, joka ei sovi Vercelin serverless-ajoon.

## Käyttöönotto

1. Generoi avain: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. Lisää Verceliin env-muuttuja `LEIMA_MCP_KEYS` (useampi avain pilkuilla eroteltuna).
   Ilman tätä `/mcp` palauttaa 503 — reitti on oletuksena kiinni, toisin kuin `/api/stamp`.
3. ChatGPT → Settings → Connectors → (developer mode) → uusi connector:
   - URL: `https://leima.io/mcp?key=<avain>`
   - Authentication: none (avain kulkee URL:ssa, koska connector ei osaa lähettää omia headereita)

Muut asiakkaat voivat lähettää avaimen headerina `Authorization: Bearer <avain>`.
Avaimen voi perua poistamalla sen `LEIMA_MCP_KEYS`:stä.

## Työkalu `stamp_citation`

| Parametri | Pakollinen | Merkitys |
|---|---|---|
| `claim` | kyllä | Väite (max 2000 merkkiä) |
| `source_url` | jompikumpi | Web-sivu tai PDF; Leima hakee itse → `provenance: fetched_by_leima` |
| `source_text` | jompikumpi | URL:n kanssa: lainattu kohta (max 5000), joka tarkistetaan lähdettä vasten ja sisällytetään hashattuun verdictiin. Yksinään: koko lähde → `provenance: agent_supplied` |
| `source_title` | ei | Lähdeviitetekstiin |

Vastaus pitää kaksikerrosmallin kerrokset erillään:

```json
{
  "type": "LeimaCitationVerdict",
  "schema_version": "0.1",
  "claim": "...",
  "source":   { "url", "final_url", "title", "fetched_at", "provenance", "cited_passage" },
  "verdict":  { "nature": "ai_assessment", "category", "summary", "passes", "model", "timestamp" },
  "evidence": { "nature": "hash_commitment", "input_hash", "verdict_hash", "arweave_tx", "arweave_url", "package_url",
                "storage": { "network", "permanent", "gateway", "content", "status": "submitted", "confirmation": "not_checked" } },
  "citation": "Title. URL (accessed YYYY-MM-DD). Leima stamp: https://gateway.irys.xyz/<tx>"
}
```

Rakenne on valittu niin, että siitä tulee suoraan W3C VC:n `credentialSubject`
(ks. `docs/todo/W3C_VC_MIGRATION_PLAN.md`). Arweaveen menee edelleen vain hash-tietue.

`evidence.storage` kertoo tallennusverkon: `irys-devnet` on aina `permanent: false`. Leima ei
tarkista Arweave-vahvistusta, joten `status` on `submitted`.

## Puhelimen capturet (`POST /api/stamp/device-capture`)

Research Appliance -puhelimen `browser`-paketti voidaan leimata samalla putkella (multipart:
`claim`, valinnainen `cited_passage`, `package`). Vastaus on sama `LeimaCitationVerdict`, mutta
`source.provenance` on `device_captured`, `source.capture` kertoo paketin tiivisteet ja
hankintatavan, ja lisäksi on `limits`. Lähdetiedosto on koko ZIP, joten `input_hash` on paketin
sha256. Ks. `docs/RESEARCH_APPLIANCE_ARCHITECTURE.md` luku 6b. Reitti on avoin kuten `/api/stamp`.

## Avoimet asiat

- Kutsumäärän rajoitus avainkohtaisesti (nyt vain avain).
- Kesto 20–90 s. Jos ChatGPT aikakatkaisee, jaetaan `submit` + `get_result` -pariksi.
- `package_url` toimii vain niin kauan kuin sessio on muistissa (1 h, sama instanssi) — sama rajoite kuin `/api/stamp`:ssa.
