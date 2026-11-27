"""Machines and hoops people can pick, and the file format each one reads."""

# Hoop limits are width x height as the hoop is mounted; designs are not auto-rotated.
MACHINES = {
    "brother_4x4": {"name": "Brother 4x4", "max_w": 100.0, "max_h": 100.0, "format": "pes"},
    "brother_5x7": {"name": "Brother 5x7", "max_w": 130.0, "max_h": 180.0, "format": "pes"},
    "brother_6x10": {"name": "Brother 6x10", "max_w": 160.0, "max_h": 260.0, "format": "pes"},
    "brother_8x12": {"name": "Brother 8x12", "max_w": 200.0, "max_h": 300.0, "format": "pes"},
    "janome_sq14": {"name": "Janome SQ14", "max_w": 140.0, "max_h": 140.0, "format": "jef"},
    "janome_re20": {"name": "Janome RE20", "max_w": 170.0, "max_h": 200.0, "format": "jef"},
    "husqvarna_240x150": {"name": "Husqvarna Viking 240x150", "max_w": 240.0, "max_h": 150.0, "format": "vp3"},
    "bernina_medium": {"name": "Bernina Medium", "max_w": 100.0, "max_h": 130.0, "format": "exp"},
    "bernina_large_oval": {"name": "Bernina Large Oval", "max_w": 145.0, "max_h": 255.0, "format": "exp"},
    "tajima_dst": {"name": "Tajima / commercial (DST)", "max_w": 200.0, "max_h": 300.0, "format": "dst"},
}
