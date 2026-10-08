"""Regressão do segundo achado da auditoria de 08/10/2026: mesmo depois de
sanitizar a QUERY (ver test_script_gen_image_query.py), a NASA Images API
ainda devolve fotos institucionais/administrativas (memorial de desastre,
emblema de missão, evento de imprensa) pra buscas genéricas o bastante -
essas fotos SÃO reais do espaço/NASA o bastante pra passar no filtro visual
CLIP. _is_non_astronomy_content filtra pela CATEGORIA do conteúdo (usando
metadado que a API já devolve - keywords/description - e que antes era
descartado), não pelo tema buscado."""

from pipeline import visual_source


def test_disaster_memorial_blocked():
    data = {
        "title": "Memorial - Archives from Columbia",
        "keywords": ["Columbia", "Memorial", "STS-107", "disaster", "rememberance", "tragedy"],
        "description": "A display of artifacts featuring nine items recovered from the STS-107 tragedy...",
    }
    assert visual_source._is_non_astronomy_content(data) is True


def test_mission_patch_blocked():
    data = {
        "title": "MISSION PATCH - GEMINI-5 SPACE FLIGHT - MSC",
        "keywords": ["GEMINI 5 FLIGHT", "GEMINI PROGRAM", "INSIGNIAS", "LOGO"],
        "description": "This is the insignia of the Gemini-Titan 5 mission...",
    }
    assert visual_source._is_non_astronomy_content(data) is True


def test_processing_facility_blocked():
    data = {
        "title": "SRB Processing Facilities Media Event",
        "keywords": ["work order 3104522", "pathfinder"],
        "description": "During a media tour of the Rotation, Processing and Surge Facility...",
    }
    assert visual_source._is_non_astronomy_content(data) is True


def test_real_astronomy_photo_not_blocked():
    data = {
        "title": "Behemoth Black Hole Found in an Unlikely Place",
        "keywords": ["Hubble", "HST", "black hole", "black", "hole", "Hubble Space Telescope"],
        "description": "This computer-simulated image shows a supermassive black hole at the core...",
    }
    assert visual_source._is_non_astronomy_content(data) is False


def test_orion_nebula_not_blocked():
    data = {
        "title": "Orion Nebula and Bow Shock",
        "keywords": ["Orion Nebula", "Hubble Space Telescope"],
        "description": "Astronomers using NASA Hubble Space Telescope have found a bow shock...",
    }
    assert visual_source._is_non_astronomy_content(data) is False


def test_missing_keywords_and_description_handled():
    # Campos ausentes/None são comuns na API real (visto em produção) - não
    # pode lançar exceção nem bloquear por padrão nesse caso.
    data = {"title": "Saturn Rings", "keywords": None, "description": None}
    assert visual_source._is_non_astronomy_content(data) is False
