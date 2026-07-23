# Távközlési vállalati ontológia v0.1

## 1. Cél

Az ontológia egy 350+ fős távközlési nagyvállalat heterogén tudását fogja
össze:

- szervezet és felelősség;
- folyamatok;
- értékesítés és ügyfélkezelés;
- szolgáltatások és termékek;
- alkalmazások és informatikai rendszerek;
- hálózati architektúra;
- hálózati elemek és végponti eszközök;
- fizikai és logikai kapcsolatok;
- karbantartás és üzemeltetés.

Nem cél egy teljes iparági ontológia előre történő megalkotása. Az első
verzió kis, kontrollált felső szintű típuskészletet és bővíthető subtype
registryt ad.

## 2. Szemantikai határ

A GraphRAG knowledge graph dokumentált tudást reprezentál, nem élő
CMDB/NMS/inventory állapotot.

Egy assertion jelentése:

```text
Az adott forrásdokumentum az adott verzióban ezt állította.
```

Nem automatikusan:

```text
A hálózat jelenlegi valós konfigurációja ez.
```

Későbbi inventory vagy NMS connector külön source class és trust policy
alatt működhet.

## 3. Entity type-ok

### Üzleti és szervezeti

| Kód | Jelentés |
|---|---|
| `ORGANIZATION` | vállalat vagy szervezet |
| `ORG_UNIT` | igazgatóság, osztály, csoport |
| `PERSON` | dokumentumban szereplő személy |
| `ROLE` | munkakör vagy funkcionális szerep |
| `PROCESS` | üzleti vagy műszaki folyamat |
| `CAPABILITY` | vállalati képesség |
| `POLICY` | szabályzat, előírás, elv |
| `PRODUCT` | értékesíthető termék |
| `SERVICE` | ügyfél- vagy belső szolgáltatás |
| `CUSTOMER_SEGMENT` | ügyfélszegmens |
| `EXTERNAL_PARTY` | partner, beszállító, hatóság, külső fél |

### Technikai

| Kód | Jelentés |
|---|---|
| `SYSTEM` | informatikai vagy hálózati rendszer |
| `APPLICATION` | alkalmazás/szoftver |
| `COMPONENT` | rendszerkomponens vagy alrendszer |
| `NETWORK_ELEMENT` | logikai vagy fizikai hálózati elem |
| `DEVICE_MODEL` | eszközmodell |
| `DEVICE_INSTANCE` | konkrét eszközpéldány |
| `NETWORK_SEGMENT` | hálózatrész vagy domain |
| `INTERFACE` | fizikai/logikai interfész |
| `PROTOCOL` | hálózati vagy alkalmazási protokoll |
| `TECHNOLOGY` | technológia vagy szabvány |
| `SITE` | telephely, node-helyszín, POP |
| `LOCATION` | általános földrajzi vagy szervezeti hely |
| `INFRASTRUCTURE_ASSET` | kábel, nyomvonal, rack és más infrastruktúra |

### Általános

| Kód | Jelentés |
|---|---|
| `DOCUMENT` | dokumentumként hivatkozott objektum |
| `CONCEPT` | fogalom, módszer vagy absztrakt kategória |
| `OTHER` | kontrollált fallback |

## 4. Entity subtype registry

CMTS, CBR, ASR, OLT, ONT, modem és node nem új Neo4j label, hanem
verziózott subtype.

Kezdeti példák:

```text
NETWORK_ELEMENT:
  CMTS
  CBR
  ASR_ROUTER
  OLT
  HFC_NODE
  ACCESS_NODE
  AGGREGATION_ROUTER

DEVICE_MODEL / DEVICE_INSTANCE:
  ONT
  CABLE_MODEM
  SMART_DEVICE
  ROUTER
  SWITCH
  SET_TOP_BOX
```

A pilot corpus után kell pontosítani. Az LLM csak az aktív registryből
választhat; ismeretlen esetben `OTHER` és `proposed_subtype` warning.

## 5. Entity scope

```text
category
type
model
instance
logical
```

Példa:

```text
ONT                         type/category
Huawei EG8145V5             model
egy sorozatszámmal jelölt ONT instance
```

Type/model/instance nem merge-elhető automatikusan.

## 6. Predicate-ek

### Szerkezet

```text
PART_OF
INSTANCE_OF
HAS_COMPONENT
```

### Függőség és használat

```text
DEPENDS_ON
USES
SUPPORTS
IMPLEMENTS
```

### Felelősség

```text
OWNS
RESPONSIBLE_FOR
OPERATES
MAINTAINS
```

### Folyamat

```text
INPUT_TO
OUTPUT_OF
PRECEDES
TRIGGERS
```

### Szolgáltatás és külső kapcsolat

```text
PROVIDES
SERVES
SUPPLIED_BY
```

### Topológia

```text
CONNECTS_TO
TERMINATES_AT
ROUTES_VIA
LOCATED_AT
```

### Dokumentáció

```text
DESCRIBES
APPLIES_TO
REFERENCES
```

### Fallback

```text
RELATED_TO
```

Az inverz kapcsolatokat query-szinten is elő lehet állítani; nem kell
mindkét irányt külön assertionként tárolni.

## 7. Hálózati réteg

A kapcsolat típusa és hálózati rétege külön mező.

```text
network_layer:
  physical
  access
  layer_2
  layer_3
  transport
  service
  business
```

Typed assertion property jelöltek:

- directionality;
- interface A/B;
- protocol;
- medium;
- capacity;
- environment;
- geographic/organizational scope;
- valid from/to;
- source explicitness.

Csak forrásban szereplő property menthető evidence-szel.

## 8. Példa cross-domain lánc

```text
(ORG_UNIT)-[:RESPONSIBLE_FOR]->(PROCESS)
(PROCESS)-[:USES]->(APPLICATION)
(APPLICATION)-[:DEPENDS_ON]->(SYSTEM)
(SYSTEM)-[:DEPENDS_ON]->(NETWORK_ELEMENT)
(NETWORK_ELEMENT)-[:CONNECTS_TO {network_layer: "layer_3"}]->(NETWORK_ELEMENT)
(SYSTEM)-[:PROVIDES]->(SERVICE)
```

A tényleges Neo4j projekcióban ezek reifikált
`RelationshipAssertion` node-ok evidence kapcsolatokkal.

## 9. Entity resolution szabályok

Automatikus merge csak:

- azonos erős külső azonosító;
- azonos, egyértelmű sorozatszám vagy rendszerazonosító;
- azonos type/scope;
- determinisztikus, verziózott normalization rule.

Nem automatikus:

- fuzzy névegyezés;
- embedding hasonlóság;
- rövidítés önmagában;
- azonos eszközcsalád;
- type és instance keveredése;
- azonos név eltérő szervezeti vagy hálózati scope-ban.

## 10. Ontológia-verziózás

PostgreSQL registry:

```text
ontology_versions
entity_type_definitions
entity_subtype_definitions
predicate_definitions
predicate_inverse_mappings
property_definitions
```

Extraction run mindig hivatkozik az ontológiaverzióra.

Új subtype hozzáadása nem írja át automatikusan a régi extraction outputot.
Újra-extraction külön, explicit job.

