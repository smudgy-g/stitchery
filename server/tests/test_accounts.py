import base64
import io
import os
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException
from jwt.algorithms import OKPAlgorithm
from fastapi.testclient import TestClient
from PIL import Image
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app import accounts
from app.main import app
from app.preprocess import get_thread_catalog

AUTH_URL = "https://ep-test.neonauth.example.neon.tech/neondb/auth"
ORIGIN = "https://ep-test.neonauth.example.neon.tech"
RECT_PES = (Path(__file__).parent / "fixtures" / "rect40.pes").read_bytes()


class Keys:
    """Stands in for PyJWKClient: serves a key made here, as Neon's JWKS would."""
    def __init__(self, private):
        self.jwk = jwt.PyJWK(OKPAlgorithm.to_jwk(private.public_key(), as_dict=True), algorithm="EdDSA")

    def get_signing_key_from_jwt(self, _token):
        return self.jwk


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.private = Ed25519PrivateKey.generate()
        patcher = patch.multiple(accounts, NEON_AUTH_URL=AUTH_URL, jwks=Keys(self.private))
        patcher.start()
        self.addCleanup(patcher.stop)

    def token(self, **claims):
        payload = {"sub": "user-1", "iss": ORIGIN, "aud": ORIGIN, "exp": int(time.time()) + 60, **claims}
        return jwt.encode(payload, self.private, algorithm="EdDSA")

    def test_valid_token_gives_the_user(self):
        self.assertEqual(accounts.current_user(f"Bearer {self.token()}"), "user-1")

    def test_bad_tokens_are_refused(self):
        for header in ("", "Bearer nonsense", f"Bearer {self.token(iss='https://evil.example')}",
                       f"Bearer {self.token(exp=int(time.time()) - 10)}",
                       f"Bearer {jwt.encode({'sub': 'x', 'iss': ORIGIN, 'aud': ORIGIN}, Ed25519PrivateKey.generate(), algorithm='EdDSA')}"):
            with self.subTest(header=header[:30]), self.assertRaises(HTTPException) as caught:
                accounts.current_user(header)
            self.assertEqual(caught.exception.status_code, 401)


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "set TEST_DATABASE_URL to a throwaway Postgres")
class DesignTests(unittest.TestCase):
    """Runs against a scratch database with a stand-in for Neon Auth's user table."""

    @classmethod
    def setUpClass(cls):
        cls.pool = ConnectionPool(os.environ["TEST_DATABASE_URL"], min_size=1, max_size=2, kwargs={"row_factory": dict_row})
        with cls.pool.connection() as conn:
            conn.execute('drop table if exists designs; create schema if not exists neon_auth;'
                         'create table if not exists neon_auth."user" (id uuid primary key)')
            conn.execute(accounts.SCHEMA)
        cls.patcher = patch.object(accounts, "pool", cls.pool)
        cls.patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        cls.pool.close()

    def setUp(self):
        self.client = TestClient(app)
        self.alice, self.bob = str(uuid.uuid4()), str(uuid.uuid4())
        with self.pool.connection() as conn:
            conn.execute('insert into neon_auth."user" (id) values (%s), (%s)', (self.alice, self.bob))
        self.addCleanup(app.dependency_overrides.clear)

    def as_user(self, user):
        app.dependency_overrides[accounts.current_user] = lambda: user

    def save(self, file=RECT_PES, **extra):
        thread = get_thread_catalog()[0][0]["id"]
        body = {"name": "Rect", "machine_key": "brother_4x4", "file_base64": base64.b64encode(file).decode(), "threads": [thread], **extra}
        return self.client.post("/api/designs", json=body)

    def test_save_list_download_delete_are_per_person(self):
        self.as_user(self.alice)
        saved = self.save()
        self.assertEqual(saved.status_code, 200, saved.text)
        design_id = saved.json()["id"]

        [listed] = self.client.get("/api/designs").json()
        self.assertEqual((listed["name"], listed["format"]), ("Rect", "pes"))
        self.assertTrue(listed["thumbnail"].startswith("data:image/png;base64,"))
        # Drawn in the chosen thread, not the Brother palette colour the PES stores
        png = Image.open(io.BytesIO(base64.b64decode(listed["thumbnail"].split(",", 1)[1]))).convert("RGBA")
        self.assertIn(tuple(get_thread_catalog()[0][0]["rgb"]), {c[:3] for _, c in png.getcolors(1 << 16) if c[3]})
        self.assertGreater(listed["stitch_count"], 0)
        file = self.client.get(f"/api/designs/{design_id}/file").json()
        self.assertEqual((base64.b64decode(file["file_base64"]), file["file_name"]), (RECT_PES, "Rect.pes"))

        self.as_user(self.bob)
        self.assertEqual(self.client.get("/api/designs").json(), [])
        self.assertEqual(self.client.get(f"/api/designs/{design_id}/file").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/designs/{design_id}").status_code, 404)

        self.as_user(self.alice)
        self.assertEqual(self.client.delete(f"/api/designs/{design_id}").status_code, 204)
        self.assertEqual(self.client.get("/api/designs").json(), [])

    def test_rejects_files_that_are_not_designs(self):
        self.as_user(self.alice)
        for extra in ({"file": b"not a design"}, {"machine_key": "nope"}, {"threads": ["nope"]}):
            with self.subTest(extra=list(extra)):
                self.assertEqual(self.save(**extra).status_code, 400)
        self.assertEqual(self.save(name="").status_code, 422)

    def test_signed_out_is_refused(self):
        with patch.multiple(accounts, NEON_AUTH_URL=AUTH_URL, jwks=Keys(Ed25519PrivateKey.generate())):
            self.assertEqual(self.client.get("/api/designs").status_code, 401)
