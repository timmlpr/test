"""Deterministic sample data used ONLY in DEMO_MODE so every screen is clickable without network or keys.
All demo data is clearly labelled as demo in the UI and never mixed with real results."""
from __future__ import annotations

import hashlib

from app.adapters.base import Adapter, AdapterMeta

DEMO_BREACHES = [
    {"name": "Beispiel-Forum 2019", "domain": "forum.example", "year": "2019", "data_types": ["email", "password", "username"],
     "description": "Demo-Datensatz: Ein Forum verlor E-Mail-Adressen und gehashte Passwörter.", "verified": True,
     "reference": "https://example.org/demo/forum-2019", "records": 120000},
    {"name": "Muster-Shop 2022", "domain": "shop.example", "year": "2022", "data_types": ["address", "email", "name", "phone"],
     "description": "Demo-Datensatz: Kundendaten eines Onlineshops mit Lieferadressen.", "verified": True,
     "reference": "https://example.org/demo/shop-2022", "records": 48000},
    {"name": "Fitness-App 2024", "domain": "fit.example", "year": "2024", "data_types": ["birthdate", "email", "location"],
     "description": "Demo-Datensatz: Profildaten inkl. Geburtsdatum.", "verified": False,
     "reference": "https://example.org/demo/fit-2024", "records": 9000},
]

DEMO_HITS = [
    {"source": "demo_search", "title": "Vereinsseite – Mitgliederliste mit Name und Wohnort", "url": "https://verein.example/mitglieder",
     "snippet": "… Name, Wohnort und Telefonnummer …", "data_type": "phone", "risk": "high"},
    {"source": "demo_search", "title": "Alter Blogkommentar mit voller Adresse", "url": "https://blog.example/2015/kommentar",
     "snippet": "… Musterstraße 1, 12345 Musterstadt …", "data_type": "address", "risk": "high"},
    {"source": "demo_search", "title": "Personensuchmaschine (Beispiel)", "url": "https://people-search.example/profil",
     "snippet": "Name, Alter, Stadt", "data_type": "name", "risk": "medium"},
    {"source": "demo_search", "title": "Lauf-Ergebnisliste 2021", "url": "https://lauf.example/ergebnisse/2021",
     "snippet": "Name, Jahrgang, Verein", "data_type": "birthdate", "risk": "medium"},
    {"source": "demo_search", "title": "Öffentliches Profil auf einem Fotoportal", "url": "https://fotos.example/user",
     "snippet": "Benutzername und Profilbild", "data_type": "username", "risk": "low"},
    {"source": "wikipedia", "title": "Namensgleiche Person (nicht sicher zuordenbar)", "url": "https://de.wikipedia.org/wiki/Beispiel",
     "snippet": "Gleicher Name, vermutlich andere Person", "data_type": "name", "risk": "low", "attributable": False},
]


class Demo(Adapter):
    meta = AdapterMeta(name="demo", label="Demo data", modules=["*"], terms_url="https://example.org", data_types=["*"],
                       notes="Only active in DEMO_MODE.")

    @staticmethod
    def seed(value: str) -> int:
        return int(hashlib.sha256(value.encode()).hexdigest(), 16)

    def breaches(self, email: str) -> list[dict]:
        n = self.seed(email) % 3 + 1
        return DEMO_BREACHES[:n]

    def search(self, phrase: str) -> list[dict]:
        return [dict(h) for h in DEMO_HITS]
