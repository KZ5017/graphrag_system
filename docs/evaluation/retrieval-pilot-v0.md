# Retrieval pilot v0

## Cél és határ

Ez a kis, verziózott értékelési készlet a Phase 3 keyword, semantic és hybrid
retrieval összehasonlítására szolgál az első read-only pilot vaulton. Nem
értékeli a későbbi entity/graph csatornát, és nem tekinti a dokumentumok
állításait élő hálózati állapotnak.

## Korpusz

| ID | Kérdés | Elsődleges releváns dokumentum |
|---|---|---|
| R01 | Hogyan kérdezhetők le a MARUO végpontok Nemesisből? | `Belső_tudásbázis/NOC/MARUO/MARUO_végpontok_lekérdezése_Nemesisből.md` |
| R02 | Hol ellenőrizhető egy PPPoE session egyedileg? | `Belső_tudásbázis/NOC/MARUO/MARUO_végpontok_lekérdezése_Nemesisből.md` |
| R03 | Mi az SMTP tiltott ügyfél visszaengedésének folyamata? | `Belső_tudásbázis/NOC/Folyamatok/SMTP-tiltott-ügyfelek-kezelése.md` |
| R04 | Mikor kell értesíteni az éjszakás vezénylésben? | `Belső_tudásbázis/NOC/Műszak/éjszakás_vezénylés_feltételei.md` |
| R05 | Mi változott a vasárnapi munkavégzés és készenlét szabályaiban? | `Belső_tudásbázis/NOC/Műszak/vasárnapi_munkavégzés_szabályok.md` |
| R06 | Hogyan indítható modem reset Nemesisből és hol látszik a log? | `Eszközök/Szolgáltatói_eszközök/Végponti_eszközök/Koax_hálózat/Modem/Nemesisből_indított_modem_reset_logolása.md` |
| R07 | Hogyan kezelhető egy Huawei ONT? | `Eszközök/Szolgáltatói_eszközök/Végponti_eszközök/Optikai_hálózat/huawei-ont-k-kezelési-utmutato.md` |
| R08 | Hogyan kell üzembe helyezni a Xiaomi TV Box S eszközt? | `Belső_tudásbázis/NOC/Helpdesk/AndroidTV_Box/Xiaomi_TV_Box_S_Uzembehelyezés.md` |
| R09 | Milyen módjai és eszközei vannak a helyi AI Asszisztensnek? | `Belső_tudásbázis/Saját_fejlesztésű_rendszerek/Helyi_AI_Asszisztens/Módok_és_eszközök.md` |
| R10 | Milyen adatkezelési és kontextuskorlátai vannak a helyi AI Asszisztensnek? | `Belső_tudásbázis/Saját_fejlesztésű_rendszerek/Helyi_AI_Asszisztens/Korlátok_és_adatkezelés.md` |
| R11 | Hogyan lehet hibajegyet rögzíteni a WOP MARUO felületén? | `Belső_tudásbázis/NOC/MARUO/WOP_felhasználói_kézikönyv.md` |
| R12 | Hogyan állítható be hívásátirányítás Android telefonon? | `Belső_tudásbázis/NOC/Helpdesk/Mobiltelefon/Hívásátirányítás/Android/hivas_atiranyitas_android.md` |

## Futtatási protokoll

Minden kérdés ugyanazon scan ID, parser/chunker verzió és aktív embedding
profil mellett fut háromszor: `keyword`, `semantic`, majd `hybrid`
stratégiával, `limit=5` értékkel. A találat akkor dokumentumszinten releváns,
ha az aktuális PostgreSQL dokumentumverzióból származik és a fenti útvonalhoz
tartozik. A chunk-szintű relevanciát külön, kézzel kell megítélni.

Rögzítendő mutatók:

- document Recall@5;
- chunk MRR@5;
- nDCG@5 kézi 0/1/2 relevanciajelöléssel;
- stale hit count és provider-degradation warning;
- p50/p95 latency csatornánként;
- visszaadott hit- és context chunkok összes karaktere.

Az első éles BGE-M3 baseline csak akkor tekinthető rögzítettnek, ha az LM
Studio modellazonosítója, runtime-probe szerinti dimenziója és a
`model_profile_id` is bekerül az eredményjegyzőkönyvbe.
