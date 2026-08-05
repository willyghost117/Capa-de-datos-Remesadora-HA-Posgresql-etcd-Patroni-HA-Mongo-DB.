from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4


FIRST_NAMES = [
    "Ana", "Luis", "Carlos", "Maria", "Sofia", "Jorge", "Lucia", "Diego",
    "Valeria", "Fernando", "Gabriela", "Mario", "Elena", "Ricardo"
]
LAST_NAMES = [
    "Morales", "Garcia", "Lopez", "Perez", "Hernandez", "Castillo",
    "Ramirez", "Gomez", "Diaz", "Vasquez", "Reyes", "Mendez"
]
COMPANY_PREFIX = ["Servicios", "Comercial", "Inversiones", "Soluciones", "Exportadora"]
COMPANY_SUFFIX = ["del Centro", "Maya", "Internacional", "Global", "Los Altos"]
CITIES = {
    "GT": ["Guatemala", "Mixco", "Quetzaltenango", "Escuintla"],
    "US": ["Los Angeles", "Houston", "Miami", "New York"],
    "MX": ["Ciudad de Mexico", "Guadalajara", "Monterrey", "Puebla"],
    "SV": ["San Salvador", "Santa Ana", "Soyapango"],
    "HN": ["Tegucigalpa", "San Pedro Sula", "La Ceiba"],
}


def money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def rate(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


@dataclass
class SyntheticParty:
    party_id: int
    legal_name: str
    country_code: str
    party_type: str


class DataFactory:
    def __init__(self, seed: int) -> None:
        self.random = random.Random(seed)

    def name(self) -> tuple[str, str, str]:
        first = self.random.choice(FIRST_NAMES)
        last = f"{self.random.choice(LAST_NAMES)} {self.random.choice(LAST_NAMES)}"
        return first, last, f"{first} {last}"

    def company_name(self) -> str:
        return f"{self.random.choice(COMPANY_PREFIX)} {self.random.choice(COMPANY_SUFFIX)}, S.A."

    def birth_date(self) -> date:
        years = self.random.randint(21, 70)
        days = self.random.randint(0, 364)
        return date.today() - timedelta(days=years * 365 + days)

    def incorporation_date(self) -> date:
        years = self.random.randint(2, 30)
        days = self.random.randint(0, 364)
        return date.today() - timedelta(days=years * 365 + days)

    def document_number(self, prefix: str, index: int) -> str:
        return f"{prefix}-{index:08d}-{self.random.randint(10, 99)}"

    def phone(self) -> str:
        return f"+502{self.random.randint(30000000, 59999999)}"

    def email(self, code: str) -> str:
        return f"{code.lower()}@example.test"

    def address(self, country_code: str) -> tuple[str, str, str]:
        city = self.random.choice(CITIES.get(country_code, ["Capital"]))
        line = f"{self.random.randint(1, 30)} Avenida {self.random.randint(1, 99)}-{self.random.randint(1, 99)}"
        region = "Region Central"
        return line, city, region

    def event_id(self) -> str:
        return str(uuid4())
