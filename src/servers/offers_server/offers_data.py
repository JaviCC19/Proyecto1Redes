"""
offers_data.py

In-memory sample dataset for the "Offers Recommendation" MCP server
(industry use case: retail / e-commerce promotions engine).

In a real deployment this would be backed by a database; for this
project a small, self-contained catalog is enough to demonstrate the
tool logic end to end.
"""

from __future__ import annotations

OFFERS: list[dict] = [
    {
        "id": "OF-001",
        "title": "50% de descuento en audífonos inalámbricos",
        "category": "electronica",
        "tags": ["audifonos", "musica", "bluetooth", "tecnologia", "gadgets"],
        "discount_percent": 50,
        "price_original": 400.0,
        "price_final": 200.0,
        "min_purchase": None,
        "valid_until": "2026-09-30",
        "description": "Audífonos inalámbricos con cancelación de ruido, ideal para "
                        "quienes disfrutan la música o trabajan en modo remoto.",
    },
    {
        "id": "OF-002",
        "title": "2x1 en combos de comida rápida",
        "category": "comida",
        "tags": ["comida", "restaurante", "familia", "fin de semana"],
        "discount_percent": 50,
        "price_original": 120.0,
        "price_final": 60.0,
        "min_purchase": None,
        "valid_until": "2026-08-31",
        "description": "Promoción 2x1 válida en combos seleccionados, ideal para "
                        "compartir en familia o con amigos.",
    },
    {
        "id": "OF-003",
        "title": "30% de descuento en paquete turístico a Antigua Guatemala",
        "category": "viajes",
        "tags": ["viajes", "turismo", "fin de semana", "descanso"],
        "discount_percent": 30,
        "price_original": 1500.0,
        "price_final": 1050.0,
        "min_purchase": None,
        "valid_until": "2026-10-15",
        "description": "Paquete de fin de semana que incluye hospedaje y tour guiado.",
    },
    {
        "id": "OF-004",
        "title": "25% de descuento en ropa deportiva",
        "category": "ropa",
        "tags": ["ropa", "deporte", "gimnasio", "ejercicio", "salud"],
        "discount_percent": 25,
        "price_original": 300.0,
        "price_final": 225.0,
        "min_purchase": 150.0,
        "valid_until": "2026-09-10",
        "description": "Aplica en toda la línea de ropa y calzado deportivo.",
    },
    {
        "id": "OF-005",
        "title": "15% de descuento en laptops para estudiantes",
        "category": "tecnologia",
        "tags": ["laptop", "estudio", "universidad", "tecnologia", "trabajo"],
        "discount_percent": 15,
        "price_original": 6000.0,
        "price_final": 5100.0,
        "min_purchase": None,
        "valid_until": "2026-12-01",
        "description": "Descuento exclusivo para estudiantes universitarios en laptops "
                        "seleccionadas, ideal para programar o hacer trabajos.",
    },
    {
        "id": "OF-006",
        "title": "40% de descuento en electrodomésticos de cocina",
        "category": "hogar",
        "tags": ["hogar", "cocina", "electrodomesticos", "familia"],
        "discount_percent": 40,
        "price_original": 800.0,
        "price_final": 480.0,
        "min_purchase": None,
        "valid_until": "2026-09-20",
        "description": "Incluye licuadoras, freidoras de aire y cafeteras.",
    },
    {
        "id": "OF-007",
        "title": "20% de descuento en suscripción de streaming de música",
        "category": "entretenimiento",
        "tags": ["musica", "streaming", "entretenimiento", "tecnologia"],
        "discount_percent": 20,
        "price_original": 60.0,
        "price_final": 48.0,
        "min_purchase": None,
        "valid_until": "2026-11-30",
        "description": "Plan familiar con descuento por los primeros 6 meses.",
    },
    {
        "id": "OF-008",
        "title": "10% de descuento en libros y material de estudio",
        "category": "educacion",
        "tags": ["libros", "estudio", "universidad", "lectura"],
        "discount_percent": 10,
        "price_original": 250.0,
        "price_final": 225.0,
        "min_purchase": None,
        "valid_until": "2026-10-31",
        "description": "Aplica en librerías afiliadas, incluye libros técnicos.",
    },
]

# Simulated "claims" storage (kept only in memory for the lifetime of the
# server process). A real system would persist this in a database.
CLAIMS: list[dict] = []
